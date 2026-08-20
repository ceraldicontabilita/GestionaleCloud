"""
Ingest quietanze F24 (PDF) da Google Drive.

Legge i file `.pdf` dalla cartella Drive delle quietanze e li passa al
MOTORE UNICO di import (app/services/quietanze_import.py) — lo stesso
dell'upload manuale dalla pagina F24: parsing, dedup per impronta md5,
salvataggio in `quietanze_f24` e matching automatico con gli F24 del
commercialista (match → F24 pagato; nessun match → alert).
I file elaborati (importati o duplicati noti) vengono spostati nella
sottocartella Drive `Elaborate` (creata se manca).

Configurazione (env / settings):
GOOGLE_DRIVE_QUIETANZE_FOLDER_ID
  GOOGLE_SERVICE_ACCOUNT_JSON_QUIETANZE (o il service account condiviso
  GOOGLE_DRIVE_SA_FILE / GOOGLE_DRIVE_SA_JSON)
  ENABLE_DRIVE_QUIETANZE_SYNC (acceso su scelta esplicita dell'utente 10/07)

Helper Drive (credenziali, Elaborate, download, spostamento) RIUSATI da
drive_invoice_ingest: stessa logica, nessuna duplicazione.
"""
import asyncio
import hashlib
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from app.config import settings
from app.services.drive_invoice_ingest import (
    _load_credentials,
    _get_or_create_inbox_folder,
    _get_or_create_elaborate_folder,
    _get_or_create_error_folder,
    _download_bytes,
    _move_to_folder,
    _move_to_elaborate,
)

logger = logging.getLogger(__name__)

_STATO_KEY = "drive_quietanze_last_sync"

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


def _folder_id() -> Optional[str]:
    """ID della cartella quietanze configurato con il nome canonico."""
    return settings.GOOGLE_DRIVE_QUIETANZE_FOLDER_ID


def _load_credentials_quietanze():
    """Service account DEDICATO alle quietanze se configurato, altrimenti
    quello condiviso del modulo fatture. Ritorna (credentials, None) o (None, errore)."""
    if settings.GOOGLE_SERVICE_ACCOUNT_JSON_QUIETANZE:
        try:
            from google.oauth2 import service_account
            from app.services.drive_invoice_ingest import _parse_sa_json, _SCOPES
            info = _parse_sa_json(settings.GOOGLE_SERVICE_ACCOUNT_JSON_QUIETANZE)
            return service_account.Credentials.from_service_account_info(info, scopes=_SCOPES), None
        except Exception as e:
            return None, f"GOOGLE_SERVICE_ACCOUNT_JSON_QUIETANZE non valido: {e}"
    return _load_credentials()


def is_configured() -> bool:
    return bool(
        settings.ENABLE_DRIVE_QUIETANZE_SYNC
        and _folder_id()
        and (settings.GOOGLE_SERVICE_ACCOUNT_JSON_QUIETANZE
             or settings.GOOGLE_DRIVE_SA_FILE or settings.GOOGLE_DRIVE_SA_JSON
             or settings.GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON)
    )


def is_quietanza_filename(name: str) -> bool:
    """Classificazione pura: nella cartella quietanze si lavorano solo i PDF."""
    return bool(name) and name.lower().endswith(".pdf")


def _build_drive_service():
    """Client Drive v3 da service account. None se non disponibile."""
    if not is_configured():
        return None
    creds, err = _load_credentials_quietanze()
    if creds is None:
        logger.error(f"Drive quietanze: {err}")
        return None
    try:
        from googleapiclient.discovery import build
        return build("drive", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:
        logger.error(f"Drive quietanze: errore costruzione service: {e}")
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
            if is_quietanza_filename(f["name"]):
                out.append(f)
        page_token = res.get("nextPageToken")
        if not page_token:
            break
    return out


async def get_status(db) -> Dict[str, Any]:
    state = await db["sistema_stato"].find_one({"chiave": _STATO_KEY}, {"_id": 0}) or {}
    credenziali_errore = None
    if is_configured():
        _, credenziali_errore = _load_credentials_quietanze()
    return {
        "configured": is_configured(),
        "credenziali_ok": is_configured() and credenziali_errore is None,
        "credenziali_errore": credenziali_errore,
        "folder_id": _folder_id(),
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
            "message": "Imposta GOOGLE_DRIVE_QUIETANZE_FOLDER_ID "
                       "e il service account (GOOGLE_DRIVE_SA_FILE o GOOGLE_DRIVE_SA_JSON).",
        }
    creds, cred_err = _load_credentials_quietanze()
    if creds is None:
        return {"status": "error", "message": f"Credenziali Google Drive non valide: {cred_err}"}
    service = _build_drive_service()
    if service is None:
        return {"status": "error", "message": "Service Drive non disponibile (errore costruzione client)."}

    from app.services.f24_canonico import importa_quietanza

    parent_id = _folder_id()
    result = {
        "status": "ok", "total": 0, "imported": 0, "duplicates": 0,
        "matchati": 0, "senza_match": 0, "errors": 0, "moved": 0, "details": [],
    }
    try:
        inbox_id = _get_or_create_inbox_folder(service, parent_id)
        elaborate_id = _get_or_create_elaborate_folder(service, parent_id)
        error_id = _get_or_create_error_folder(service, parent_id)
        source_id = inbox_id or parent_id
        pdf_files = _list_pdf_files(service, source_id)
        result["total"] = len(pdf_files)
        for f in pdf_files:
            fid, fname = f["id"], f["name"]
            try:
                content = _download_bytes(service, fid)
                if not content:
                    result["errors"] += 1
                    result["details"].append({"file": fname, "error": "file vuoto"})
                    if error_id:
                        _move_to_folder(service, fid, source_id, error_id)
                    continue
                esito = await importa_quietanza(db, content, fname, source="drive_quietanze")
                if not esito.get("success"):
                    # Parsing fallito: NON spostare, resta visibile per diagnosi
                    result["errors"] += 1
                    result["details"].append({"file": fname, "error": esito.get("error")})
                    if error_id:
                        _move_to_folder(service, fid, source_id, error_id)
                    continue
                if esito.get("duplicate"):
                    result["duplicates"] += 1
                else:
                    result["imported"] += 1
                    if esito.get("f24_matchati"):
                        result["matchati"] += 1
                    else:
                        result["senza_match"] += 1
                    logger.info(f"Drive quietanze: importata {fname}")
                    try:
                        from app.services.event_bus import propagate_event, EventTypes
                        await propagate_event(EventTypes.DOCUMENTO_ACQUISITO, {
                            "documento_id": esito.get("quietanza_id"),
                            "filename": fname,
                            "origine": "drive_quietanze",
                            "mime_type": "application/pdf",
                            "hash_file": hashlib.md5(content).hexdigest(),
                            "category": "quietanza_f24",
                        }, db, source_module="drive_quietanze_ingest")
                    except Exception:
                        logger.exception("Drive quietanze: errore propagazione evento documento.acquisito")
                # Sposta in `Elaborate` i file processati (importati o duplicati noti).
                if elaborate_id:
                    _move_to_elaborate(service, fid, source_id, elaborate_id)
                    result["moved"] += 1
            except Exception as e:
                logger.error(f"Drive quietanze: errore su {fname}: {e}")
                result["errors"] += 1
                result["details"].append({"file": fname, "error": str(e)})
                if error_id:
                    try:
                        _move_to_folder(service, fid, source_id, error_id)
                    except Exception:
                        logger.exception("Drive quietanze: impossibile spostare %s in Errori", fname)
    except Exception as e:
        logger.error(f"Drive quietanze: errore sync: {e}")
        now = datetime.now(timezone.utc).isoformat()
        await db["sistema_stato"].update_one(
            {"chiave": _STATO_KEY},
            {"$set": {"valore": now, "last_error": str(e), "updated_at": now}},
            upsert=True,
        )
        return {"status": "error", "message": str(e)}

    prev = await db["sistema_stato"].find_one({"chiave": _STATO_KEY}, {"_id": 0}) or {}
    last_result = {k: result[k] for k in ("total", "imported", "duplicates", "matchati", "senza_match", "errors", "moved")}
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


async def verifica_quadratura_elaborate(db) -> Dict[str, Any]:
    """Doppio controllo Elaborate ↔ gestionale per le QUIETANZE.

    Ripassa TUTTI i PDF archiviati nella sottocartella "Elaborate" e verifica
    che ognuno abbia la sua quietanza nel gestionale (dedup per impronta md5
    su `quietanze_f24.pdf_hash`, la stessa dell'import): presente = quadrato,
    assente = buco recuperato (re-import nel motore unico, matching incluso).
    Non sposta file, niente doppioni.
    """
    if not is_configured():
        return {"status": "not_configured"}
    service = _build_drive_service()
    if service is None:
        return {"status": "error", "message": "Service Drive non disponibile"}

    from app.services.f24_canonico import importa_quietanza, COLL_QUIETANZE

    parent_id = _folder_id()
    esito = {"status": "ok", "controllati": 0, "quadrati": 0,
             "recuperati": 0, "errori": 0, "details": []}
    try:
        elaborate_id = _get_or_create_elaborate_folder(service, parent_id)
        if not elaborate_id:
            return {"status": "ok", "message": "Nessuna cartella Elaborate", **esito}
        for f in _list_pdf_files(service, elaborate_id):
            esito["controllati"] += 1
            try:
                content = _download_bytes(service, f["id"])
                if not content:
                    esito["errori"] += 1
                    continue
                content_hash = hashlib.md5(content).hexdigest()
                existing = await db[COLL_QUIETANZE].find_one(
                    {"pdf_hash": content_hash}, {"_id": 0, "id": 1}
                )
                if existing:
                    esito["quadrati"] += 1
                    continue
                res = await importa_quietanza(db, content, f["name"], source="drive_quietanze_quadratura")
                if res.get("success") and not res.get("duplicate"):
                    esito["recuperati"] += 1
                    esito["details"].append({"file": f["name"], "recuperato": True})
                    logger.warning(f"Quadratura quietanze: recuperato buco {f['name']}")
                elif not res.get("success"):
                    esito["errori"] += 1
                    esito["details"].append({"file": f["name"], "error": res.get("error")})
                else:
                    esito["quadrati"] += 1
            except Exception as e:
                esito["errori"] += 1
                esito["details"].append({"file": f["name"], "error": str(e)})
    except Exception as e:
        return {"status": "error", "message": str(e), **esito}

    if esito["recuperati"] or esito["errori"]:
        try:
            from app.services.alert_engine import genera_alert
            await genera_alert(
                "DOC_QUADRATURA_DRIVE", "quadratura_quietanze", "quietanze_f24",
                f"Quadratura Drive quietanze: {esito['recuperati']} recuperate, "
                f"{esito['errori']} errori su {esito['controllati']} file in Elaborate",
                db,
            )
        except Exception:
            logger.exception("Alert quadratura quietanze non generato")

    now = datetime.now(timezone.utc).isoformat()
    await db["sistema_stato"].update_one(
        {"chiave": _STATO_KEY},
        {"$set": {"last_quadratura": {"quando": now, **{k: esito[k] for k in ('controllati', 'quadrati', 'recuperati', 'errori')}}}},
        upsert=True,
    )
    return esito
