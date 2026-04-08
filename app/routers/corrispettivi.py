"""
Corrispettivi — Upload XML RT, parse, salva.
Collection: corrispettivi
Prefix: /api/corrispettivi
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime
from typing import Optional
import logging

from app.database import get_database
from app.parsers.corrispettivi_xml import parse_corrispettivo_xml

router = APIRouter()
logger = logging.getLogger(__name__)


def _oid(doc):
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


@router.post("/upload-xml")
async def upload_corrispettivo(file: UploadFile = File(...), db: AsyncIOMotorDatabase = Depends(get_database)):
    content = await file.read()
    xml_str = content.decode("utf-8", errors="replace")
    parsed = parse_corrispettivo_xml(xml_str)
    if parsed.get("errore"):
        raise HTTPException(400, parsed["errore"])

    # Il parser ritorna 'dedup_key', non 'chiave'
    dedup = parsed.get("dedup_key", "")
    existing = await db["corrispettivi"].find_one({"dedup_key": dedup})
    if existing:
        return {"ok": True, "stato": "duplicato"}

    parsed["filename"] = file.filename
    parsed["imported_at"] = datetime.utcnow()
    await db["corrispettivi"].insert_one(parsed)

    # Il parser ritorna 'totale_corrispettivi', non 'totale_incassato'
    return {
        "ok": True,
        "stato": "importato",
        "data": parsed.get("data", ""),
        "totale": parsed.get("totale_corrispettivi", 0),
    }


@router.get("")
async def lista_corrispettivi(anno: Optional[int] = None, mese: Optional[int] = None,
                              skip: int = 0, limit: int = 50,
                              db: AsyncIOMotorDatabase = Depends(get_database)):
    filtro = {}
    if anno:
        filtro["data"] = {"$regex": f"^{anno}"}
        if mese:
            filtro["data"] = {"$regex": f"^{anno}-{mese:02d}"}
    cursor = db["corrispettivi"].find(filtro).sort("data", -1).skip(skip).limit(limit)
    items = [_oid(doc) async for doc in cursor]
    return {"items": items, "totale": await db["corrispettivi"].count_documents(filtro)}


@router.get("/stats")
async def stats_corrispettivi(anno: Optional[int] = None, db: AsyncIOMotorDatabase = Depends(get_database)):
    filtro = {"data": {"$regex": f"^{anno}"}} if anno else {}
    pipeline = [
        {"$match": filtro},
        {"$group": {"_id": {"$substr": ["$data", 0, 7]},
                    "totale": {"$sum": "$totale_corrispettivi"},
                    "n": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    mesi = await db["corrispettivi"].aggregate(pipeline).to_list(12)
    return {"mesi": mesi}
