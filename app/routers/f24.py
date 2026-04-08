"""
Router F24 — Ceraldi ERP
PREFIX: /api/f24

Collection MongoDB: f24

Endpoints:
  POST   /api/f24/upload-pdf          → import batch PDF
  GET    /api/f24                     → lista con filtri (anno, mese, stato, sezione)
  GET    /api/f24/{id}                → singolo documento
  GET    /api/f24/{id}/pdf            → PDF originale
  POST   /api/f24/{id}/segna-pagato   → marca pagato manualmente
  GET    /api/f24/ricerca-tributo     → cerca tributo per codice+anno (per avvisi)
  GET    /api/f24/riepilogo/{anno}    → totali annuali per sezione
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import JSONResponse, FileResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from datetime import datetime
import os, re

from app.database import get_database

router = APIRouter(prefix="/api/f24", tags=["F24"])

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "f24")
os.makedirs(UPLOAD_DIR, exist_ok=True)

AZIENDA_ID = "b0295759-35ce-4b34-a6b4-f01b883234ad"


def _oid(doc):
    doc["_id"] = str(doc["_id"])
    return doc


# ═══════════════════════════════════════════════════════
# POST /upload-pdf  — import batch PDF F24
# ═══════════════════════════════════════════════════════
@router.post("/upload-pdf")
async def upload_f24_pdf(
    files: list[UploadFile] = File(...),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    from app.parsers.f24_parser import parse_f24_pdf

    risultati = []
    for upload in files:
        pdf_bytes = await upload.read()
        filename = upload.filename or "f24.pdf"

        # Salva PDF originale
        safe_name = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", filename)
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        dest = os.path.join(UPLOAD_DIR, f"{ts}_{safe_name}")
        with open(dest, "wb") as f:
            f.write(pdf_bytes)

        try:
            documenti = parse_f24_pdf(pdf_bytes, filename)
        except Exception as e:
            risultati.append({"file": filename, "ok": False, "errore": str(e)})
            continue

        for doc in documenti:
            doc["azienda_id"] = AZIENDA_ID
            doc["pdf_path"] = dest
            doc["created_at"] = datetime.utcnow()
            doc["updated_at"] = datetime.utcnow()

            # Upsert su (codice_fiscale, scadenza, pagina)
            existing = await db["f24"].find_one({
                "codice_fiscale": doc.get("codice_fiscale"),
                "scadenza": doc.get("scadenza"),
                "pagina": doc.get("pagina", 1),
            })
            if existing:
                await db["f24"].update_one(
                    {"_id": existing["_id"]},
                    {"$set": {**doc, "updated_at": datetime.utcnow()}}
                )
                risultati.append({
                    "file": filename,
                    "ok": True,
                    "azione": "aggiornato",
                    "id": str(existing["_id"]),
                    "scadenza": doc.get("scadenza"),
                    "saldo_finale": doc.get("saldo_finale"),
                })
            else:
                res = await db["f24"].insert_one(doc)
                risultati.append({
                    "file": filename,
                    "ok": True,
                    "azione": "inserito",
                    "id": str(res.inserted_id),
                    "scadenza": doc.get("scadenza"),
                    "saldo_finale": doc.get("saldo_finale"),
                })

    return {"risultati": risultati, "totale": len(risultati)}


# ═══════════════════════════════════════════════════════
# GET /  — lista F24 con filtri
# ═══════════════════════════════════════════════════════
@router.get("")
async def lista_f24(
    anno: int = None,
    mese: int = None,
    sezione: str = None,
    codice_tributo: str = None,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    q = {"azienda_id": AZIENDA_ID}

    if anno:
        q["scadenza"] = {"$regex": f"^{anno}"}
    if mese and anno:
        q["scadenza"] = f"{anno}-{mese:02d}"

    if codice_tributo:
        q["tributi_flat.codice_tributo"] = codice_tributo
    if sezione:
        q["tributi_flat.sezione"] = sezione.upper()

    cursor = db["f24"].find(q).sort("scadenza", -1)
    docs = []
    async for doc in cursor:
        docs.append(_oid(doc))
    return docs


# ═══════════════════════════════════════════════════════
# GET /{id}  — singolo F24
# ═══════════════════════════════════════════════════════
@router.get("/{fid}")
async def get_f24(fid: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    doc = await db["f24"].find_one({"_id": ObjectId(fid)})
    if not doc:
        raise HTTPException(404, "F24 non trovato")
    return _oid(doc)


# ═══════════════════════════════════════════════════════
# GET /{id}/pdf  — scarica PDF originale
# ═══════════════════════════════════════════════════════
@router.get("/{fid}/pdf")
async def download_f24_pdf(fid: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    doc = await db["f24"].find_one({"_id": ObjectId(fid)})
    if not doc:
        raise HTTPException(404, "F24 non trovato")
    path = doc.get("pdf_path", "")
    if not path or not os.path.exists(path):
        raise HTTPException(404, "PDF non disponibile")
    return FileResponse(path, media_type="application/pdf",
                        filename=f"F24_{doc.get('scadenza','')}.pdf")


# ═══════════════════════════════════════════════════════
# POST /{id}/segna-pagato  — marca pagato manualmente
# ═══════════════════════════════════════════════════════
@router.post("/{fid}/segna-pagato")
async def segna_pagato(fid: str, body: dict = {}, db: AsyncIOMotorDatabase = Depends(get_database)):
    upd = {"stato": "pagato", "updated_at": datetime.utcnow()}
    if body.get("data_pagamento"):
        upd["data_pagamento"] = body["data_pagamento"]
    res = await db["f24"].update_one({"_id": ObjectId(fid)}, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(404, "F24 non trovato")
    return {"ok": True}


# ═══════════════════════════════════════════════════════
# GET /ricerca-tributo  — per riconciliazione avvisi
# ═══════════════════════════════════════════════════════
@router.get("/ricerca-tributo")
async def ricerca_tributo(
    codice: str = Query(...),
    anno_rif: str = Query(None),
    mese_rif: str = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Cerca se un tributo è stato pagato.
    Ritorna tutti gli F24 che contengono quel codice tributo/anno/mese.
    Usato per rispondere a avvisi bonari, cartelle ADE/ADR.
    """
    q = {
        "azienda_id": AZIENDA_ID,
        "tributi_flat.codice_tributo": codice,
    }
    if anno_rif:
        q["tributi_flat.anno_rif"] = anno_rif
    if mese_rif:
        q["tributi_flat.mese_rif"] = mese_rif

    cursor = db["f24"].find(q).sort("scadenza", 1)
    risultati = []
    async for doc in cursor:
        # Filtra solo i righi rilevanti
        righi = [
            r for r in doc.get("tributi_flat", [])
            if r.get("codice_tributo") == codice
            and (not anno_rif or r.get("anno_rif") == anno_rif)
            and (not mese_rif or r.get("mese_rif") == mese_rif)
        ]
        risultati.append({
            "_id": str(doc["_id"]),
            "scadenza": doc.get("scadenza"),
            "data_pagamento": doc.get("data_pagamento"),
            "stato": doc.get("stato"),
            "pdf_path": doc.get("pdf_path"),
            "saldo_finale": doc.get("saldo_finale"),
            "banca": doc.get("banca"),
            "righi_trovati": righi,
        })

    return {
        "codice": codice,
        "anno_rif": anno_rif,
        "mese_rif": mese_rif,
        "trovati": len(risultati),
        "pagamenti": risultati,
        "esito": "PAGATO" if risultati else "NON TROVATO — verificare",
    }


# ═══════════════════════════════════════════════════════
# GET /riepilogo/{anno}  — totali annuali per sezione
# ═══════════════════════════════════════════════════════
@router.get("/riepilogo/{anno}")
async def riepilogo_annuale(anno: int, db: AsyncIOMotorDatabase = Depends(get_database)):
    pipeline = [
        {"$match": {
            "azienda_id": AZIENDA_ID,
            "scadenza": {"$regex": f"^{anno}"},
            "pagina": 1,
        }},
        {"$group": {
            "_id": None,
            "totale_versato": {"$sum": "$saldo_finale"},
            "n_f24": {"$sum": 1},
            "scadenze": {"$push": {
                "scadenza": "$scadenza",
                "data_pagamento": "$data_pagamento",
                "saldo_finale": "$saldo_finale",
                "stato": "$stato",
                "_id": {"$toString": "$_id"},
            }},
        }},
    ]
    async for doc in db["f24"].aggregate(pipeline):
        doc.pop("_id", None)
        return doc
    return {"totale_versato": 0, "n_f24": 0, "scadenze": []}
