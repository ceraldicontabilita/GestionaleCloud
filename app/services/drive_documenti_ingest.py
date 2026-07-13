"""
Ingest generico di documenti da cartelle Drive dedicate → hub `documents_inbox`.

Un solo motore per i nuovi canali documentali (scelta utente 12/07/2026):
dichiarazione IVA, cartelle esattoriali, avvisi bonari. Legge i PDF dalla
cartella Drive del canale, deduplica per impronta md5, li deposita in
`documents_inbox` con la `category` giusta e li sposta in `Elaborate`. Riusa
gli helper Drive collaudati di drive_cedolini_ingest (credenziali, service,
lista, download, spostamento).

Ogni canale si accende solo quando su Render sono valorizzati il folder id e
l'interruttore ENABLE_DRIVE_*_SYNC.
"""
import asyncio
import base64
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.config import settings
from app.constants.tipi_documento import set_tassonomia_documento
from app.services import drive_cedolini_ingest as _base

logger = logging.getLogger(__name__)

# Definizione dei canali: come risolvere folder id, interruttore e categoria.
CANALI: Dict[str, Dict[str, Any]] = {
    "dichiarazione_iva": {
        "category": "dichiarazione_iva",
        "label": "Dichiarazioni IVA",
        "folder": lambda s: s.GOOGLE_DRIVE_DICHIARAZIONI_IVA_FOLDER_ID or s.DRIVE_FOLDER_DICHIARAZIONI_IVA_ID,
        "enable": lambda s: s.ENABLE_DRIVE_DICHIARAZIONI_IVA_SYNC,
    },
    "cartella_esattoriale": {
        "category": "cartella_esattoriale",
        "label": "Cartelle Esattoriali",
        "folder": lambda s: s.GOOGLE_DRIVE_CARTELLE_ESATTORIALI_FOLDER_ID or s.DRIVE_FOLDER_CARTELLE_ESATTORIALI_ID,
        "enable": lambda s: s.ENABLE_DRIVE_CARTELLE_ESATTORIALI_SYNC,
    },
    "avviso_bonario": {
        "category": "avviso_bonario",
        "label": "Avvisi Bonari",
        "folder": lambda s: s.GOOGLE_DRIVE_AVVISI_BONARI_FOLDER_ID or s.DRIVE_FOLDER_AVVISI_BONARI_ID,
        "enable": lambda s: s.ENABLE_DRIVE_AVVISI_BONARI_SYNC,
    },
}

_locks: Dict[str, asyncio.Lock] = {c: asyncio.Lock() for c in CANALI}


def _folder_id(canale: str) -> Optional[str]:
    return CANALI[canale]["folder"](settings)


def is_enabled(canale: str) -> bool:
    return bool(CANALI[canale]["enable"](settings))


def is_configured(canale: str) -> bool:
    return bool(_folder_id(canale))


def _build_inbox_doc(content: bytes, filename: str, canale: str) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    conf = CANALI[canale]
    doc = {
        "id": __import__("uuid").uuid4().hex,
        "filename": filename,
        "pdf_data": base64.b64encode(content).decode(),
        "file_hash": hashlib.md5(content).hexdigest(),
        "size_bytes": len(content),
        "fonte": f"drive_{canale}",
        "source": f"drive_{canale}",
        "stato": "importato",
        "status": "nuovo",
        "processed": False,
        "xml_processed": True,  # già classificato: non passa dal routing email
        "created_at": now,
        "downloaded_at": now,
    }
    # Tassonomia canonica: tipo_documento + alias categoria/category coerenti (P2-3)
    return set_tassonomia_documento(doc, conf["category"], label=conf["label"])


async def sync(db, canale: str) -> Dict[str, Any]:
    """Un ciclo di import per il canale indicato."""
    if canale not in CANALI:
        return {"status": "error", "message": f"Canale sconosciuto: {canale}"}
    if not is_enabled(canale):
        return {"status": "disabled", "message": f"Canale {canale} spento"}
    if not is_configured(canale):
        return {"status": "not_configured",
                "message": f"Imposta la cartella Drive del canale {canale} su Render."}
    lock = _locks[canale]
    if lock.locked():
        return {"status": "running", "message": "Sincronizzazione già in corso"}
    async with lock:
        return await _do_sync(db, canale)


async def _do_sync(db, canale: str) -> Dict[str, Any]:
    creds, cred_err = _base._load_credentials_cedolini()
    if creds is None:
        return {"status": "error", "message": f"Credenziali Google Drive non valide: {cred_err}"}
    service = _base._build_drive_service()
    if service is None:
        return {"status": "error", "message": "Service Drive non disponibile."}

    parent_id = _folder_id(canale)
    result = {"status": "ok", "canale": canale, "total": 0, "imported": 0,
              "duplicates": 0, "errors": 0, "moved": 0, "details": []}
    try:
        elaborate_id = _base._get_or_create_elaborate_folder(service, parent_id)
        pdf_files = _base._list_pdf_files(service, parent_id)
        result["total"] = len(pdf_files)
        for f in pdf_files:
            fid, fname = f["id"], f["name"]
            try:
                content = _base._download_bytes(service, fid)
                if not content:
                    result["errors"] += 1
                    result["details"].append({"file": fname, "error": "file vuoto"})
                    continue
                content_hash = hashlib.md5(content).hexdigest()
                existing = await db["documents_inbox"].find_one(
                    {"file_hash": content_hash}, {"_id": 0, "id": 1}
                )
                if existing:
                    result["duplicates"] += 1
                else:
                    doc = _build_inbox_doc(content, fname, canale)
                    await db["documents_inbox"].insert_one(doc)
                    result["imported"] += 1
                    logger.info(f"Drive {canale}: importato {fname}")
                if elaborate_id:
                    _base._move_to_elaborate(service, fid, parent_id, elaborate_id)
                    result["moved"] += 1
            except Exception as e:
                logger.error(f"Drive {canale}: errore su {fname}: {e}")
                result["errors"] += 1
                result["details"].append({"file": fname, "error": str(e)})
    except Exception as e:
        logger.error(f"Drive {canale}: errore ciclo: {e}")
        return {"status": "error", "canale": canale, "message": str(e)}
    return result


async def sync_tutti(db) -> Dict[str, Any]:
    """Esegue l'ingest di tutti i canali abilitati e configurati."""
    esiti = {}
    for canale in CANALI:
        if is_enabled(canale) and is_configured(canale):
            esiti[canale] = await sync(db, canale)
    return {"status": "ok", "canali": esiti}
