"""Ingest generico di documenti da cartelle Drive dedicate -> documents_inbox.

Il motore lavora soltanto nelle cartelle lifecycle ``DA ELABORARE`` del
canale. Non scandisce ricorsivamente la radice e non attraversa archivi,
``ELABORATE``, ``ERRORI`` o cartelle di lavoro laterali.

Profondita' intenzionale per canale:
- bonifico: 2 livelli, per ``BONIFICI DIPENDENTI/<dipendente>/DA ELABORARE``;
- verbale: 1 livello, per ``VERBALI_AUTO/DA ELABORARE`` senza entrare nelle
  viste ``01_VERBALI``, ``02_NOTIFICHE``, ``03_PAGAMENTI`` ecc.;
- canali fiscali generici: 1 livello salvo futura struttura verificata.

Ogni documento elaborato resta nello stesso fascicolo logico: l'eventuale
``ELABORATE``/``ERRORI`` viene risolto sotto il medesimo parent dell'inbox.
"""
import asyncio
import base64
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.config import settings
from app.constants.tipi_documento import set_tassonomia_documento
from app.services.drive_folder_registry import get_folder_id
from app.services.drive_invoice_ingest import (
    _close_drive_service,
    _download_bytes,
    _get_or_create_elaborate_folder,
    _get_or_create_error_folder,
    _get_or_create_inbox_folder,
    _load_credentials,
    _move_to_folder,
    _move_to_elaborate,
)
from app.services.drive_lifecycle_tree import (
    discover_lifecycle_folders,
    resolve_inboxes_or_legacy,
)
from app.services.fiscal_document_ingestion import FiscalDocumentIngestionService

logger = logging.getLogger(__name__)


CANALI: Dict[str, Dict[str, Any]] = {
    "bonifico": {
        "category": "bonifico",
        "label": "Bonifici effettuati",
        "folder": lambda s: s.GOOGLE_DRIVE_BONIFICI_FOLDER_ID or get_folder_id("bonifico"),
        "enable": lambda s: s.ENABLE_DRIVE_BONIFICI_SYNC,
        "lifecycle_depth": 2,
    },
    "dichiarazione_iva": {
        "category": "dichiarazione_iva",
        "label": "Dichiarazioni IVA",
        "folder": lambda s: s.GOOGLE_DRIVE_DICHIARAZIONI_IVA_FOLDER_ID or get_folder_id("dichiarazione_iva"),
        "enable": lambda s: s.ENABLE_DRIVE_DICHIARAZIONI_IVA_SYNC,
        "lifecycle_depth": 1,
    },
    "cartella_esattoriale": {
        "category": "cartella_esattoriale",
        "label": "Cartelle Esattoriali",
        "folder": lambda s: (
            s.GOOGLE_DRIVE_CARTELLE_ESATTORIALI_FOLDER_ID
            or get_folder_id("cartella_esattoriale")
        ),
        "enable": lambda s: s.ENABLE_DRIVE_CARTELLE_ESATTORIALI_SYNC,
        "lifecycle_depth": 1,
    },
    "avviso_bonario": {
        "category": "avviso_bonario",
        "label": "Avvisi Bonari",
        "folder": lambda s: s.GOOGLE_DRIVE_AVVISI_BONARI_FOLDER_ID or get_folder_id("avviso_bonario"),
        "enable": lambda s: s.ENABLE_DRIVE_AVVISI_BONARI_SYNC,
        "lifecycle_depth": 1,
    },
    "verbale": {
        "category": "verbale",
        "label": "Verbali e avvisi PagoPA",
        "folder": lambda s: s.DRIVE_VERBALI_FOLDER_ID or get_folder_id("verbale"),
        "enable": lambda s: s.ENABLE_DRIVE_VERBALI_SYNC,
        "lifecycle_depth": 1,
    },
}

_locks: Dict[str, asyncio.Lock] = {c: asyncio.Lock() for c in CANALI}
_GENERIC_BATCH_SIZE = 25


def _batch_size() -> int:
    """Massimo documenti elaborati per canale in un singolo ciclo."""
    return _GENERIC_BATCH_SIZE


def _folder_id(canale: str) -> Optional[str]:
    return CANALI[canale]["folder"](settings)


def is_enabled(canale: str) -> bool:
    return bool(CANALI[canale]["enable"](settings))


def is_configured(canale: str) -> bool:
    return bool(_folder_id(canale))


def _lifecycle_depth(canale: str) -> int:
    return int(CANALI[canale].get("lifecycle_depth", 1))


def _build_drive_service():
    """Client Drive condiviso, indipendente dalla configurazione Cedolini."""
    creds, err = _load_credentials()
    if creds is None:
        return None, err
    try:
        from googleapiclient.discovery import build

        return build("drive", "v3", credentials=creds, cache_discovery=False), None
    except Exception as exc:
        return None, f"errore costruzione client Drive: {exc}"


def _list_pdf_files_direct(service, parent_id: str) -> List[Dict[str, Any]]:
    """Elenca solo PDF figli DIRETTI dell'inbox, mai sottocartelle."""
    q = (
        f"'{parent_id}' in parents and trashed = false "
        "and (name contains '.pdf' or name contains '.PDF')"
    )
    out: List[Dict[str, Any]] = []
    page_token = None
    while True:
        res = service.files().list(
            q=q,
            fields="nextPageToken, files(id, name, mimeType)",
            pageSize=100,
            pageToken=page_token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        for item in res.get("files", []):
            if item.get("mimeType") == "application/vnd.google-apps.folder":
                continue
            if (item.get("name") or "").lower().endswith(".pdf"):
                out.append(item)
        page_token = res.get("nextPageToken")
        if not page_token:
            break
    return out


def _resolve_state_folder(
    service,
    lifecycle_parent_id: str,
    state: str,
) -> Optional[str]:
    """Riusa uno stato esistente anche se scritto in maiuscolo; crea solo se manca."""
    existing = discover_lifecycle_folders(
        service,
        lifecycle_parent_id,
        max_depth=1,
        states=(state,),
    )
    for item in existing:
        if item.get("lifecycle_parent_id") == lifecycle_parent_id:
            return item.get("folder_id")

    if state == "elaborate":
        return _get_or_create_elaborate_folder(service, lifecycle_parent_id)
    if state == "error":
        return _get_or_create_error_folder(service, lifecycle_parent_id)
    raise ValueError(f"Stato lifecycle non supportato: {state}")


def _build_inbox_doc(
    content: bytes,
    filename: str,
    canale: str,
    *,
    drive_file_id: Optional[str] = None,
    source_path: Optional[str] = None,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    conf = CANALI[canale]
    doc = {
        "id": __import__("uuid").uuid4().hex,
        "filename": filename,
        "pdf_data": base64.b64encode(content).decode(),
        "file_hash": hashlib.md5(content).hexdigest(),
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
        "fonte": f"drive_{canale}",
        "source": f"drive_{canale}",
        "drive_file_id": drive_file_id,
        "source_path": source_path or filename,
        "stato": "importato",
        "status": "nuovo",
        "processed": False,
        "xml_processed": True,
        "created_at": now,
        "downloaded_at": now,
        "company_id": settings.FISCAL_COMPANY_ID,
    }
    return set_tassonomia_documento(doc, conf["category"], label=conf["label"])


async def sync(db, canale: str) -> Dict[str, Any]:
    """Esegue un ciclo di import per un canale configurato."""
    if canale not in CANALI:
        return {"status": "error", "message": f"Canale sconosciuto: {canale}"}
    if not is_enabled(canale):
        return {"status": "disabled", "message": f"Canale {canale} spento"}
    if not is_configured(canale):
        return {
            "status": "not_configured",
            "message": f"Imposta la cartella Drive del canale {canale} su Render.",
        }
    lock = _locks[canale]
    if lock.locked():
        return {"status": "running", "message": "Sincronizzazione gia' in corso"}
    async with lock:
        return await _do_sync(db, canale)


async def _do_sync(db, canale: str) -> Dict[str, Any]:
    service, service_error = _build_drive_service()
    if service is None:
        return {
            "status": "error",
            "message": f"Service Drive non disponibile: {service_error or 'errore sconosciuto'}",
        }

    root_id = _folder_id(canale)
    result: Dict[str, Any] = {
        "status": "ok",
        "canale": canale,
        "total": 0,
        "processed": 0,
        "pending_estimate": 0,
        "imported": 0,
        "duplicates": 0,
        "errors": 0,
        "moved": 0,
        "inboxes": 0,
        "details": [],
    }

    try:
        inboxes = resolve_inboxes_or_legacy(
            service,
            root_id,
            _get_or_create_inbox_folder,
            max_depth=_lifecycle_depth(canale),
        )
        result["inboxes"] = len(inboxes)
        remaining = _batch_size()

        for inbox in inboxes:
            source_id = inbox["inbox_id"]
            lifecycle_parent_id = inbox["lifecycle_parent_id"]
            relative_inbox = inbox.get("relative_path") or "DA ELABORARE"
            elaborate_id = _resolve_state_folder(service, lifecycle_parent_id, "elaborate")
            error_id = _resolve_state_folder(service, lifecycle_parent_id, "error")
            pdf_files = _list_pdf_files_direct(service, source_id)
            result["total"] += len(pdf_files)

            selected = pdf_files[:remaining] if remaining > 0 else []
            result["pending_estimate"] += max(0, len(pdf_files) - len(selected))

            for file_info in selected:
                remaining -= 1
                result["processed"] += 1
                fid = file_info["id"]
                fname = file_info["name"]
                source_path = f"{relative_inbox}/{fname}"
                try:
                    content = _download_bytes(service, fid)
                    if not content:
                        result["errors"] += 1
                        result["details"].append({"source_path": source_path, "error": "file vuoto"})
                        if error_id:
                            _move_to_folder(service, fid, source_id, error_id)
                        continue

                    content_hash = hashlib.sha256(content).hexdigest()
                    legacy_md5 = hashlib.md5(content).hexdigest()
                    existing = await db["documents_inbox"].find_one(
                        {
                            "$or": [
                                {"sha256": content_hash},
                                {"file_hash": content_hash},
                                {"file_hash": legacy_md5},
                            ]
                        },
                        {"_id": 0, "id": 1, "fiscal_document_id": 1},
                    )

                    if existing:
                        result["duplicates"] += 1
                        document_id = existing["id"]
                    else:
                        doc = _build_inbox_doc(
                            content,
                            fname,
                            canale,
                            drive_file_id=fid,
                            source_path=source_path,
                        )
                        await db["documents_inbox"].insert_one(doc)

                        if canale in {
                            "dichiarazione_iva",
                            "cartella_esattoriale",
                            "avviso_bonario",
                        }:
                            registered = await FiscalDocumentIngestionService(db).ingest(
                                content=content,
                                filename=fname,
                                source=f"drive_{canale}",
                                category_hint=CANALI[canale]["category"],
                                source_metadata={
                                    "drive_file_id": fid,
                                    "source_path": source_path,
                                },
                            )
                            await db["documents_inbox"].update_one(
                                {"id": doc["id"]},
                                {
                                    "$set": {
                                        "fiscal_document_id": registered["document_id"],
                                        "fiscal_version_id": registered["version_id"],
                                    }
                                },
                            )

                        result["imported"] += 1
                        document_id = doc["id"]
                        logger.info("Drive %s: importato %s", canale, source_path)

                    if canale == "verbale":
                        from app.services.verbali_document_import import process_verbale_document

                        detail = await process_verbale_document(
                            db,
                            document_id=document_id,
                            content=content,
                            filename=fname,
                            source="drive_verbale",
                        )
                        result["details"].append({
                            "source_path": source_path,
                            "processing": detail,
                        })

                    if elaborate_id:
                        _move_to_elaborate(service, fid, source_id, elaborate_id)
                        result["moved"] += 1

                except Exception as exc:
                    logger.error("Drive %s: errore su %s: %s", canale, source_path, exc)
                    result["errors"] += 1
                    result["details"].append({"source_path": source_path, "error": str(exc)})
                    if error_id:
                        try:
                            _move_to_folder(service, fid, source_id, error_id)
                        except Exception:
                            logger.exception(
                                "Drive %s: impossibile spostare %s in Errori",
                                canale,
                                source_path,
                            )

        return result
    except Exception as exc:
        logger.exception("Drive %s: errore ciclo", canale)
        return {"status": "error", "canale": canale, "message": str(exc)}
    finally:
        _close_drive_service(service)


async def sync_tutti(db) -> Dict[str, Any]:
    """Esegue l'ingest di tutti i canali abilitati e configurati."""
    esiti = {}
    for canale in CANALI:
        if is_enabled(canale) and is_configured(canale):
            esiti[canale] = await sync(db, canale)
    return {"status": "ok", "canali": esiti}
