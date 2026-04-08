"""
Fatture Passive — Upload XML manuale + Sync automatica PEC SDI.
Collection: fatture_passive
Prefix: /api/fatture
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends, BackgroundTasks
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from datetime import datetime
from typing import Optional
import logging

from app.database import get_database
from app.parsers.fattura_xml import parse_fattura_xml
from app.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


def _oid(doc):
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


async def _import_xml_bytes(
    xml_bytes: bytes,
    filename: str,
    db: AsyncIOMotorDatabase,
    source: str = "upload",
    message_id: str = "",
) -> dict:
    """
    Logica condivisa tra upload manuale e sync PEC.
    Ritorna: {inserite, duplicate, totale_file, fatture[]}
    """
    try:
        # Prova UTF-8, poi latin-1 per P7M/vecchi file
        for enc in ("utf-8", "latin-1", "cp1252"):
            try:
                xml_str = xml_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            return {"errore": "Encoding XML non riconosciuto", "inserite": 0, "duplicate": 0}

        fatture = parse_fattura_xml(xml_str)
    except Exception as e:
        return {"errore": f"Errore parsing XML: {e}", "inserite": 0, "duplicate": 0}

    if not fatture:
        return {"errore": "Nessuna fattura nel file", "inserite": 0, "duplicate": 0}

    inserite, duplicate = 0, 0
    for f in fatture:
        if await db["fatture_passive"].find_one({"dedup_key": f["dedup_key"]}):
            duplicate += 1
            continue

        doc = {
            "fornitore_denominazione": f["cedente"].get("denominazione", ""),
            "fornitore_piva": f["cedente"].get("partita_iva", ""),
            "numero": f["numero"],
            "data": f["data"],
            "anno": int(f["data"][:4]) if f["data"] and len(f["data"]) >= 4 else 0,
            "tipo_documento": f["tipo_documento"],
            "importo_totale": f["importo_totale"],
            "imponibile": f["imponibile"],
            "iva": f["iva"],
            "causale": f["causale"],
            "linee": f["linee"],
            "riepilogo_iva": f["riepilogo_iva"],
            "pagamenti": f["pagamenti"],
            "dedup_key": f["dedup_key"],
            "stato": "da_confermare",
            "source": source,  # "upload" | "pec_auto"
            "xml_filename": filename,
            "pec_message_id": message_id,
            "created_at": datetime.utcnow(),
        }
        await db["fatture_passive"].insert_one(doc)
        inserite += 1

        if f["cedente"].get("partita_iva"):
            await db["fornitori"].update_one(
                {"partita_iva": f["cedente"]["partita_iva"]},
                {"$set": {
                    "denominazione": f["cedente"]["denominazione"],
                    "partita_iva": f["cedente"]["partita_iva"],
                    "updated_at": datetime.utcnow(),
                },
                 "$setOnInsert": {"created_at": datetime.utcnow()}},
                upsert=True,
            )

    return {
        "inserite": inserite,
        "duplicate": duplicate,
        "totale_file": len(fatture),
    }


# ── LISTA / STATS ──────────────────────────────────────────────────────────

@router.get("")
async def lista_fatture(
    anno: Optional[int] = None,
    fornitore: Optional[str] = None,
    source: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    filtro = {}
    if anno:
        filtro["anno"] = anno
    if fornitore:
        filtro["$or"] = [
            {"fornitore_denominazione": {"$regex": fornitore, "$options": "i"}},
            {"fornitore_piva": fornitore},
        ]
    if source:
        filtro["source"] = source
    cursor = db["fatture_passive"].find(filtro).sort("data", -1).skip(skip).limit(limit)
    result = [_oid(doc) async for doc in cursor]
    totale = await db["fatture_passive"].count_documents(filtro)
    return {"items": result, "totale": totale}


@router.get("/stats")
async def stats_fatture(anno: int = 2026, db: AsyncIOMotorDatabase = Depends(get_database)):
    pipeline = [
        {"$match": {"anno": anno}},
        {"$group": {
            "_id": None,
            "imponibile": {"$sum": "$imponibile"},
            "iva": {"$sum": "$iva"},
            "totale": {"$sum": "$importo_totale"},
            "count": {"$sum": 1},
            "da_pec": {"$sum": {"$cond": [{"$eq": ["$source", "pec_auto"]}, 1, 0]}},
        }}
    ]
    agg = await db["fatture_passive"].aggregate(pipeline).to_list(1)
    return agg[0] if agg else {"imponibile": 0, "iva": 0, "totale": 0, "count": 0, "da_pec": 0}


# ── UPLOAD MANUALE ─────────────────────────────────────────────────────────

@router.post("/upload-xml")
async def upload_fattura_xml(
    file: UploadFile = File(...),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    content = await file.read()
    result = await _import_xml_bytes(
        xml_bytes=content,
        filename=file.filename,
        db=db,
        source="upload",
    )
    if result.get("errore"):
        raise HTTPException(400, result["errore"])
    return {"ok": True, **result}


# ── SYNC AUTOMATICA PEC SDI ────────────────────────────────────────────────

@router.post("/sync-pec")
async def sync_fatture_pec(
    db: AsyncIOMotorDatabase = Depends(get_database),
    dry_run: bool = False,
):
    """
    Scarica fatture XML non lette dalla PEC Aruba (mittente SDI).
    dry_run=true → mostra cosa verrebbe importato senza salvare.
    """
    # Credenziali PEC da variabili d'ambiente
    host = "imaps.pec.aruba.it"
    port = 993
    user = "fatturazioneceraldi@pec.it"
    password = "L)9*kd5+78]?%LmF"

    if not password:
        raise HTTPException(500, "Credenziali PEC non configurate nel .env")

    from app.services.pec_fatture_service import fetch_fatture_from_pec

    try:
        email_items = await fetch_fatture_from_pec(
            host=host,
            port=port,
            user=user,
            password=password,
            mark_seen=not dry_run,
        )
    except Exception as e:
        logger.error(f"Errore connessione PEC: {e}")
        raise HTTPException(503, f"Errore connessione PEC: {e}")

    if not email_items:
        return {
            "ok": True,
            "email_processate": 0,
            "inserite": 0,
            "duplicate": 0,
            "messaggi": [],
        }

    totale_inserite = 0
    totale_duplicate = 0
    log_messaggi = []

    for item in email_items:
        if dry_run:
            log_messaggi.append({
                "filename": item["filename"],
                "from": item["from"],
                "subject": item["subject"][:80],
                "date": item["date"],
                "stato": "dry_run",
            })
            continue

        result = await _import_xml_bytes(
            xml_bytes=item["xml_bytes"],
            filename=item["filename"],
            db=db,
            source="pec_auto",
            message_id=item.get("message_id", ""),
        )

        totale_inserite += result.get("inserite", 0)
        totale_duplicate += result.get("duplicate", 0)

        log_messaggi.append({
            "filename": item["filename"],
            "from": item["from"],
            "subject": item["subject"][:80],
            "date": item["date"],
            "inserite": result.get("inserite", 0),
            "duplicate": result.get("duplicate", 0),
            "errore": result.get("errore"),
        })

    # Salva log sync in DB
    if not dry_run:
        await db["sync_log"].insert_one({
            "tipo": "pec_fatture",
            "timestamp": datetime.utcnow(),
            "email_processate": len(email_items),
            "inserite": totale_inserite,
            "duplicate": totale_duplicate,
            "dettagli": log_messaggi,
        })

    return {
        "ok": True,
        "email_processate": len(email_items),
        "inserite": totale_inserite,
        "duplicate": totale_duplicate,
        "messaggi": log_messaggi,
    }


@router.get("/sync-log")
async def get_sync_log(
    limit: int = 20,
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Storico delle sincronizzazioni PEC."""
    cursor = db["sync_log"].find({"tipo": "pec_fatture"}).sort("timestamp", -1).limit(limit)
    items = [_oid(doc) async for doc in cursor]
    return {"items": items}


# ── DETTAGLIO FATTURA ──────────────────────────────────────────────────────

@router.get("/{fatt_id}")
async def get_fattura(fatt_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    doc = await db["fatture_passive"].find_one({"_id": ObjectId(fatt_id)})
    if not doc:
        raise HTTPException(404, "Fattura non trovata")
    return _oid(doc)
