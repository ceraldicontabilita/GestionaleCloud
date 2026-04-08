"""
Distinte Pagamento BPM — Upload PDF, parse, salva.
Collection: distinte_pagamento
Prefix: /api/distinte
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime
import logging

from app.database import get_database
from app.parsers.distinta_bpm import parse_distinta_pdf  # nome corretto

router = APIRouter()
logger = logging.getLogger(__name__)


def _oid(doc):
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


@router.post("/upload-pdf")
async def upload_distinta(file: UploadFile = File(...), db: AsyncIOMotorDatabase = Depends(get_database)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Solo PDF")
    content = await file.read()

    try:
        parsed = parse_distinta_pdf(pdf_bytes=content)
    except Exception as e:
        raise HTTPException(400, f"Errore parsing PDF: {e}")

    # Il parser ritorna: numero_bonifici, bonifici[], totale, data_disposizione
    parsed["filename"] = file.filename
    parsed["imported_at"] = datetime.utcnow()
    result = await db["distinte_pagamento"].insert_one(parsed)

    # Riconcilia bonifici con dipendenti per IBAN
    riconciliati = 0
    bonifici = parsed.get("bonifici", [])
    for bon in bonifici:
        iban = bon.get("iban")
        if iban:
            dip = await db["dipendenti"].find_one({"iban": iban})
            if dip:
                bon["dipendente_id"] = str(dip["_id"])
                bon["dipendente_nome"] = f"{dip.get('cognome', '')} {dip.get('nome', '')}"
                riconciliati += 1

    if riconciliati > 0:
        await db["distinte_pagamento"].update_one(
            {"_id": result.inserted_id},
            {"$set": {"bonifici": bonifici, "riconciliati": riconciliati}}
        )

    return {
        "ok": True,
        "n_bonifici": parsed.get("numero_bonifici", 0),
        "totale": parsed.get("totale", 0),
        "riconciliati_dipendenti": riconciliati,
    }


@router.get("")
async def lista_distinte(skip: int = 0, limit: int = 20,
                         db: AsyncIOMotorDatabase = Depends(get_database)):
    cursor = db["distinte_pagamento"].find().sort("imported_at", -1).skip(skip).limit(limit)
    items = [_oid(doc) async for doc in cursor]
    return {"items": items, "totale": await db["distinte_pagamento"].count_documents({})}
