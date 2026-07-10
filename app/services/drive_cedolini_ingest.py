"""
Ingest cedolini paga (PDF) da Google Drive.

Legge i file `.pdf` da una cartella Drive configurata, li deduplica per hash
md5 contro `documents_inbox` (stesso campo `file_hash` dei cedolini email) e
li inserisce in `documents_inbox` nello STESSO formato dei cedolini arrivati
via email: da lì la pipeline esistente (`processa_nuovi_documenti` ->
parser cedolini -> prima nota salari -> verifica trattenute) li lavora
senza modifiche. I file elaborati (importati o duplicati noti) vengono
spostati nella sottocartella Drive `Elaborate` (creata se manca).

Configurazione (env / settings):
  GOOGLE_DRIVE_CEDOLINI_FOLDER_ID : id della cartella Drive dei cedolini
  GOOGLE_DRIVE_SA_FILE            : path al JSON del service account, oppure
  GOOGLE_DRIVE_SA_JSON            : il JSON del service account inline

Se non configurato, `get_status` lo segnala e `sync` è un no-op.
Lo stato dell'ultimo sync è salvato in `sistema_stato` (chiave dedicata).

Il client Drive e gli helper (credenziali, cartella Elaborate, download,
spostamento) sono RIUSATI da `drive_invoice_ingest`: stessa logica, nessuna
duplicazione.
"""
import asyncio
import base64
import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from app.config import settings
# Riuso degli helper del modulo fatture Drive (stesso service account,
# stessa gestione Elaborate): sono funzioni parametrizzate sul folder id,
# quindi utilizzabili così come sono senza toccare quel modulo.
from app.services.drive_invoice_ingest import (
    _load_credentials,
    _get_or_create_elaborate_folder,
    _download_bytes,
    _move_to_elaborate,
)

logger = logging.getLogger(__name__)

# Stato sync in sistema_stato (chiave dedicata, pattern aruba_notifiche)
_STATO_KEY = "drive_cedolini_last_sync"

# Un solo sync alla volta (manuale + job orario non devono sovrapporsi).
_sync_lock = asyncio.Lock()
_bg_task: Optional[asyncio.Task] = None


def is_sync_running() -> bool:
    return _sync_lock.locked()


def start_background_sync(db) -> bool:
    """Avvia un sync in background. Ritorna False se ce n'è già uno in corso."""
    global _bg_task
    if _sync_lock.locked():
        return False
    _bg_task = asyncio.create_task(sync(db))
    return True


def is_configured() -> bool:
    return bool(
        settings.GOOGLE_DRIVE_CEDOLINI_FOLDER_ID
        and (settings.GOOGLE_DRIVE_SA_FILE or settings.GOOGLE_DRIVE_SA_JSON)
    )


def is_cedolino_filename(name: str) -> bool:
    """Classificazione pura: nella cartella cedolini si lavorano solo i PDF."""
    return bool(name) and name.lower().endswith(".pdf")


def build_inbox_doc(content: bytes, filename: str) -> Dict[str, Any]:
    """Costruisce il documento `documents_inbox` nel formato dei cedolini email.

    Campi chiave per la pipeline esistente (vedi email_monitor_service):
      - category 'busta_paga' + processed False + pdf_data base64: è ESATTAMENTE
        la query di `processa_nuovi_documenti` (parser cedolini -> prima nota)
      - file_hash md5: stesso campo usato per la dedup dei cedolini email
      - tipo_documento/categoria 'cedolino': come impostato dal routing Gmail
    """
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(uuid.uuid4()),
        "filename": filename,
        "pdf_data": base64.b64encode(content).decode(),
        "file_hash": hashlib.md5(content).hexdigest(),
        "size_bytes": len(content),
        "category": "busta_paga",       # campo letto da processa_nuovi_documenti
        "category_label": "Buste Paga",
        "tipo_documento": "cedolino",
        "categoria": "cedolino",
        "fonte": "drive_cedolini",
        "stato": "importato",
        "status": "nuovo",
        "processed": False,
        "processed_to": None,
        # già classificato: non deve passare dal routing mittenti email
        "xml_processed": True,
        "created_at": now,
        "downloaded_at": now,
    }


def _build_drive_service():
    """Client Drive v3 da service account. None se non disponibile.

    Non riusa `drive_invoice_ingest._build_drive_service` perché quello
    verifica la configurazione della cartella FATTURE: qui serve lo stesso
    client ma con il check sulla cartella cedolini.
    """
    if not is_configured():
        return None
    creds, err = _load_credentials()
    if creds is None:
        logger.error(f"Drive cedolini: {err}")
        return None
    try:
        from googleapiclient.discovery import build
        return build("drive", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:
        logger.error(f"Drive cedolini: errore costruzione service: {e}")
        return None


def _list_pdf_files(service, parent_id: str) -> List[Dict[str, Any]]:
    q = (
        f"'{parent_id}' in parents and trashed = false "
        "and (name contains '.pdf' or name contains '.PDF')"
    )
    out: List[Dict[str, Any]] = []
    page_token = None
    while True:
        res = service.files().list(
            q=q, fields="nextPageToken, files(id, name, mimeType)",
            pageSize=100, pageToken=page_token,
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute()
        for f in res.get("files", []):
            if f.get("mimeType") == "application/vnd.google-apps.folder":
                continue
            if is_cedolino_filename(f["name"]):
                out.append(f)
        page_token = res.get("nextPageToken")
        if not page_token:
            break
    return out


async def get_status(db) -> Dict[str, Any]:
    state = await db["sistema_stato"].find_one({"chiave": _STATO_KEY}, {"_id": 0}) or {}
    credenziali_errore = None
    if is_configured():
        _, credenziali_errore = _load_credentials()
    return {
        "configured": is_configured(),
        "credenziali_ok": is_configured() and credenziali_errore is None,
        "credenziali_errore": credenziali_errore,
        "folder_id": settings.GOOGLE_DRIVE_CEDOLINI_FOLDER_ID,
        "sync_running": is_sync_running(),
        "last_sync": state.get("valore"),
        "last_result": state.get("last_result"),
        "last_error": state.get("last_error"),
        "total_imported": state.get("total_imported", 0),
    }


async def sync(db) -> Dict[str, Any]:
    """Esegue un ciclo di import. Se un sync è già in corso, non fa nulla."""
    if _sync_lock.locked():
        return {"status": "running", "message": "Sincronizzazione già in corso"}
    async with _sync_lock:
        return await _do_sync(db)


async def _do_sync(db) -> Dict[str, Any]:
    if not is_configured():
        return {
            "status": "not_configured",
            "message": "Imposta GOOGLE_DRIVE_CEDOLINI_FOLDER_ID e il service account "
                       "(GOOGLE_DRIVE_SA_FILE o GOOGLE_DRIVE_SA_JSON).",
        }
    creds, cred_err = _load_credentials()
    if creds is None:
        return {"status": "error", "message": f"Credenziali Google Drive non valide: {cred_err}"}
    service = _build_drive_service()
    if service is None:
        return {"status": "error", "message": "Service Drive non disponibile (errore costruzione client)."}

    parent_id = settings.GOOGLE_DRIVE_CEDOLINI_FOLDER_ID
    result = {
        "status": "ok", "total": 0, "imported": 0, "duplicates": 0,
        "errors": 0, "moved": 0, "details": [],
    }
    try:
        elaborate_id = _get_or_create_elaborate_folder(service, parent_id)
        pdf_files = _list_pdf_files(service, parent_id)
        result["total"] = len(pdf_files)
        for f in pdf_files:
            fid, fname = f["id"], f["name"]
            try:
                content = _download_bytes(service, fid)
                if not content:
                    result["errors"] += 1
                    result["details"].append({"file": fname, "error": "file vuoto"})
                    continue  # non spostare: resta per il retry
                content_hash = hashlib.md5(content).hexdigest()
                existing = await db["documents_inbox"].find_one(
                    {"file_hash": content_hash}, {"_id": 0, "id": 1}
                )
                if existing:
                    result["duplicates"] += 1
                else:
                    doc = build_inbox_doc(content, fname)
                    await db["documents_inbox"].insert_one(doc)
                    result["imported"] += 1
                    logger.info(f"Drive cedolini: importato {fname}")
                    # Evento documento acquisito (stesso pattern del monitor email)
                    try:
                        from app.services.event_bus import propagate_event, EventTypes
                        await propagate_event(EventTypes.DOCUMENTO_ACQUISITO, {
                            "documento_id": doc["id"],
                            "filename": fname,
                            "origine": "drive_cedolini",
                            "mime_type": "application/pdf",
                            "hash_file": doc["file_hash"],
                            "category": "busta_paga",
                        }, db, source_module="drive_cedolini_ingest")
                    except Exception:
                        logger.exception("Drive cedolini: errore propagazione evento documento.acquisito")
                # Sposta in `Elaborate` i file processati (importati o duplicati noti).
                if elaborate_id:
                    _move_to_elaborate(service, fid, parent_id, elaborate_id)
                    result["moved"] += 1
            except Exception as e:
                logger.error(f"Drive cedolini: errore su {fname}: {e}")
                result["errors"] += 1
                result["details"].append({"file": fname, "error": str(e)})
    except Exception as e:
        logger.error(f"Drive cedolini: errore sync: {e}")
        # Persisti l'errore globale: il sync gira in background e lo stato
        # si legge da /drive/status, non dalla risposta HTTP.
        now = datetime.now(timezone.utc).isoformat()
        await db["sistema_stato"].update_one(
            {"chiave": _STATO_KEY},
            {"$set": {"valore": now, "last_error": str(e), "updated_at": now}},
            upsert=True,
        )
        return {"status": "error", "message": str(e)}

    # Aggancia SUBITO la pipeline esistente dei cedolini (la stessa che lavora
    # quelli arrivati via email): parser PDF -> anagrafiche -> riepilogo ->
    # prima nota salari. Senza questa chiamata i documenti resterebbero in
    # attesa del prossimo giro del monitor email (comunque idempotente).
    if result["imported"] > 0:
        try:
            from app.services.email_monitor_service import processa_nuovi_documenti
            proc = await processa_nuovi_documenti(db)
            result["cedolini_processati"] = proc.get("buste_paga", 0)
        except Exception as e:
            logger.error(f"Drive cedolini: errore pipeline processamento: {e}")
            result["details"].append({"pipeline": str(e)})

    prev = await db["sistema_stato"].find_one({"chiave": _STATO_KEY}, {"_id": 0}) or {}
    last_result = {k: result[k] for k in ("total", "imported", "duplicates", "errors", "moved")}
    # Persisti i primi errori per-file: senza, si vede solo il conteggio
    # e la diagnosi è impossibile.
    last_result["details"] = result["details"][:5]
    now = datetime.now(timezone.utc).isoformat()
    await db["sistema_stato"].update_one(
        {"chiave": _STATO_KEY},
        {"$set": {
            "valore": now,
            "last_result": last_result,
            "last_error": None,
            "total_imported": prev.get("total_imported", 0) + result["imported"],
            "updated_at": now,
        }},
        upsert=True,
    )
    return result
