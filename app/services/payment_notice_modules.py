"""Moduli da pagare: codice e importo stampati insieme, mai prove di pagamento."""
from __future__ import annotations

import re
import hashlib
from decimal import Decimal

POSTAL = re.compile(r"\b18(\d{18})12(\d{12})10(\d{10})3(896|674)\b")


def _amount(value: str) -> Decimal:
    return Decimal(value.replace(".", "").replace(",", "."))


def parse_notice_modules(content: bytes) -> list[dict]:
    import fitz

    modules = {}
    try:
        pdf = fitz.open(stream=content, filetype="pdf")
    except Exception:
        return []
    with pdf:
        for page_number, page in enumerate(pdf, 1):
            text = page.get_text()
            upper = text.upper()
            if any(marker in upper for marker in ("TRANSAZIONE ESEGUITA", "PAGAMENTO ESEGUITO", "PAGAMENTO MAV")):
                continue
            found = []
            if "BOLLO DELL'UFFICIO POSTALE" in upper and "CODICE CLIENTE" in upper:
                for match in POSTAL.finditer(text):
                    code, account, cents, _ = match.groups()
                    amount = Decimal(cents) / 100
                    # Il barcode deve essere confermato anche dai campi leggibili.
                    if not re.search(rf"(?m)^\s*<?{code}>?\s*$", text):
                        continue
                    printed = f"{amount:.2f}".replace(".", ",")
                    if printed not in text.replace(".", ""):
                        continue
                    found.append((code, amount, "BOLLETTINO_POSTALE", account))
            elif "CODICE IDENTIFICATIVO MAV" in upper and "TIMBRO DATARIO" in upper:
                codes = set(re.findall(r"(?m)^\s*(\d{17})\s*$", text))
                amounts = {_amount(a) for a in re.findall(r"(?m)^\s*([\d.]+,\d{2})\s*$", text)}
                if len(codes) == len(amounts) == 1:
                    found.append((codes.pop(), amounts.pop(), "MAV", None))
            elif "MODULO DI PAGAMENTO" in upper and "CODICE MODULO DI PAGAMENTO" in upper:
                bank = upper.split("BOLLETTINO POSTALE PA")[0]
                codes = set(re.findall(r"\b(1800\d{14})\b", bank))
                amounts = {_amount(a) for a in re.findall(r"EURO\s+([\d.]+,\d{2})\b", bank)}
                if len(codes) == len(amounts) == 1:
                    found.append((codes.pop(), amounts.pop(), "PAGOPA", None))
            for code, amount, kind, account in found:
                if amount <= 0:
                    continue
                modules.setdefault((code, str(amount)), {
                    "code": code, "amount": float(amount), "amount_cents": int(amount * 100),
                    "kind": kind, "account": account, "page_number": page_number,
                    "is_payment_receipt": False, "parser_version": "notice-modules-v1",
                })
    return list(modules.values())


async def collega_moduli_verbale(db, document_id: str, content: bytes) -> dict:
    """Recupera i bollettini dell'originale senza alterare i campi corretti a mano."""
    modules = parse_notice_modules(content)
    if not modules:
        return {"collegati": 0}
    digest = hashlib.sha256(content).hexdigest()
    candidates = await db["verbali_noleggio"].find({"$or": [
        {"source_document_id": document_id}, {"document_ids": document_id},
        {"pdf_hash": digest}, {"source_sha256": digest},
    ]}, {"_id": 0, "pdf_data": 0}).to_list(20)
    if len(candidates) != 1:
        return {"collegati": 0, "motivo": "originale_non_univoco"}
    verbale = candidates[0]
    await db["verbali_noleggio"].update_one({"id": verbale["id"]}, {"$set": {
        "payment_modules": modules, "payment_modules_source_sha256": digest,
    }})
    codes = list({m["code"] for m in modules})
    receipts = await db["ricevute_pagopa"].find({"$or": [
        {"identificativo_bolletta": {"$in": codes}}, {"iuv": {"$in": codes}},
    ], "duplicate_of": {"$exists": False}}, {"_id": 0, "pdf_data": 0}).to_list(100)
    from app.services.pagopa_receipts import _associate_receipt_to_verbale
    linked = 0
    for receipt in receipts:
        if receipt.get("is_payment_receipt") is False or receipt.get("verbale_id") not in (None, verbale["id"]):
            continue
        result = await _associate_receipt_to_verbale(
            db, receipt_id=receipt["id"], parsed=receipt, amount=receipt.get("importo"))
        if result.get("matched"):
            await db["ricevute_pagopa"].update_one({"id": receipt["id"]}, {"$set": {
                "verbale_id": result["verbale_id"], "stato_verbale": "agganciata", "stato": "associata",
                "riconciliazione_verbale": result,
            }})
            linked += 1
    return {"collegati": linked}
