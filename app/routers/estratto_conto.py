"""
Estratto Conto — Upload PDF BPM, parse, salva movimenti.
Collection: estratto_conto_movimenti
Prefix: /api/estratto-conto
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime
from typing import Optional
import hashlib
import logging

from app.database import get_database
from app.parsers.estratto_conto_bpm import parse_estratto_conto_pdf

router = APIRouter()
logger = logging.getLogger(__name__)
COLL = "estratto_conto_movimenti"


def _oid(doc):
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


def _chiave(mov: dict) -> str:
    raw = f"{mov['data_operazione']}|{mov['descrizione'][:30]}|{mov['importo']}"
    return hashlib.md5(raw.encode()).hexdigest()


@router.post("/upload-pdf")
async def upload_estratto_conto(file: UploadFile = File(...), db: AsyncIOMotorDatabase = Depends(get_database)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Solo PDF")
    content = await file.read()

    try:
        parsed = parse_estratto_conto_pdf(pdf_bytes=content)
    except Exception as e:
        raise HTTPException(400, f"Errore parsing PDF: {e}")

    movimenti = parsed.get("movimenti", [])
    if not movimenti:
        raise HTTPException(400, "Nessun movimento trovato nel PDF")

    importati = 0
    duplicati = 0

    for mov in movimenti:
        mov["chiave"] = _chiave(mov)
        mov["riconciliato"] = False
        if await db[COLL].find_one({"chiave": mov["chiave"]}):
            duplicati += 1
            continue
        mov["filename"] = file.filename
        mov["imported_at"] = datetime.utcnow()
        await db[COLL].insert_one(mov)
        importati += 1

    totale_entrate = round(sum(m["avere"] for m in movimenti), 2)
    totale_uscite = round(sum(m["dare"] for m in movimenti), 2)

    return {
        "ok": True,
        "importati": importati,
        "duplicati": duplicati,
        "totale_entrate": totale_entrate,
        "totale_uscite": totale_uscite,
        "saldo_netto": round(totale_entrate - totale_uscite, 2),
        "saldo_iniziale": parsed.get("saldo_iniziale", 0),
        "saldo_finale": parsed.get("saldo_finale", 0),
    }


@router.get("")
async def lista_movimenti(
    data_da: Optional[str] = None, data_a: Optional[str] = None,
    categoria: Optional[str] = None,
    riconciliato: Optional[bool] = None,
    skip: int = 0, limit: int = 100,
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    filtro = {}
    if data_da:
        filtro.setdefault("data_operazione", {})["$gte"] = data_da
    if data_a:
        filtro.setdefault("data_operazione", {})["$lte"] = data_a
    if categoria:
        filtro["categoria"] = categoria
    if riconciliato is not None:
        filtro["riconciliato"] = riconciliato

    cursor = db[COLL].find(filtro).sort("data_operazione", -1).skip(skip).limit(limit)
    items = [_oid(doc) async for doc in cursor]
    totale = await db[COLL].count_documents(filtro)
    return {"items": items, "totale": totale}


@router.get("/saldo")
async def saldo_banca(db: AsyncIOMotorDatabase = Depends(get_database)):
    pipeline = [
        {"$group": {"_id": None,
                    "saldo": {"$sum": "$importo"},
                    "entrate": {"$sum": {"$cond": [{"$gt": ["$importo", 0]}, "$importo", 0]}},
                    "uscite": {"$sum": {"$cond": [{"$lt": ["$importo", 0]}, {"$abs": "$importo"}, 0]}},
                    "n_movimenti": {"$sum": 1}}}
    ]
    agg = await db[COLL].aggregate(pipeline).to_list(1)
    r = agg[0] if agg else {}
    return {
        "saldo": round(r.get("saldo", 0), 2),
        "entrate": round(r.get("entrate", 0), 2),
        "uscite": round(r.get("uscite", 0), 2),
        "n_movimenti": r.get("n_movimenti", 0),
    }
