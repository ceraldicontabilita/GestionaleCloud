"""
Ingest fatture XML da Google Drive.

Legge i file `.xml` e `.xml.p7m` (buste firmate) da una cartella Drive
configurata, li importa con la pipeline CONDIVISA `process_xml_bytes` (riuso,
niente duplicazione) e sposta i file elaborati in una sottocartella `Elaborate`.

Configurazione (env / settings):
  GOOGLE_DRIVE_FATTURE_FOLDER_ID : id della cartella Drive sorgente
  GOOGLE_DRIVE_SA_FILE           : path al JSON del service account, oppure
  GOOGLE_DRIVE_SA_JSON           : il JSON del service account inline

Se non configurato, `get_status` lo segnala e `sync` è un no-op.
"""
import asyncio
import gc
import io
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from app.config import settings

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/drive"]
_INBOX_FOLDER_NAME = "Da elaborare"
_ELABORATE_FOLDER_NAME = "Elaborate"
_ERROR_FOLDER_NAME = "Errori"
_SYNC_STATE_COLLECTION = "drive_sync_state"
_SYNC_STATE_ID = "fatture_drive"

# Un solo sync alla volta (manuale + job 15 min non devono sovrapporsi).
_sync_lock = asyncio.Lock()
_bg_task: Optional[asyncio.Task] = None
_rebuild_lock = asyncio.Lock()
_rebuild_task: Optional[asyncio.Task] = None
_WEB_REBUILD_BATCH_SIZE = 10


def _batch_size() -> int:
    """Numero massimo di XML per ciclo, con limiti sicuri anche se l'env e' errata."""
    try:
        configured = int(settings.DRIVE_FATTURE_BATCH_SIZE)
    except (TypeError, ValueError):
        configured = 1
    return max(1, min(configured, 100))


def _select_batch(files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return list(files[:_batch_size()])


def is_sync_running() -> bool:
    return _sync_lock.locked()


def is_rebuild_running() -> bool:
    return _rebuild_lock.locked()


def _folder_id() -> Optional[str]:
    """ID della cartella fatture configurato con il nome canonico."""
    return settings.GOOGLE_DRIVE_FATTURE_FOLDER_ID


def start_background_sync(db) -> bool:
    """Avvia un sync in background. Ritorna False se ce n'è già uno in corso."""
    global _bg_task
    if _sync_lock.locked() or _rebuild_lock.locked():
        return False
    _bg_task = asyncio.create_task(sync(db))
    return True


def start_background_rebuild(db, *, reset: bool = False) -> bool:
    """Avvia un lotto riprendibile senza spostare file Drive.

    Il web worker non deve tenere in memoria l'intero archivio per molti
    minuti: su istanze con memoria contenuta Render terminerebbe il processo e
    il recupero ripartirebbe sempre dal primo file. Il cursore del lotto viene
    salvato in ``drive_sync_state`` e la chiamata successiva riprende dal file
    seguente.
    """
    global _rebuild_task
    if _rebuild_lock.locked() or _sync_lock.locked():
        return False
    _rebuild_task = asyncio.create_task(
        ricostruisci_archivio_drive_lotto(db, reset=reset)
    )
    return True


def is_configured() -> bool:
    return bool(
        settings.ENABLE_DRIVE_FATTURE_SYNC
        and _folder_id()
        and (settings.GOOGLE_SERVICE_ACCOUNT_JSON_FATTURE
             or settings.GOOGLE_DRIVE_SA_FILE or settings.GOOGLE_DRIVE_SA_JSON
             or settings.GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON)
    )


def _parse_sa_json(raw: str) -> dict:
    """Parsa il JSON del service account tollerando i formati "sporchi" tipici
    del copia-incolla nelle variabili d'ambiente:
    - JSON normale (caso corretto)
    - JSON con virgolette escapate (\"type\": ...) e sequenze \n della
      private_key trasformate in "backslash + a-capo reale" — succede
      incollando il contenuto già JSON-encodato come stringa
    """
    raw = raw.strip()
    # Eventuali apici/virgolette esterne aggiunte per sbaglio
    if (raw.startswith("'") and raw.endswith("'")) or (raw.startswith('"') and raw.endswith('"')):
        raw = raw[1:-1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # De-corruzione: "backslash + newline reale" -> escape \n valido,
    # poi de-escape delle virgolette (\" -> ").
    cleaned = raw.replace('\\\n', '\\n').replace('\\"', '"')
    return json.loads(cleaned)


def _load_credentials():
    """Ritorna (credentials, None) o (None, messaggio_errore)."""
    try:
        from google.oauth2 import service_account
    except ImportError as e:
        return None, f"dipendenze google mancanti: {e}"
    try:
        shared_json = settings.GOOGLE_DRIVE_SA_JSON or settings.GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON
        if shared_json:
            info = _parse_sa_json(shared_json)
            return service_account.Credentials.from_service_account_info(info, scopes=_SCOPES), None
        return service_account.Credentials.from_service_account_file(
            settings.GOOGLE_DRIVE_SA_FILE, scopes=_SCOPES
        ), None
    except json.JSONDecodeError as e:
        return None, f"GOOGLE_DRIVE_SA_JSON non è un JSON valido: {e}"
    except Exception as e:
        return None, f"credenziali service account non valide: {e}"


def _load_credentials_fatture():
    """Account dedicato fatture se presente, altrimenti account condiviso."""
    if settings.GOOGLE_SERVICE_ACCOUNT_JSON_FATTURE:
        try:
            from google.oauth2 import service_account
            info = _parse_sa_json(settings.GOOGLE_SERVICE_ACCOUNT_JSON_FATTURE)
            return service_account.Credentials.from_service_account_info(info, scopes=_SCOPES), None
        except Exception as exc:
            return None, f"GOOGLE_SERVICE_ACCOUNT_JSON_FATTURE non valido: {exc}"
    return _load_credentials()


def _build_drive_service():
    """Costruisce il client Drive v3 da service account. None se non disponibile."""
    if not is_configured():
        return None
    creds, err = _load_credentials_fatture()
    if creds is None:
        logger.error(f"Drive ingest: {err}")
        return None
    try:
        from googleapiclient.discovery import build
        return build("drive", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:
        logger.error(f"Drive ingest: errore costruzione service: {e}")
        return None


def _close_drive_service(service) -> None:
    """Chiude connessioni HTTP Drive e forza il rilascio delle risorse native."""
    try:
        close = getattr(service, "close", None)
        if callable(close):
            close()
    except Exception:
        logger.debug("Chiusura client Drive non riuscita", exc_info=True)


def _get_or_create_folder(service, parent_id: str, folder_name: str) -> Optional[str]:
    q = (
        f"name = '{folder_name}' and '{parent_id}' in parents "
        "and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )
    res = service.files().list(
        q=q, fields="files(id)", pageSize=1,
        supportsAllDrives=True, includeItemsFromAllDrives=True,
    ).execute()
    files = res.get("files", [])
    if files:
        return files[0]["id"]
    meta = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = service.files().create(body=meta, fields="id", supportsAllDrives=True).execute()
    return folder.get("id")


def _find_folder(service, parent_id: str, folder_name: str) -> Optional[str]:
    """Trova una sottocartella senza crearla o modificare Drive."""
    q = (
        f"name = '{folder_name}' and '{parent_id}' in parents "
        "and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )
    res = service.files().list(
        q=q, fields="files(id)", pageSize=1,
        supportsAllDrives=True, includeItemsFromAllDrives=True,
    ).execute()
    files = res.get("files", [])
    return files[0]["id"] if files else None


def _source_folders(service, parent_id: str) -> List[tuple[str, str]]:
    """Cartelle da rileggere per una ricostruzione completa e non distruttiva."""
    folders = [("radice", parent_id)]
    for name in (_INBOX_FOLDER_NAME, _ELABORATE_FOLDER_NAME, _ERROR_FOLDER_NAME):
        folder_id = _find_folder(service, parent_id, name)
        if folder_id:
            folders.append((name, folder_id))
    return folders


def _get_or_create_inbox_folder(service, parent_id: str) -> Optional[str]:
    return _get_or_create_folder(service, parent_id, _INBOX_FOLDER_NAME)


def _get_or_create_elaborate_folder(service, parent_id: str) -> Optional[str]:
    return _get_or_create_folder(service, parent_id, _ELABORATE_FOLDER_NAME)


def _get_or_create_error_folder(service, parent_id: str) -> Optional[str]:
    return _get_or_create_folder(service, parent_id, _ERROR_FOLDER_NAME)


def _list_xml_files(service, parent_id: str) -> List[Dict[str, Any]]:
    q = (
        f"'{parent_id}' in parents and trashed = false "
        "and (name contains '.xml' or name contains '.XML')"
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
            fn = f["name"].lower()
            # .xml puri e .xml.p7m (buste firmate CAdES: l'XML viene
            # estratto dalla pipeline condivisa process_xml_bytes)
            if fn.endswith(".xml") or fn.endswith(".xml.p7m"):
                out.append(f)
        page_token = res.get("nextPageToken")
        if not page_token:
            break
    return out


def _download_bytes(service, file_id: str) -> bytes:
    from googleapiclient.http import MediaIoBaseDownload
    buf = io.BytesIO()
    req = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    downloader = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


def _move_to_folder(service, file_id: str, parent_id: str, target_id: str):
    service.files().update(
        fileId=file_id, addParents=target_id, removeParents=parent_id,
        fields="id, parents", supportsAllDrives=True,
    ).execute()


def _move_to_elaborate(service, file_id: str, parent_id: str, elaborate_id: str):
    _move_to_folder(service, file_id, parent_id, elaborate_id)


async def get_status(db) -> Dict[str, Any]:
    state = await db[_SYNC_STATE_COLLECTION].find_one({"_id": _SYNC_STATE_ID}) or {}
    credenziali_errore = None
    if is_configured():
        _, credenziali_errore = _load_credentials_fatture()
    return {
        "configured": is_configured(),
        "credenziali_ok": is_configured() and credenziali_errore is None,
        "credenziali_errore": credenziali_errore,
        "folder_id": _folder_id(),
        "sync_running": is_sync_running(),
        "rebuild_running": is_rebuild_running(),
        "last_sync": state.get("last_sync"),
        "last_result": state.get("last_result"),
        "last_error": state.get("last_error"),
        "total_imported": state.get("total_imported", 0),
        "last_rebuild": state.get("last_rebuild"),
        "last_rebuild_result": state.get("last_rebuild_result"),
    }


async def sync(db) -> Dict[str, Any]:
    """Esegue un ciclo di import. Se un sync è già in corso, non fa nulla."""
    if _sync_lock.locked() or _rebuild_lock.locked():
        return {"status": "running", "message": "Sincronizzazione già in corso"}
    async with _sync_lock:
        return await _do_sync(db)


async def _do_sync(db) -> Dict[str, Any]:
    if not is_configured():
        return {
            "status": "not_configured",
            "message": "Imposta GOOGLE_DRIVE_FATTURE_FOLDER_ID e il service account "
                       "(GOOGLE_DRIVE_SA_FILE o GOOGLE_DRIVE_SA_JSON).",
        }
    creds, cred_err = _load_credentials_fatture()
    if creds is None:
        return {"status": "error", "message": f"Credenziali Google Drive non valide: {cred_err}"}
    service = _build_drive_service()
    if service is None:
        return {"status": "error", "message": "Service Drive non disponibile (errore costruzione client)."}

    # Import locale per evitare import circolari con il router.
    from app.routers.invoices.fatture_upload import process_xml_bytes

    parent_id = _folder_id()
    result = {
        "status": "ok", "total": 0, "imported": 0, "duplicates": 0,
        "archiviate": 0, "errors": 0, "moved": 0, "details": [],
    }
    try:
        inbox_id = _get_or_create_inbox_folder(service, parent_id)
        elaborate_id = _get_or_create_elaborate_folder(service, parent_id)
        error_id = _get_or_create_error_folder(service, parent_id)
        source_id = inbox_id or parent_id
        xml_files = _list_xml_files(service, source_id)
        batch = _select_batch(xml_files)
        result["total"] = len(xml_files)
        result["attempted"] = len(batch)
        result["pending"] = max(len(xml_files) - len(batch), 0)
        for f in batch:
            fid, fname = f["id"], f["name"]
            try:
                content = _download_bytes(service, fid)
                # applica_filtro_anno (richiesta utente 14/07/2026): solo le
                # fatture Drive con data fattura nell'anno corrente entrano
                # nel flusso attivo (Prima Nota/scadenzario/alert/magazzino);
                # gli anni precedenti finiscono in archivio_storico, sola
                # consultazione — vedi archivia_fattura_storica.
                res = await process_xml_bytes(
                    db, content, fname, source="google_drive", applica_filtro_anno=True
                )
                st = res.get("status")
                if st == "imported":
                    result["imported"] += 1
                elif st == "duplicate":
                    result["duplicates"] += 1
                elif st == "archiviata":
                    result["archiviate"] += 1
                else:
                    result["errors"] += 1
                    result["details"].append({"file": fname, "error": res.get("error")})
                    if error_id:
                        _move_to_folder(service, fid, source_id, error_id)
                    continue
                # Sposta in `Elaborate` i file processati (importati, archiviati
                # o duplicati noti).
                if elaborate_id:
                    _move_to_elaborate(service, fid, source_id, elaborate_id)
                    result["moved"] += 1
            except Exception as e:
                logger.error(f"Drive ingest: errore su {fname}: {e}")
                result["errors"] += 1
                result["details"].append({"file": fname, "error": str(e)})
                if error_id:
                    try:
                        _move_to_folder(service, fid, source_id, error_id)
                    except Exception:
                        logger.exception("Drive ingest: impossibile spostare %s in Errori", fname)
    except Exception as e:
        logger.error(f"Drive ingest: errore sync: {e}")
        # Persisti l'errore globale: il sync gira in background e la card
        # Admin lo legge dallo stato, non dalla risposta HTTP.
        await db[_SYNC_STATE_COLLECTION].update_one(
            {"_id": _SYNC_STATE_ID},
            {"$set": {
                "last_sync": datetime.now(timezone.utc).isoformat(),
                "last_error": str(e),
            }},
            upsert=True,
        )
        return {"status": "error", "message": str(e)}

    prev = await db[_SYNC_STATE_COLLECTION].find_one({"_id": _SYNC_STATE_ID}) or {}
    last_result = {k: result[k] for k in (
        "total", "attempted", "pending", "imported", "duplicates",
        "archiviate", "errors", "moved",
    )}
    # Persisti i primi errori per-file: senza, la card Admin mostra solo il
    # conteggio e la diagnosi è impossibile.
    last_result["details"] = result["details"][:5]
    await db[_SYNC_STATE_COLLECTION].update_one(
        {"_id": _SYNC_STATE_ID},
        {"$set": {
            "last_sync": datetime.now(timezone.utc).isoformat(),
            "last_result": last_result,
            "last_error": None,
            "total_imported": prev.get("total_imported", 0) + result["imported"],
        }},
        upsert=True,
    )
    return result


def _safe_rebuild_batch_size(value: int) -> int:
    """Limita i lotti web per non saturare memoria o timeout del servizio."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = _WEB_REBUILD_BATCH_SIZE
    return max(1, min(parsed, 20))


async def ricostruisci_archivio_drive_lotto(
    db,
    *,
    batch_size: int = _WEB_REBUILD_BATCH_SIZE,
    reset: bool = False,
) -> Dict[str, Any]:
    """Ricostruisce un lotto ordinato e persiste un cursore riprendibile.

    La scansione comprende radice, ``Da elaborare``, ``Elaborate`` ed
    ``Errori`` e non modifica mai Drive. I file sono ordinati per ID Drive:
    dopo ogni lotto viene memorizzato l'ultimo ID completato. Un riavvio del
    servizio può quindi ripetere al massimo il lotto corrente (la pipeline è
    idempotente), senza ricominciare l'intero archivio.
    """
    if _rebuild_lock.locked() or _sync_lock.locked():
        return {"status": "running", "message": "Ricostruzione gia' in corso"}

    async with _rebuild_lock:
        if not is_configured():
            return {"status": "not_configured", "message": "Drive fatture non configurato"}
        creds, cred_err = _load_credentials_fatture()
        if creds is None:
            return {"status": "error", "message": f"Credenziali non valide: {cred_err}"}
        service = _build_drive_service()
        if service is None:
            return {"status": "error", "message": "Service Drive non disponibile"}

        from app.routers.invoices.fatture_upload import process_xml_bytes

        state = await db[_SYNC_STATE_COLLECTION].find_one({"_id": _SYNC_STATE_ID}) or {}
        previous = state.get("last_rebuild_result") or {}
        can_resume = (
            not reset
            and previous.get("status") in {"pending", "running", "processing"}
            and (
                bool(previous.get("cursor"))
                or (
                    previous.get("status") == "processing"
                    and isinstance(previous.get("inflight"), dict)
                    and bool(previous["inflight"].get("id"))
                )
            )
        )
        cursor = str(previous.get("cursor")) if can_resume else None
        started_at = (
            previous.get("started_at") if can_resume
            else datetime.now(timezone.utc).isoformat()
        )
        counters = {
            key: int(previous.get(key, 0) or 0) if can_resume else 0
            for key in ("imported", "duplicates", "archiviate", "errors")
        }
        folders: Dict[str, int] = {}
        details: List[Dict[str, str]] = list(previous.get("details") or [])[-10:]
        crashed_inflight = previous.get("inflight") if can_resume else None

        try:
            unique_files: Dict[str, Dict[str, Any]] = {}
            for folder_name, folder_id in _source_folders(service, _folder_id()):
                files = await asyncio.to_thread(_list_xml_files, service, folder_id)
                folders[folder_name] = len(files)
                for file_info in files:
                    unique_files.setdefault(file_info["id"], file_info)

            ordered = sorted(unique_files.values(), key=lambda item: str(item["id"]))

            # Se il processo e' terminato mentre un file era marcato in
            # lavorazione, quel documento e' il candidato certo del crash.
            # L'originale resta su Drive, viene contato e mostrato come errore,
            # ma il cursore avanza per non bloccare l'intera ricostruzione.
            if (
                previous.get("status") == "processing"
                and isinstance(crashed_inflight, dict)
                and crashed_inflight.get("id")
                and str(crashed_inflight["id"]) > str(cursor or "")
            ):
                cursor = str(crashed_inflight["id"])
                counters["errors"] += 1
                details.append({
                    "file": str(crashed_inflight.get("name") or cursor),
                    "error": "processo interrotto durante il parsing; originale Drive conservato",
                })

            if cursor:
                remaining = [item for item in ordered if str(item["id"]) > cursor]
            else:
                remaining = ordered
            already_processed = len(ordered) - len(remaining)
            batch = remaining[:_safe_rebuild_batch_size(batch_size)]

            for file_info in batch:
                content = None
                outcome = None
                inflight_checkpoint: Dict[str, Any] = {
                    "status": "processing",
                    "total": len(ordered),
                    "processed": already_processed,
                    "pending": max(len(ordered) - already_processed, 0),
                    **counters,
                    "folders": folders,
                    "cursor": cursor,
                    "inflight": {
                        "id": str(file_info["id"]),
                        "name": str(file_info["name"]),
                    },
                    "batch_size": _safe_rebuild_batch_size(batch_size),
                    "started_at": started_at,
                    "details": details[-10:],
                }
                await db[_SYNC_STATE_COLLECTION].update_one(
                    {"_id": _SYNC_STATE_ID},
                    {"$set": {"last_rebuild_result": inflight_checkpoint}},
                    upsert=True,
                )
                try:
                    content = await asyncio.to_thread(
                        _download_bytes, service, file_info["id"],
                    )
                    outcome = await process_xml_bytes(
                        db,
                        content,
                        file_info["name"],
                        source="ricostruzione_drive",
                        applica_filtro_anno=True,
                        replay_storico=True,
                    )
                    status = outcome.get("status")
                    if status == "imported":
                        counters["imported"] += 1
                    elif status == "duplicate":
                        counters["duplicates"] += 1
                    elif status == "archiviata":
                        counters["archiviate"] += 1
                    else:
                        counters["errors"] += 1
                        details.append({
                            "file": file_info["name"],
                            "error": str(outcome.get("error") or "errore")[:200],
                        })
                except Exception as exc:
                    logger.exception(
                        "Ricostruzione Drive a lotti: errore sul file %s",
                        file_info["name"],
                    )
                    counters["errors"] += 1
                    details.append({
                        "file": file_info["name"], "error": str(exc)[:200],
                    })
                finally:
                    # Non trattenere XML/parsing tra un documento e il successivo.
                    content = None
                    outcome = None
                cursor = str(file_info["id"])
                already_processed += 1
                await asyncio.sleep(0)

            processed = already_processed
            pending = max(len(ordered) - processed, 0)
            completed = pending == 0
            completed_at = datetime.now(timezone.utc).isoformat() if completed else None
            checkpoint: Dict[str, Any] = {
                "status": "ok" if completed else "pending",
                "total": len(ordered),
                "processed": processed,
                "pending": pending,
                **counters,
                "folders": folders,
                "cursor": cursor,
                "batch_processed": len(batch),
                "batch_size": _safe_rebuild_batch_size(batch_size),
                "started_at": started_at,
                "details": details[:10],
            }
            update: Dict[str, Any] = {"last_rebuild_result": checkpoint}
            if completed_at:
                update["last_rebuild"] = completed_at
            await db[_SYNC_STATE_COLLECTION].update_one(
                {"_id": _SYNC_STATE_ID}, {"$set": update}, upsert=True,
            )
            return checkpoint
        except Exception as exc:
            logger.exception("Ricostruzione Drive a lotti fallita")
            checkpoint = {
                "status": "error",
                "message": str(exc)[:300],
                "cursor": cursor,
                "started_at": started_at,
                **counters,
                "folders": folders,
            }
            await db[_SYNC_STATE_COLLECTION].update_one(
                {"_id": _SYNC_STATE_ID},
                {"$set": {"last_rebuild_result": checkpoint}},
                upsert=True,
            )
            return checkpoint
        finally:
            await asyncio.to_thread(_close_drive_service, service)
            gc.collect()


_STATI_RICOSTRUZIONE_INCOMPLETA = {"pending", "processing"}


async def riprendi_ricostruzione_se_incompleta(
    db, *, batch_size: int = 20,
) -> Dict[str, Any]:
    """Job periodico: porta a termine da sola una ricostruzione lasciata a meta'.

    Audit 03/09/2026: la ricostruzione avviata il 21/08 era ferma a
    ``processing`` (64 fatture su 754) perche' il lotto successivo veniva
    lanciato solo da un click in Admin; nel frattempo l'archivio ``invoices``
    era vuoto e costi, IVA a credito e debiti fornitori risultavano zero.
    Se lo stato salvato e' ``pending`` o ``processing`` esegue il lotto
    seguente (riprendibile dal cursore, idempotente, senza spostare file);
    con qualsiasi altro stato (``ok``, ``error``, mai avviata) non fa nulla.
    """
    if _rebuild_lock.locked() or _sync_lock.locked():
        return {"status": "running", "message": "Sincronizzazione o ricostruzione in corso"}
    if not is_configured():
        return {"status": "not_configured", "message": "Drive fatture non configurato"}
    state = await db[_SYNC_STATE_COLLECTION].find_one({"_id": _SYNC_STATE_ID}) or {}
    previous = state.get("last_rebuild_result") or {}
    stato = previous.get("status")
    if stato not in _STATI_RICOSTRUZIONE_INCOMPLETA:
        return {"status": "skipped", "stato_precedente": stato}
    logger.info(
        "[DRIVE-FATTURE] ricostruzione incompleta (%s, %s/%s): riprendo un lotto",
        stato, previous.get("processed"), previous.get("total"),
    )
    return await ricostruisci_archivio_drive_lotto(db, batch_size=batch_size)


async def ricostruisci_archivio_drive(db) -> Dict[str, Any]:
    """Rilegge tutti gli XML Drive e ricostruisce i record mancanti.

    Include radice, ``Da elaborare``, ``Elaborate`` ed ``Errori``. La pipeline
    fatture e' idempotente e questa procedura non chiama mai le API di move,
    delete o trash: gli originali e la loro collocazione restano invariati.
    """
    if _rebuild_lock.locked() or _sync_lock.locked():
        return {"status": "running", "message": "Ricostruzione gia' in corso"}
    async with _rebuild_lock:
        if not is_configured():
            return {"status": "not_configured", "message": "Drive fatture non configurato"}
        creds, cred_err = _load_credentials_fatture()
        if creds is None:
            return {"status": "error", "message": f"Credenziali non valide: {cred_err}"}
        service = _build_drive_service()
        if service is None:
            return {"status": "error", "message": "Service Drive non disponibile"}

        from app.routers.invoices.fatture_upload import process_xml_bytes

        result: Dict[str, Any] = {
            "status": "running", "total": 0, "processed": 0,
            "imported": 0, "duplicates": 0, "archiviate": 0, "errors": 0,
            "folders": {}, "details": [],
        }
        try:
            unique_files: Dict[str, Dict[str, Any]] = {}
            for folder_name, folder_id in _source_folders(service, _folder_id()):
                files = await asyncio.to_thread(_list_xml_files, service, folder_id)
                result["folders"][folder_name] = len(files)
                for file_info in files:
                    unique_files.setdefault(file_info["id"], file_info)
            result["total"] = len(unique_files)

            await db[_SYNC_STATE_COLLECTION].update_one(
                {"_id": _SYNC_STATE_ID},
                {"$set": {"last_rebuild_result": {
                    **{k: result[k] for k in (
                        "status", "total", "processed", "imported", "duplicates",
                        "archiviate", "errors", "folders",
                    )},
                }}},
                upsert=True,
            )

            for index, file_info in enumerate(unique_files.values(), start=1):
                try:
                    content = await asyncio.to_thread(
                        _download_bytes, service, file_info["id"],
                    )
                    outcome = await process_xml_bytes(
                        db, content, file_info["name"],
                        source="ricostruzione_drive",
                        applica_filtro_anno=True,
                        replay_storico=True,
                    )
                    status = outcome.get("status")
                    if status == "imported":
                        result["imported"] += 1
                    elif status == "duplicate":
                        result["duplicates"] += 1
                    elif status == "archiviata":
                        result["archiviate"] += 1
                    else:
                        result["errors"] += 1
                        if len(result["details"]) < 20:
                            result["details"].append({
                                "file": file_info["name"],
                                "error": str(outcome.get("error") or "errore")[:200],
                            })
                except Exception as exc:
                    logger.exception(
                        "Ricostruzione Drive: errore sul file %s", file_info["name"],
                    )
                    result["errors"] += 1
                    if len(result["details"]) < 20:
                        result["details"].append({
                            "file": file_info["name"], "error": str(exc)[:200],
                        })
                result["processed"] = index

                # Checkpoint visibile in Admin senza una scrittura Sheets per
                # ogni singolo documento.
                if index % 25 == 0 or index == result["total"]:
                    checkpoint = {k: result[k] for k in (
                        "status", "total", "processed", "imported", "duplicates",
                        "archiviate", "errors", "folders",
                    )}
                    await db[_SYNC_STATE_COLLECTION].update_one(
                        {"_id": _SYNC_STATE_ID},
                        {"$set": {"last_rebuild_result": checkpoint}},
                        upsert=True,
                    )
                await asyncio.sleep(0)
        except Exception as exc:
            logger.exception("Ricostruzione completa Drive fallita")
            result["status"] = "error"
            result["message"] = str(exc)[:300]
        else:
            result["status"] = "ok"

        completed_at = datetime.now(timezone.utc).isoformat()
        final_result = {k: result[k] for k in (
            "status", "total", "processed", "imported", "duplicates",
            "archiviate", "errors", "folders",
        )}
        await db[_SYNC_STATE_COLLECTION].update_one(
            {"_id": _SYNC_STATE_ID},
            {"$set": {
                "last_rebuild": completed_at,
                "last_rebuild_result": final_result,
            }},
            upsert=True,
        )
        return result


# ============================================================================
# QUADRATURA ELABORATE ↔ GESTIONALE (doppio controllo)
# ============================================================================
# I file elaborati vengono spostati nella sottocartella Drive "Elaborate":
# da li' il sync normale non li guarda piu'. Se un import fosse andato storto
# a meta' (file spostato ma record non scritto), quella fattura resterebbe
# invisibile per sempre. Questa verifica ripassa TUTTI i file di Elaborate
# nella stessa pipeline idempotente:
#   - record gia' presente  -> "duplicate"  -> quadra, nessuna azione
#   - record MANCANTE       -> viene importato ORA (recupero automatico)
#   - parse fallito          -> segnalato nei dettagli
# Non sposta ne' modifica nessun file: Elaborate resta l'archivio.

async def verifica_quadratura_elaborate(db) -> Dict[str, Any]:
    """Doppio controllo: ogni file in Elaborate deve avere la sua fattura nel
    gestionale. I buchi vengono recuperati automaticamente (import idempotente).
    """
    if not is_configured():
        return {"status": "not_configured",
                "message": "Configura prima il service account e la cartella Drive."}
    creds, cred_err = _load_credentials_fatture()
    if creds is None:
        return {"status": "error", "message": f"Credenziali non valide: {cred_err}"}
    service = _build_drive_service()
    if service is None:
        return {"status": "error", "message": "Service Drive non disponibile."}

    from app.routers.invoices.fatture_upload import process_xml_bytes

    parent_id = _folder_id()
    esito: Dict[str, Any] = {
        "status": "ok", "totale_file_elaborate": 0,
        "quadrati": 0, "recuperati": 0, "errori": 0,
        "dettaglio_recuperati": [], "dettaglio_errori": [],
    }
    try:
        elaborate_id = _get_or_create_elaborate_folder(service, parent_id)
        if not elaborate_id:
            return {"status": "error", "message": "Cartella Elaborate non trovata."}

        files = _list_xml_files(service, elaborate_id)
        esito["totale_file_elaborate"] = len(files)

        for f in files:
            fid, fname = f["id"], f["name"]
            try:
                content = _download_bytes(service, fid)
                # Stesso filtro anno di _do_sync: un buco riparato qui non
                # deve "ripescare" nel flusso attivo una fattura storica già
                # correttamente archiviata (o mai vista) — vedi archivia_fattura_storica.
                res = await process_xml_bytes(
                    db, content, fname, source="quadratura_drive", applica_filtro_anno=True
                )
                st = res.get("status")
                if st == "duplicate":
                    esito["quadrati"] += 1
                elif st in ("imported", "archiviata"):
                    # BUCO TROVATO E RIPARATO: il file era in Elaborate ma la
                    # fattura non esisteva nel gestionale.
                    esito["recuperati"] += 1
                    if len(esito["dettaglio_recuperati"]) < 50:
                        esito["dettaglio_recuperati"].append(fname)
                else:
                    esito["errori"] += 1
                    if len(esito["dettaglio_errori"]) < 20:
                        esito["dettaglio_errori"].append({"file": fname, "errore": res.get("error")})
            except Exception as e:
                esito["errori"] += 1
                if len(esito["dettaglio_errori"]) < 20:
                    esito["dettaglio_errori"].append({"file": fname, "errore": str(e)[:200]})
    except Exception as e:
        logger.error(f"Quadratura Elaborate: errore: {e}")
        return {"status": "error", "message": str(e)}

    # Se sono stati trovati buchi, genera un avviso: non deve mai passare
    # inosservato che dei file "elaborati" non avevano il loro record.
    if esito["recuperati"] > 0 or esito["errori"] > 0:
        try:
            from app.services.alert_engine import genera_alert
            await genera_alert(
                "DOC_QUADRATURA_DRIVE", "drive_fatture", "documents_inbox",
                f"Quadratura Drive Elaborate: {esito['recuperati']} fatture recuperate "
                f"(erano archiviate senza record nel gestionale), {esito['errori']} file in errore. "
                f"Recuperate: {', '.join(esito['dettaglio_recuperati'][:10])}",
                db,
            )
        except Exception:
            logger.exception("Quadratura: errore generazione alert")

    # Persisti l'ultima quadratura nello stato del sync (visibile in Admin).
    await db[_SYNC_STATE_COLLECTION].update_one(
        {"_id": _SYNC_STATE_ID},
        {"$set": {
            "last_quadratura": datetime.now(timezone.utc).isoformat(),
            "last_quadratura_result": {k: esito[k] for k in
                                        ("totale_file_elaborate", "quadrati", "recuperati", "errori")},
        }},
        upsert=True,
    )
    return esito
