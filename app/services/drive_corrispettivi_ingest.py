"""
Ingest corrispettivi RT (XML) da Google Drive.

Legge i file XML del registratore telematico dalla cartella Drive
configurata e li processa con la pipeline UNICA dei corrispettivi
(CorrispettiviService.process_xml: parsing, dedup per hash contenuto e
per data, prima nota). I file elaborati (importati o duplicati noti)
vengono spostati nella sottocartella Drive `Elaborate`.

Prima questo canale esisteva solo sulla carta (LOGICA §2 lo dichiarava
attivo ma nessun codice leggeva la cartella): i corrispettivi entravano
solo da import manuale.

Configurazione (env / settings):
  GOOGLE_DRIVE_CORRISPETTIVI_FOLDER_ID : id della cartella Drive
  GOOGLE_DRIVE_SA_FILE / GOOGLE_DRIVE_SA_JSON : service account (condiviso)

Helper Drive riusati da drive_invoice_ingest (stesso service account,
stessa gestione Elaborate). Stato sync in sistema_stato, chiave dedicata.
"""
import asyncio
import io
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import PurePosixPath
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

_STATO_KEY = "drive_corrispettivi_last_sync"

_sync_lock = asyncio.Lock()
_bg_task: Optional[asyncio.Task] = None
_MAX_ZIP_ENTRIES = 5000
_MAX_ZIP_ENTRY_BYTES = 10 * 1024 * 1024
_MAX_ZIP_TOTAL_BYTES = 100 * 1024 * 1024


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
    """ID cartella: nome canonico o alias reale dell'ambiente Render."""
    return (settings.GOOGLE_DRIVE_CORRISPETTIVI_FOLDER_ID
            or settings.DRIVE_FOLDER_CORRISPETTIVI_ID
            or settings.DRIVE_CORRISPETTIVI_FOLDER_ID)


def _load_credentials_corrispettivi():
    """Service account DEDICATO ai corrispettivi se configurato, altrimenti
    quello condiviso del modulo fatture."""
    if settings.GOOGLE_SERVICE_ACCOUNT_JSON_CORRISPETTIVI:
        try:
            from google.oauth2 import service_account
            from app.services.drive_invoice_ingest import _parse_sa_json, _SCOPES
            info = _parse_sa_json(settings.GOOGLE_SERVICE_ACCOUNT_JSON_CORRISPETTIVI)
            return service_account.Credentials.from_service_account_info(info, scopes=_SCOPES), None
        except Exception as e:
            return None, f"GOOGLE_SERVICE_ACCOUNT_JSON_CORRISPETTIVI non valido: {e}"
    return _load_credentials()


def is_configured() -> bool:
    return bool(
        settings.ENABLE_DRIVE_CORRISPETTIVI_SYNC
        and _folder_id()
        and (settings.GOOGLE_SERVICE_ACCOUNT_JSON_CORRISPETTIVI
             or settings.GOOGLE_DRIVE_SA_FILE or settings.GOOGLE_DRIVE_SA_JSON
             or settings.GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON)
    )


def is_corrispettivo_filename(name: str) -> bool:
    """Accetta XML RT singoli e ZIP contenenti XML RT."""
    return bool(name) and name.lower().endswith((".xml", ".zip"))


def _xml_documents_from_source(name: str, content: bytes) -> List[tuple[str, bytes]]:
    """Restituisce gli XML senza estrarre file su disco.

    Gli archivi sono limitati per numero e dimensione per evitare path
    traversal e zip bomb. Gli elementi estranei sono ignorati; uno ZIP senza
    XML e' invece un errore operativo visibile.
    """
    if name.lower().endswith(".xml"):
        return [(name, content)]
    if not name.lower().endswith(".zip"):
        raise ValueError("Formato corrispettivo supportato: XML o ZIP")
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError("Archivio ZIP non valido") from exc

    documents: List[tuple[str, bytes]] = []
    total_bytes = 0
    with archive:
        entries = [entry for entry in archive.infolist() if not entry.is_dir()]
        if len(entries) > _MAX_ZIP_ENTRIES:
            raise ValueError(f"Archivio ZIP con troppi file ({len(entries)})")
        for entry in entries:
            normalized = entry.filename.replace("\\", "/")
            path = PurePosixPath(normalized)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"Percorso non sicuro nello ZIP: {entry.filename}")
            if not normalized.lower().endswith(".xml"):
                continue
            if entry.file_size > _MAX_ZIP_ENTRY_BYTES:
                raise ValueError(f"XML troppo grande nello ZIP: {entry.filename}")
            total_bytes += entry.file_size
            if total_bytes > _MAX_ZIP_TOTAL_BYTES:
                raise ValueError("Contenuto XML dello ZIP troppo grande")
            try:
                xml_content = archive.read(entry)
            except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                raise ValueError(f"XML non leggibile nello ZIP: {entry.filename}") from exc
            if not xml_content:
                raise ValueError(f"XML vuoto nello ZIP: {entry.filename}")
            documents.append((f"{name}::{normalized}", xml_content))
    if not documents:
        raise ValueError("Archivio ZIP senza file XML")
    return documents


def _build_drive_service():
    if not is_configured():
        return None
    creds, err = _load_credentials_corrispettivi()
    if creds is None:
        logger.error(f"Drive corrispettivi: {err}")
        return None
    try:
        from googleapiclient.discovery import build
        return build("drive", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:
        logger.error(f"Drive corrispettivi: errore costruzione service: {e}")
        return None


def _list_source_files(service, parent_id: str) -> List[Dict[str, Any]]:
    q = (
        f"'{parent_id}' in parents and trashed = false "
        "and (name contains '.xml' or name contains '.XML' "
        "or name contains '.zip' or name contains '.ZIP')"
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
            if is_corrispettivo_filename(f["name"]):
                out.append(f)
        page_token = res.get("nextPageToken")
        if not page_token:
            break
    return out


def _list_xml_files(service, parent_id: str) -> List[Dict[str, Any]]:
    """Alias compatibile: ora include anche le sorgenti ZIP."""
    return _list_source_files(service, parent_id)


async def get_status(db) -> Dict[str, Any]:
    state = await db["sistema_stato"].find_one({"chiave": _STATO_KEY}, {"_id": 0}) or {}
    credenziali_errore = None
    if is_configured():
        _, credenziali_errore = _load_credentials_corrispettivi()
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
            "message": "Imposta GOOGLE_DRIVE_CORRISPETTIVI_FOLDER_ID e il service "
                       "account (GOOGLE_DRIVE_SA_FILE o GOOGLE_DRIVE_SA_JSON).",
        }
    creds, cred_err = _load_credentials_corrispettivi()
    if creds is None:
        return {"status": "error", "message": f"Credenziali Google Drive non valide: {cred_err}"}
    service = _build_drive_service()
    if service is None:
        return {"status": "error", "message": "Service Drive non disponibile."}

    from app.services.corrispettivi_service import get_corrispettivi_service
    corr_service = get_corrispettivi_service(db)

    parent_id = _folder_id()
    result = {
        "status": "ok", "total": 0, "documents": 0,
        "imported": 0, "duplicates": 0,
        "archiviate": 0, "errors": 0, "moved": 0, "details": [],
    }
    try:
        inbox_id = _get_or_create_inbox_folder(service, parent_id)
        elaborate_id = _get_or_create_elaborate_folder(service, parent_id)
        error_id = _get_or_create_error_folder(service, parent_id)
        source_id = inbox_id or parent_id
        source_files = _list_source_files(service, source_id)
        result["total"] = len(source_files)
        for f in source_files:
            fid, fname = f["id"], f["name"]
            try:
                content = _download_bytes(service, fid)
                if not content:
                    result["errors"] += 1
                    result["details"].append({"file": fname, "error": "file vuoto"})
                    if error_id:
                        _move_to_folder(service, fid, source_id, error_id)
                    continue
                # Pipeline UNICA corrispettivi: dedup per hash e per data
                # sono già dentro process_xml — nessun doppione possibile.
                # applica_filtro_anno (richiesta utente 14/07/2026, stesso
                # selettore anno condiviso con l'import fatture): un
                # corrispettivo di un anno diverso da quello attivo viene
                # archiviato per sola consultazione, non in Prima Nota.
                source_has_errors = False
                documents = _xml_documents_from_source(fname, content)
                result["documents"] += len(documents)
                for document_name, xml_content in documents:
                    esito = await corr_service.process_xml(
                        xml_content, document_name, applica_filtro_anno=True,
                    )
                    stato = esito.get("status")
                    if stato == "duplicate":
                        result["duplicates"] += 1
                    elif stato == "error":
                        source_has_errors = True
                        result["errors"] += 1
                        result["details"].append({
                            "file": document_name, "error": esito.get("message"),
                        })
                    elif stato == "archiviata":
                        result["archiviate"] += 1
                        logger.info("Drive corrispettivi: archiviato %s", document_name)
                    else:
                        result["imported"] += 1
                        logger.info("Drive corrispettivi: importato %s", document_name)
                if source_has_errors:
                    if error_id:
                        _move_to_folder(service, fid, source_id, error_id)
                    continue
                # Sposta in `Elaborate` i file processati (importati/duplicati)
                if elaborate_id:
                    _move_to_elaborate(service, fid, source_id, elaborate_id)
                    result["moved"] += 1
            except Exception as e:
                logger.error(f"Drive corrispettivi: errore su {fname}: {e}")
                result["errors"] += 1
                result["details"].append({"file": fname, "error": str(e)})
                if error_id:
                    try:
                        _move_to_folder(service, fid, source_id, error_id)
                    except Exception:
                        logger.exception("Drive corrispettivi: impossibile spostare %s in Errori", fname)
    except Exception as e:
        logger.error(f"Drive corrispettivi: errore sync: {e}")
        now = datetime.now(timezone.utc).isoformat()
        await db["sistema_stato"].update_one(
            {"chiave": _STATO_KEY},
            {"$set": {"valore": now, "last_error": str(e), "updated_at": now}},
            upsert=True,
        )
        return {"status": "error", "message": str(e)}

    prev = await db["sistema_stato"].find_one({"chiave": _STATO_KEY}, {"_id": 0}) or {}
    last_result = {k: result[k] for k in (
        "total", "documents", "imported", "duplicates", "archiviate", "errors", "moved",
    )}
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
    """Doppio controllo Elaborate ↔ gestionale per i CORRISPETTIVI.

    Stessa logica della quadratura fatture: ripassa TUTTI gli XML archiviati
    nella sottocartella "Elaborate" e verifica che ognuno abbia il suo
    corrispettivo nel gestionale. process_xml è idempotente (dedup per hash
    contenuto e per data): duplicate = quadrato, imported = buco recuperato.
    Non sposta file, non può creare doppioni.
    """
    if not is_configured():
        return {"status": "not_configured"}
    service = _build_drive_service()
    if service is None:
        return {"status": "error", "message": "Service Drive non disponibile"}

    from app.services.corrispettivi_service import get_corrispettivi_service
    corr_service = get_corrispettivi_service(db)

    parent_id = _folder_id()
    esito = {"status": "ok", "controllati": 0, "quadrati": 0,
             "recuperati": 0, "errori": 0, "details": []}
    try:
        elaborate_id = _get_or_create_elaborate_folder(service, parent_id)
        if not elaborate_id:
            return {"status": "ok", "message": "Nessuna cartella Elaborate", **esito}
        for f in _list_source_files(service, elaborate_id):
            try:
                content = _download_bytes(service, f["id"])
                if not content:
                    esito["errori"] += 1
                    continue
                # Stesso filtro anno di _do_sync: un buco riparato qui non
                # deve ripescare nel flusso attivo un corrispettivo storico
                # (finisce comunque archiviato, non in Prima Nota).
                for document_name, xml_content in _xml_documents_from_source(f["name"], content):
                    esito["controllati"] += 1
                    r = await corr_service.process_xml(
                        xml_content, document_name, applica_filtro_anno=True,
                    )
                    if r.get("status") == "duplicate":
                        esito["quadrati"] += 1
                    elif r.get("status") == "error":
                        esito["errori"] += 1
                        esito["details"].append({"file": document_name, "error": r.get("message")})
                    else:
                        esito["recuperati"] += 1
                        esito["details"].append({"file": document_name, "recuperato": True})
                        logger.warning("Quadratura corrispettivi: recuperato buco %s", document_name)
            except Exception as e:
                esito["errori"] += 1
                esito["details"].append({"file": f["name"], "error": str(e)})
    except Exception as e:
        return {"status": "error", "message": str(e), **esito}

    if esito["recuperati"] or esito["errori"]:
        try:
            from app.services.alert_engine import genera_alert
            await genera_alert(
                "DOC_QUADRATURA_DRIVE", "quadratura_corrispettivi", "corrispettivi",
                f"Quadratura Drive corrispettivi: {esito['recuperati']} recuperati, "
                f"{esito['errori']} errori su {esito['controllati']} file in Elaborate",
                db,
            )
        except Exception:
            logger.exception("Alert quadratura corrispettivi non generato")

    now = datetime.now(timezone.utc).isoformat()
    await db["sistema_stato"].update_one(
        {"chiave": _STATO_KEY},
        {"$set": {"last_quadratura": {"quando": now, **{k: esito[k] for k in ('controllati', 'quadrati', 'recuperati', 'errori')}}}},
        upsert=True,
    )
    return esito
