"""
Router F24 Privati — Ceraldi ERP
PREFIX: /api/f24-privati

Gestisce F24 di persone fisiche NON appartenenti a Ceraldi Group S.R.L.
Attualmente: CERALDI MICHELE (CF: CRLMHL50R01F352F)
Collection MongoDB: f24_privati (separata da f24 aziendale)

Endpoints:
  POST   /api/f24-privati/upload-pdf
  GET    /api/f24-privati
  GET    /api/f24-privati/{id}
  GET    /api/f24-privati/{id}/pdf
  GET    /api/f24-privati/riepilogo/{cf}/{anno}
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from datetime import datetime
import os, re

from app.database import get_database
from app.parsers.f24_parser import parse_f24_pdf

router = APIRouter(prefix="/api/f24-privati", tags=["F24 Privati"])

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "f24_privati")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Soggetti privati noti (non Ceraldi Group SRL)
PRIVATI_NOTI = {
    "CRLMHL50R01F352F": {
        "nome": "Ceraldi Michele",
        "data_nascita": "01/10/1950",
        "comune_nascita": "Mondragone (CE)",
        "domicilio": "Napoli NA, Piazza Nazionale 26",
    }
}

def _oid(doc):
    doc["_id"] = str(doc["_id"])
    return doc


@router.post("/upload-pdf")
async def upload_f24_privato(
    files: list[UploadFile] = File(...),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    risultati = []
    for upload in files:
        pdf_bytes = await upload.read()
        filename = upload.filename or "f24_privato.pdf"

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
            # Verifica che NON sia un F24 aziendale
            cf = doc.get("codice_fiscale", "")
            if cf == "04523831214":
                risultati.append({
                    "file": filename, "ok": False,
                    "errore": "F24 aziendale Ceraldi Group — usa il modulo F24 principale"
                })
                continue

            # Arricchisce con dati anagrafici se CF noto
            if cf in PRIVATI_NOTI:
                doc["anagrafica"] = PRIVATI_NOTI[cf]
            
            doc["pdf_path"] = dest
            doc["created_at"] = datetime.utcnow()
            doc["updated_at"] = datetime.utcnow()
            doc["stato"] = "pagato"
            doc["sezione"] = "privati"

            existing = await db["f24_privati"].find_one({
                "codice_fiscale": cf,
                "scadenza": doc.get("scadenza"),
                "pagina": doc.get("pagina", 1),
            })
            if existing:
                await db["f24_privati"].update_one(
                    {"_id": existing["_id"]},
                    {"$set": {**doc, "updated_at": datetime.utcnow()}}
                )
                risultati.append({
                    "file": filename, "ok": True, "azione": "aggiornato",
                    "id": str(existing["_id"]),
                    "contribuente": doc.get("anagrafica", {}).get("nome", cf),
                    "scadenza": doc.get("scadenza"),
                    "saldo_finale": doc.get("saldo_finale"),
                })
            else:
                res = await db["f24_privati"].insert_one(doc)
                risultati.append({
                    "file": filename, "ok": True, "azione": "inserito",
                    "id": str(res.inserted_id),
                    "contribuente": doc.get("anagrafica", {}).get("nome", cf),
                    "scadenza": doc.get("scadenza"),
                    "saldo_finale": doc.get("saldo_finale"),
                })

    return {"risultati": risultati, "totale": len(risultati)}


@router.get("")
async def lista_f24_privati(
    cf: str = Query(None),
    anno: int = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    q = {}
    if cf:
        q["codice_fiscale"] = cf
    if anno:
        q["scadenza"] = {"$regex": f"^{anno}"}
    
    cursor = db["f24_privati"].find(q).sort("scadenza", -1)
    docs = []
    async for doc in cursor:
        docs.append(_oid(doc))
    return docs


@router.get("/soggetti")
async def lista_soggetti(db: AsyncIOMotorDatabase = Depends(get_database)):
    """Restituisce i CF distinti presenti in f24_privati con nome."""
    pipeline = [
        {"$group": {"_id": "$codice_fiscale", "n_f24": {"$sum": 1},
                    "totale": {"$sum": "$saldo_finale"},
                    "ultimo": {"$max": "$scadenza"},
                    "anagrafica": {"$first": "$anagrafica"}}},
        {"$sort": {"_id": 1}}
    ]
    result = []
    async for doc in db["f24_privati"].aggregate(pipeline):
        result.append({
            "cf": doc["_id"],
            "nome": doc.get("anagrafica", {}).get("nome", doc["_id"]),
            "n_f24": doc["n_f24"],
            "totale": doc["totale"],
            "ultimo": doc["ultimo"],
        })
    # Arricchisce con privati noti anche se non hanno ancora F24
    cf_presenti = {r["cf"] for r in result}
    for cf, info in PRIVATI_NOTI.items():
        if cf not in cf_presenti:
            result.append({
                "cf": cf, "nome": info["nome"],
                "n_f24": 0, "totale": 0, "ultimo": None,
            })
    return result


@router.get("/riepilogo/{cf}/{anno}")
async def riepilogo_privato(cf: str, anno: int, db: AsyncIOMotorDatabase = Depends(get_database)):
    pipeline = [
        {"$match": {"codice_fiscale": cf, "scadenza": {"$regex": f"^{anno}"}, "pagina": 1}},
        {"$group": {
            "_id": None,
            "totale_versato": {"$sum": "$saldo_finale"},
            "n_f24": {"$sum": 1},
            "scadenze": {"$push": {
                "scadenza": "$scadenza",
                "data_pagamento": "$data_pagamento",
                "saldo_finale": "$saldo_finale",
                "_id": {"$toString": "$_id"},
                "note_ravvedimento": "$note_ravvedimento",
            }}
        }}
    ]
    async for doc in db["f24_privati"].aggregate(pipeline):
        doc.pop("_id", None)
        doc["anagrafica"] = PRIVATI_NOTI.get(cf, {"nome": cf})
        return doc
    return {"totale_versato": 0, "n_f24": 0, "scadenze": [],
            "anagrafica": PRIVATI_NOTI.get(cf, {"nome": cf})}


@router.get("/{fid}")
async def get_f24_privato(fid: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    doc = await db["f24_privati"].find_one({"_id": ObjectId(fid)})
    if not doc:
        raise HTTPException(404, "F24 non trovato")
    return _oid(doc)


@router.get("/{fid}/pdf")
async def download_f24_privato_pdf(fid: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    doc = await db["f24_privati"].find_one({"_id": ObjectId(fid)})
    if not doc:
        raise HTTPException(404, "F24 non trovato")
    path = doc.get("pdf_path", "")
    if not path or not os.path.exists(path):
        raise HTTPException(404, "PDF non disponibile")
    nome = doc.get("anagrafica", {}).get("nome", "privato").replace(" ", "_")
    return FileResponse(path, media_type="application/pdf",
                        filename=f"F24_{nome}_{doc.get('scadenza','')}.pdf")
