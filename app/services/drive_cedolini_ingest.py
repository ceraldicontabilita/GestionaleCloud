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
import io
import logging
import posixpath
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Dict, Any, Iterator, Optional, List, Tuple

from app.config import settings
# Riuso degli helper del modulo fatture Drive (stesso service account,
# stessa gestione Elaborate): sono funzioni parametrizzate sul folder id,
# quindi utilizzabili così come sono senza toccare quel modulo.
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
    """Estrae ricorsivamente tutti i PDF da uno ZIP, preservando il path.

    L'iteratore mantiene in memoria solo il membro corrente. I limiti sono gli
    stessi anti zip-bomb usati dagli upload del gestionale.
    """
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
        "source_path": source_path or filename,
        "source_container": source_container,
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
    """Visita tutte le sottocartelle Drive e conserva il percorso relativo."""
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
    """Compatibilita' per la quadratura: ora include anche le sottocartelle."""
    return _list_source_files_recursive(service, parent_id, include_archives=False)


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
        "errors": 0, "moved": 0, "details": [],
    }
    try:
        inbox_id = _get_or_create_inbox_folder(service, parent_id)
        elaborate_id = _get_or_create_elaborate_folder(service, parent_id)
        error_id = _get_or_create_error_folder(service, parent_id)
        source_id = inbox_id or parent_id
        source_files = _list_source_files_recursive(service, source_id)
        result["source_files"] = len(source_files)
        for f in source_files:
            fid, fname = f["id"], f["name"]
            source_parent_id = f.get("parent_id") or source_id
            relative_path = f.get("relative_path") or fname
            try:
                content = _download_bytes(service, fid)
                if not content:
                    result["errors"] += 1
                    result["details"].append({"file": fname, "error": "file vuoto"})
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
                    # Evento documento acquisito (stesso pattern del monitor email)
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
                # Sposta in `Elaborate` i file processati (importati o duplicati noti).
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
            result["cedolini_processati"] = 0
            result["parser_errors"] = []
            # La pipeline legge lotti da 100: svuotali tutti. Gli errori parser
            # vengono marcati e saltati ai giri successivi, senza bloccare la coda.
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
    last_result["cedolini_processati"] = result.get("cedolini_processati", 0)
    last_result["parser_errors"] = len(result.get("parser_errors", []))
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


async def verifica_quadratura_elaborate(db) -> Dict[str, Any]:
    """Doppio controllo Elaborate ↔ gestionale per i CEDOLINI.

    Ripassa TUTTI i PDF archiviati nella sottocartella "Elaborate" e verifica
    che ognuno abbia il suo documento nel gestionale (dedup per impronta md5,
    la stessa dell'import): presente = quadrato, assente = buco recuperato
    (re-import nella stessa pipeline). Non sposta file, niente doppioni.
    """
    if not is_configured():
        return {"status": "not_configured"}
    service = _build_drive_service()
    if service is None:
        return {"status": "error", "message": "Service Drive non disponibile"}

    parent_id = _folder_id()
    esito = {"status": "ok", "controllati": 0, "quadrati": 0,
             "recuperati": 0, "errori": 0, "details": []}
    try:
        elaborate_id = _get_or_create_elaborate_folder(service, parent_id)
        if not elaborate_id:
            return {"status": "ok", "message": "Nessuna cartella Elaborate", **esito}
        recuperati_da_processare = 0
        for f in _list_source_files_recursive(service, elaborate_id):
            try:
                content = _download_bytes(service, f["id"])
                if not content:
                    esito["errori"] += 1
                    continue
                relative_path = f.get("relative_path") or f["name"]
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
                esito["details"].append({"source_path": f.get("relative_path"), "error": str(e)})
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
        {"$set": {"last_quadratura": {"quando": now, **{k: esito[k] for k in ('controllati', 'quadrati', 'recuperati', 'errori')}}}},
        upsert=True,
    )
    return esito


# Sotto quante ore un documento non ancora processato non è un "buco" ma
# semplicemente in attesa del prossimo giro schedulato (orario).
_ORE_SOGLIA_BLOCCATO = 6


async def verifica_documenti_bloccati(db) -> Dict[str, Any]:
    """Richiesta utente 15/07/2026: "sii sicuro che tutti i cedolini che ci
    sono sono stati caricati in contabilità" — verifica_quadratura_elaborate
    controlla solo Drive ↔ documents_inbox (il file è arrivato nel
    gestionale), ma NON che sia davvero diventato un cedolino vero in
    `cedolini` (parsing PDF fallito, dipendente non riconosciuto, o
    eccezione nella pipeline lasciano il documento con `processed=False`
    per sempre, senza nessun avviso).

    Ripassa i due punti di ingresso reali dei cedolini (Drive → documents_inbox
    categoria "busta_paga"; email → cedolini_email_attachments) e segnala
    quelli MAI marcati come processati oltre la soglia (non un semplice "in
    attesa del prossimo giro orario"). Sola lettura: non tocca né riprocessa
    nulla, la riparazione resta un'azione esplicita (drive_sync /
    quadratura)."""
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
