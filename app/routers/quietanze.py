"""
Router Quietanze — Ceraldi ERP
PREFIX: /api/quietanze

Le quietanze sono le RICEVUTE UFFICIALI dei pagamenti F24 telematici.
Contengono il Protocollo Telematico = prova legale del pagamento.

Collection MongoDB: quietanze

Endpoints:
  POST /api/quietanze/upload-pdf   → import batch PDF quietanze
  GET  /api/quietanze               → lista con filtri (anno, mese)
  GET  /api/quietanze/{id}          → singola quietanza
  GET  /api/quietanze/{id}/pdf      → PDF originale
  POST /api/quietanze/riconcilia-f24 → associa quietanza a F24
  GET  /api/quietanze/non-riconciliate → quietanze senza F24 corrispondente
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from datetime import datetime
import os, re

from app.database import get_database

router = APIRouter(prefix="/api/quietanze", tags=["Quietanze"])

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "quietanze")
os.makedirs(UPLOAD_DIR, exist_ok=True)

AZIENDA_ID = "b0295759-35ce-4b34-a6b4-f01b883234ad"


def _oid(doc):
    if "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


@router.post("/upload-pdf")
async def upload_quietanza(
    files: list[UploadFile] = File(...),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    from app.parsers.quietanza_parser import parse_quietanza_pdf

    risultati = []
    for upload in files:
        pdf_bytes = await upload.read()
        filename = upload.filename or "quietanza.pdf"

        safe_name = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", filename)
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        dest = os.path.join(UPLOAD_DIR, f"{ts}_{safe_name}")
        with open(dest, "wb") as f:
            f.write(pdf_bytes)

        try:
            doc = parse_quietanza_pdf(pdf_bytes, filename)
        except Exception as e:
            risultati.append({"file": filename, "ok": False, "errore": str(e)})
            continue

        if not doc:
            risultati.append({"file": filename, "ok": False, "errore": "Non è una quietanza ADE valida"})
            continue

        doc["azienda_id"] = AZIENDA_ID
        doc["pdf_path"] = dest
        doc["created_at"] = datetime.utcnow()

        # Upsert su protocollo telematico (chiave univoca ADE)
        proto = doc.get("protocollo_telematico")
        if proto:
            existing = await db["quietanze"].find_one({"protocollo_telematico": proto})
        else:
            existing = None

        if existing:
            await db["quietanze"].update_one(
                {"_id": existing["_id"]},
                {"$set": {**doc, "updated_at": datetime.utcnow()}}
            )
            risultati.append({
                "file": filename, "ok": True, "azione": "aggiornata",
                "id": str(existing["_id"]),
                "protocollo": proto,
                "data_versamento": doc.get("data_versamento"),
                "saldo_finale": doc.get("saldo_finale"),
            })
        else:
            res = await db["quietanze"].insert_one(doc)
            # Tenta riconciliazione automatica con F24
            ric = await _auto_riconcilia(db, str(res.inserted_id), doc)
            risultati.append({
                "file": filename, "ok": True, "azione": "inserita",
                "id": str(res.inserted_id),
                "protocollo": proto,
                "data_versamento": doc.get("data_versamento"),
                "saldo_finale": doc.get("saldo_finale"),
                "riconciliazione_auto": ric,
            })

    return {"risultati": risultati, "totale": len(risultati)}


async def _auto_riconcilia(db, quietanza_id: str, doc: dict) -> dict:
    """
    Tenta di riconciliare automaticamente la quietanza con un F24.
    Logica: cerca F24 con stesso saldo_finale e data_pagamento vicina.
    """
    saldo = doc.get("saldo_finale", 0)
    data_v = doc.get("data_versamento", "")

    if not saldo:
        return {"ok": False, "motivo": "Saldo non disponibile"}

    # Cerca F24 non scartato con stesso saldo (tolleranza 0.05€)
    f24s = await db["f24"].find({
        "azienda_id": AZIENDA_ID,
        "stato": {"$ne": "scartato"},
        "saldo_finale": {"$gte": saldo - 0.05, "$lte": saldo + 0.05},
        "riconciliazione_quietanza": {"$exists": False},
    }).sort("scadenza", 1).to_list(10)

    if not f24s:
        return {"ok": False, "motivo": f"Nessun F24 con saldo €{saldo} trovato"}

    # Preferisce quello con data pagamento più vicina
    best = f24s[0]
    for f in f24s:
        if f.get("data_pagamento", "") == data_v:
            best = f
            break

    # Aggiorna F24 con riferimento alla quietanza
    await db["f24"].update_one(
        {"_id": best["_id"]},
        {"$set": {
            "stato": "riconciliato",
            "riconciliazione_quietanza": {
                "quietanza_id": quietanza_id,
                "protocollo_telematico": doc.get("protocollo_telematico"),
                "data_versamento": data_v,
                "saldo_quietanza": saldo,
                "riconciliato_il": datetime.utcnow(),
            },
            "updated_at": datetime.utcnow(),
        }}
    )
    # Aggiorna quietanza con riferimento al F24
    await db["quietanze"].update_one(
        {"_id": ObjectId(quietanza_id)},
        {"$set": {"f24_id": str(best["_id"]), "f24_scadenza": best.get("scadenza")}}
    )

    return {
        "ok": True,
        "f24_id": str(best["_id"]),
        "f24_scadenza": best.get("scadenza"),
        "delta": round(abs(saldo - best.get("saldo_finale", 0)), 2),
    }


@router.get("")
async def lista_quietanze(
    anno: int = None,
    mese: int = None,
    solo_non_riconciliate: bool = False,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    q = {"azienda_id": AZIENDA_ID}
    if anno:
        q["data_versamento"] = {"$regex": f"^{anno}"}
    if solo_non_riconciliate:
        q["f24_id"] = {"$exists": False}

    cursor = db["quietanze"].find(q).sort("data_versamento", -1)
    docs = []
    async for doc in cursor:
        docs.append(_oid(doc))
    return docs


@router.get("/non-riconciliate")
async def quietanze_non_riconciliate(db: AsyncIOMotorDatabase = Depends(get_database)):
    cursor = db["quietanze"].find({
        "azienda_id": AZIENDA_ID,
        "f24_id": {"$exists": False}
    }).sort("data_versamento", -1)
    docs = []
    async for doc in cursor:
        docs.append(_oid(doc))
    return {"totale": len(docs), "quietanze": docs}


@router.get("/{qid}")
async def get_quietanza(qid: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    doc = await db["quietanze"].find_one({"_id": ObjectId(qid)})
    if not doc:
        raise HTTPException(404, "Quietanza non trovata")
    return _oid(doc)


@router.get("/{qid}/pdf")
async def download_quietanza_pdf(qid: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    doc = await db["quietanze"].find_one({"_id": ObjectId(qid)})
    if not doc:
        raise HTTPException(404, "Quietanza non trovata")
    path = doc.get("pdf_path", "")
    if not path or not os.path.exists(path):
        raise HTTPException(404, "PDF non disponibile")
    proto = doc.get("protocollo_telematico", "quietanza")
    return FileResponse(path, media_type="application/pdf",
                        filename=f"Quietanza_{proto}.pdf")


@router.post("/riconcilia-f24")
async def riconcilia_manuale(body: dict, db: AsyncIOMotorDatabase = Depends(get_database)):
    """Associa manualmente una quietanza a un F24."""
    qid = body.get("quietanza_id")
    fid = body.get("f24_id")

    q_doc = await db["quietanze"].find_one({"_id": ObjectId(qid)})
    f_doc = await db["f24"].find_one({"_id": ObjectId(fid)})

    if not q_doc or not f_doc:
        raise HTTPException(404, "Quietanza o F24 non trovati")

    delta = round(abs((q_doc.get("saldo_finale", 0) - f_doc.get("saldo_finale", 0))), 2)

    await db["f24"].update_one(
        {"_id": ObjectId(fid)},
        {"$set": {
            "stato": "riconciliato",
            "riconciliazione_quietanza": {
                "quietanza_id": qid,
                "protocollo_telematico": q_doc.get("protocollo_telematico"),
                "data_versamento": q_doc.get("data_versamento"),
                "saldo_quietanza": q_doc.get("saldo_finale"),
                "riconciliato_il": datetime.utcnow(),
                "manuale": True,
            },
            "updated_at": datetime.utcnow(),
        }}
    )
    await db["quietanze"].update_one(
        {"_id": ObjectId(qid)},
        {"$set": {"f24_id": fid, "f24_scadenza": f_doc.get("scadenza")}}
    )

    return {
        "ok": True,
        "delta": delta,
        "messaggio": f"Quietanza riconciliata con F24 scadenza {f_doc.get('scadenza')}",
        "attenzione": f"Delta importo: €{delta}" if delta > 0.10 else None,
    }
