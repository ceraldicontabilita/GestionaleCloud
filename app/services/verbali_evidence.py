"""Regole canoniche per gli importi dei verbali.

Un numero prodotto da OCR/regex/LLM e' soltanto un candidato. Non puo'
alimentare liste operative, dashboard o stati di pagamento finche' una fonte
documentale o un operatore non lo ha confermato esplicitamente.
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, Optional


STATI_IMPORTO_VERIFICATI = {
    "VERIFICATO_DOCUMENTO",
    "VERIFICATO_PAGAMENTO",
    "CONFERMATO_OPERATORE",
}


def amount_to_cents(value: Any) -> Optional[int]:
    """Converte un importo in centesimi senza passare da float binari."""
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return None
    try:
        if isinstance(value, str):
            normalized = value.strip().replace("EUR", "").replace("€", "").replace(" ", "")
            if "," in normalized:
                normalized = normalized.replace(".", "").replace(",", ".")
            value_decimal = Decimal(normalized)
        else:
            value_decimal = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return int((value_decimal * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _verified_cents(record: Dict[str, Any]) -> Optional[int]:
    explicitly_verified = record.get("importo_verificato") is True or (
        str(record.get("importo_stato") or "").upper() in STATI_IMPORTO_VERIFICATI
    )
    if not explicitly_verified:
        return None

    cents = record.get("importo_centesimi")
    if isinstance(cents, int) and not isinstance(cents, bool) and cents >= 0:
        return cents
    return amount_to_cents(record.get("importo"))


def _candidate_exists(record: Dict[str, Any]) -> bool:
    candidate = record.get("importo_candidato_centesimi")
    if isinstance(candidate, int) and not isinstance(candidate, bool):
        return candidate > 0
    for field in ("importo_candidato", "importo"):
        cents = amount_to_cents(record.get(field))
        if cents is not None and cents > 0:
            return True
    return False


def describe_verbale_amount(record: Dict[str, Any]) -> Dict[str, Any]:
    """Restituisce solo l'importo operativo verificato.

    Il candidato non viene esposto numericamente nella lista: resta nel record
    per audit/revisione, ma l'interfaccia mostra soltanto che esiste un dato OCR
    da controllare.
    """
    cents = _verified_cents(record)
    if cents is not None:
        return {
            "importo": float(Decimal(cents) / Decimal(100)),
            "importo_centesimi": cents,
            "importo_verificato": True,
            "importo_stato": str(record.get("importo_stato") or "VERIFICATO").upper(),
            "importo_fonte": record.get("importo_fonte") or record.get("fonte_importo"),
            "importo_candidato_presente": False,
        }

    return {
        "importo": None,
        "importo_centesimi": None,
        "importo_verificato": False,
        "importo_stato": "DA_VERIFICARE",
        "importo_fonte": record.get("importo_candidato_fonte") or "OCR_NON_VERIFICATO",
        "importo_candidato_presente": _candidate_exists(record),
    }


def sanitize_verbale_amount(record: Dict[str, Any]) -> Dict[str, Any]:
    """Copia il record sostituendo il vecchio importo con la vista probatoria."""
    sanitized = dict(record)
    sanitized.update(describe_verbale_amount(record))
    return sanitized


def describe_verbale_date(record: Dict[str, Any]) -> Dict[str, Any]:
    """Separa la data operativa da una prima data letta nel PDF/OCR."""
    verified = record.get("data_verbale_verificata") is True or str(
        record.get("data_verbale_stato") or ""
    ).upper() in STATI_IMPORTO_VERIFICATI
    raw_date = record.get("data_verbale") or record.get("data_violazione")
    if verified and raw_date:
        return {
            "data_verbale": raw_date,
            "data_verbale_verificata": True,
            "data_verbale_stato": str(record.get("data_verbale_stato") or "VERIFICATA").upper(),
            "data_verbale_candidato_presente": False,
        }
    return {
        "data_verbale": None,
        "data_verbale_verificata": False,
        "data_verbale_stato": "DA_VERIFICARE",
        "data_verbale_candidato_presente": bool(
            record.get("data_verbale_candidato") or raw_date
        ),
    }


def sanitize_verbale_evidence(record: Dict[str, Any]) -> Dict[str, Any]:
    sanitized = sanitize_verbale_amount(record)
    sanitized.update(describe_verbale_date(record))
    stato_originale = str(record.get("stato") or "sconosciuto").lower()
    if stato_originale in {"pagato", "pagato_attesa_quietanza", "pagato_attesa_fattura", "riconciliato"}:
        has_payment_evidence = bool(
            record.get("pagato_documentalmente") is True
            or record.get("banca_verificata") is True
            or record.get("pagamento_id")
            or record.get("ricevuta_pagopa_id")
            or record.get("paypal_transaction_id")
            or record.get("movimento_banca_id")
        )
        if not sanitized["importo_verificato"] or not has_payment_evidence:
            sanitized["stato_originale"] = stato_originale
            sanitized["stato"] = "da_verificare"
            sanitized["stato_motivo"] = "Importo o prova di pagamento non verificati"
    return sanitized
