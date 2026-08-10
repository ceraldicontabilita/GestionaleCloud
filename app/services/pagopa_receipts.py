"""Import canonico e parsing conservativo delle ricevute PagoPA/CBILL."""
from __future__ import annotations

import base64
import hashlib
import io
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.services.payment_invoice_matching import amounts_equal_to_cent


COLLECTION_RICEVUTE = "ricevute_pagopa"


def parse_receipt_pdf(content: bytes) -> dict[str, Any]:
    text = ""
    try:
        from pypdf import PdfReader

        text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages)
    except Exception:
        pass
    compact = re.sub(r"\s+", " ", text)
    code = None
    for pattern in (
        r"(?:identificativo\s+(?:univoco\s+)?(?:versamento|bolletta)|IUV|CBILL)\s*[:#-]?\s*(\d{15,20})",
        r"\b([03]\d{17})\b",
    ):
        match = re.search(pattern, compact, re.IGNORECASE)
        if match:
            code = match.group(1)
            break
    amount = None
    amount_match = re.search(
        r"(?:importo\s+(?:pagato|versato|totale)|totale)\s*[:€EUR ]*([\d.]+,\d{2})",
        compact, re.IGNORECASE,
    )
    if amount_match:
        amount = float(amount_match.group(1).replace(".", "").replace(",", "."))
    payment_date = None
    date_match = re.search(
        r"(?:data\s+(?:del\s+)?pagamento|pagato\s+il)\s*:?\s*(\d{2}/\d{2}/\d{4})",
        compact, re.IGNORECASE,
    )
    if date_match:
        day, month, year = date_match.group(1).split("/")
        payment_date = f"{year}-{month}-{day}"
    return {
        "identificativo_bolletta": code,
        "importo": amount,
        "data_pagamento": payment_date,
        "text_detected": bool(text.strip()),
    }


async def find_bank_movement(db, code: str, amount: Any):
    if not code or amount in (None, ""):
        return None
    movements = await db.estratto_conto_movimenti.find({
        "$or": [
            {"descrizione_originale": {"$regex": re.escape(code)}},
            {"descrizione": {"$regex": re.escape(code)}},
        ],
        "ricevuta_pagopa_id": {"$in": [None, ""]},
    }, {"_id": 0}).limit(20).to_list(20)
    exact = [item for item in movements if amounts_equal_to_cent(item.get("importo"), amount)]
    return exact[0] if len(exact) == 1 else None


async def import_receipt(
    db, *, content: bytes, filename: str, company_id: str,
    source: str = "upload_manuale", overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    parsed = parse_receipt_pdf(content)
    values = {**parsed, **{key: value for key, value in (overrides or {}).items() if value not in (None, "")}}
    code = str(values.get("identificativo_bolletta") or "").strip()
    amount = values.get("importo")
    if not code or amount in (None, ""):
        return {
            "success": False, "filename": filename,
            "error": "Ricevuta PagoPA/CBILL senza IUV/codice bolletta e importo leggibili",
            "requires_review": True,
        }

    pdf_hash = hashlib.sha256(content).hexdigest()
    existing = await db[COLLECTION_RICEVUTE].find_one(
        {"pdf_hash": pdf_hash}, {"_id": 0},
    )
    if existing:
        return {"success": True, "duplicate": True, "receipt": existing,
                "riconciliazione_fiscale": existing.get("riconciliazione_fiscale")}

    receipt_id = str(uuid.uuid4())
    movement = await find_bank_movement(db, code, amount)
    now = datetime.now(timezone.utc).isoformat()
    receipt = {
        "id": receipt_id, "filename": filename, "content_type": "application/pdf",
        "size": len(content), "pdf_data": base64.b64encode(content).decode("utf-8"),
        "pdf_hash": pdf_hash, "importo": float(amount),
        "data_pagamento": values.get("data_pagamento"),
        "identificativo_bolletta": code,
        "beneficiario": values.get("beneficiario") or "AGENZIA DELLE ENTRATE - RISCOSSIONE",
        "note": values.get("note"), "source": source,
        "movimento_id": movement.get("id") if movement else None,
        "associazione_automatica": bool(movement), "created_at": now,
    }
    if movement:
        receipt.update({"movimento_data": movement.get("data"),
                        "movimento_importo": movement.get("importo")})
        await db.estratto_conto_movimenti.update_one(
            {"id": movement["id"]}, {"$set": {
                "ricevuta_pagopa_id": receipt_id, "ricevuta_filename": filename,
                "updated_at": now,
            }},
        )
    await db[COLLECTION_RICEVUTE].insert_one(receipt.copy())

    from app.services.fiscal_evidence import register_document
    from app.services.fiscal_payment_reconciliation import reconcile_fiscal_payment

    document = await register_document(
        db, company_id=company_id, content=content, filename=filename, source=source,
        source_ref=receipt_id, category="riscossione",
        metadata={"receipt_collection": COLLECTION_RICEVUTE},
    )
    fiscal_match = await reconcile_fiscal_payment(
        db, company_id=company_id,
        payment={**receipt, "amount": amount, "payment_date": receipt.get("data_pagamento")},
        source_type="RICEVUTA_CBILL" if "CBILL" in filename.upper() else "RICEVUTA_PAGOPA",
        source_id=receipt_id, document_id=document.get("document_id"), version_id=document.get("id"),
    )
    if fiscal_match.get("matched"):
        patch = {
            "fiscal_payment_id": fiscal_match["payment_id"],
            "fiscal_target_id": fiscal_match["target_id"],
            "fiscal_target_type": fiscal_match["target_type"],
            "cartelle_collegate": fiscal_match["linked_claim_ids"],
            "riconciliazione_fiscale": fiscal_match,
        }
        receipt.update(patch)
        await db[COLLECTION_RICEVUTE].update_one({"id": receipt_id}, {"$set": patch})
    return {"success": True, "duplicate": False, "receipt": receipt,
            "riconciliazione_fiscale": fiscal_match}
