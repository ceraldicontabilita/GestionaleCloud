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
import io
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from app.config import settings

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/drive"]
_ELABORATE_FOLDER_NAME = "Elaborate"
_SYNC_STATE_COLLECTION = "drive_sync_state"
_SYNC_STATE_ID = "fatture_drive"

# Un solo sync alla volta (manuale + job 15 min non devono sovrapporsi).
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
        settings.GOOGLE_DRIVE_FATTURE_FOLDER_ID
        and (settings.GOOGLE_DRIVE_SA_FILE or settings.GOOGLE_DRIVE_SA_JSON)
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
        if settings.GOOGLE_DRIVE_SA_JSON:
            info = _parse_sa_json(settings.GOOGLE_DRIVE_SA_JSON)
            return service_account.Credentials.from_service_account_info(info, scopes=_SCOPES), None
        return service_account.Credentials.from_service_account_file(
            settings.GOOGLE_DRIVE_SA_FILE, scopes=_SCOPES
        ), None
    except json.JSONDecodeError as e:
        return None, f"GOOGLE_DRIVE_SA_JSON non è un JSON valido: {e}"
    except Exception as e:
        return None, f"credenziali service account non valide: {e}"


def _build_drive_service():
    """Costruisce il client Drive v3 da service account. None se non disponibile."""
    if not is_configured():
        return None
    creds, err = _load_credentials()
    if creds is None:
        logger.error(f"Drive ingest: {err}")
        return None
    try:
        from googleapiclient.discovery import build
        return build("drive", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:
        logger.error(f"Drive ingest: errore costruzione service: {e}")
        return None


def _get_or_create_elaborate_folder(service, parent_id: str) -> Optional[str]:
    q = (
        f"name = '{_ELABORATE_FOLDER_NAME}' and '{parent_id}' in parents "
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
        "name": _ELABORATE_FOLDER_NAME,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = service.files().create(body=meta, fields="id", supportsAllDrives=True).execute()
    return folder.get("id")


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


def _move_to_elaborate(service, file_id: str, parent_id: str, elaborate_id: str):
    service.files().update(
        fileId=file_id, addParents=elaborate_id, removeParents=parent_id,
        fields="id, parents", supportsAllDrives=True,
    ).execute()


async def get_status(db) -> Dict[str, Any]:
    state = await db[_SYNC_STATE_COLLECTION].find_one({"_id": _SYNC_STATE_ID}) or {}
    credenziali_errore = None
    if is_configured():
        _, credenziali_errore = _load_credentials()
    return {
        "configured": is_configured(),
        "credenziali_ok": is_configured() and credenziali_errore is None,
        "credenziali_errore": credenziali_errore,
        "folder_id": settings.GOOGLE_DRIVE_FATTURE_FOLDER_ID,
        "sync_running": is_sync_running(),
        "last_sync": state.get("last_sync"),
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
            "message": "Imposta GOOGLE_DRIVE_FATTURE_FOLDER_ID e il service account "
                       "(GOOGLE_DRIVE_SA_FILE o GOOGLE_DRIVE_SA_JSON).",
        }
    creds, cred_err = _load_credentials()
    if creds is None:
        return {"status": "error", "message": f"Credenziali Google Drive non valide: {cred_err}"}
    service = _build_drive_service()
    if service is None:
        return {"status": "error", "message": "Service Drive non disponibile (errore costruzione client)."}

    # Import locale per evitare import circolari con il router.
    from app.routers.invoices.fatture_upload import process_xml_bytes

    parent_id = settings.GOOGLE_DRIVE_FATTURE_FOLDER_ID
    result = {
        "status": "ok", "total": 0, "imported": 0, "duplicates": 0,
        "errors": 0, "moved": 0, "details": [],
    }
    try:
        elaborate_id = _get_or_create_elaborate_folder(service, parent_id)
        xml_files = _list_xml_files(service, parent_id)
        result["total"] = len(xml_files)
        for f in xml_files:
            fid, fname = f["id"], f["name"]
            try:
                content = _download_bytes(service, fid)
                res = await process_xml_bytes(db, content, fname, source="google_drive")
                st = res.get("status")
                if st == "imported":
                    result["imported"] += 1
                elif st == "duplicate":
                    result["duplicates"] += 1
                else:
                    result["errors"] += 1
                    result["details"].append({"file": fname, "error": res.get("error")})
                    continue  # non spostare i file in errore: restano per il retry
                # Sposta in `Elaborate` i file processati (importati o duplicati noti).
                if elaborate_id:
                    _move_to_elaborate(service, fid, parent_id, elaborate_id)
                    result["moved"] += 1
            except Exception as e:
                logger.error(f"Drive ingest: errore su {fname}: {e}")
                result["errors"] += 1
                result["details"].append({"file": fname, "error": str(e)})
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
    last_result = {k: result[k] for k in ("total", "imported", "duplicates", "errors", "moved")}
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
    creds, cred_err = _load_credentials()
    if creds is None:
        return {"status": "error", "message": f"Credenziali non valide: {cred_err}"}
    service = _build_drive_service()
    if service is None:
        return {"status": "error", "message": "Service Drive non disponibile."}

    from app.routers.invoices.fatture_upload import process_xml_bytes

    parent_id = settings.GOOGLE_DRIVE_FATTURE_FOLDER_ID
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
                res = await process_xml_bytes(db, content, fname, source="quadratura_drive")
                st = res.get("status")
                if st == "duplicate":
                    esito["quadrati"] += 1
                elif st == "imported":
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
