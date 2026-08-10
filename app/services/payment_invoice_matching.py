"""Regole comuni e conservative per collegare pagamenti e fatture.

Un collegamento automatico richiede sempre il numero fattura esplicito e
l'importo uguale al centesimo. Nome/P.IVA del fornitore sono controlli
aggiuntivi contro collisioni tra documenti di soggetti diversi.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
import re


def money_cents(value: Any) -> int | None:
    """Converte un importo in centesimi senza confronti approssimativi float."""
    if value in (None, ""):
        return None
    text = (
        str(value)
        .strip()
        .replace("\u00a0", "")
        .replace("€", "")
        .replace(" ", "")
    )
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        amount = Decimal(text).copy_abs().quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None
    return int(amount * 100)


def amounts_equal_to_cent(left: Any, right: Any) -> bool:
    left_cents, right_cents = money_cents(left), money_cents(right)
    return left_cents is not None and left_cents > 0 and left_cents == right_cents


def normalize_invoice_reference(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def invoice_reference_equals(left: Any, right: Any) -> bool:
    left_norm = normalize_invoice_reference(left)
    return bool(left_norm and left_norm == normalize_invoice_reference(right))


def invoice_reference_in_text(reference: Any, text: Any) -> bool:
    """Verifica che il numero documento sia citato come riferimento fattura.

    Per numeri molto brevi richiede sempre una parola come ``fattura``/``FT``;
    per riferimenti lunghi ammette anche la forma isolata, mantenendo confini
    alfanumerici per non confondere date, CRO o parti di altri codici.
    """
    raw = str(reference or "").strip().upper()
    narrative = str(text or "").upper()
    compact = normalize_invoice_reference(raw)
    if not compact or not narrative:
        return False

    parts = [re.escape(part) for part in re.findall(r"[A-Z0-9]+", raw)]
    if not parts:
        return False
    flexible = r"[^A-Z0-9]*".join(parts)
    prefix = r"(?:FATTURA|FATTURE|FATT|FAT|FT|INVOICE|INV|DOCUMENTO|DOC)\s*(?:N[.°º]?\s*)?"
    if re.search(rf"{prefix}{flexible}(?![A-Z0-9])", narrative):
        return True
    if len(compact) < 4:
        return False
    return re.search(rf"(?<![A-Z0-9]){flexible}(?![A-Z0-9])", narrative) is not None
