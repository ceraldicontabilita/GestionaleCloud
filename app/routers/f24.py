"""
F24 — Upload PDF, parse tributi, salva.
Collection: f24
Prefix: /api/f24
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime
from typing import Optional
import hashlib, logging

from app.database import get_database
from app.parsers.f24 import parse_f24_pdf

router = APIRouter()
logger = logging.getLogger(__name__)


def _oid(doc):
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


@router.post("/upload-pdf")
async def upload_f24(file: UploadFile = File(...), db: AsyncIOMotorDatabase = Depends(get_database)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Solo PDF")
    content = await file.read()
    parsed = parse_f24_pdf(pdf_bytes=content)
    if parsed.get("errore"):
        raise HTTPException(400, parsed["errore"])

    data = parsed.get("data_versamento", "")
    totale = parsed.get("totale_versato", 0)
    chiave = hashlib.md5(f"{data}|{totale}".encode()).hexdigest()

    existing = await db["f24"].find_one({"chiave": chiave})
    if existing:
        return {"ok": True, "stato": "duplicato", "chiave": chiave}

    parsed["chiave"] = chiave
    parsed["filename"] = file.filename
    parsed["imported_at"] = datetime.utcnow()
    parsed["stato"] = "importato"
    parsed["riconciliato"] = False
    await db["f24"].insert_one(parsed)

    return {"ok": True, "stato": "importato", "data": data, "totale": totale, "n_tributi": parsed["n_tributi"]}


@router.get("")
async def lista_f24(anno: Optional[int] = None, skip: int = 0, limit: int = 50,
                    db: AsyncIOMotorDatabase = Depends(get_database)):
    filtro = {}
    if anno:
        filtro["data_versamento"] = {"$regex": f"^{anno}"}
    cursor = db["f24"].find(filtro).sort("data_versamento", -1).skip(skip).limit(limit)
    items = [_oid(doc) async for doc in cursor]
    return {"items": items, "totale": await db["f24"].count_documents(filtro)}
