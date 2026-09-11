"""
Ingest cedolini paga (PDF) da Google Drive.

Legge i file `.pdf` dalle inbox Drive reali, li deduplica per hash md5 contro
`documents_inbox` e li inserisce nello STESSO formato dei cedolini arrivati
via email. La pipeline esistente (`processa_nuovi_documenti` -> parser
cedolini -> prima nota salari -> verifica trattenute) li lavora senza
modifiche.

La struttura Drive canonica puo' essere annidata:
  CEDOLINI PAGA/<dipendente>/DA ELABORARE
I file elaborati/errori vengono quindi spostati nelle cartelle sorelle dello
stesso dipendente, non in una cartella globale alla radice.

Configurazione (env / settings):
  GOOGLE_DRIVE_CEDOLINI_FOLDER_ID : id della cartella Drive dei cedolini
  GOOGLE_DRIVE_SA_FILE            : path al JSON del service account, oppure
  GOOGLE_DRIVE_SA_JSON            : il JSON del service account inline

Se non configurato, `get_status` lo segnala e `sync` è un no-op.
Lo stato dell'ultimo sync è salvato in `sistema_stato` (chiave dedicata).
"""
import asyncio
import base64
import hashlib
import io
import logging
import posixpath
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Dict, Any, Iterator, Optional, List, Tuple

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
from app.services.drive_lifecycle_tree import (
    discover_lifecycle_folders,
    resolve_inboxes_or_legacy,
)

logger = logging.getLogger(__name__)

_STATO_KEY = "drive_cedolini_last_sync"
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
    """ID della cartella cedolini configurato con il nome canonico."""
    return settings.GOOGLE_DRIVE_CEDOLINI_FOLDER_ID


def _load_credentials_cedolini():
    """Service account DEDICATO ai cedolini se configurato, altrimenti quello
    condiviso del modulo fatture. Ritorna (credentials, None) o (None, errore)."""
    if settings.GOOGLE_SERVICE_ACCOUNT_JSON_CEDOLINI:
        try:
            from google.oauth2 import service_account
            from app.services.drive_invoice_ingest import _parse_sa_json, _SCOPES
            info = _parse_sa_json(settings.GOOGLE_SERVICE_ACCOUNT_JSON_CEDOLINI)
            return service_account.Credentials.from_service_account_info(info, scopes=_SCOPES), None
        except Exception as e:
            return None, f"GOOGLE_SERVICE_ACCOUNT_JSON_CEDOLINI non valido: {e}"
    return _load_credentials()


def is_configured() -> bool:
    return bool(
        settings.ENABLE_DRIVE_CEDOLINI_SYNC
        and _folder_id()
        and (settings.GOOGLE_SERVICE_ACCOUNT_JSON_CEDOLINI
             or settings.GOOGLE_DRIVE_SA_FILE or settings.GOOGLE_DRIVE_SA_JSON
             or settings.GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON)
    )


def is_cedolino_filename(name: str) -> bool:
    """Classificazione pura: nella cartella cedolini si lavorano solo i PDF."""
    return bool(name) and name.lower().endswith(".pdf")


def is_cedolini_archive(name: str) -> bool:
    """Gli archivi ZIP possono contenere cartelle annidate di cedolini PDF."""
    return bool(name) and name.lower().endswith(".zip")


def _safe_archive_path(name: str) -> Optional[str]:
    """Normalizza un membro ZIP e rifiuta path assoluti o con traversal."""
    normalized = (name or "").replace("\\", "/")
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or ".." in path.parts:
        return None
    cleaned = posixpath.normpath(normalized).lstrip("./")
    return cleaned if cleaned and cleaned != "." else None


def iter_pdf_members(content: bytes) -> Iterator[Tuple[str, bytes]]:
    """Estrae ricorsivamente tutti i PDF da uno ZIP, preservando il path."""
    from app.utils.upload_guard import controlla_zip

    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        controlla_zip(len(infos), sum(max(0, info.file_size) for info in infos))
        for info in infos:
            safe_path = _safe_archive_path(info.filename)
            if not safe_path or not is_cedolino_filename(safe_path):
                continue
            if info.flag_bits & 0x1:
                raise ValueError("ZIP cifrato: impossibile leggere i cedolini")
            member = archive.read(info)
            if not member.startswith(b"%PDF"):
                raise ValueError("Membro con estensione PDF ma contenuto non valido")
            yield safe_path, member


def build_inbox_doc(
    content: bytes,
    filename: str,
    *,
    source_path: Optional[str] = None,
    source_container: Optional[str] = None,
) -> Dict[str, Any]:
    """Costruisce il documento `documents_inbox` nel formato dei cedolini email."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(uuid.uuid4()),
        "filename": filename,
        "source_path": source_path or filename,
        "source_container": source_container,
        "pdf_data": base64.b64encode(content).decode(),
        "file_hash": hashlib.md5(content).hexdigest(),
        "size_bytes": len(content),
        "category": "busta_paga",
        "category_label": "Buste Paga",
        "tipo_documento": "cedolino",
        "categoria": "cedolino",
        "fonte": "drive_cedolini",
        "stato": "importato",
        "status": "nuovo",
        "processed": False,
        "processed_to": None,
        "xml_processed": True,
        "created_at": now,
        "downloaded_at": now,
    }


def _build_drive_service():
    """Client Drive v3 da service account. None se non disponibile."""
    if not is_configured():
        return None
    creds, err = _load_credentials_cedolini()
    if creds is None:
        logger.error(f"Drive cedolini: {err}")
        return None
    try:
        from googleapiclient.discovery import build
        return build("drive", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:
        logger.error(f"Drive cedolini: errore costruzione service: {e}")
        return None


def _list_children(service, parent_id: str) -> List[Dict[str, Any]]:
    q = f"'{parent_id}' in parents and trashed = false"
    out: List[Dict[str, Any]] = []
    page_token = None
    while True:
        res = service.files().list(
            q=q, fields="nextPageToken, files(id, name, mimeType)",
            pageSize=100, pageToken=page_token,
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute()
        out.extend(res.get("files", []))
        page_token = res.get("nextPageToken")
        if not page_token:
            break
    return out


def _list_source_files_recursive(
    service,
    parent_id: str,
    *,
    include_archives: bool = True,
) -> List[Dict[str, Any]]:
    """Visita tutte le sottocartelle della singola inbox e conserva il path."""
    folder_mime = "application/vnd.google-apps.folder"
    pending: List[Tuple[str, str]] = [(parent_id, "")]
    found: List[Dict[str, Any]] = []
    visited = set()
    while pending:
        folder_id, prefix = pending.pop(0)
        if folder_id in visited:
            continue
        visited.add(folder_id)
        for item in _list_children(service, folder_id):
            name = item.get("name") or ""
            relative_path = posixpath.join(prefix, name) if prefix else name
            if item.get("mimeType") == folder_mime:
                pending.append((item["id"], relative_path))
                continue
            if is_cedolino_filename(name) or (include_archives and is_cedolini_archive(name)):
                found.append({
                    **item,
                    "parent_id": folder_id,
                    "relative_path": relative_path,
                })
    return found


def _list_pdf_files(service, parent_id: str) -> List[Dict[str, Any]]:
    """Compatibilita' per la quadratura: include anche le sottocartelle."""
    return _list_source_files_recursive(service, parent_id, include_archives=False)


def _inbox_contexts(service, parent_id: str) -> List[Dict[str, Any]]:
    return resolve_inboxes_or_legacy(
        service,
        parent_id,
        _get_or_create_inbox_folder,
        max_depth=2,
    )


async def get_status(db) -> Dict[str, Any]:
    state = await db["sistema_stato"].find_one({"chiave": _STATO_KEY}, {"_id": 0}) or {}
    credenziali_errore = None
    if is_configured():
        _, credenziali_errore = _load_credentials_cedolini()
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
            "message": "Imposta GOOGLE_DRIVE_CEDOLINI_FOLDER_ID e il service account "
                       "(GOOGLE_DRIVE_SA_FILE o GOOGLE_DRIVE_SA_JSON).",
        }
    creds, cred_err = _load_credentials_cedolini()
    if creds is None:
        return {"status": "error", "message": f"Credenziali Google Drive non valide: {cred_err}"}
    service = _build_drive_service()
    if service is None:
        return {"status": "error", "message": "Service Drive non disponibile (errore costruzione client)."}

    parent_id = _folder_id()
    result = {
        "status": "ok", "total": 0, "imported": 0, "duplicates": 0,
        "errors": 0, "moved": 0, "details": [], "source_inboxes": 0,
    }
    try:
        contexts = _inbox_contexts(service, parent_id)
        result["source_inboxes"] = len(contexts)
        source_files: List[Dict[str, Any]] = []
        for context in contexts:
            source_id = context["inbox_id"]
            for file_info in _list_source_files_recursive(service, source_id):
                local_path = file_info.get("relative_path") or file_info.get("name") or ""
                source_files.append({
                    **file_info,
                    "_source_id": source_id,
                    "_lifecycle_parent_id": context["lifecycle_parent_id"],
                    "_source_path": (
                        f"{context['relative_path']}/{local_path}"
                        if local_path else context["relative_path"]
                    ),
                })
        result["source_files"] = len(source_files)

        lifecycle_cache: Dict[str, tuple[Optional[str], Optional[str]]] = {}
        for f in source_files:
            fid, fname = f["id"], f["name"]
            source_id = f["_source_id"]
            source_parent_id = f.get("parent_id") or source_id
            lifecycle_parent_id = f["_lifecycle_parent_id"]
            relative_path = f["_source_path"]
            if lifecycle_parent_id not in lifecycle_cache:
                lifecycle_cache[lifecycle_parent_id] = (
                    _get_or_create_elaborate_folder(service, lifecycle_parent_id),
                    _get_or_create_error_folder(service, lifecycle_parent_id),
                )
            elaborate_id, error_id = lifecycle_cache[lifecycle_parent_id]

            try:
                content = _download_bytes(service, fid)
                if not content:
                    result["errors"] += 1
                    result["details"].append({"source_path": relative_path, "error": "file vuoto"})
                    if error_id:
                        _move_to_folder(service, fid, source_parent_id, error_id)
                    continue

                if is_cedolini_archive(fname):
                    pdf_items = iter_pdf_members(content)
                else:
                    if not content.startswith(b"%PDF"):
                        raise ValueError("File con estensione PDF ma contenuto non valido")
                    pdf_items = iter([(relative_path, content)])

                for member_path, pdf_content in pdf_items:
                    result["total"] += 1
                    content_hash = hashlib.md5(pdf_content).hexdigest()
                    existing = await db["documents_inbox"].find_one(
                        {"file_hash": content_hash}, {"_id": 0, "id": 1}
                    )
                    if existing:
                        result["duplicates"] += 1
                        continue

                    display_name = PurePosixPath(member_path).name
                    doc = build_inbox_doc(
                        pdf_content,
                        display_name,
                        source_path=member_path,
                        source_container=relative_path if is_cedolini_archive(fname) else None,
                    )
                    await db["documents_inbox"].insert_one(doc)
                    result["imported"] += 1
                    logger.info("Drive cedolini: importato documento hash=%s", content_hash[:12])
                    try:
                        from app.services.event_bus import propagate_event, EventTypes
                        await propagate_event(EventTypes.DOCUMENTO_ACQUISITO, {
                            "documento_id": doc["id"],
                            "filename": display_name,
                            "origine": "drive_cedolini",
                            "mime_type": "application/pdf",
                            "hash_file": doc["file_hash"],
                            "category": "busta_paga",
                        }, db, source_module="drive_cedolini_ingest")
                    except Exception:
                        logger.exception("Drive cedolini: errore propagazione evento documento.acquisito")

                if elaborate_id:
                    _move_to_elaborate(service, fid, source_parent_id, elaborate_id)
                    result["moved"] += 1
            except Exception as e:
                logger.error("Drive cedolini: errore su sorgente hash=%s: %s", fid, e)
                result["errors"] += 1
                result["details"].append({"source_path": relative_path, "error": str(e)})
                if error_id:
                    try:
                        _move_to_folder(service, fid, source_parent_id, error_id)
                    except Exception:
                        logger.exception("Drive cedolini: impossibile spostare sorgente in Errori")
    except Exception as e:
        logger.error(f"Drive cedolini: errore sync: {e}")
        now = datetime.now(timezone.utc).isoformat()
        await db["sistema_stato"].update_one(
            {"chiave": _STATO_KEY},
            {"$set": {"valore": now, "last_error": str(e), "updated_at": now}},
            upsert=True,
        )
        return {"status": "error", "message": str(e)}

    if result["imported"] > 0:
        try:
            from app.services.email_monitor_service import processa_nuovi_documenti
            result["cedolini_processati"] = 0
            result["parser_errors"] = []
            max_batches = max(1, (result["imported"] + 99) // 100 + 1)
            for _ in range(max_batches):
                proc = await processa_nuovi_documenti(db)
                processed = proc.get("buste_paga", 0)
                result["cedolini_processati"] += processed
                result["parser_errors"].extend(proc.get("errori", []))
                if processed == 0:
                    break
        except Exception as e:
            logger.error(f"Drive cedolini: errore pipeline processamento: {e}")
            result["details"].append({"pipeline": str(e)})

    prev = await db["sistema_stato"].find_one({"chiave": _STATO_KEY}, {"_id": 0}) or {}
    last_result = {k: result[k] for k in ("total", "imported", "duplicates", "errors", "moved")}
    last_result["source_files"] = result.get("source_files", 0)
    last_result["source_inboxes"] = result.get("source_inboxes", 0)
    last_result["cedolini_processati"] = result.get("cedolini_processati", 0)
    last_result["parser_errors"] = len(result.get("parser_errors", []))
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
    """Doppio controllo Elaborate ↔ gestionale per i CEDOLINI.

    Ripassa tutte le ``Elaborate`` canoniche dei dipendenti e verifica che ogni
    PDF abbia il proprio documento nel gestionale. Non crea una cartella
    ``Elaborate`` globale alla radice.
    """
    if not is_configured():
        return {"status": "not_configured"}
    service = _build_drive_service()
    if service is None:
        return {"status": "error", "message": "Service Drive non disponibile"}

    parent_id = _folder_id()
    esito = {"status": "ok", "controllati": 0, "quadrati": 0,
             "recuperati": 0, "errori": 0, "details": [], "cartelle_elaborate": 0}
    try:
        elaborate_folders = discover_lifecycle_folders(
            service, parent_id, max_depth=2, states=("elaborate",),
        )
        esito["cartelle_elaborate"] = len(elaborate_folders)
        if not elaborate_folders:
            return {"status": "ok", "message": "Nessuna cartella Elaborate", **esito}

        recuperati_da_processare = 0
        for folder in elaborate_folders:
            for f in _list_source_files_recursive(service, folder["folder_id"]):
                try:
                    content = _download_bytes(service, f["id"])
                    if not content:
                        esito["errori"] += 1
                        continue
                    local_path = f.get("relative_path") or f["name"]
                    relative_path = f"{folder['relative_path']}/{local_path}"
                    if is_cedolini_archive(f["name"]):
                        pdf_items = iter_pdf_members(content)
                    else:
                        pdf_items = iter([(relative_path, content)])
                    for member_path, pdf_content in pdf_items:
                        esito["controllati"] += 1
                        content_hash = hashlib.md5(pdf_content).hexdigest()
                        existing = await db["documents_inbox"].find_one(
                            {"file_hash": content_hash}, {"_id": 0, "id": 1}
                        )
                        if existing:
                            esito["quadrati"] += 1
                            continue
                        doc = build_inbox_doc(
                            pdf_content,
                            PurePosixPath(member_path).name,
                            source_path=member_path,
                            source_container=relative_path if is_cedolini_archive(f["name"]) else None,
                        )
                        await db["documents_inbox"].insert_one(doc)
                        esito["recuperati"] += 1
                        recuperati_da_processare += 1
                        esito["details"].append({"source_path": member_path, "recuperato": True})
                        logger.warning("Quadratura cedolini: recuperato hash=%s", content_hash[:12])
                except Exception as e:
                    esito["errori"] += 1
                    esito["details"].append({
                        "source_path": f"{folder['relative_path']}/{f.get('relative_path') or f.get('name')}",
                        "error": str(e),
                    })

        if recuperati_da_processare:
            try:
                from app.services.email_monitor_service import processa_nuovi_documenti
                await processa_nuovi_documenti(db)
            except Exception:
                logger.exception("Quadratura cedolini: errore pipeline processamento")
    except Exception as e:
        return {"status": "error", "message": str(e), **esito}

    if esito["recuperati"] or esito["errori"]:
        try:
            from app.services.alert_engine import genera_alert
            await genera_alert(
                "DOC_QUADRATURA_DRIVE", "quadratura_cedolini", "documents_inbox",
                f"Quadratura Drive cedolini: {esito['recuperati']} recuperati, "
                f"{esito['errori']} errori su {esito['controllati']} file in Elaborate",
                db,
            )
        except Exception:
            logger.exception("Alert quadratura cedolini non generato")

    now = datetime.now(timezone.utc).isoformat()
    await db["sistema_stato"].update_one(
        {"chiave": _STATO_KEY},
        {"$set": {"last_quadratura": {"quando": now, **{k: esito[k] for k in (
            'controllati', 'quadrati', 'recuperati', 'errori', 'cartelle_elaborate'
        )}}}},
        upsert=True,
    )
    return esito


_ORE_SOGLIA_BLOCCATO = 6


async def verifica_documenti_bloccati(db) -> Dict[str, Any]:
    """Verifica i cedolini acquisiti ma non trasformati in record contabili."""
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    soglia = (now - timedelta(hours=_ORE_SOGLIA_BLOCCATO)).isoformat()

    bloccati_drive = await db["documents_inbox"].find(
        {"category": "busta_paga", "processed": {"$ne": True}, "created_at": {"$lt": soglia}},
        {"_id": 0, "id": 1, "filename": 1, "created_at": 1},
    ).to_list(500)

    bloccati_email = await db["cedolini_email_attachments"].find(
        {"processed": {"$ne": True}, "created_at": {"$lt": soglia}},
        {"_id": 0, "id": 1, "filename": 1, "created_at": 1},
    ).to_list(500)

    for d in bloccati_drive:
        d["canale"] = "drive"
    for d in bloccati_email:
        d["canale"] = "email"

    return {
        "soglia_ore": _ORE_SOGLIA_BLOCCATO,
        "totale_bloccati": len(bloccati_drive) + len(bloccati_email),
        "bloccati": bloccati_drive + bloccati_email,
    }
