"""
Dipendenti router — CRUD + Pignoramenti
Collection: dipendenti (MAI "dipendenti")
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from datetime import datetime, date
from typing import Optional, List
import re
import logging
import os
import uuid

from app.database import get_database

router = APIRouter()
logger = logging.getLogger(__name__)

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "pignoramenti")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def oid(doc):
    """Convert ObjectId to string in a document."""
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


# ─── DIPENDENTI CRUD ───────────────────────────────────────

@router.get("")
async def lista_dipendenti(stato: Optional[str] = None, db: AsyncIOMotorDatabase = Depends(get_database)):
    filtro = {}
    if stato:
        filtro["stato"] = stato
    cursor = db["dipendenti"].find(filtro).sort("cognome", 1)
    result = []
    async for doc in cursor:
        result.append(oid(doc))
    return result


@router.get("/{dip_id}")
async def get_dipendente(dip_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    doc = await db["dipendenti"].find_one({"_id": ObjectId(dip_id)})
    if not doc:
        raise HTTPException(404, "Dipendente non trovato")
    return oid(doc)


@router.post("")
async def crea_dipendente(data: dict, db: AsyncIOMotorDatabase = Depends(get_database)):
    data.setdefault("stato", "attivo")
    data.setdefault("pignoramenti", [])
    data["created_at"] = datetime.utcnow()
    data["updated_at"] = datetime.utcnow()
    result = await db["dipendenti"].insert_one(data)
    return {"_id": str(result.inserted_id), "ok": True}


@router.put("/{dip_id}")
async def aggiorna_dipendente(dip_id: str, data: dict, db: AsyncIOMotorDatabase = Depends(get_database)):
    data["updated_at"] = datetime.utcnow()
    result = await db["dipendenti"].update_one({"_id": ObjectId(dip_id)}, {"$set": data})
    if result.matched_count == 0:
        raise HTTPException(404, "Dipendente non trovato")
    return {"ok": True, "modified": result.modified_count}


# ─── PIGNORAMENTI ──────────────────────────────────────────

@router.get("/{dip_id}/pignoramenti")
async def lista_pignoramenti(dip_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    doc = await db["dipendenti"].find_one({"_id": ObjectId(dip_id)}, {"pignoramenti": 1})
    if not doc:
        raise HTTPException(404, "Dipendente non trovato")
    return doc.get("pignoramenti", [])


@router.post("/{dip_id}/pignoramenti")
async def aggiungi_pignoramento(dip_id: str, data: dict, db: AsyncIOMotorDatabase = Depends(get_database)):
    data["id"] = str(uuid.uuid4())[:8]
    data.setdefault("stato", "ricevuto")
    data["created_at"] = datetime.utcnow().isoformat()

    result = await db["dipendenti"].update_one(
        {"_id": ObjectId(dip_id)},
        {"$push": {"pignoramenti": data}}
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Dipendente non trovato")
    return {"ok": True, "pignoramento_id": data["id"]}


@router.put("/{dip_id}/pignoramenti/{pig_id}/stato")
async def aggiorna_stato_pignoramento(
    dip_id: str, pig_id: str, data: dict,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    nuovo_stato = data.get("stato")
    if nuovo_stato not in ("ricevuto", "dichiarazione_generata", "dichiarazione_inviata", "in_trattenuta", "estinto", "cessato_rapporto"):
        raise HTTPException(400, "Stato non valido")

    result = await db["dipendenti"].update_one(
        {"_id": ObjectId(dip_id), "pignoramenti.id": pig_id},
        {"$set": {"pignoramenti.$.stato": nuovo_stato, "updated_at": datetime.utcnow()}}
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Pignoramento non trovato")
    return {"ok": True}


# ─── UPLOAD PDF PIGNORAMENTO + PARSING ─────────────────────

@router.post("/upload-pignoramento")
async def upload_pignoramento(file: UploadFile = File(...), db: AsyncIOMotorDatabase = Depends(get_database)):
    """Upload PDF pignoramento, parse C.F. debitore, match con dipendente."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Solo file PDF accettati")

    content = await file.read()
    filename = f"{uuid.uuid4().hex[:12]}_{file.filename}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(content)

    # Parse PDF per estrarre dati
    parsed = await _parse_pignoramento_pdf(filepath)
    if not parsed.get("debitore_cf"):
        return {"ok": False, "error": "C.F. debitore non trovato nel PDF", "file": filename}

    # Match con dipendente
    dip = await db["dipendenti"].find_one({"codice_fiscale": parsed["debitore_cf"]})
    if not dip:
        return {
            "ok": False,
            "error": f"Nessun dipendente con C.F. {parsed['debitore_cf']}",
            "parsed": parsed,
            "file": filename
        }

    # Crea record pignoramento
    pig = {
        "id": str(uuid.uuid4())[:8],
        "numero_documento": parsed.get("numero_documento", ""),
        "data_documento": parsed.get("data_documento", ""),
        "ente_creditore": parsed.get("ente_creditore", "municipia"),
        "debitore_nome": parsed.get("debitore_nome", ""),
        "debitore_cf": parsed["debitore_cf"],
        "importo": parsed.get("importo", 0),
        "targa": parsed.get("targa", ""),
        "anno_riferimento": parsed.get("anno_riferimento", ""),
        "pec_destinazione": parsed.get("pec_destinazione", "rcrc-affarilegali@pec.it"),
        "pdf_originale": filename,
        "stato": "cessato_rapporto" if dip.get("stato") == "cessato" else "ricevuto",
        "created_at": datetime.utcnow().isoformat(),
    }

    await db["dipendenti"].update_one(
        {"_id": dip["_id"]},
        {"$push": {"pignoramenti": pig}}
    )

    return {
        "ok": True,
        "dipendente": f"{dip.get('cognome', '')} {dip.get('nome', '')}",
        "dipendente_id": str(dip["_id"]),
        "stato_dipendente": dip.get("stato", "attivo"),
        "pignoramento": pig,
        "message": "Dipendente cessato — genera Dichiarazione Stragiudiziale" if dip.get("stato") == "cessato" else "Pignoramento associato"
    }


async def _parse_pignoramento_pdf(filepath: str) -> dict:
    """Estrae dati chiave da PDF pignoramento."""
    import pdfplumber
    text = ""
    try:
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages[:4]:
                text += (page.extract_text() or "") + "\n"
    except Exception as e:
        logger.error(f"Errore parsing PDF: {e}")
        return {}

    result = {}

    # C.F. debitore (pattern: C.F./P.I XXXYYY...)
    cf_match = re.search(r'C\.F\./P\.I\s+([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])', text)
    if cf_match:
        result["debitore_cf"] = cf_match.group(1)

    # Nome debitore
    nome_match = re.search(r'nei confronti di\s+([A-Z\'\s]+?),?\s+C\.F', text)
    if nome_match:
        result["debitore_nome"] = nome_match.group(1).strip()

    # Numero documento
    doc_match = re.search(r'(\d{20,30})\s+\d{2}/\d{2}/\d{4}', text)
    if doc_match:
        result["numero_documento"] = doc_match.group(1)

    # Data documento
    data_match = re.search(r'\d{20,30}\s+(\d{2}/\d{2}/\d{4})', text)
    if data_match:
        result["data_documento"] = data_match.group(1)

    # Importo totale
    importo_match = re.search(r'TOTALE DA PAGARE\s*€?\s*([\d.,]+)', text)
    if importo_match:
        result["importo"] = float(importo_match.group(1).replace(".", "").replace(",", "."))

    # Targa
    targa_match = re.search(r'Targa\s*:\s*([A-Z]{2}\d{3}[A-Z]{2})', text)
    if targa_match:
        result["targa"] = targa_match.group(1)

    # Anno riferimento
    anno_match = re.search(r'Anno\s*:\s*(\d{4})', text)
    if anno_match:
        result["anno_riferimento"] = anno_match.group(1)

    # Ente
    if "MUNICIPIA" in text.upper():
        result["ente_creditore"] = "municipia"
        result["pec_destinazione"] = "rcrc-affarilegali@pec.it"
    elif "AGENZIA DELLE ENTRATE" in text.upper():
        result["ente_creditore"] = "ader"
    elif "INPS" in text.upper():
        result["ente_creditore"] = "inps"

    return result


# ─── GENERA DICHIARAZIONE STRAGIUDIZIALE ───────────────────

@router.post("/{dip_id}/pignoramenti/{pig_id}/genera-dichiarazione")
async def genera_dichiarazione(dip_id: str, pig_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    """Genera PDF Dichiarazione Stragiudiziale di Terzo per dipendente cessato."""
    dip = await db["dipendenti"].find_one({"_id": ObjectId(dip_id)})
    if not dip:
        raise HTTPException(404, "Dipendente non trovato")

    pig = None
    for p in dip.get("pignoramenti", []):
        if p.get("id") == pig_id:
            pig = p
            break
    if not pig:
        raise HTTPException(404, "Pignoramento non trovato")

    # Genera PDF
    from app.services.dichiarazione_generator import genera_pdf_dichiarazione
    filename = f"Dichiarazione_{pig.get('debitore_cf', 'XX')}_{pig.get('numero_documento', 'XX')}.pdf"
    filepath = os.path.join(UPLOAD_DIR, filename)

    genera_pdf_dichiarazione(filepath, dip, pig)

    # Aggiorna stato
    await db["dipendenti"].update_one(
        {"_id": ObjectId(dip_id), "pignoramenti.id": pig_id},
        {"$set": {
            "pignoramenti.$.stato": "dichiarazione_generata",
            "pignoramenti.$.dichiarazione_pdf_path": filename,
        }}
    )

    return {"ok": True, "file": filename, "download": f"/api/dipendenti/download/{filename}"}


@router.get("/download/{filename}")
async def download_file(filename: str):
    from fastapi.responses import FileResponse
    filepath = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(404, "File non trovato")
    return FileResponse(filepath, filename=filename, media_type="application/pdf")
