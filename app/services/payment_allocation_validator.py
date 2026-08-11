"""Regole canoniche per le allocazioni pagamento -> documento.

Questo modulo è intenzionalmente privo di effetti collaterali: valida importi
e ruoli documentali prima che i router possano scrivere collegamenti.  Gli
importi vengono normalizzati in centesimi interi; i float presenti nei dati
storici sono accettati solo come input e mai usati per la quadratura.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, Iterable, Optional


CENT = Decimal("0.01")


def to_cents(value: Any) -> int:
    """Converte un importo in centesimi senza passare da aritmetica binaria."""
    if value is None or value == "":
        return 0
    if isinstance(value, bool):
        return int(value) * 100
    text = str(value).strip().replace(" ", "")
    if not text:
        return 0
    # Accetta sia 1.234,56 sia 1234.56 e non interpreta un separatore singolo
    # come migliaia quando è seguito da una o due cifre decimali.
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return int((Decimal(text) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return 0


def invoice_total_cents(invoice: Dict[str, Any]) -> int:
    return to_cents(
        invoice.get("total_amount")
        if invoice.get("total_amount") is not None
        else invoice.get("importo_totale")
    )


def invoice_paid_cents(invoice: Dict[str, Any]) -> int:
    return max(0, to_cents(invoice.get("importo_pagato")))


def is_credit_note(invoice: Dict[str, Any]) -> bool:
    """TD04/TD08 sono documenti di rettifica, non debiti da pagare."""
    tipo = str(
        invoice.get("tipo_documento")
        or invoice.get("document_type")
        or invoice.get("tipoDocumento")
        or ""
    ).strip().upper()
    return tipo in {"TD04", "TD08"} or str(invoice.get("document_role") or "").lower() in {
        "credit_note",
        "nota_credito",
    }


def existing_invoice_allocations_cents(
    invoice: Dict[str, Any], exclude_allocation_id: Optional[str] = None,
) -> int:
    """Somma tutte le quote positive già impegnate sulla fattura."""
    links = invoice.get("assegni_collegati") or []
    linked = 0
    for link in links:
        if not isinstance(link, dict):
            continue
        if exclude_allocation_id and str(link.get("assegno_id")) == str(exclude_allocation_id):
            continue
        quota = to_cents(link.get("quota"))
        if quota > 0:
            linked += quota
    bank_links = invoice.get("payment_allocations") or []
    bank_linked = sum(
        to_cents(link.get("quota_cents")) if not isinstance(link.get("quota_cents"), int)
        else int(link.get("quota_cents"))
        for link in bank_links
        if isinstance(link, dict)
        and (not exclude_allocation_id or str(link.get("allocation_id")) != str(exclude_allocation_id))
        and str(link.get("status") or "confirmed").lower() not in {"stornata", "reversed", "annullata"}
    )
    # importo_pagato include anche bonifici/cassa. Le quote strumento gia'
    # registrate non vanno contate due volte.
    confirmed_checks = sum(
        to_cents(link.get("quota"))
        for link in links
        if isinstance(link, dict)
        and (not exclude_allocation_id or str(link.get("assegno_id")) != str(exclude_allocation_id))
        and link.get("banca_confermata")
        and to_cents(link.get("quota")) > 0
    )
    non_instrument_paid = max(0, invoice_paid_cents(invoice) - confirmed_checks - bank_linked)
    return linked + bank_linked + non_instrument_paid


def validate_invoice_allocation(
    invoice: Dict[str, Any],
    requested_cents: Any,
    *,
    allocation_id: Optional[str] = None,
    allow_credit: bool = False,
) -> Dict[str, Any]:
    """Valida una quota senza scrivere dati.

    ``status`` è uno dei valori condivisi dalle pagine: ``valid``,
    ``ambiguous`` o ``conflicting``.  Un documento senza importo valido e una
    nota di credito usata come pagamento sono sempre conflittuali.
    """
    # Il parametro è canonico in centesimi; per comodità dei chiamanti
    # interattivi accettiamo anche stringhe/Decimal in euro. Un int è già un
    # conteggio di centesimi e non viene moltiplicato di nuovo.
    requested = requested_cents if isinstance(requested_cents, int) else to_cents(requested_cents)
    total = invoice_total_cents(invoice)
    committed = existing_invoice_allocations_cents(invoice, allocation_id)
    residual = max(0, total - committed)
    if requested <= 0:
        return {"allowed": bool(allow_credit and requested < 0), "status": "conflicting",
                "reason": "quota_non_positiva", "total_cents": total,
                "committed_cents": committed, "residual_cents": residual,
                "requested_cents": requested}
    if is_credit_note(invoice) and not allow_credit:
        return {"allowed": False, "status": "conflicting", "reason": "nota_di_credito_non_pagabile",
                "total_cents": total, "committed_cents": committed,
                "residual_cents": residual, "requested_cents": requested}
    if total <= 0:
        return {"allowed": False, "status": "conflicting", "reason": "totale_documento_non_valido",
                "total_cents": total, "committed_cents": committed,
                "residual_cents": residual, "requested_cents": requested}
    if committed + requested > total:
        return {"allowed": False, "status": "conflicting", "reason": "quota_supera_residuo",
                "total_cents": total, "committed_cents": committed,
                "residual_cents": residual, "requested_cents": requested}
    return {"allowed": True, "status": "valid", "reason": None,
            "total_cents": total, "committed_cents": committed,
            "residual_cents": max(0, residual - requested), "requested_cents": requested}


def allocation_status(invoice: Dict[str, Any]) -> str:
    """Deriva uno stato comune per archivio, banca, Prima Nota e fornitori."""
    explicit = str(invoice.get("payment_allocation_status") or "").lower()
    if explicit in {"valid", "ambiguous", "conflicting"}:
        return explicit
    if invoice.get("associazione_conflittuale") or invoice.get("allocation_conflict_reason"):
        return "conflicting"
    if invoice.get("associazione_ambigua") or invoice.get("stato") == "da_confermare":
        return "ambiguous"
    links = invoice.get("assegni_collegati") or []
    if links or invoice.get("movimento_bancario_id") or invoice.get("prima_nota_banca_id"):
        return "valid"
    return "ambiguous"


def allocation_summary(invoice: Dict[str, Any]) -> Dict[str, Any]:
    total = invoice_total_cents(invoice)
    committed = existing_invoice_allocations_cents(invoice)
    status = "conflicting" if committed > total > 0 else allocation_status(invoice)
    return {
        "payment_allocation_status": status,
        "allocated_cents": committed,
        "residual_cents": max(0, total - committed),
        "allocation_conflict_reason": invoice.get("allocation_conflict_reason")
        or ("quota_supera_residuo" if committed > total > 0 else None),
    }
