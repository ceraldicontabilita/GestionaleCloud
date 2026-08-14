"""Regole conservative per collegare pagamenti PayPal e fatture.

Numero fattura e importo non sono identificativi globali: possono ripetersi
tra fornitori diversi.  Questo modulo rende esplicite le evidenze usate dai
router PayPal e non consente mai un collegamento basato sul solo importo.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Iterable, Optional
import re

from app.services.identity_matching import nome_tokens
from app.services.payment_invoice_matching import (
    amounts_equal_to_cent,
    invoice_reference_equals,
)


_LEGAL_TOKENS = {
    "srl", "spa", "sas", "snc", "ss", "ltd", "limited", "llc",
    "inc", "gmbh", "ag", "bv", "nv", "sa", "ab",
}


def normalize_tax_id(value: Any) -> str:
    """Normalizza P.IVA/CF conservando solo lettere e cifre, senza prefisso IT."""
    normalized = re.sub(r"[^A-Z0-9]", "", str(value or "").upper())
    if normalized.startswith("IT") and len(normalized) == 13:
        normalized = normalized[2:]
    return normalized


def _business_tokens(value: Any) -> frozenset[str]:
    return frozenset(token for token in nome_tokens(str(value or "")) if token not in _LEGAL_TOKENS)


def business_name_matches(left: Any, right: Any) -> bool:
    """Confronta ragioni sociali senza accettare una parola generica isolata."""
    a, b = _business_tokens(left), _business_tokens(right)
    if not a or not b:
        return False
    if a == b:
        return True
    smaller, larger = (a, b) if len(a) <= len(b) else (b, a)
    # Una denominazione puo' contenere il titolare o una specifica aggiuntiva,
    # ma servono almeno due token concordanti. Un solo token crea falsi match.
    return len(smaller) >= 2 and smaller.issubset(larger)


def invoice_supplier_name(invoice: Dict[str, Any]) -> str:
    return str(
        invoice.get("supplier_name")
        or invoice.get("fornitore_ragione_sociale")
        or invoice.get("cedente_denominazione")
        or invoice.get("fornitore_denominazione")
        or invoice.get("ragione_sociale_fornitore")
        or ""
    ).strip()


def invoice_tax_ids(invoice: Dict[str, Any]) -> set[str]:
    keys = (
        "supplier_vat", "cedente_piva", "piva_cedente", "partita_iva",
        "piva", "supplier_tax_code", "cedente_codice_fiscale",
        "codice_fiscale_cedente", "codice_fiscale",
    )
    return {tax_id for key in keys if (tax_id := normalize_tax_id(invoice.get(key)))}


def invoice_number(invoice: Dict[str, Any]) -> str:
    return str(
        invoice.get("invoice_number") or invoice.get("numero_fattura")
        or invoice.get("numero_documento") or ""
    ).strip()


def invoice_amount(invoice: Dict[str, Any]) -> float:
    try:
        return abs(float(invoice.get("total_amount") or invoice.get("importo_totale") or 0))
    except (TypeError, ValueError):
        return 0.0


def normalize_currency(value: Any) -> str:
    """Normalizza il codice ISO della valuta, lasciando vuoto se assente."""
    return str(value or "").strip().upper()


def invoice_currency(invoice: Dict[str, Any]) -> str:
    return normalize_currency(
        invoice.get("divisa")
        or invoice.get("currency")
        or invoice.get("valuta")
    )


def transaction_currency(transaction: Dict[str, Any]) -> str:
    return normalize_currency(
        transaction.get("currency")
        or transaction.get("valuta")
        or transaction.get("divisa")
    )


def transaction_amount(transaction: Dict[str, Any]) -> float:
    try:
        return abs(float(transaction.get("importo") or transaction.get("lordo") or transaction.get("amount") or 0))
    except (TypeError, ValueError):
        return 0.0


def _parse_date(value: Any) -> Optional[date]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text[:10]).date()
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%d-%m-%Y").date()
        except ValueError:
            return None


def _first(values: Iterable[Any]) -> str:
    return next((str(value).strip() for value in values if str(value or "").strip()), "")


def evaluate_paypal_invoice_match(
    transaction: Dict[str, Any],
    invoice: Dict[str, Any],
    supplier_mapping: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Restituisce evidenze, punteggio e decisione di associazione sicura.

    Una fattura e' associabile solo se l'identita' del fornitore e' provata
    (P.IVA/CF, denominazione o email) e l'importo coincide al centesimo.
    Quando PayPal espone il numero fattura questo deve coincidere. Quando non
    lo espone, una data entro 120 giorni abilita la candidatura; il chiamante
    deve comunque accettarla soltanto se resta univoca.
    """
    mapping = supplier_mapping or {}
    evidenze: list[str] = []

    mapped_tax_ids = {
        tax_id
        for key in ("fornitore_piva", "piva", "partita_iva", "codice_fiscale")
        if (tax_id := normalize_tax_id(mapping.get(key)))
    }
    tax_match = bool(mapped_tax_ids & invoice_tax_ids(invoice))
    if tax_match:
        evidenze.append("partita_iva_o_cf")

    supplier_name = invoice_supplier_name(invoice)
    candidate_names = (
        mapping.get("fornitore_nome"), mapping.get("fornitore_ragione_sociale"),
        mapping.get("nome"), mapping.get("ragione_sociale"),
        transaction.get("nome_controparte"), transaction.get("payer_name"),
    )
    name_match = any(business_name_matches(name, supplier_name) for name in candidate_names if name)
    if name_match:
        evidenze.append("denominazione_fornitore")

    tx_email = _first((transaction.get("email_controparte"), transaction.get("payer_email"))).casefold()
    inv_email = _first((invoice.get("supplier_email"), invoice.get("cedente_email"), invoice.get("email_cedente"))).casefold()
    email_match = bool(tx_email and inv_email and tx_email == inv_email)
    if email_match:
        evidenze.append("email_fornitore")

    reference = _first((transaction.get("invoice_id_fornitore"), transaction.get("invoice_id")))
    reference_match = bool(reference and invoice_reference_equals(invoice_number(invoice), reference))
    if reference_match:
        evidenze.append("numero_fattura")

    tx_amount, inv_amount = transaction_amount(transaction), invoice_amount(invoice)
    amount_match = amounts_equal_to_cent(tx_amount, inv_amount)
    if amount_match:
        evidenze.append("importo")

    tx_currency = transaction_currency(transaction)
    inv_currency = invoice_currency(invoice)
    currency_match = not (tx_currency and inv_currency) or tx_currency == inv_currency
    if tx_currency and inv_currency and currency_match:
        evidenze.append("valuta")

    tx_date = _parse_date(transaction.get("data") or transaction.get("initiation_date") or transaction.get("date"))
    inv_date = _parse_date(invoice.get("invoice_date") or invoice.get("data_fattura") or invoice.get("data_documento"))
    days = abs((tx_date - inv_date).days) if tx_date and inv_date else None
    date_match = days is not None and days <= 120
    if date_match:
        evidenze.append("data_entro_120_giorni")

    supplier_identity = tax_match or name_match or email_match
    reference_or_date = reference_match if reference else date_match
    associabile = supplier_identity and reference_or_date and amount_match and currency_match
    score = (
        (60 if tax_match else 0)
        + (45 if name_match else 0)
        + (50 if email_match else 0)
        + (30 if reference_match else 0)
        + (20 if amount_match else 0)
        + (5 if tx_currency and inv_currency and currency_match else 0)
        + (5 if date_match else 0)
    )
    return {
        "associabile": associabile,
        "identita_fornitore": supplier_identity,
        "score": score,
        "evidenze": evidenze,
        "scarto": None if associabile else (
            "identita_fornitore_non_verificata" if not supplier_identity
            else "numero_fattura_non_coincidente" if reference and not reference_match
            else "data_non_compatibile" if not reference and not date_match
            else "importo_non_coincidente_al_centesimo" if not amount_match
            else "valuta_non_coincidente"
        ),
    }
