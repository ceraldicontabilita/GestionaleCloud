"""
Router Gestione Documenti
API per scaricare, visualizzare e processare documenti dalle email.
"""

from fastapi import APIRouter, BackgroundTasks, Query, HTTPException, Depends, UploadFile, File, Header
from app.utils.dependencies import get_current_admin_mfa_user, get_current_admin_user
from app.utils.ruoli import richiedi_admin
from fastapi.responses import StreamingResponse
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from pathlib import Path
import asyncio
import re
from decimal import Decimal, InvalidOperation
import base64
import hashlib
import uuid

from app.database import Database
from app.utils.error_handler import handle_errors
from app.services.email_document_downloader import (
    download_documents_from_email,
    DOCUMENTS_DIR,
    CATEGORIES
)
from app.services.email_monitor_service import (
    start_monitor, stop_monitor, get_monitor_status, run_full_sync
)
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/drive/fiscal/sync")
async def sincronizza_drive_fiscale_incrementale(
    _admin: Dict[str, Any] = Depends(get_current_admin_mfa_user),
) -> Dict[str, Any]:
    """Compatibilita': verifica l'indice senza importare binari in Drive/Supabase."""
    import asyncio
    from app.services.drive_document_index import get_status
    try:
        result = await asyncio.to_thread(get_status)
        return {
            **result,
            "legacy_import_disabled": True,
            "message": "Import PDF disattivato: gli originali restano su Google Drive.",
        }
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/tax-codes/status")
async def stato_codici_tributo(
    _admin: Dict[str, Any] = Depends(richiedi_admin),
) -> Dict[str, Any]:
    db = Database.get_db()
    latest = await db["tax_code_registry_versions"].find_one({}, {"_id": 0}, sort=[("fetched_at", -1)])
    return latest or {"status": "not_initialized"}


@router.get("/tax-codes")
async def elenco_codici_tributo(
    q: str = Query("", max_length=200),
    tipo_imposta: str = Query("", max_length=100),
    contesto_uso: str = Query("", max_length=100),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    _admin: Dict[str, Any] = Depends(richiedi_admin),
) -> Dict[str, Any]:
    """Consulta lo snapshot ufficiale AdE incluso, senza creare fatti contabili."""
    from app.services.tax_code_registry import search_bundled_tax_codes
    return search_bundled_tax_codes(q, tipo_imposta, contesto_uso, offset, limit)


@router.post("/tax-codes/sync")
async def sincronizza_codici_tributo(
    _admin: Dict[str, Any] = Depends(get_current_admin_mfa_user),
) -> Dict[str, Any]:
    from app.services.tax_code_registry import sync_tax_code_registry
    return await sync_tax_code_registry(Database.get_db())


@router.post("/fiscal/ingest")
async def acquisisci_documento_fiscale(
    file: UploadFile = File(...),
    expected_sha256: Optional[str] = Query(None, min_length=64, max_length=64),
    _admin: Dict[str, Any] = Depends(get_current_admin_mfa_user),
) -> Dict[str, Any]:
    """Ingresso fiscale manuale dentro Documenti, con SHA-256 e pagina prova."""
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="PDF oltre il limite di 50 MB")
    from app.services.fiscal_document_ingestion import FiscalDocumentIngestionService

    service = FiscalDocumentIngestionService(Database.get_db())
    try:
        return await service.ingest(
            content=content,
            filename=file.filename or "documento.pdf",
            source="documenti_upload",
            source_metadata={"uploaded_by": _admin.get("user_id")},
            expected_sha256=expected_sha256,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ============================================================
# ENDPOINT MONITOR EMAIL
# ============================================================

@router.post("/monitor/start")
@handle_errors
async def avvia_monitor(
    intervallo_minuti: int = Query(10, ge=1, le=60, description="Intervallo in minuti")
) -> Dict[str, Any]:
    """
    Avvia il monitoraggio automatico della posta.
    Default: controlla ogni 10 minuti.
    """
    db = Database.get_db()
    intervallo_secondi = intervallo_minuti * 60

    started = start_monitor(db, intervallo_secondi)

    return {
        "success": started,
        "message": f"Monitor avviato (ogni {intervallo_minuti} minuti)" if started else "Monitor già in esecuzione",
        "status": get_monitor_status()
    }


@router.post("/monitor/stop")
@handle_errors
async def ferma_monitor() -> Dict[str, Any]:
    """Ferma il monitoraggio automatico."""
    stopped = stop_monitor()
    return {
        "success": stopped,
        "message": "Monitor fermato",
        "status": get_monitor_status()
    }


@router.get("/monitor/status")
@handle_errors
async def stato_monitor() -> Dict[str, Any]:
    """Ritorna lo stato del monitor email."""
    db = Database.get_db()

    # Conta documenti nel DB
    total_docs = await db["documents_inbox"].count_documents({})
    processed_docs = await db["documents_inbox"].count_documents({"processed": True})

    status = get_monitor_status()
    status["database"] = {
        "documenti_totali": total_docs,
        "documenti_processati": processed_docs,
        "documenti_da_processare": total_docs - processed_docs
    }

    return status


@router.post("/monitor/sync-now")
@handle_errors
async def sync_immediato() -> Dict[str, Any]:
    """
    Esegue immediatamente un ciclo completo di sincronizzazione:
    1. Scarica nuovi documenti dalla posta
    2. Ricategorizza documenti nelle cartelle corrette
    3. Processa tutti i nuovi documenti
    """
    db = Database.get_db()
    result = await run_full_sync(db)
    return result


@router.get("/telegram/status")
@handle_errors
async def telegram_status() -> Dict[str, Any]:
    """Verifica se Telegram è configurato."""
    from app.services.telegram_notifications import is_configured, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

    configured = is_configured()

    return {
        "configurato": configured,
        "bot_token_presente": bool(TELEGRAM_BOT_TOKEN),
        "chat_id_presente": bool(TELEGRAM_CHAT_ID),
        "istruzioni": None if configured else "Aggiungi TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID nel file .env"
    }


@router.post("/telegram/test")
@handle_errors
async def telegram_test() -> Dict[str, Any]:
    """Invia un messaggio di test su Telegram."""
    from app.services.telegram_notifications import test_connection

    result = await test_connection()

    if not result.get("configured"):
        raise HTTPException(
            status_code=400,
            detail="Telegram non configurato. Aggiungi TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID in .env"
        )

    return result


_ARCHIVE_STATUSES = {"nuovo", "processato", "errore"}
#: Come ogni stato canonico e' scritto davvero in archivio: `errore_parser`
#: (376 documenti) e `elaborato` (1.417) li scrivono percorsi diversi, e con
#: il solo nome canonico la card «Errori» diceva 0.
_ARCHIVE_STATUS_VARIANTS: Dict[str, tuple] = {
    "nuovo": ("nuovo",),
    "processato": ("processato", "elaborato"),
    "errore": ("errore", "errore_parser"),
}
_ARCHIVE_STATUS_CANONICO = {
    variante: canonico
    for canonico, varianti in _ARCHIVE_STATUS_VARIANTS.items()
    for variante in varianti
}


def stato_archivio_canonico(status: Any) -> Any:
    """Lo stato canonico (nuovo/processato/errore) di una variante d'archivio."""
    return _ARCHIVE_STATUS_CANONICO.get(status, status)
_ARCHIVE_PAYLOAD_FIELDS = {
    "pdf_data": 0,
    "file_base64": 0,
    "xml_content": 0,
    "raw_content": 0,
    "content": 0,
}


def _archive_query(
    *,
    categoria: Optional[str] = None,
    status: Optional[str] = None,
    anno: Optional[int] = None,
    search: Optional[str] = None,
) -> Dict[str, Any]:
    """Costruisce filtri archivio senza interpretare la ricerca come regex.

    L'anno filtra esclusivamente il periodo/data del documento. La data email
    o di acquisizione non puo' attribuire silenziosamente un documento storico
    all'esercizio corrente.
    """
    clauses: List[Dict[str, Any]] = []
    if categoria:
        clauses.append({"category": categoria})
    if status:
        varianti = _ARCHIVE_STATUS_VARIANTS.get(status, (status,))
        clauses.append({"status": {"$in": list(varianti)}})
    if anno:
        year = str(anno)
        clauses.append({
            "$or": [
                {"anno": anno},
                {"anno": year},
                {"periodo": {"$regex": rf"^{year}"}},
                {"document_date": {"$regex": year}},
                {"data_documento": {"$regex": year}},
            ]
        })
    if search:
        literal = re.escape(search.strip())
        if literal:
            matcher = {"$regex": literal, "$options": "i"}
            clauses.append({
                "$or": [
                    {"filename": matcher},
                    {"email_subject": matcher},
                    {"email_from": matcher},
                    {"category_label": matcher},
                    {"fonte": matcher},
                    {"source": matcher},
                    {"processed_to": matcher},
                ]
            })
    if not clauses:
        return {}
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def _archive_document_metadata(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Normalizza solo metadati; payload e contenuti non escono nella lista."""
    item = dict(doc)
    for field in _ARCHIVE_PAYLOAD_FIELDS:
        item.pop(field, None)
    canonico = stato_archivio_canonico(item.get("status"))
    if canonico != item.get("status"):
        item["status_originale"] = item.get("status")
        item["status"] = canonico

    item["source_label"] = (
        item.get("fonte")
        or item.get("source")
        or ("email" if item.get("email_from") else None)
        or "non_indicata"
    )
    item["document_date_display"] = (
        item.get("document_date")
        or item.get("data_documento")
    )
    item["periodo_documentale"] = (
        item.get("periodo")
        or item.get("anno")
        or (str(item["document_date_display"])[:7] if item["document_date_display"] else None)
    )
    item["acquired_at"] = (
        item.get("email_date")
        or item.get("downloaded_at")
        or item.get("created_at")
    )
    item["archive_date"] = item["document_date_display"]
    item["size_bytes"] = item.get("size_bytes") or item.get("file_size") or 0

    anomalies: List[str] = []
    if not item.get("id"):
        anomalies.append("identificativo_mancante")
    if item.get("status") == "errore" or item.get("processing_error") or item.get("error"):
        anomalies.append("errore_elaborazione")
    if not item.get("category") or item.get("category") in {"auto", "altro"}:
        anomalies.append("classificazione_da_verificare")
    if item.get("processed") and not item.get("processed_to"):
        anomalies.append("collegamento_mancante")
    if item.get("duplicate") or item.get("is_duplicate"):
        anomalies.append("duplicato_segnalato")
    if not item.get("periodo_documentale"):
        anomalies.append("periodo_da_verificare")
    item["anomalies"] = anomalies
    item["linked_to"] = item.get("processed_to") or item.get("destinazione")
    return item


@router.get("/lista")
@handle_errors
async def lista_documenti(
    categoria: Optional[str] = Query(None, description="Filtra per categoria"),
    status: Optional[str] = Query(None, description="Filtra per status: nuovo, processato, errore"),
    anno: Optional[int] = Query(None, ge=2018, le=2100),
    search: Optional[str] = Query(None, max_length=120),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
) -> Dict[str, Any]:
    """Archivio paginato dei metadati, senza PDF/XML/Base64 nella risposta."""
    if categoria and categoria not in CATEGORIES:
        raise HTTPException(status_code=400, detail="Categoria documento non valida")
    if status and status not in _ARCHIVE_STATUSES:
        raise HTTPException(status_code=400, detail="Stato documento non valido")

    db = Database.get_db()
    query = _archive_query(
        categoria=categoria,
        status=status,
        anno=anno,
        search=search,
    )
    projection = {"_id": 0, **_ARCHIVE_PAYLOAD_FIELDS}
    documents = await db["documents_inbox"].find(query, projection).sort(
        [("downloaded_at", -1), ("created_at", -1), ("id", -1)]
    ).skip(skip).limit(limit).to_list(limit)
    documents = [_archive_document_metadata(doc) for doc in documents]

    category_pipeline: List[Dict[str, Any]] = []
    status_pipeline: List[Dict[str, Any]] = []
    if query:
        category_pipeline.append({"$match": query})
        status_pipeline.append({"$match": query})
    category_pipeline.append({"$group": {"_id": "$category", "count": {"$sum": 1}}})
    status_pipeline.append({"$group": {"_id": "$status", "count": {"$sum": 1}}})
    by_category = {
        (doc.get("_id") or "senza_categoria"): doc["count"]
        async for doc in db["documents_inbox"].aggregate(category_pipeline)
    }
    by_status: Dict[str, int] = {}
    async for doc in db["documents_inbox"].aggregate(status_pipeline):
        chiave = stato_archivio_canonico(doc.get("_id")) or "senza_stato"
        by_status[chiave] = by_status.get(chiave, 0) + doc["count"]
    total = await db["documents_inbox"].count_documents(query)

    return {
        "documents": documents,
        "total": total,
        "skip": skip,
        "limit": limit,
        "has_more": skip + len(documents) < total,
        "by_category": by_category,
        "by_status": by_status,
        "categories": CATEGORIES,
    }


_ADMINISTRATIVE_CATEGORIES = {
    "tributi_locali": {"tari_avviso", "tari_istanza_compensazione"},
    "riscossione": {"ader_sospensione", "ader_definizione_agevolata", "cartella_esattoriale"},
    "personale": {"dimissioni_telematiche"},
    "famiglia": set(),
}


@router.get("/amministrativi/familiari")
async def lista_anagrafica_familiari() -> Dict[str, Any]:
    """Anagrafica consultiva usata per smistamento e ricerca documentale."""
    from app.services.personal_family_registry import public_profiles

    return {"items": public_profiles(), "total": len(public_profiles())}


@router.get("/amministrativi")
@handle_errors
async def lista_atti_amministrativi(
    area: Optional[str] = Query(None),
    anno: Optional[int] = Query(None, ge=2018, le=2100),
    search: Optional[str] = Query(None, max_length=120),
    review_only: bool = Query(False),
    limit: int = Query(200, ge=1, le=500),
) -> Dict[str, Any]:
    """Vista documentale di TARI/AdeR e cessazioni.

    Gli atti restano evidenze documentali: nessun avviso o modulo viene
    promosso implicitamente a pagamento, chiusura o variazione del dipendente.
    I verbali stradali vivono esclusivamente nel fascicolo Noleggi/Verbali.
    """
    if area and area not in _ADMINISTRATIVE_CATEGORIES:
        raise HTTPException(status_code=400, detail="Area amministrativa non valida")

    # Drive e il relativo indice verificato sono l'archivio operativo. I PDF
    # restano su Drive; documents_inbox viene usato solo come compatibilita'
    # quando l'indice non e' configurato o temporaneamente disponibile.
    try:
        from app.services.drive_document_index import list_administrative_documents
        drive_payload = await asyncio.to_thread(
            list_administrative_documents,
            area=area,
            year=str(anno) if anno else None,
            q=search,
            review_only=review_only,
            limit=limit,
        )
        if drive_payload["overview"]["total"] > 0:
            return {
                **drive_payload,
                "payment_evidence_count": 0,
                "areas": {key: sorted(value) for key, value in _ADMINISTRATIVE_CATEGORIES.items()},
            }
    except (RuntimeError, ValueError, ImportError) as exc:
        logger.warning("Indice Drive atti amministrativi non disponibile: %s", exc)

    categories = (
        _ADMINISTRATIVE_CATEGORIES[area]
        if area
        else set().union(*_ADMINISTRATIVE_CATEGORIES.values())
    )
    clauses: List[Dict[str, Any]] = [{"category": {"$in": sorted(categories)}}]
    if anno:
        year = str(anno)
        clauses.append({"$or": [
            {"parsed_metadata.anno_tributo": anno},
            {"parsed_metadata.data_trasmissione": {"$regex": f"^{year}"}},
            {"parsed_metadata.data_decorrenza_recesso": {"$regex": f"^{year}"}},
            {"document_date": {"$regex": year}},
            {"source_context.email_date": {"$regex": f"^{year}"}},
            {"downloaded_at": {"$regex": f"^{year}"}},
        ]})
    if search and search.strip():
        matcher = {"$regex": re.escape(search.strip()), "$options": "i"}
        clauses.append({"$or": [
            {"filename": matcher}, {"category_label": matcher},
            {"parsed_metadata.lavoratore_cf": matcher},
            {"parsed_metadata.protocollo": matcher},
            {"parsed_metadata.codice_contribuente": matcher},
            {"parsed_metadata.numeri_cartella": matcher},
            {"source_context.archive_path": matcher},
        ]})
    if review_only:
        clauses.append({"parsed_metadata.requires_review": True})

    query: Dict[str, Any] = {"$and": clauses}
    projection = {"_id": 0, **_ARCHIVE_PAYLOAD_FIELDS}
    db = Database.get_db()
    filtered_total = await db["documents_inbox"].count_documents(query)
    documents = await db["documents_inbox"].find(query, projection).sort(
        [("downloaded_at", -1), ("id", -1)]
    ).limit(limit).to_list(limit)
    documents = [_archive_document_metadata(item) for item in documents]

    category_to_area = {
        category: group
        for group, group_categories in _ADMINISTRATIVE_CATEGORIES.items()
        for category in group_categories
    }
    filtered_counts = {key: 0 for key in _ADMINISTRATIVE_CATEGORIES}
    filtered_requires_review = 0
    for item in documents:
        item["administrative_area"] = category_to_area.get(item.get("category"))
        group = item.get("administrative_area")
        if group:
            filtered_counts[group] += 1
        if (item.get("parsed_metadata") or {}).get("requires_review"):
            filtered_requires_review += 1

    overview_counts: Dict[str, int] = {}
    for group, group_categories in _ADMINISTRATIVE_CATEGORIES.items():
        # ``famiglia`` e' una vista documentale separata e oggi non ha
        # categorie di documents_inbox. Supabase/PostgREST non deve ricevere
        # un filtro ``$in: []``: sul live causava il 500 dell'intera pagina.
        overview_counts[group] = (
            await db["documents_inbox"].count_documents({
                "category": {"$in": sorted(group_categories)},
            })
            if group_categories else 0
        )
    all_categories = sorted(set().union(*_ADMINISTRATIVE_CATEGORIES.values()))
    overview_requires_review = await db["documents_inbox"].count_documents({
        "category": {"$in": all_categories},
        "parsed_metadata.requires_review": True,
    })

    return {
        "items": documents,
        "counts": filtered_counts,
        "total": filtered_total,
        "requires_review": filtered_requires_review,
        "overview": {
            "counts": overview_counts,
            "total": sum(overview_counts.values()),
            "requires_review": overview_requires_review,
        },
        "payment_evidence_count": sum(bool(item.get("is_payment_evidence")) for item in documents),
        "areas": {key: sorted(value) for key, value in _ADMINISTRATIVE_CATEGORIES.items()},
    }


# Store per tracciare task in background

# Stato dei task in memoria (in produzione usare Redis)
_download_tasks: Dict[str, Dict] = {}

# Lock globale per operazioni email/DB
_email_operation_lock = asyncio.Lock()
_current_operation: Optional[str] = None


def is_email_operation_running() -> bool:
    """Verifica se c'è un'operazione email in corso."""
    return _email_operation_lock.locked()


def get_current_operation() -> Optional[str]:
    """Restituisce il nome dell'operazione in corso."""
    return _current_operation


@router.get("/lock-status")
@handle_errors
async def get_lock_status():
    """Restituisce lo stato del lock per operazioni email/DB."""
    return {
        "locked": is_email_operation_running(),
        "operation": get_current_operation(),
        "message": f"Operazione in corso: {_current_operation}" if _current_operation else "Nessuna operazione in corso"
    }


async def _execute_email_download(task_id: str, db, email_user: str, email_password: str,
                                   giorni: int, folder: str, keywords: List[str]):
    """Esegue il download in background e aggiorna lo stato del task."""
    global _current_operation

    try:
        async with _email_operation_lock:
            _current_operation = "download_documenti_email"
            _download_tasks[task_id]["status"] = "in_progress"
            _download_tasks[task_id]["message"] = "Connessione al server email..."

            result = await download_documents_from_email(
                db=db,
                email_user=email_user,
                email_password=email_password,
                since_days=giorni,
                folder=folder,
                search_keywords=keywords if keywords else None
            )

            _download_tasks[task_id]["status"] = "completed"
            _download_tasks[task_id]["result"] = result
            _download_tasks[task_id]["message"] = "Download completato!"
            _download_tasks[task_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
            _current_operation = None

    except Exception as e:
        logger.error(f"Errore download task {task_id}: {e}")
        _download_tasks[task_id]["status"] = "error"
        _download_tasks[task_id]["error"] = str(e)
        _download_tasks[task_id]["message"] = f"Errore: {str(e)}"
        _current_operation = None


@router.post("/scarica-da-email")
@handle_errors
async def scarica_documenti_email(
    giorni: int = Query(30, ge=1, le=2000, description="Scarica email degli ultimi N giorni (max 2000 per storico)"),
    folder: str = Query("INBOX", description="Cartella email"),
    parole_chiave: Optional[str] = Query(None, description="Parole chiave separate da virgola per filtrare email"),
    background: bool = Query(False, description="Se true, esegue in background e restituisce task_id")
) -> Dict[str, Any]:
    """
    Scarica documenti allegati dalle email.
    Usa le credenziali configurate nel .env.
    Se parole_chiave è specificato, cerca email con quelle parole nell'oggetto.
    Se background=true, avvia il download in background e restituisce un task_id per il polling.

    NOTA: Se c'è già un'operazione email in corso, restituisce errore.
    """
    # Verifica se c'è già un'operazione in corso
    if is_email_operation_running():
        raise HTTPException(
            status_code=423,  # Locked
            detail=f"Operazione in corso: {get_current_operation()}. Attendere il completamento."
        )

    db = Database.get_db()

    # Recupera credenziali email: prima dall'account configurato in
    # email_accounts (stesso helper usato dalla ricerca fatture PayPal, che
    # funziona), poi fallback alle env var. Prima leggeva SOLO le env var:
    # su Render non sono impostate → il bottone rispondeva sempre 400.
    from app.services.gmail_search import get_gmail_credentials
    email_user, email_password, _imap = await get_gmail_credentials(db)

    if not email_user or not email_password:
        raise HTTPException(
            status_code=400,
            detail="Credenziali email non configurate: nessun account in email_accounts e nessuna variabile EMAIL_USER/EMAIL_APP_PASSWORD"
        )

    # Parsing parole chiave
    keywords = []
    if parole_chiave:
        keywords = [k.strip() for k in parole_chiave.split(',') if k.strip()]

    if background:
        # Modalità background: crea task e restituisce subito
        task_id = str(uuid.uuid4())
        _download_tasks[task_id] = {
            "task_id": task_id,
            "status": "pending",
            "message": "Avvio download...",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "giorni": giorni,
            "keywords": keywords,
            "result": None,
            "error": None
        }

        # Avvia il task in background
        asyncio.create_task(_execute_email_download(
            task_id, db, email_user, email_password, giorni, folder, keywords
        ))

        return {
            "success": True,
            "background": True,
            "task_id": task_id,
            "message": "Download avviato in background. Usa /documenti/task/{task_id} per controllare lo stato."
        }

    # Modalità sincrona (comportamento originale)
    try:
        result = await download_documents_from_email(
            db=db,
            email_user=email_user,
            email_password=email_password,
            since_days=giorni,
            folder=folder,
            search_keywords=keywords if keywords else None
        )

        return result

    except Exception as e:
        logger.error(f"Errore download documenti: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/task/{task_id}")
@handle_errors
async def get_task_status(task_id: str) -> Dict[str, Any]:
    """Controlla lo stato di un task di download in background."""
    if task_id not in _download_tasks:
        raise HTTPException(status_code=404, detail="Task non trovato")

    task = _download_tasks[task_id]

    # Pulisci task completati vecchi di 1 ora
    current_time = datetime.now(timezone.utc)
    for tid in list(_download_tasks.keys()):
        t = _download_tasks[tid]
        if t.get("completed_at"):
            completed = datetime.fromisoformat(t["completed_at"].replace("Z", "+00:00"))
            if (current_time - completed).total_seconds() > 3600:
                del _download_tasks[tid]

    return task


@router.get("/categorie")
@handle_errors
async def get_categorie() -> Dict[str, Any]:
    """Elenco categorie documenti."""
    return {
        "categories": CATEGORIES,
        "descriptions": {
            "f24": "Modelli F24 per pagamento tributi",
            "fattura": "Fatture elettroniche e PDF",
            "busta_paga": "Cedolini e Libro Unico del Lavoro",
            "estratto_conto": "Estratti conto e movimenti bancari",
            "quietanza": "Quietanze di pagamento F24",
            "bonifico": "Distinte e conferme bonifici",
            "altro": "Altri documenti non categorizzati"
        }
    }


@router.get("/documento/{doc_id}")
@handle_errors
async def get_documento(doc_id: str) -> Dict[str, Any]:
    """Dettaglio singolo documento."""
    db = Database.get_db()

    doc = await db["documents_inbox"].find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Documento non trovato")

    return doc


# Collezioni allegati email dove finiscono i documenti scaricati dalla posta
# (oltre a documents_inbox usato da Drive/upload manuale). Il download generico
# deve risolvere l'id anche qui, altrimenti gli allegati email danno 404
# (fix 13/07/2026, P0-2 verifica Documenti).
@router.get("/documento/{doc_id}/download")
async def download_documento(doc_id: str):
    """Alias: l'originale si apre da `/api/originale/documento/{id}` (DRV-04).

    Resta perche' i link scritti nei fogli Excel gia' inviati puntano qui.
    """
    from app.routers.originale import reindirizza_a_originale

    return reindirizza_a_originale("documento", doc_id, scarica=True)


@router.post("/documento/{doc_id}/processa")
@handle_errors
async def processa_documento(
    doc_id: str,
    destinazione: str = Query(..., description="Dove caricare: f24, fatture, buste_paga, estratto_conto")
) -> Dict[str, Any]:
    """
    Processa un documento e lo carica nella sezione appropriata.
    Architettura Drive/Supabase: usa solo pdf_data da Drive/Supabase.
    """
    db = Database.get_db()

    doc = await db["documents_inbox"].find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Documento non trovato")

    # Architettura Drive/Supabase: usa solo pdf_data
    pdf_data = doc.get("pdf_data")
    if not pdf_data:
        raise HTTPException(status_code=404, detail="PDF non disponibile in Drive/Supabase. Eseguire migrazione dati.")

    # Mappa destinazioni agli endpoint
    destination_map = {
        "f24": "f24_unificato",
        "fatture": "invoices",
        "buste_paga": "buste_paga",
        "estratto_conto": "estratto_conto",
        "quietanze": "quietanze_f24"
    }

    if destinazione not in destination_map:
        raise HTTPException(status_code=400, detail=f"Destinazione non valida. Usa: {list(destination_map.keys())}")

    # Aggiorna stato documento
    await db["documents_inbox"].update_one(
        {"id": doc_id},
        {"$set": {
            "status": "processato",
            "processed": True,
            "processed_to": destinazione,
            "processed_at": datetime.now(timezone.utc).isoformat()
        }}
    )

    return {
        "success": True,
        "message": f"Documento pronto per caricamento in {destinazione}",
        "pdf_data_available": True,
        "destinazione": destinazione,
        "nota": "Usa l'endpoint di upload specifico per completare il caricamento"
    }


@router.post("/documento/{doc_id}/cambia-categoria")
@handle_errors
async def cambia_categoria_documento(
    doc_id: str,
    nuova_categoria: str = Query(..., description="Nuova categoria")
) -> Dict[str, Any]:
    """
    Cambia la categoria di un documento.
    Architettura Drive/Supabase: aggiorna solo i metadati nel database.
    """
    db = Database.get_db()

    if nuova_categoria not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Categoria non valida. Usa: {list(CATEGORIES.keys())}")

    doc = await db["documents_inbox"].find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Documento non trovato")

    # Architettura Drive/Supabase: aggiorna solo metadati, nessuna operazione su filesystem
    await db["documents_inbox"].update_one(
        {"id": doc_id},
        {"$set": {
            "category": nuova_categoria,
            "category_label": CATEGORIES[nuova_categoria],
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )

    return {
        "success": True,
        "nuova_categoria": nuova_categoria,
        "category_label": CATEGORIES[nuova_categoria]
    }


@router.post("/documento/{doc_id}/annulla-processamento")
@handle_errors
async def annulla_processamento_documento(doc_id: str) -> Dict[str, Any]:
    """
    Annulla un "processa" con destinazione sbagliata (es. click su F24 per
    un documento che era in realtà una Cartella Esattoriale — segnalato
    dall'utente 18/07/2026: "ho cliccato f24 ed ho sbagliato come
    riclassifico?"). processa_documento non scrive nulla nella collezione di
    destinazione (si limita a segnare processed_to sul documento; serve poi
    un endpoint di upload specifico per completare il caricamento), quindi
    annullare è solo un reset dei metadati: il documento torna tra i "da
    processare" con la sua categoria originale (già corretta) invariata.
    """
    db = Database.get_db()

    doc = await db["documents_inbox"].find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    if not doc.get("processed") and doc.get("status") != "processato":
        raise HTTPException(status_code=400, detail="Documento non risulta processato")

    await db["documents_inbox"].update_one(
        {"id": doc_id},
        {
            "$set": {"status": "nuovo"},
            "$unset": {"processed": "", "processed_to": "", "processed_at": ""},
        },
    )

    return {"success": True, "id": doc_id, "category": doc.get("category")}


@router.delete("/documento/{doc_id}")
@handle_errors
async def elimina_documento(doc_id: str) -> Dict[str, Any]:
    """
    Elimina un documento.
    Architettura Drive/Supabase: elimina solo dal database.
    """
    db = Database.get_db()

    doc = await db["documents_inbox"].find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Documento non trovato")

    # Architettura Drive/Supabase: elimina solo dal database
    await db["documents_inbox"].delete_one({"id": doc_id})

    return {"success": True, "deleted": doc_id}


@router.post("/elimina-processati")
@handle_errors
async def elimina_documenti_processati() -> Dict[str, Any]:
    """
    Elimina tutti i documenti già processati.
    Architettura Drive/Supabase: elimina solo dal database.
    """
    db = Database.get_db()

    # Conta documenti da eliminare
    count_to_delete = await db["documents_inbox"].count_documents({"processed": True})

    # Elimina dal database (architettura Drive/Supabase)
    await db["documents_inbox"].delete_many({"processed": True})

    return {
        "success": True,
        "deleted_count": count_to_delete
    }


@router.get("/statistiche")
@handle_errors
async def statistiche_documenti() -> Dict[str, Any]:
    """Statistiche sui documenti."""
    db = Database.get_db()

    totale = await db["documents_inbox"].count_documents({})
    nuovi = await db["documents_inbox"].count_documents({"status": "nuovo"})
    processati = await db["documents_inbox"].count_documents({"processed": True})

    # Per categoria
    pipeline = [
        {"$group": {
            "_id": "$category",
            "count": {"$sum": 1},
            "nuovi": {"$sum": {"$cond": [{"$eq": ["$status", "nuovo"]}, 1, 0]}},
            "processati": {"$sum": {"$cond": [{"$eq": ["$processed", True]}, 1, 0]}}
        }}
    ]
    by_category = []
    async for doc in db["documents_inbox"].aggregate(pipeline):
        by_category.append({
            "category": doc["_id"],
            "category_label": CATEGORIES.get(doc["_id"], doc["_id"]),
            "count": doc["count"],
            "nuovi": doc["nuovi"],
            "processati": doc["processati"]
        })

    # Ultimo download
    ultimo = await db["documents_inbox"].find_one(
        {},
        {"_id": 0, "downloaded_at": 1}
    )
    ultimo_download = ultimo.get("downloaded_at") if ultimo else None

    # Spazio su disco
    total_size = 0
    for cat_dir in CATEGORIES.values():
        dir_path = DOCUMENTS_DIR / cat_dir
        if dir_path.exists():
            for f in dir_path.iterdir():
                if f.is_file():
                    total_size += f.stat().st_size

    return {
        "totale": totale,
        "nuovi": nuovi,
        "processati": processati,
        "da_processare": nuovi,
        "by_category": by_category,
        "ultimo_download": ultimo_download,
        "spazio_disco_mb": round(total_size / (1024 * 1024), 2),
        "categories": CATEGORIES
    }


@router.get("/cartelle-email")
@handle_errors
async def get_cartelle_email() -> Dict[str, Any]:
    """Lista cartelle email disponibili."""
    import imaplib

    from app.services.gmail_search import get_gmail_credentials
    db = Database.get_db()
    email_user, email_password, _imap = await get_gmail_credentials(db)

    if not email_user or not email_password:
        return {"folders": ["INBOX"], "error": "Credenziali non configurate"}

    try:
        conn = imaplib.IMAP4_SSL("imap.gmail.com")
        conn.login(email_user, email_password)

        status, folders = conn.list()

        folder_list = []
        if status == 'OK':
            for folder in folders:
                if isinstance(folder, bytes):
                    # Parse folder name
                    parts = folder.decode().split(' "/" ')
                    if len(parts) > 1:
                        folder_list.append(parts[1].strip('"'))

        conn.logout()

        return {
            "folders": folder_list,
            "email_user": email_user
        }

    except Exception as e:
        return {
            "folders": ["INBOX"],
            "error": str(e)
        }


@router.post("/sync-f24-automatico")
@handle_errors
async def sync_f24_automatico(
    giorni: int = Query(30, ge=1, le=365)
) -> Dict[str, Any]:
    """Alias legacy: processa gli F24 gia' in `documents_inbox`.

    Prima scaricava da solo la INBOX (un secondo downloader: la posta si legge
    solo con `email_full_download`, tutte le cartelle) e scriveva i modelli con
    un lettore e una dedup propri. Il parametro `giorni` resta per compatibilita'
    e non ha effetto.
    """
    esito = await processa_f24_scaricati()
    return {
        **esito,
        "f24_trovati": esito.get("f24_processati", 0) + esito.get("f24_errori", 0),
        "f24_caricati": esito.get("f24_processati", 0),
        "messaggio": "La posta la scarica solo il giro orario; qui si processano gli F24 gia' in inbox",
    }


@router.post("/processa-f24-scaricati")
@handle_errors
async def processa_f24_scaricati() -> Dict[str, Any]:
    """Processa gli F24 in `documents_inbox` non ancora processati.

    Ogni PDF passa da `importa_modello_bytes`, l'ingresso unico dei modelli:
    lettura, quadratura, dedup per contenuto, ricerca di quietanza e addebito.
    """
    from app.services.f24_canonico import importa_modello_bytes
    import base64

    db = Database.get_db()

    f24_docs = await db["documents_inbox"].find(
        {"category": "f24", "processed": {"$ne": True}},
        {"_id": 0}
    ).to_list(100)

    if not f24_docs:
        return {
            "success": True,
            "message": "Nessun F24 da processare",
            "f24_processati": 0,
            "errori": []
        }

    f24_caricati = []
    f24_errori = []

    for doc in f24_docs:
        try:
            pdf_data = doc.get("pdf_data")
            if not pdf_data:
                f24_errori.append({"file": doc["filename"], "errore": "PDF non disponibile in Drive/Supabase"})
                continue

            esito = await importa_modello_bytes(
                db, base64.b64decode(pdf_data), doc.get("filename") or "f24.pdf",
                source="documents_inbox",
                source_metadata={
                    "source_document_id": doc.get("id"),
                    "email_subject": doc.get("email_subject", ""),
                    "email_from": doc.get("email_from", ""),
                    "email_date": doc.get("email_date", ""),
                },
            )
            if not esito.get("success"):
                f24_errori.append({"file": doc["filename"], "errore": esito.get("error", "Parsing fallito")})
                await db["documents_inbox"].update_one(
                    {"id": doc["id"]},
                    {"$set": {
                        "status": "errore_parser", "processed": False,
                        "parser_errors": [esito.get("error", "Parsing fallito")],
                        "parser_checked_at": datetime.now(timezone.utc).isoformat(),
                    }},
                )
                continue

            await db["documents_inbox"].update_one(
                {"id": doc["id"]},
                {"$set": {
                    "status": "processato",
                    "processed": True,
                    "processed_to": "f24_unificato",
                    "f24_id": esito.get("f24_id"),
                    "note": "Già presente" if esito.get("duplicate") else None,
                    "processed_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            if esito.get("duplicate"):
                continue
            f24_caricati.append({
                "file": doc["filename"],
                "f24_id": esito.get("f24_id"),
                "tributi": esito.get("righe_tributo", 0),
            })

        except Exception as e:
            f24_errori.append({"file": doc["filename"], "errore": f"{type(e).__name__}: {e}"})

    return {
        "success": True,
        "f24_processati": len(f24_caricati),
        "f24_errori": len(f24_errori),
        "dettagli": f24_caricati,
        "errori": f24_errori if f24_errori else None
    }



@router.get("/ultimo-sync")
@handle_errors
async def get_ultimo_sync() -> Dict[str, Any]:
    """Restituisce info sull'ultimo sync F24."""
    db = Database.get_db()

    # Ultimo documento scaricato
    ultimo_doc = await db["documents_inbox"].find_one(
        {"category": "f24"},
        {"_id": 0, "downloaded_at": 1, "filename": 1}
    )

    # Conta F24 da processare
    da_processare = await db["documents_inbox"].count_documents({
        "category": "f24",
        "processed": {"$ne": True}
    })

    # Ultimo F24 importato
    ultimo_f24 = await db["f24_unificato"].find_one(
        {"auto_imported": True},
        {"_id": 0, "file_name": 1, "import_date": 1}
    )

    return {
        "ultimo_download": ultimo_doc.get("downloaded_at") if ultimo_doc else None,
        "ultimo_file": ultimo_doc.get("filename") if ultimo_doc else None,
        "f24_da_processare": da_processare,
        "ultimo_f24_importato": ultimo_f24
    }



@router.post("/sync-estratti-conto")
@handle_errors
async def sync_estratti_conto() -> Dict[str, Any]:
    """
    Processa tutti gli estratti conto dalla inbox.
    Supporta:
    - Estratti conto carte Nexi
    - Estratti conto bancari BPM (se riconosciuti)

    I movimenti vengono salvati in estratto_conto_nexi per carte
    o estratto_conto_movimenti per conto corrente.
    """
    db = Database.get_db()

    # Trova estratti conto non processati
    docs = await db["documents_inbox"].find(
        {"category": "estratto_conto", "processed": {"$ne": True}},
        {"_id": 0}
    ).to_list(100)

    if not docs:
        return {
            "success": True,
            "message": "Nessun estratto conto da processare",
            "processati": 0,
            "errori": []
        }

    from app.parsers.estratto_conto_nexi_parser import EstrattoContoNexiParser
    import base64 as b64

    processati = []
    errori = []

    for doc in docs:
        filename = doc.get("filename", "")

        # Architettura Drive/Supabase: usa pdf_data
        pdf_data = doc.get("pdf_data")
        if not pdf_data:
            errori.append({"file": filename, "errore": "PDF non disponibile in Drive/Supabase"})
            continue

        try:
            # Decodifica PDF da base64
            pdf_content = b64.b64decode(pdf_data)

            # Prova parser Nexi
            parser = EstrattoContoNexiParser()
            result = parser.parse_pdf(pdf_content)

            if result.get("success"):
                transazioni = result.get("transazioni", [])
                metadata = result.get("metadata", {})

                if transazioni:
                    # Salva in estratto_conto_nexi
                    import uuid
                    estratto_id = str(uuid.uuid4())

                    estratto_record = {
                        "id": estratto_id,
                        "filename": filename,
                        "pdf_data": pdf_data,  # Architettura Drive/Supabase
                        "tipo": "nexi_carta",
                        "metadata": metadata,
                        "totale_transazioni": len(transazioni),
                        "totale_importo": result.get("totale_importo", 0),
                        "email_source": {
                            "subject": doc.get("email_subject"),
                            "from": doc.get("email_from"),
                            "date": doc.get("email_date")
                        },
                        "import_date": datetime.now(timezone.utc).isoformat(),
                        "source": "email_sync"
                    }

                    # Controlla duplicati
                    existing = await db["estratto_conto_nexi"].find_one({
                        "filename": filename
                    })

                    if not existing:
                        await db["estratto_conto_nexi"].insert_one(dict(estratto_record).copy())

                        # Salva transazioni singole per riconciliazione
                        for idx, trans in enumerate(transazioni):
                            trans_record = {
                                "id": f"{estratto_id}_{idx}",
                                "estratto_id": estratto_id,
                                "data": trans.get("data"),
                                "data_valuta": trans.get("data_valuta"),
                                "descrizione": trans.get("descrizione", ""),
                                "esercente": trans.get("esercente", ""),
                                "importo": trans.get("importo", 0),
                                "tipo": "carta_credito",
                                "categoria": trans.get("categoria"),
                                "riconciliato": False,
                                "fattura_id": None,
                                "created_at": datetime.now(timezone.utc).isoformat()
                            }
                            # Usa una copia per separare il record dalla risposta.
                            await db["estratto_conto_movimenti"].insert_one(dict(trans_record).copy())

                    # Aggiorna stato documento
                    await db["documents_inbox"].update_one(
                        {"id": doc["id"]},
                        {"$set": {
                            "status": "processato",
                            "processed": True,
                            "processed_to": "estratto_conto_nexi",
                            "processed_at": datetime.now(timezone.utc).isoformat()
                        }}
                    )

                    processati.append({
                        "file": filename,
                        "tipo": "nexi_carta",
                        "transazioni": len(transazioni),
                        "importo_totale": result.get("totale_importo", 0),
                        "periodo": metadata.get("mese_riferimento", "")
                    })
                else:
                    # Nessuna transazione trovata, potrebbe essere solo riepilogo
                    processati.append({
                        "file": filename,
                        "tipo": "nexi_carta",
                        "transazioni": 0,
                        "nota": "Solo riepilogo, nessun dettaglio movimenti"
                    })

                    await db["documents_inbox"].update_one(
                        {"id": doc["id"]},
                        {"$set": {
                            "status": "processato",
                            "processed": True,
                            "processed_to": "estratto_conto_nexi",
                            "nota": "Solo riepilogo",
                            "processed_at": datetime.now(timezone.utc).isoformat()
                        }}
                    )
            else:
                errori.append({
                    "file": filename,
                    "errore": result.get("error", "Parsing fallito")
                })

        except Exception as e:
            errori.append({"file": filename, "errore": str(e)})

    return {
        "success": True,
        "processati": len(processati),
        "errori_count": len(errori),
        "dettagli": processati,
        "errori": errori if errori else None,
        "messaggio": f"Processati {len(processati)} estratti conto" if processati else "Nessun estratto conto processato"
    }



# (route morte rimosse — §13.2, pulizia 2026-07-13: /sync-buste-paga,
# /riepilogo-cedolini GET+POST, /confronto-cedolini-prima-nota. Widget "buste
# paga da pagare" mai esposto in UI, zero chiamanti; i cedolini vivi passano da
# Drive (scheduler orario), upload-auto (LUL) e prima_nota_salari.)


@router.post("/sync-estratti-bnl")
@handle_errors
async def sync_estratti_bnl() -> Dict[str, Any]:
    """
    Processa tutti gli estratti conto BNL dalla inbox.
    Supporta:
    - Estratti conto corrente BNL
    - Estratti conto carte di credito BNL Business

    I movimenti vengono salvati in estratto_conto_movimenti.
    """
    db = Database.get_db()

    # Cerca documenti BNL sia in "estratto_conto" che in "altro"
    docs = await db["documents_inbox"].find(
        {
            "processed": {"$ne": True},
            "$or": [
                {"category": "estratto_conto"},
                {"category": "altro", "filename": {"$regex": "BNL|bnl", "$options": "i"}}
            ]
        },
        {"_id": 0}
    ).to_list(200)

    if not docs:
        return {
            "success": True,
            "message": "Nessun estratto conto BNL da processare",
            "processati": 0,
            "errori": []
        }

    from app.parsers.estratto_conto_bnl_parser import parse_estratto_conto_bnl
    import base64

    processati = []
    errori = []

    for doc in docs:
        pdf_data = doc.get("pdf_data")
        filename = doc.get("filename", "")

        # Salta se non è un file BNL
        if "BNL" not in filename.upper() and "bnl" not in filename.lower():
            # Potrebbe essere Nexi o altro, salta
            continue

        if not pdf_data:
            errori.append({"file": filename, "errore": "PDF non disponibile in Drive/Supabase"})
            continue

        try:
            # Architettura Drive/Supabase: decodifica da Base64
            pdf_content = base64.b64decode(pdf_data)

            # Usa parser BNL
            result = parse_estratto_conto_bnl(pdf_content)

            if result.get("success"):
                transazioni = result.get("transazioni", [])
                metadata = result.get("metadata", {})
                tipo_doc = result.get("tipo_documento", "bnl")

                import uuid
                estratto_id = str(uuid.uuid4())

                # Determina la collezione di destinazione
                collection_name = "estratto_conto_bnl"

                estratto_record = {
                    "id": estratto_id,
                    "filename": filename,
                    "pdf_data": pdf_data,  # Architettura Drive/Supabase
                    "tipo": tipo_doc,
                    "banca": "BNL",
                    "metadata": metadata,
                    "totale_transazioni": len(transazioni),
                    "totale_entrate": result.get("totale_entrate", 0),
                    "totale_uscite": result.get("totale_uscite", 0),
                    "email_source": {
                        "subject": doc.get("email_subject"),
                        "from": doc.get("email_from"),
                        "date": doc.get("email_date")
                    },
                    "import_date": datetime.now(timezone.utc).isoformat(),
                    "source": "email_sync"
                }

                # Controlla duplicati
                existing = await db[collection_name].find_one({
                    "filename": filename
                })

                if not existing:
                    await db[collection_name].insert_one(dict(estratto_record).copy())

                    # Salva transazioni singole per riconciliazione
                    for idx, trans in enumerate(transazioni):
                        trans_record = {
                            "id": f"{estratto_id}_{idx}",
                            "estratto_id": estratto_id,
                            "data": trans.get("data_contabile", trans.get("data")),
                            "data_valuta": trans.get("data_valuta"),
                            "descrizione": trans.get("descrizione", ""),
                            "importo": trans.get("importo", 0),
                            "tipo": trans.get("tipo", "movimento"),
                            "causale_abi": trans.get("causale_abi"),
                            "banca": "BNL",
                            "riconciliato": False,
                            "fattura_id": None,
                            "created_at": datetime.now(timezone.utc).isoformat()
                        }
                        await db["estratto_conto_movimenti"].insert_one(dict(trans_record).copy())

                # Aggiorna stato documento e categoria se era "altro"
                update_data = {
                    "status": "processato",
                    "processed": True,
                    "processed_to": collection_name,
                    "processed_at": datetime.now(timezone.utc).isoformat()
                }

                # Se era in "altro", ricategorizza come "estratto_conto"
                if doc.get("category") == "altro":
                    update_data["category"] = "estratto_conto"
                    update_data["category_label"] = "Estratti Conto"

                await db["documents_inbox"].update_one(
                    {"id": doc["id"]},
                    {"$set": update_data}
                )

                processati.append({
                    "file": filename,
                    "tipo": tipo_doc,
                    "transazioni": len(transazioni),
                    "entrate": result.get("totale_entrate", 0),
                    "uscite": result.get("totale_uscite", 0),
                    "periodo": f"{metadata.get('periodo_da', '')} - {metadata.get('periodo_a', '')}"
                })
            else:
                errori.append({
                    "file": filename,
                    "errore": result.get("error", "Parsing fallito")
                })

        except Exception as e:
            logger.error(f"Errore parsing BNL {filename}: {e}")
            errori.append({"file": filename, "errore": str(e)})

    return {
        "success": True,
        "processati": len(processati),
        "errori_count": len(errori),
        "dettagli": processati,
        "errori": errori if errori else None,
        "messaggio": f"Processati {len(processati)} estratti conto BNL" if processati else "Nessun estratto conto BNL processato"
    }


@router.post("/ricategorizza-documenti")
@handle_errors
async def ricategorizza_documenti() -> Dict[str, Any]:
    """
    Ricategorizza automaticamente i documenti nella categoria 'altro'
    che possono essere riconosciuti come altri tipi.
    """
    db = Database.get_db()

    # Trova documenti in "altro" non processati
    docs = await db["documents_inbox"].find(
        {"category": "altro", "processed": {"$ne": True}},
        {"_id": 0}
    ).to_list(500)

    if not docs:
        return {
            "success": True,
            "message": "Nessun documento da ricategorizzare",
            "ricategorizzati": 0
        }

    ricategorizzati = []

    for doc in docs:
        filename = doc.get("filename", "").lower()
        new_category = None

        # Riconosci BNL
        if "bnl" in filename:
            new_category = "estratto_conto"
        # Riconosci estratti conto
        elif "estratto" in filename or "conto" in filename:
            new_category = "estratto_conto"
        # Riconosci buste paga
        elif "paga" in filename or "cedolino" in filename or "lul" in filename:
            new_category = "busta_paga"
        # Riconosci F24
        elif "f24" in filename:
            new_category = "f24"
        # Riconosci PayPal
        elif "paypal" in filename:
            new_category = "estratto_conto"

        if new_category:
            await db["documents_inbox"].update_one(
                {"id": doc["id"]},
                {"$set": {
                    "category": new_category,
                    "category_label": {
                        "estratto_conto": "Estratti Conto",
                        "busta_paga": "Buste Paga",
                        "f24": "F24",
                        "fattura": "Fatture"
                    }.get(new_category, new_category.replace("_", " ").title()),
                    "ricategorizzato_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            ricategorizzati.append({
                "file": doc.get("filename"),
                "da": "altro",
                "a": new_category
            })

    return {
        "success": True,
        "ricategorizzati": len(ricategorizzati),
        "dettagli": ricategorizzati
    }


@router.post("/processa-tutti")
@handle_errors
async def processa_tutti_documenti() -> Dict[str, Any]:
    """
    Endpoint combinato che:
    1. Ricategorizza i documenti
    2. Processa estratti conto Nexi
    3. Processa estratti conto BNL

    NOTA (audit-codice 04/09/2026): il passo "buste paga" chiamava una
    funzione `sync_buste_paga()` mai definita in questo file (NameError
    sempre catturato dal try/except, quindi l'endpoint "riusciva" ma non
    processava mai nulla). I cedolini hanno un solo sistema di ingestione
    canonico (cartella unica Drive / email_download -> cedolini_manager ->
    salari_unificati_v2, vedi CLAUDE.md "Cedolini: un solo sistema"): questo
    endpoint combinato non deve duplicarlo con una chiamata inventata.
    """
    risultati = {
        "ricategorizzazione": None,
        "estratti_nexi": None,
        "estratti_bnl": None
    }

    try:
        # 1. Ricategorizza
        risultati["ricategorizzazione"] = await ricategorizza_documenti()
    except Exception as e:
        risultati["ricategorizzazione"] = {"error": str(e)}

    try:
        # 2. Estratti Nexi
        risultati["estratti_nexi"] = await sync_estratti_conto()
    except Exception as e:
        risultati["estratti_nexi"] = {"error": str(e)}

    try:
        # 3. Estratti BNL
        risultati["estratti_bnl"] = await sync_estratti_bnl()
    except Exception as e:
        risultati["estratti_bnl"] = {"error": str(e)}

    return {
        "success": True,
        "risultati": risultati,
        "sommario": {
            "ricategorizzati": risultati.get("ricategorizzazione", {}).get("ricategorizzati", 0),
            "estratti_nexi_processati": risultati.get("estratti_nexi", {}).get("processati", 0),
            "estratti_bnl_processati": risultati.get("estratti_bnl", {}).get("processati", 0)
        }
    }



@router.post("/reimporta-da-filesystem")
@handle_errors
async def reimporta_documenti_da_filesystem(
    force: bool = Query(False, description="Forza reimportazione anche se esistenti nel DB"),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """
    Scansiona la cartella /app/documents e reimporta tutti i documenti nel database.
    Utile quando il database è stato resettato ma i file sono ancora su disco.
    """
    import uuid

    db = Database.get_db()

    # DEPRECATO: Questo endpoint è per migrazione legacy.
    # Architettura Drive/Supabase: legge file da disco e li salva come Base64 in Drive/Supabase.

    # Categorie e sottocartelle
    category_dirs = {
        "Buste Paga": "busta_paga",
        "Estratti Conto": "estratto_conto",
        "F24": "f24",
        "Fatture": "fattura",
        "Altri": "altro"
    }

    importati = []
    saltati = []
    errori = []

    base_path = Path("/tmp/documents")

    for dir_name, category in category_dirs.items():
        dir_path = base_path / dir_name
        if not dir_path.exists():
            continue

        for file_path in dir_path.iterdir():
            if not file_path.is_file():
                continue

            # Salta file di sistema
            if file_path.name.startswith('.'):
                continue

            filename = file_path.name
            filepath = str(file_path)

            # Architettura Drive/Supabase: leggi file e codifica in Base64
            try:
                with open(filepath, 'rb') as f:
                    file_content = f.read()
                    file_hash = hashlib.md5(file_content).hexdigest()
                    pdf_base64 = base64.b64encode(file_content).decode('utf-8')
            except Exception as e:
                errori.append({"file": filename, "errore": f"Impossibile leggere file: {e}"})
                continue

            # Controlla se già esiste nel DB
            existing = await db["documents_inbox"].find_one({
                "$or": [
                    {"filename": filename, "file_hash": file_hash},
                    {"file_hash": file_hash}
                ]
            })

            if existing and not force:
                saltati.append(filename)
                continue

            # Ricategorizza automaticamente in base al nome
            final_category = category
            filename_lower = filename.lower()

            if "bnl" in filename_lower:
                final_category = "estratto_conto"
            elif "nexi" in filename_lower:
                final_category = "estratto_conto"
            elif "paypal" in filename_lower:
                final_category = "estratto_conto"
            elif "paga" in filename_lower or "cedolino" in filename_lower:
                final_category = "busta_paga"
            elif "f24" in filename_lower:
                final_category = "f24"

            # Crea record documento con pdf_data (Drive/Supabase)
            doc_record = {
                "id": str(uuid.uuid4()),
                "filename": filename,
                "pdf_data": pdf_base64,  # Architettura Drive/Supabase
                "category": final_category,
                "category_label": {
                    "estratto_conto": "Estratti Conto",
                    "busta_paga": "Buste Paga",
                    "f24": "F24",
                    "fattura": "Fatture",
                    "altro": "Altri"
                }.get(final_category, "Altri"),
                "status": "nuovo",
                "processed": False,
                "file_hash": file_hash,
                "file_size": len(file_content),
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
                "source": "filesystem_import_migrated"
            }

            try:
                if existing and force:
                    await db["documents_inbox"].update_one(
                        {"_id": existing["_id"]},
                        {"$set": doc_record}
                    )
                else:
                    await db["documents_inbox"].insert_one(dict(doc_record).copy())

                importati.append({
                    "file": filename,
                    "categoria": final_category
                })
            except Exception as e:
                errori.append({"file": filename, "errore": str(e)})

    # Statistiche per categoria
    by_category = {}
    for doc in importati:
        cat = doc["categoria"]
        by_category[cat] = by_category.get(cat, 0) + 1

    return {
        "success": True,
        "importati": len(importati),
        "saltati": len(saltati),
        "errori_count": len(errori),
        "per_categoria": by_category,
        "dettagli": importati[:50] if len(importati) > 50 else importati,
        "errori": errori if errori else None,
        "messaggio": f"Importati {len(importati)} documenti dal filesystem"
    }


# ============================================================
# UPLOAD AUTOMATICO CON RICONOSCIMENTO TIPO
# ============================================================

from app.utils.error_handler import handle_errors

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_INBOX_BYTES = 10 * 1024 * 1024
MAX_ZIP_UPLOAD_BYTES = 100 * 1024 * 1024
MAX_ZIP_FILES = 1000
MAX_ZIP_UNCOMPRESSED_BYTES = 250 * 1024 * 1024
MAX_ZIP_COMPRESSION_RATIO = 200
SUPPORTED_UPLOAD_SUFFIXES = {
    ".pdf", ".xml", ".p7m", ".xlsx", ".xls", ".csv", ".zip",
}


_PARTITA_IVA_UE = re.compile(
    r"\b(?:AT|BE|BG|CY|CZ|DE|DK|EE|EL|ES|FI|FR|HR|HU|IE|LT|LU|LV|MT|NL|PL|PT|RO|SE|SI|SK)"
    r"\s?([0-9A-Z]{8,12})\b"
)


def partita_iva_estera_nel_testo(testo: str) -> bool:
    """Una partita IVA UE non italiana nel testo (es. «IE9813461A» di SumUp).

    Almeno sette cifre dopo il prefisso: un IBAN (piu' lungo) o una parola
    in maiuscolo non bastano.
    """
    for trovata in _PARTITA_IVA_UE.finditer(str(testo or "").upper()):
        if sum(c.isdigit() for c in trovata.group(1)) >= 7:
            return True
    return False


def _pdf_text_for_detection(file_content: bytes, max_pages: int = 5) -> str:
    """Legge apertura e coda del PDF confrontando PyPDF e PyMuPDF."""
    from app.services.pdf_text_extraction import extract_pdf_text

    return extract_pdf_text(file_content, max_pages=max_pages, include_tail=True)


def _spreadsheet_text_for_detection(filename: str, file_content: bytes) -> str:
    """Legge solo un piccolo campione di intestazioni CSV/XLS/XLSX."""
    lower = filename.lower()
    if lower.endswith(".csv"):
        for encoding in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                return file_content[:64 * 1024].decode(encoding)
            except UnicodeDecodeError:
                continue
        return ""
    if not lower.endswith((".xlsx", ".xls")):
        return ""
    try:
        import io
        import pandas as pd

        engine = "xlrd" if lower.endswith(".xls") else "openpyxl"
        frame = pd.read_excel(
            io.BytesIO(file_content), engine=engine, nrows=20, dtype=object,
        )
        values: List[str] = [str(column) for column in frame.columns]
        for row in frame.itertuples(index=False, name=None):
            values.extend(str(value) for value in row if value not in (None, ""))
            if len(values) >= 300:
                break
        return " ".join(values[:300])
    except Exception:
        return ""

# Il cedolino Zucchetti (busta e stampa di controllo del Libro Unico) nel
# livello testo scrive gli spazi come «s»: «NETTOsDELsMESE». La struttura
# si riconosce da tre caselle insieme, mai dal nome file, che spesso e' solo
# «Cognome Nome - Mese Anno».
_ZUCCHETTI_CASELLE = (
    re.compile(r"NETTOS?DELS?MESE"),
    re.compile(r"TOTALES?COMPETENZE"),
    re.compile(r"TOTALES?TRATTENUTE"),
    re.compile(r"PERIODOS?DIS?RETRIBUZIONE"),
)


def _e_cedolino_zucchetti(marker_pdf_text: str) -> bool:
    return sum(bool(c.search(marker_pdf_text)) for c in _ZUCCHETTI_CASELLE) >= 3


def _e_contratto_di_lavoro(compact_pdf_text: str) -> bool:
    from app.parsers.busta_paga_multi_template import RIQUADRO_NETTO
    from app.services.cedolini_motore import _CONTRATTO

    return bool(_CONTRATTO.search(compact_pdf_text) and not RIQUADRO_NETTO.search(compact_pdf_text))


async def rileva_tipo_documento(filename: str, file_content: bytes) -> str:
    """``detect_document_type`` in un thread: legge il PDF e, per le scansioni,
    avvia l'OCR, che tiene la CPU per decine di secondi. Sul loop del server
    fermava anche ``/api/health`` e Render riavviava l'istanza (502)."""
    return await asyncio.to_thread(detect_document_type, filename, file_content)


def _tipo_dichiarazione(filename: str, pdf_text: str) -> str | None:
    """Tipo di un PDF che e' una dichiarazione fiscale (o un suo quadro), altrimenti None.

    Un quadro del 770 stampato da solo e' un pezzo della dichiarazione gia'
    archiviata, non una seconda dichiarazione ne' un «da classificare».
    Dichiarazioni fiscali (770/IVA/IRAP/LIPE/Redditi SC): classificatore
    deterministico unico, cosi' upload manuale e cartella unica Drive finiscono
    nello stesso fiscal_documents.
    """
    from app.services.componenti_770 import TIPO as TIPO_COMPONENTE_770, quadro as quadro_770
    from app.services.fiscal_domain import DocumentType, classify_document

    if quadro_770(filename, pdf_text):
        return TIPO_COMPONENTE_770
    dichiarazione = classify_document(filename, pdf_text)
    if dichiarazione["document_type"] in {
        DocumentType.MODELLO_770.value, DocumentType.DICHIARAZIONE_IVA.value,
        DocumentType.LIPE.value, DocumentType.DICHIARAZIONE_IRAP.value,
        DocumentType.REDDITI_SC.value,
    }:
        return "dichiarazione_fiscale"
    return None


def detect_document_type(filename: str, file_content: bytes) -> str:
    """Classifica solo con prove documentali sufficienti.

    Un nome generico o un foglio Excel qualsiasi non devono diventare un
    estratto conto. Allo stesso modo la sola intestazione dell'Agenzia delle
    Entrate non basta per classificare un PDF come F24.
    """
    lower = Path(filename or "documento").name.lower()
    if lower.endswith(".zip"):
        return "archivio_zip"

    if lower.endswith((".xml", ".p7m", ".xml.p7m")):
        detection_content = file_content
        if lower.endswith(".p7m"):
            from app.services.xml_invoice_processor import extract_xml_from_p7m

            extracted = extract_xml_from_p7m(file_content)
            if extracted is None:
                return "auto"
            detection_content = extracted
        try:
            content_str = detection_content.decode("utf-8", errors="ignore")
        except Exception:
            content_str = ""
        if any(marker in content_str for marker in (
            "DatiRT", "DataOraRilevazione", "CodiceFiscaleEsercente",
            "PIVAEsercente", "RegistratoreTelematicoComp",
        )):
            return "corrispettivo"
        if "FatturaElettronica" in content_str or "fatturaelettronicaheader" in content_str.lower():
            return "fattura"
        # Un XML non FatturaPA va conservato e classificato, non inviato al
        # parser fatture con un falso positivo.
        return "auto"

    if lower.endswith(".pdf"):
        if "identita" in lower or "identity_card" in lower:
            return "documento_identita"
        if "visura" in lower:
            return "visura_camerale"
        if "tari" in lower and any(marker in lower for marker in (
            "istanza", "rimborso", "compensazione",
        )):
            return "tari_istanza_compensazione"

    # Prima del nome file prevale la natura probatoria del contenuto. Una
    # nota INPS puo citare il modello F24 senza essere un F24; un avviso
    # PagoPA contiene IUV/CBILL ma non dimostra alcun pagamento.
    pdf_text = _pdf_text_for_detection(file_content).upper() if lower.endswith(".pdf") else ""
    if len(pdf_text.strip()) < 80 and any(clue in lower for clue in (
        "istanza", "identita", "carta", "visura", "ant_",
    )):
        try:
            from app.services.pagopa_receipts import _extract_receipt_text

            pdf_text = _extract_receipt_text(file_content)[0].upper() or pdf_text
        except Exception:
            pass
    compact_pdf_text = re.sub(r"\s+", " ", pdf_text)
    # I modelli F24 generati da alcuni intermediari hanno glifi spezzati
    # (``DELEG A IRREVO CABILE`` / ``SALD O FINALE``).  Il testo con tutti i
    # separatori rimossi conserva comunque la struttura semantica e deve
    # essere usato prima del nome file.
    marker_pdf_text = re.sub(r"[^A-Z0-9]", "", pdf_text)
    # Piano di una dilazione INPS: cita il «mod. F24» ma e' l'obbligo che le
    # quietanze RC01 dovranno pagare, rata per rata.
    from app.services.dilazioni_inps import TIPO as TIPO_DILAZIONE_INPS, riconosci as e_dilazione_inps

    if e_dilazione_inps(compact_pdf_text):
        return TIPO_DILAZIONE_INPS
    # Prospetto contabile del consulente del lavoro: cosa l'F24 del mese dovra' versare.
    from app.services.prospetti_contabili import TIPO as TIPO_PROSPETTO, riconosci as e_prospetto_contabile

    if lower.endswith(".pdf") and e_prospetto_contabile(pdf_text):
        return TIPO_PROSPETTO
    # «Elenco netti» delle paghe: i netti da bonificare, non una busta paga (prima del lettore cedolini).
    from app.services.elenchi_netti import TIPO as TIPO_ELENCO_NETTI, riconosci as e_elenco_netti

    if lower.endswith(".pdf") and e_elenco_netti(compact_pdf_text):
        return TIPO_ELENCO_NETTI
    if any(marker in compact_pdf_text for marker in (
        "NOTA DI RETTIFICA", "STAMPA SINTESI RETTIFICA", "MODELLO DMRA",
        "DIFFERENZE CONTRIBUTIVE",
    )):
        return "nota_rettifica_inps"
    if _e_cedolino_zucchetti(marker_pdf_text):
        return "cedolino"
    # Sentenza, precetto, relata e attestazione di una causa: prova del
    # perche' di bonifici senza fattura (spese di lite), mai un pagamento.
    from app.services.atti_giudiziari import tipo_atto
    from app.services.cartelle_pagamento import e_cartella_pagamento

    if lower.endswith(".pdf") and tipo_atto(compact_pdf_text):
        return "atto_giudiziario"
    # Cartella di pagamento dell'Agente della riscossione: obbligo da pagare, non un pagamento.
    if lower.endswith(".pdf") and e_cartella_pagamento(compact_pdf_text):
        return "cartella_pagamento"
    if _e_contratto_di_lavoro(compact_pdf_text):
        # Un contratto cita la busta paga ma non e' un cedolino: resta un
        # documento da classificare, non una busta da leggere.
        return "auto"
    # Contabile di un bonifico disposto: cita la banca del beneficiario
    # («Banca Nazionale del Lavoro») e il classificatore degli estratti la
    # prendeva per un estratto BNL, con il nome file solo «Cognome_data_EUR».
    if "ILSEGUENTEBONIFICO" in marker_pdf_text and (
        "REGISTRIAMOAVOSTRODEBITO" in marker_pdf_text or "IBANBENEFICIARIO" in marker_pdf_text
    ):
        return "bonifici"
    # Contabile di filiale BPM (versamento allo sportello): cita il conto
    # corrente e il lettore degli estratti la prenderebbe per un estratto.
    from app.services.contabili_filiale import TIPO as TIPO_CONTABILE_FILIALE, riconosci as e_contabile_filiale

    if lower.endswith(".pdf") and e_contabile_filiale(compact_pdf_text):
        return TIPO_CONTABILE_FILIALE
    if all(marker in compact_pdf_text for marker in (
        "SEZIONE 1", "LAVORATORE", "RECESSO DAL RAPPORTO DI LAVORO",
    )) or "MODULO RECESSO RAPPORTO DI LAVORO" in compact_pdf_text:
        return "dimissioni_telematiche"
    if "AVVISO DI PAGAMENTO TARI" in compact_pdf_text:
        return "tari_avviso"
    if (
        "ISTANZADIRIMBORSOCOMPENSAZIONETARI" in marker_pdf_text
        or "TARI-ISTANZARIMBORSOCOMPENSAZIONE" in marker_pdf_text
    ):
        return "tari_istanza_compensazione"
    if "VISURA ORDINARIA SOCIETA" in compact_pdf_text:
        return "visura_camerale"
    if any(marker in marker_pdf_text for marker in (
        "IDENTITAIDENTITYCARD", "CARTADIIDENTITA", "IDENTITYCARD",
    )):
        return "documento_identita"
    if "SOSPENSIONE LEGALE DELLA RISCOSSIONE" in compact_pdf_text:
        return "ader_sospensione"
    if any(marker in compact_pdf_text for marker in (
        "DICHIARAZIONE DI ADESIONE ALLA DEFINIZIONE AGEVOLATA",
        "ROTTAMAZIONE-QUATER", "ROTTAMAZIONE QUATER",
    )):
        return "ader_definizione_agevolata"
    if any(marker in compact_pdf_text for marker in (
        "VERBALE DI ACCERTAMENTO DI VIOLAZIONE",
        "RELAZIONE DI NOTIFICAZIONE DI ATTO AMMINISTRATIVO",
    )) and any(marker in compact_pdf_text for marker in (
        "CODICE DELLA STRADA", "SANZIONE AMMINISTRATIVA",
    )):
        return "verbale_codice_strada"
    # Le contabili bancarie sono prove documentali di un pagamento eseguito,
    # ma CBILL, MAV/RAV e bollettino postale conservano identificativi diversi
    # e non devono essere appiattiti su una ricevuta PagoPA generica.
    if any(marker in compact_pdf_text for marker in (
        "CODICE IDENTIFICATIVO CBILL", "CBILL - PAGOPA", "CODICE TRANSAZIONE CBILL",
    )):
        return "ricevuta_cbill"
    if "PAGAMENTO MAV" in compact_pdf_text:
        return "ricevuta_mav"
    if "PAGAMENTO RAV" in compact_pdf_text:
        return "ricevuta_rav"
    if "BOLLETTINO POSTALE" in compact_pdf_text and any(
        marker in compact_pdf_text for marker in ("COD.RIF", "ID. POSTE")
    ):
        return "ricevuta_bollettino_postale"
    if any(marker in compact_pdf_text for marker in (
        "ATTESTAZIONE DI PAGAMENTO", "ESITO : PAGAMENTO ESEGUITO",
        "IMPORTO TOTALE PAGATO", "RICEVUTA TELEMATICA",
    )):
        return "ricevuta_pagopa"
    # Ricevuta «per l'utente» di Mooney: il livello testo porta solo il marchio
    # e il riquadro degli importi, il resto e' un'immagine (lo legge l'OCR).
    # Il testo esce con le lettere spaziate («Mo  o  n  ey»): si confronta senza separatori.
    if "MOONEY" in marker_pdf_text and "RICEVUTAPERLUTENTE" in marker_pdf_text:
        return "ricevuta_pagopa"
    # «Ricevuta di pagamento» dell'Agente della Riscossione (attestazione dal
    # portale, una cartella o piu' documenti con lo stesso IUV).
    if (
        "RICEVUTA DI PAGAMENTO" in compact_pdf_text
        and "AGENTE DELLA RISCOSSIONE" in compact_pdf_text
        and "DETTAGLIO TRANSAZIONE" in compact_pdf_text
    ):
        return "ricevuta_pagopa"

    # Struttura positiva del modello F24.  Non dipendere dal nome file e non
    # usare una singola parola: una nota INPS o un avviso PagoPA possono
    # citare F24, ma non contengono simultaneamente delega, anagrafica e
    # griglia dei codici tributo/saldo.
    f24_structure_markers = (
        "CODICEFISCALE" in marker_pdf_text,
        "CODICETRIBUTO" in marker_pdf_text,
        "SALDOFINALE" in marker_pdf_text or "SALDODELEGA" in marker_pdf_text,
        "SEZIONEERARIO" in marker_pdf_text or "SEZIONEINPS" in marker_pdf_text
        or "SEZIONEREGIONI" in marker_pdf_text,
        bool(re.search(r"\b(?:1|2|3|6|7|8|9)\d{3}\b", pdf_text)),
    )
    if (
        "DELEGAIRREVOCABILE" in marker_pdf_text
        or "MODELLODIPAGAMENTOUNIFICATO" in marker_pdf_text
    ) and sum(f24_structure_markers) >= 2:
        # La stampa del Cassetto fiscale («Data/Ore/Utente», «Soggetto: ... ( cf )») ha la forma
        # del modello ma e' la copia di una delega VERSATA: una quietanza, anche senza protocollo.
        from app.services.f24_parser import e_stampa_cassetto

        if lower.endswith(".pdf") and e_stampa_cassetto(pdf_text):
            return "quietanza_f24"
        return "f24"
    # F24 pagata del 2018-2019: il modulo con i dati sovrapposti. Nessuna intestazione
    # («delega irrevocabile» non c'e'): comincia col codice banca+data (B, ABI, CAB, ggmmaa)
    # e ha righe di sezione (ERARIO, INPS, REGIONI, IMU/TRIB.LOCALI).
    if (
        lower.endswith(".pdf")
        and re.match(r"\s*(?:\[PAGINA \d+\]\s*)?B\d{15,17}\b", pdf_text)
        and any(sezione in pdf_text for sezione in ("ERARIO", "INPS", "REGIONI", "TRIB.LOCALI"))
    ):
        return "quietanza_f24"
    if (
        "AVVISO DI PAGAMENTO" in compact_pdf_text
        or "QUANTO E QUANDO PAGARE" in compact_pdf_text
        or "RATA UNICA ENTRO IL" in compact_pdf_text
    ):
        return "avviso_pagopa"

    # Segnali espliciti nel nome, dal piu specifico al piu generico.
    if "identita" in lower or "identity_card" in lower:
        return "documento_identita"
    if "visura" in lower:
        return "visura_camerale"
    if "tari" in lower and any(marker in lower for marker in ("istanza", "rimborso", "compensazione")):
        return "tari_istanza_compensazione"
    if any(keyword in lower for keyword in ("ricevutatelematica", "ricevuta_pagopa", "ricevuta-pagopa")):
        return "ricevuta_pagopa"
    if any(keyword in lower for keyword in (
        "quietanza_cbill", "quietanza-cbill", "ricevuta_cbill", "ricevuta-cbill",
    )):
        return "ricevuta_pagopa"
    if any(keyword in lower for keyword in ("avvisodigitale", "avviso_pagopa", "avviso-pagopa")):
        return "avviso_pagopa"
    if any(keyword in lower for keyword in ("rettifica", "dmra")) and "inps" in compact_pdf_text:
        return "nota_rettifica_inps"
    if (
        any(keyword in lower for keyword in ("cbill", "pagopa", "pago_pa", "pago-pa"))
        and any(keyword in lower for keyword in ("quietanza", "ricevuta", "pagamento", "eseguito"))
    ):
        return "ricevuta_pagopa"
    if any(keyword in lower for keyword in ("cbill", "pagopa", "pago_pa", "pago-pa")):
        # Dal solo nome non e' possibile affermare che il pagamento sia
        # avvenuto: il default sicuro e' avviso/obbligazione.
        return "avviso_pagopa"
    if any(keyword in lower for keyword in (
        "quietanza", "ricevuta_f24", "ricevuta-f24", "pagamento_f24",
    )):
        return "quietanza_f24"
    if re.search(r"(^|[^a-z0-9])f24([^a-z0-9]|$)", lower) or "delega_f24" in lower:
        return "f24"
    if lower.endswith(".pdf") and any(keyword in lower for keyword in (
        "cedolin", "busta_paga", "busta paga", "libro_unico", "libro unico", "lul",
        "tredicesima", "quattordicesima",
    )):
        # Solo un PDF: «Indice_Cedolini_Gestionale.xlsx» non e' una busta paga.
        return "cedolino"
    if any(keyword in lower for keyword in ("bonifico", "bonifici", "sepa", "transfer")):
        return "bonifici"
    if any(keyword in lower for keyword in ("fattura", "invoice", "ft_")):
        return "fattura"

    if lower.endswith(".pdf"):
        # L'area Estratti conto contiene PDF dal nome generico
        # ``Estratto_Conto (N).pdf``. Prima di appiattirli sul conto corrente
        # usa lo stesso classificatore documentale del job Drive: Nexi,
        # PayPal e mutui hanno registri e regole contabili distinti.
        from app.services.classificazione_estratti import classifica

        statement_route, _reason = classifica(filename, file_content)
        routed_type = {
            "nexi": "estratto_conto_nexi",
            "paypal": "estratto_conto_paypal",
            "mutuo": "estratto_conto_mutuo",
            "sumup": "estratto_conto_sumup",
            "bank": "estratto_conto",
        }.get(statement_route)
        if routed_type:
            return routed_type
        content_str = pdf_text
        if any(marker in content_str for marker in (
            "QUIETANZA", "RICEVUTA DI VERSAMENTO", "ESITO DEL VERSAMENTO F24",
        )):
            return "quietanza_f24"
        # La LIPE ha il campo «VERSAMENTI AUTO F24»: cita F24 ma non e' un modello.
        e_lipe = "LIQUIDAZIONIPERIODICHE" in re.sub(r"[^A-Z]", "", content_str)
        f24_forte = (
            "DELEGA IRREVOCABILE A" in content_str
            or "MODELLO DI PAGAMENTO UNIFICATO" in content_str
            or ("SEZIONE ERARIO" in content_str and "CODICE TRIBUTO" in content_str)
        )
        # Anche 770, IRAP e Redditi citano «F24» (versamenti, compensazioni): la sola
        # sigla nel testo non basta, se il documento e' una dichiarazione. Sono finite
        # cosi' nel lettore dei modelli, che le bloccava come «F24 non quadrato».
        if not e_lipe and (
            f24_forte
            or (re.search(r"\bF\s*24\b", content_str)
                and not _tipo_dichiarazione(filename, pdf_text))
        ):
            return "f24"
        if any(marker in content_str for marker in ("CEDOLINO", "BUSTA PAGA", "LIBRO UNICO")):
            return "cedolino"
        # «estratto conto» da solo non e' un segno: i fornitori lo scrivono nei solleciti
        # («INVIO ESTRATTO CONTO - FATTURE SCADUTE»). Serve anche la forma dell'estratto.
        from app.services.classificazione_estratti import ha_struttura_di_estratto

        if (
            ("ESTRATTO CONTO" in content_str and ha_struttura_di_estratto(content_str))
            or ("SALDO INIZIALE" in content_str and "SALDO FINALE" in content_str)
        ):
            return "estratto_conto"
        if "BONIFICO" in content_str and ("IBAN" in content_str or "CRO" in content_str):
            return "bonifici"
        return _tipo_dichiarazione(filename, pdf_text) or "auto"

    if lower.endswith((".xlsx", ".xls", ".csv")):
        content_str = _spreadsheet_text_for_detection(lower, file_content).upper()
        if lower.endswith(".csv"):
            from app.services.pagamenti_buoni import is_canonical_csv
            if is_canonical_csv(file_content):
                return "pagamenti_buoni"
            if all(m in content_str for m in ("ID INVIO", "MATRICOLA DISPOSITIVO", "AMMONTARE DELLE VENDITE")):
                return "corrispettivi_csv_ade"
            from app.services.fatture_report_ae import e_csv_ade
            if e_csv_ade(file_content, filename):
                return "report_fatture_ricevute"
        if all(marker in content_str for marker in ("IMPORTO NETTO", "IMPORTO IVA", "FORNITORE", "STATO DEL PAGAMENTO")):
            return "spese_sumup"
        if all(marker in content_str for marker in (
            "ID SDI", "METODO DI PAGAMENTO", "TOTALE DOCUMENTO",
            "NETTO A PAGARE", "FORNITORE",
        )):
            return "report_fatture_ricevute"
        from app.services.fatture_emesse import MARCATORI_REPORT_CLIENTI
        if all(marker in content_str for marker in MARCATORI_REPORT_CLIENTI):
            return "anagrafica_clienti"
        if (
            any(keyword in lower for keyword in ("distint", "stipend", "elenco"))
            and "BENEFICIARIO" in content_str
            and ("IMPORTO" in content_str or "IBAN" in content_str)
        ):
            return "distinte_bpm"
        # Gli export Numia/BPM iniziano con Export_Mensile/Transazioni e
        # contengono Data e ora + Stato operazione + terminale/MID. Non sono
        # estratti bancari e non devono essere archiviati come generici AUTO.
        from app.services.classificazione_estratti import classifica

        statement_route, _reason = classifica(filename, file_content)
        if statement_route == "pos":
            return "pos_terminal"
        if statement_route == "sumup":
            return "estratto_conto_sumup"
        if statement_route == "bank":
            return "estratto_conto"
        bank_name = any(keyword in lower for keyword in (
            "estratto", "movimenti", "bpm", "banco", "bank_statement",
        ))
        bank_headers = (
            ("DATA" in content_str or "VALUTA" in content_str)
            and ("CAUSALE" in content_str or "DESCRIZIONE" in content_str)
            and ("IMPORTO" in content_str or "DARE" in content_str or "AVERE" in content_str)
        )
        return "estratto_conto" if bank_name or bank_headers else "auto"

    return "auto"


def _fiscal_archive_info(archive_path: str) -> tuple[str, int] | None:
    """Ricava una categoria fiscale solo dalla struttura canonica dello ZIP.

    La regola e' volutamente stretta: accetta esclusivamente il PDF completo
    ``<categoria>/<anno>/<file>.pdf``. I singoli quadri conservati, ad esempio,
    sotto ``770/<anno>/componenti_originali/...`` restano documenti di supporto
    e non diventano seconde dichiarazioni complete.
    """
    normalized = str(archive_path or "").replace("\\", "/").strip("/")
    marker = "/01_DICHIARAZIONI_FISCALI/"
    if marker not in f"/{normalized}":
        return None
    relative = f"/{normalized}".split(marker, 1)[1]
    parts = [part for part in relative.split("/") if part]
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].lower().endswith(".pdf"):
        return None
    category = {
        "770": "modello_770",
        "lipe": "lipe",
        "iva": "dichiarazione_iva",
        "irap": "dichiarazione_irap",
        "redditi_sc": "redditi_sc",
    }.get(parts[0].lower())
    return (category, int(parts[1])) if category else None


def _fiscal_category_from_archive_path(archive_path: str) -> str | None:
    info = _fiscal_archive_info(archive_path)
    return info[0] if info else None


async def _importa_estratto_conto_file(filename: str, content: bytes) -> Dict[str, Any]:
    """Un estratto conto dal caricamento manuale: lo stesso motore dell'upload
    diretto e della coda (un anno di BPM supera i 2 minuti del browser)."""
    from app.routers.bank.estratto_conto import import_estratto_conto

    class _FakeUpload:
        pass

    upload = _FakeUpload()
    upload.filename = filename

    async def _read():
        return content

    upload.read = _read
    esito: Dict[str, Any] = {"tipo_rilevato": "estratto_conto"}
    try:
        ec_result = await import_estratto_conto(upload)
        stats = ec_result.get("stats", {})
        nuovi = stats.get("nuovi", 0)
        dup = stats.get("duplicati", 0)
        esito.update({
            "success": True,
            "message": (
                f"Estratto conto importato: {nuovi} movimenti nuovi, "
                f"{dup} duplicati saltati."
            ),
            "imported": nuovi,
            "duplicates": dup,
            "movimenti_nuovi": nuovi,
            "duplicati_saltati": dup,
            "totale_letti": stats.get("totale_letti", nuovi + dup),
            "riconciliazione": ec_result.get("riconciliazione_summary"),
        })
    except Exception as ec_err:
        logger.error(
            "Import estratto conto fallito: %s (%s)", ec_err, type(ec_err).__name__,
        )
        esito.update({
            "success": False,
            "message": f"Errore import estratto conto: {str(ec_err)}",
        })
    return esito


async def _process_zip_upload_a_blocchi(filename: str, content: bytes) -> Dict[str, Any]:
    """Uno ZIP fiscale puo generare centinaia di versioni, pagine e prove.
    Il runtime Drive/Supabase sa consolidarle per collezione e scriverle in
    blocchi; senza questo contesto ogni singola pagina consuma una richiesta e
    supera rapidamente la quota Google di 60 write/minuto."""
    db = Database.get_db()
    batch_writes = getattr(db, "batch_writes", None)
    if callable(batch_writes):
        async with batch_writes():
            return await _process_zip_upload(filename, content)
    return await _process_zip_upload(filename, content)


async def _process_zip_upload(filename: str, content: bytes) -> Dict[str, Any]:
    """Espande un archivio solo dopo controlli anti zip-bomb.

    Non scrive sul filesystem e non accetta ZIP annidati. Ogni documento
    passa poi dallo stesso endpoint canonico, quindi mantiene deduplica e
    propagazioni del proprio workflow.
    """
    import io
    import zipfile

    from app.services.partenopay_archive_import import (
        import_partenopay_archive,
        is_partenopay_archive,
    )
    if is_partenopay_archive(content):
        result = await import_partenopay_archive(Database.get_db(), content, dry_run=False)
        return {
            **result,
            "tipo_rilevato": "archivio_partenopay",
            "workflow": "PARTENOPAY_ARCHIVIO_PROBATORIO",
            "filename": filename,
            "imported": result.get("inserted_or_updated", 0),
            "duplicates": result.get("invariati", 0),
            "errors": len(result.get("integrity_errors") or []),
        }

    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except (OSError, zipfile.BadZipFile) as exc:
        raise HTTPException(status_code=400, detail=f"Archivio ZIP non valido: {exc}") from exc

    with archive:
        entries = [
            info for info in archive.infolist()
            if not info.is_dir() and not info.filename.startswith("__MACOSX/")
        ]
        if not entries:
            raise HTTPException(status_code=400, detail="Archivio ZIP vuoto")
        if len(entries) > MAX_ZIP_FILES:
            raise HTTPException(
                status_code=413,
                detail=f"Archivio con troppi file: {len(entries)} (massimo {MAX_ZIP_FILES})",
            )

        total_uncompressed = sum(max(0, info.file_size) for info in entries)
        if total_uncompressed > MAX_ZIP_UNCOMPRESSED_BYTES:
            raise HTTPException(
                status_code=413,
                detail="Contenuto ZIP non compresso oltre il limite di 250 MB",
            )
        for info in entries:
            if info.file_size > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"File troppo grande nell'archivio: {Path(info.filename).name}",
                )
            if info.file_size and info.compress_size == 0:
                raise HTTPException(status_code=400, detail="Rapporto di compressione ZIP non valido")
            if info.compress_size and info.file_size / info.compress_size > MAX_ZIP_COMPRESSION_RATIO:
                raise HTTPException(
                    status_code=400,
                    detail=f"Compressione ZIP sospetta: {Path(info.filename).name}",
                )

        dettagli: List[Dict[str, Any]] = []
        importati = duplicati = errori = scartati = contabilita_ripristinata = 0
        for info in entries:
            clean_name = Path(info.filename).name
            suffix = Path(clean_name).suffix.lower()
            if not clean_name or suffix not in SUPPORTED_UPLOAD_SUFFIXES or suffix == ".zip":
                scartati += 1
                dettagli.append({
                    "filename": clean_name or info.filename,
                    "success": False,
                    "message": "Formato non supportato o archivio annidato ignorato",
                })
                continue
            payload = archive.read(info)
            nested_upload = UploadFile(filename=clean_name, file=io.BytesIO(payload))
            normalized_path = info.filename.replace("\\", "/")
            nested_upload.source_context = {
                "archive_filename": filename,
                "archive_path": normalized_path,
                "archive_group": str(Path(normalized_path).parent).replace("\\", "/"),
                "archive_sha256": hashlib.sha256(content).hexdigest(),
            }
            fiscal_info = _fiscal_archive_info(normalized_path)
            if fiscal_info:
                import asyncio
                from app.services.drive_declaration_upload import upload_declaration
                from app.services.fiscal_document_ingestion import FiscalDocumentIngestionService

                fiscal_category, filing_year = fiscal_info
                drive_item = await asyncio.to_thread(
                    upload_declaration,
                    content=payload,
                    filename=clean_name,
                    category=fiscal_category,
                    filing_year=filing_year,
                    note=f"Import da {filename}: {normalized_path}",
                )
                fiscal_source = {
                    **nested_upload.source_context,
                    "drive_document_id": drive_item.get("document_id"),
                    "drive_file_id": drive_item.get("drive_file_id"),
                    "drive_path": drive_item.get("drive_path"),
                    "drive_url": drive_item.get("drive_url"),
                }
                fiscal_item = await FiscalDocumentIngestionService(Database.get_db()).ingest(
                    content=payload,
                    filename=clean_name,
                    source="documenti_upload_auto_zip",
                    category_hint=fiscal_category,
                    source_metadata=fiscal_source,
                    expected_sha256=hashlib.sha256(payload).hexdigest(),
                )
                duplicate = fiscal_item.get("status") == "duplicate"
                if duplicate:
                    duplicati += 1
                else:
                    importati += 1
                dettagli.append({
                    "filename": clean_name,
                    "archive_path": normalized_path,
                    "tipo_rilevato": fiscal_category,
                    "success": True,
                    "duplicate": duplicate,
                    "accounting_repaired": False,
                    "message": (
                        "Documento fiscale gia presente"
                        if duplicate else "Documento importato nel registro fiscale"
                    ),
                })
                continue
            from app.services.document_import_preview import create_confirmation_token

            nested_type = await rileva_tipo_documento(clean_name, payload)
            nested_token = create_confirmation_token(
                hashlib.sha256(payload).hexdigest(), nested_type
            )
            item = await upload_documento_automatico(
                file=nested_upload, preview_token=nested_token
            )
            item = item if isinstance(item, dict) else {"success": False, "message": str(item)}
            duplicate = bool(item.get("duplicate") or item.get("action") == "duplicate")
            if item.get("accounting_repaired"):
                contabilita_ripristinata += 1
            if duplicate:
                duplicati += 1
            elif item.get("success") is False:
                errori += 1
            else:
                importati += max(1, int(item.get("imported") or 0))
            dettagli.append({
                "filename": clean_name,
                "archive_path": info.filename.replace("\\", "/"),
                "tipo_rilevato": item.get("tipo_rilevato"),
                "success": item.get("success", True),
                "duplicate": duplicate,
                "accounting_repaired": bool(item.get("accounting_repaired")),
                "message": item.get("message"),
            })

    processati = importati + duplicati + errori
    success = processati > 0 and errori == 0
    return {
        "success": success,
        "partial": bool((errori or scartati) and (importati or duplicati)),
        "tipo_rilevato": "archivio_zip",
        "workflow": "ARCHIVIO_ZIP_SICURO",
        "filename": filename,
        "imported": importati,
        "duplicates": duplicati,
        "accounting_repaired": contabilita_ripristinata,
        "errors": errori,
        "skipped": scartati,
        "action": "duplicate" if duplicati and not importati and not errori else "processed",
        "duplicate": bool(duplicati and not importati and not errori),
        "message": (
            f"ZIP elaborato: {importati} importati, {duplicati} duplicati, "
            f"{errori} errori, {scartati} ignorati"
            + (f", {contabilita_ripristinata} scritture Prima Nota ripristinate" if contabilita_ripristinata else "")
        ),
        "details": dettagli,
    }


def _messaggio_componente_770(metadata: Dict[str, Any], *, gia_presente: bool) -> str:
    quadro = metadata.get("quadro") or "?"
    if metadata.get("dichiarazione_id"):
        testo = f"Quadro {quadro} del 770 agganciato a {metadata.get('dichiarazione_filename')}"
    else:
        testo = (f"Quadro {quadro} del 770 conservato: manca il 770 intero "
                 f"({metadata.get('identificativo_dichiarazione') or 'identificativo non leggibile'})")
    return f"{testo} (era già in coda, riclassificato)" if gia_presente else testo


async def _archive_non_payment_document(
    db, *, filename: str, content: bytes, document_type: str,
    metadata: Dict[str, Any] | None = None,
    source_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Archivia un'obbligazione senza promuoverla a prova di pagamento."""
    if len(content) > MAX_INBOX_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Documento di obbligazione oltre il limite inbox di 10 MB",
        )
    digest = hashlib.sha256(content).hexdigest()
    existing = await db["documents_inbox"].find_one(
        {"sha256": digest}, {"_id": 0, "id": 1, "filename": 1},
    )
    if existing:
        return {
            "success": False, "duplicate": True, "action": "duplicate",
            "imported": 0, "tipo_rilevato": document_type,
            "doc_id": existing.get("id"), "filename": filename,
            "message": f"Documento gia acquisito: {existing.get('filename') or filename}",
        }
    import base64

    now = datetime.now(timezone.utc).isoformat()
    doc_id = f"upload_{document_type}_{digest[:16]}"
    labels = {
        "avviso_pagopa": "Avviso PagoPA da collegare",
        "nota_rettifica_inps": "Nota di rettifica INPS da verificare",
        "esito_pagopa_negativo": "Pagamento PagoPA non eseguito",
        "tari_avviso": "Avviso TARI da collegare",
        "tari_istanza_compensazione": "Istanza rimborso/compensazione TARI",
        "ader_sospensione": "Istanza di sospensione riscossione",
        "ader_definizione_agevolata": "Definizione agevolata AdeR",
        "dimissioni_telematiche": "Modulo dimissioni telematiche",
        "verbale_codice_strada": "Verbale Codice della strada",
        "visura_camerale": "Visura camerale",
        "documento_identita": "Documento di identita allegato",
        "componente_770": "Quadro del 770",
        "dilazione_inps": "Dilazione INPS (piano di ammortamento)",
        "prospetto_contabile": "Prospetto contabile del consulente",
    }
    negative_outcome = document_type == "esito_pagopa_negativo"
    evidence_roles = {
        "esito_pagopa_negativo": "esito_negativo",
        "dimissioni_telematiche": "evidenza_rapporto_lavoro",
        "ader_sospensione": "istanza_amministrativa",
        "ader_definizione_agevolata": "istanza_amministrativa",
        "verbale_codice_strada": "obbligazione",
        "tari_istanza_compensazione": "istanza_amministrativa",
        "visura_camerale": "documento_anagrafico",
        "documento_identita": "allegato_identita",
        "componente_770": "componente_dichiarazione",
        "dilazione_inps": "obbligazione",
        "prospetto_contabile": "documento_di_supporto",
    }
    if metadata is None and document_type in {
        "tari_avviso", "tari_istanza_compensazione", "visura_camerale",
        "documento_identita", "ader_sospensione", "ader_definizione_agevolata",
        "dimissioni_telematiche",
    }:
        from app.services.administrative_document_parser import extract_administrative_metadata

        metadata = extract_administrative_metadata(
            content=content, filename=filename, document_type=document_type,
        )
    association_candidates: list[dict[str, Any]] = []
    if document_type == "dimissioni_telematiche" and (metadata or {}).get("lavoratore_cf"):
        employees = await db["dipendenti"].find(
            {"codice_fiscale": (metadata or {})["lavoratore_cf"]},
            {"_id": 0, "id": 1, "codice_fiscale": 1, "nome": 1, "cognome": 1},
        ).limit(5).to_list(5)
        association_candidates.extend({"entity_type": "dipendente", **item} for item in employees)
    elif document_type in {"ader_sospensione", "ader_definizione_agevolata"}:
        claim_numbers = (metadata or {}).get("numeri_cartella") or []
        if claim_numbers:
            claims = await db["tax_collection_claims"].find(
                {"collection_number": {"$in": claim_numbers}},
                {"_id": 0, "id": 1, "collection_number": 1, "portal_status": 1},
            ).limit(100).to_list(100)
            association_candidates.extend({"entity_type": "cartella_ader", **item} for item in claims)
    parsed_metadata = metadata or {}
    record = {
        "id": doc_id, "filename": filename,
        "pdf_data": base64.b64encode(content).decode("ascii"),
        "file_hash": digest, "sha256": digest, "hash_algorithm": "sha256",
        "file_size": len(content), "category": document_type,
        "category_label": labels.get(document_type, document_type),
        "document_type": document_type,
        "evidence_role": evidence_roles.get(document_type, "obbligazione"),
        "is_payment_evidence": False, "pagato": False, "chiuso": False,
        "status": "pagamento_non_eseguito" if negative_outcome else "da_verificare",
        "processed": negative_outcome,
        "source": "upload_automatico", "downloaded_at": now,
        "source_context": source_context or {},
        "parsed_metadata": parsed_metadata,
        "obligation_status": parsed_metadata.get("obligation_status") or "APERTO",
        "data_scadenza": parsed_metadata.get("data_scadenza"),
        "relation_keys": parsed_metadata.get("relation_keys") or {},
        "parser_version": parsed_metadata.get("parser_version"),
        "association_candidates": association_candidates,
        # La policy contabile e' pura: viene conservata come proposta/audit
        # output, mai come scrittura nel registro definitivo.
        "journal_proposal": parsed_metadata.get("journal_proposal"),
    }
    await db["documents_inbox"].insert_one(record.copy())
    adempimenti = None
    if document_type == "dimissioni_telematiche":
        # Titolare 14/09/2026: il modulo di dimissioni e' la conferma delle
        # dimissioni -> alert HR + scadenza UNILAV (5 giorni). Mai bloccante.
        try:
            from app.services.dimissioni_adempimenti import registra_dimissioni

            adempimenti = await registra_dimissioni(
                db, parsed_metadata, documento_id=doc_id, filename=filename)
        except Exception:
            logger.exception("Dimissioni %s: adempimenti non registrati", doc_id)
    return {
        "success": True, "duplicate": False, "imported": 1,
        "adempimenti_dimissioni": adempimenti,
        "tipo_rilevato": document_type, "doc_id": doc_id,
        "filename": filename, "workflow": "OBBLIGAZIONE_DOCUMENTALE",
        "payment_evidence": False,
        "association_candidates": association_candidates,
        "journal_proposal": parsed_metadata.get("journal_proposal"),
        "message": labels.get(document_type, "Documento archiviato per verifica"),
    }


@router.post("/upload-auto/preview")
@handle_errors
async def anteprima_upload_documento_automatico(
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    """Classifica ed estrae senza creare documenti o fatti contabili."""
    filename = Path(file.filename or "documento").name
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail=f"File vuoto: {filename}")
    upload_limit = MAX_ZIP_UPLOAD_BYTES if filename.lower().endswith(".zip") else MAX_UPLOAD_BYTES
    if len(content) > upload_limit:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Archivio ZIP oltre il limite di 100 MB: {filename}"
                if filename.lower().endswith(".zip")
                else f"File oltre il limite di 50 MB: {filename}"
            ),
        )
    if filename.lower().endswith(".pdf"):
        from app.utils.upload_validation import verifica_pdf_reale

        verifica_pdf_reale(content, filename)

    document_type = await rileva_tipo_documento(filename, content)
    from app.services.document_import_preview import build_import_preview

    return await build_import_preview(
        Database.get_db(), content=content, filename=filename,
        document_type=document_type,
    )


@router.post("/upload-auto/render/preview")
@handle_errors
async def anteprima_upload_documento_render(
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    """Ponte Render: riusa integralmente l'anteprima canonica esistente."""
    return await anteprima_upload_documento_automatico(file=file)


@router.post("/upload-auto/render")
@handle_errors
async def upload_documento_render(
    file: UploadFile = File(...),
    preview_token: Optional[str] = Header(None, alias="X-Document-Preview-Token"),
    drive_file_id: Optional[str] = Header(None, alias="X-Source-Drive-File-ID"),
    drive_parent_id: Optional[str] = Header(None, alias="X-Source-Drive-Parent-ID"),
    source_sha256: Optional[str] = Header(None, alias="X-Source-SHA256"),
    archive_member: Optional[str] = Header(None, alias="X-Source-Archive-Member"),
) -> Dict[str, Any]:
    """Ponte autenticato Render verso lo stesso upload-auto del Gestionale."""
    from urllib.parse import unquote

    file.source_context = {
        "channel": "render_calderone",
        "drive_file_id": drive_file_id,
        "drive_parent_id": drive_parent_id,
        "source_sha256": source_sha256,
        "archive_member": unquote(archive_member or "") or None,
    }
    return await upload_documento_automatico(
        file=file, preview_token=preview_token,
    )


@router.get("/cartella-unica/stato")
@handle_errors
async def stato_cartella_unica(
    _admin: Dict[str, Any] = Depends(richiedi_admin),
) -> Dict[str, Any]:
    """Ultimo giro della cartella unica Drive e conteggi del registro."""
    from app.services import drive_cartella_unica as cu

    db = Database.get_db()
    stato = await db["sistema_stato"].find_one({"chiave": cu.CHIAVE_STATO}, {"_id": 0})
    conteggi = {}
    for cartella in (cu.ARCHIVIO, cu.ERRORI, cu.DOPPIONI, cu.ARRETRATO, "CESTINO", "RIMOSSO"):
        conteggi[cartella] = await db[cu.REGISTRO].count_documents({"cartella": cartella})
    return {"attiva": cu.attivo(),
            "giro_in_corso": cu._lock.locked() or cu.svuotamento_in_corso(),
            "ultimo_giro": stato, "registro": conteggi}


@router.post("/cartella-unica/giro")
@handle_errors
async def avvia_giro_cartella_unica(
    background_tasks: BackgroundTasks,
    tutto: bool = Query(False, description="Giri uno dopo l'altro finche' la cartella e' vuota"),
    _admin: Dict[str, Any] = Depends(richiedi_admin),
) -> Dict[str, Any]:
    """Un giro subito sulla cartella DA ELABORARE, in sottofondo; con
    ``tutto=true`` continua finche' la cartella non e' vuota."""
    from app.services import drive_cartella_unica as cu

    if not cu.radice():
        raise HTTPException(status_code=409, detail="GOOGLE_DRIVE_DATI_FOLDER_ID non impostata")
    if not cu.import_attivo():
        raise HTTPException(status_code=409, detail="Import in pausa (DRIVE_CARTELLA_UNICA_IMPORT=false)")
    if cu._lock.locked() or cu.svuotamento_in_corso():
        return {"avviato": False, "motivo": "giro_in_corso"}
    background_tasks.add_task(cu.svuota if tutto else cu.giro, Database.get_db())
    return {"avviato": True, "tutto": tutto}


@router.get("/drive-doppioni")
@handle_errors
async def censimento_doppioni_drive(
    _admin: Dict[str, Any] = Depends(richiedi_admin),
) -> Dict[str, Any]:
    """Censimento della cartella GESTIONALE: copie identiche e file tecnici da eliminare."""
    from app.services import drive_censimento_doppioni as censimento

    dati = await censimento.elenco(Database.get_db())
    return {"stato": dati["stato"], "totale": len(dati["righe"]), "righe": dati["righe"][:2000]}


@router.get("/drive-doppioni.csv")
async def censimento_doppioni_drive_csv(
    _admin: Dict[str, Any] = Depends(richiedi_admin),
) -> StreamingResponse:
    """L'elenco completo da riguardare, una riga per file marcato."""
    import csv
    import io

    from app.services import drive_censimento_doppioni as censimento

    dati = await censimento.elenco(Database.get_db())
    buffer = io.StringIO()
    scrittore = csv.writer(buffer, delimiter=";")
    scrittore.writerow(["Cartella", "Nome del file", "Tipo", "Motivo", "Originale che resta",
                        "Cartella dell'originale", "MB", "Rinomina", "Link"])
    for r in dati["righe"]:
        marcatura = r.get("marcatura") or {}
        scrittore.writerow([
            r.get("percorso"), r.get("nome"),
            "Duplicato" if r.get("ruolo") == "duplicato" else "File tecnico",
            r.get("motivo") or "", r.get("originale_nome") or "", r.get("originale_percorso") or "",
            f"{(r.get('size') or 0) / 1048576:.2f}".replace(".", ","),
            marcatura.get("nuovo_nome") or marcatura.get("motivo") or ("gia' marcato" if r.get("gia_marcato") else "da fare"),
            f"https://drive.google.com/file/d/{r.get('file_id')}/view",
        ])
    return StreamingResponse(
        iter(["\ufeff" + buffer.getvalue()]), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="doppioni_gestionale.csv"'},
    )


def _e_parcella_con_ritenuta(fattura: Dict[str, Any]) -> bool:
    """Una parcella con ritenuta d'acconto entra anche se e' di un anno passato.

    Decisione del titolare (29/09/2026): ogni 1040 versato deve avere la prova
    della sua fattura, quindi le parcelle con `DatiRitenuta` di qualunque anno
    entrano in archivio come fatture intere e alimentano le Ritenute. Le altre
    fatture di anni passati restano fuori (regola del 20/09/2026).
    """
    try:
        return Decimal(str(fattura.get("importo_ritenuta") or 0)) > 0
    except (InvalidOperation, ValueError):
        return False


async def _chiusura_fuori_anno(db, parsed: Dict[str, Any], result: Dict[str, Any]) -> bool:
    """Vero se la chiusura RT e' di un anno diverso da quello attivo.

    Dello storico interessano solo cedolini e F24: una chiusura di un altro
    anno non entra nei corrispettivi ne' in Prima Nota. Il 26/09/2026 una
    chiusura del 14/03/2023 arrivata dalla cartella unica era entrata, con i
    suoi contanti in cassa. Data mancante: resta nel flusso, come fa il motore.
    """
    from app.services.config_import import get_anno_importazione_attivo

    data_rt = str(parsed.get("data") or "")
    anno_rt = int(data_rt[:4]) if data_rt[:4].isdigit() else None
    anno_attivo = await get_anno_importazione_attivo(db)
    if not anno_rt or anno_rt == anno_attivo:
        return False
    result["imported"] = 0
    result["skipped_altro_anno"] = 1
    result["tipo_documento"] = "corrispettivo"
    result["message"] = (
        f"Chiusura RT del {data_rt}: l'anno attivo e' il {anno_attivo}, "
        "non entra nel gestionale e l'originale resta su Drive"
    )
    return True


@router.post("/upload-auto")
@handle_errors
async def upload_documento_automatico(
    file: UploadFile = File(...),
    preview_token: Optional[str] = Header(None, alias="X-Document-Preview-Token"),
) -> Dict[str, Any]:
    """
    Upload documento con riconoscimento automatico del tipo.

    Analizza nome file e contenuto per determinare il tipo:
    - PDF F24 → /api/f24/upload-pdf
    - PDF Quietanza F24 → /api/quietanze-f24/upload
    - PDF Cedolino → /api/employees/paghe/upload-pdf
    - XML Fattura → /api/fatture/upload-xml
    - Excel/CSV Estratto Conto → /api/estratto-conto-movimenti/import
    - Excel Bonifici → Archivio bonifici

    Se non riconosciuto, salva in documents_inbox per processamento manuale.
    """

    filename = Path(file.filename or "documento").name
    source_context = getattr(file, "source_context", None) or {}
    content = await file.read()

    if not content:
        raise HTTPException(status_code=400, detail=f"File vuoto: {filename}")
    upload_limit = MAX_ZIP_UPLOAD_BYTES if filename.lower().endswith(".zip") else MAX_UPLOAD_BYTES
    if len(content) > upload_limit:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Archivio ZIP oltre il limite di 100 MB: {filename}"
                if filename.lower().endswith(".zip")
                else f"File oltre il limite di 50 MB: {filename}"
            ),
        )
    if filename.lower().endswith(".pdf"):
        from app.utils.upload_validation import verifica_pdf_reale

        verifica_pdf_reale(content, filename)

    # Rileva tipo. La cartella unica Drive lo ha gia' letto (e in anticipo,
    # mentre il file davanti si registrava): rileggere un PDF per intero, OCR
    # compreso, raddoppiava il tempo di ogni file riconosciuto.
    tipo_rilevato = getattr(file, "tipo_rilevato_noto", None)
    if not isinstance(tipo_rilevato, str) or not tipo_rilevato:
        tipo_rilevato = await rileva_tipo_documento(filename, content)

    from app.services.document_import_preview import verify_confirmation_token
    from fastapi.params import Header as HeaderParameter

    content_sha256 = hashlib.sha256(content).hexdigest()
    direct_internal_call = isinstance(preview_token, HeaderParameter)
    if not direct_internal_call and (
        not preview_token or not verify_confirmation_token(
            preview_token, content_sha256, tipo_rilevato
        )
    ):
        raise HTTPException(
            status_code=428,
            detail=(
                "Anteprima obbligatoria mancante, scaduta o riferita a un file diverso. "
                "Eseguire /api/documenti/upload-auto/preview e confermare il risultato."
            ),
        )

    logger.info(f"Upload automatico: {filename} -> tipo rilevato: {tipo_rilevato}")

    if tipo_rilevato == "archivio_zip":
        # Uno ZIP fiscale puo generare centinaia di versioni, pagine e prove.
        # Il runtime Drive/Supabase sa consolidarle per collezione e scriverle in
        # blocchi; senza questo contesto ogni singola pagina consuma una
        # richiesta e supera rapidamente la quota Google di 60 write/minuto.
        return await _process_zip_upload_a_blocchi(filename, content)

    # Se non riconosciuto, salva in inbox
    if tipo_rilevato == 'auto':
        # documents_inbox conserva il payload in Base64 dentro Drive/Supabase: oltre
        # 10 MB il record si avvicina al limite BSON di 16 MB. I documenti
        # grandi devono passare da un workflow riconosciuto o da Drive.
        if len(content) > MAX_INBOX_BYTES:
            raise HTTPException(
                status_code=413,
                detail="Documento non riconosciuto oltre il limite inbox di 10 MB",
            )
        db = Database.get_db()

        # Salva file in cartella temporanea
        file_hash = hashlib.md5(content).hexdigest()

        # La stessa prova puo arrivare da upload, Gmail, PEC o Drive. Non si
        # crea una seconda copia soltanto perche cambia il canale di ingresso.
        # L'MD5 trova il candidato, lo SHA-256 del contenuto decide.
        try:
            from app.services.deduplica import esiste_documento_cross_canale

            cross_channel = await esiste_documento_cross_canale(db, file_hash, contenuto=content)
        except Exception as exc:
            logger.warning("Dedup cross-canale di %s non riuscita: %s: %s",
                           filename, type(exc).__name__, exc)
            cross_channel = None
        if cross_channel and cross_channel.get("collezione") == "documents_inbox":
            existing = await db["documents_inbox"].find_one(
                {"id": cross_channel.get("id")}, {"_id": 0, "id": 1, "filename": 1},
            ) or {}
            return {
                "success": False,
                "duplicate": True,
                "action": "duplicate",
                "imported": 0,
                "tipo_rilevato": "non_riconosciuto",
                "message": f"Documento duplicato ignorato: {existing.get('filename') or filename}",
                "doc_id": cross_channel.get("id"),
                "filename": filename,
            }
        if cross_channel:
            return {
                "success": False,
                "duplicate": True,
                "action": "duplicate",
                "imported": 0,
                "tipo_rilevato": "non_riconosciuto",
                "message": "Documento duplicato gia acquisito da un altro canale",
                "filename": filename,
            }

        doc_id = f"upload_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{file_hash[:8]}"

        # Salva nell'archivio del runtime senza copie locali permanenti.
        import base64
        pdf_base64 = base64.b64encode(content).decode('utf-8')

        doc_record = {
            "id": doc_id,
            "filename": filename,
            "pdf_data": pdf_base64,  # Contenuto in Drive/Supabase!
            "category": "altro",
            "category_label": "Da classificare",
            "status": "nuovo",
            "processed": False,
            "file_hash": file_hash,
            "sha256": content_sha256,
            "file_size": len(content),
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "source": "upload_automatico",
            "source_context": source_context,
        }

        await db["documents_inbox"].insert_one(dict(doc_record).copy())

        # --- EVENT BUS: propaga evento documento acquisito (upload manuale) ---
        try:
            from app.services.event_bus import propagate_event, EventTypes
            await propagate_event(EventTypes.DOCUMENTO_ACQUISITO, {
                "documento_id": doc_id,
                "filename": filename,
                "origine": "upload_manuale",
                "mime_type": "application/octet-stream",
                "hash_file": content_sha256,
                "mittente": None,
                "category": "altro",
            }, db, source_module="documenti_upload_auto")
        except Exception:
            logger.exception("Errore propagazione evento documento.acquisito (upload)")

        return {
            "success": True,
            "tipo_rilevato": "non_riconosciuto",
            "message": "Documento salvato in inbox per classificazione manuale",
            "doc_id": doc_id,
            "filename": filename,
            "azione_richiesta": "Classifica manualmente il documento da Strumenti > Documenti Email"
        }

    # Per i tipi riconosciuti, fai il redirect interno
    result = {
        "success": True,
        "tipo_rilevato": tipo_rilevato,
        "filename": filename,
        "message": ""
    }

    db = Database.get_db()

    try:
        if tipo_rilevato == 'corrispettivo':
            # Import corrispettivo telematico COR10 con anti-duplicato rigoroso
            # + propagazione automatica a Prima Nota Cassa/Banca
            from app.routers.invoices.corrispettivi_helpers import (
                ingest_corrispettivo_parsed,
            )
            from app.parsers.corrispettivi_parser import parse_corrispettivo_xml

            xml_content = None
            for enc in ['utf-8', 'utf-8-sig', 'latin-1', 'iso-8859-1']:
                try:
                    xml_content = content.decode(enc)
                    break
                except (UnicodeDecodeError, LookupError):
                    continue

            if not xml_content:
                result["success"] = False
                result["message"] = "Impossibile decodificare il file corrispettivo"
            else:
                parsed = parse_corrispettivo_xml(xml_content)
                if parsed.get("error"):
                    result["success"] = False
                    result["message"] = f"Errore parsing corrispettivo: {parsed['error']}"
                elif await _chiusura_fuori_anno(db, parsed, result):
                    # Stessa regola delle fatture qui sotto: nel gestionale
                    # entra solo l'anno attivo, l'originale resta su Drive.
                    pass
                else:
                    parsed["sha256"] = hashlib.sha256(content).hexdigest()
                    ingest = await ingest_corrispettivo_parsed(db, parsed, filename=filename, source="xml")
                    result["action"] = ingest["action"]
                    result["corrispettivo_id"] = ingest.get("corrispettivo_id")
                    result["prima_nota_cassa_id"] = ingest.get("prima_nota_cassa_id")
                    result["prima_nota_banca_id"] = ingest.get("prima_nota_banca_id")
                    result["accounting_repaired"] = bool(ingest.get("accounting_repaired"))
                    result["tipo_documento"] = "corrispettivo"
                    data_str = ingest.get("data", "N/A")
                    tot_str = f"{ingest.get('totale', 0):.2f}"
                    if ingest["action"] == "scartato":
                        # Lordo dei riepiloghi oltre contanti + POS senza voce
                        # dichiarata: la giornata non entra, il file va in ERRORI.
                        result["success"] = False
                        result["imported"] = 0
                        result["motivo"] = ingest.get("motivo")
                        result["message"] = (
                            f"Corrispettivo del {data_str} scartato ({ingest.get('motivo')}): "
                            f"lordo riepiloghi {ingest.get('lordo_riepiloghi')} €, contanti "
                            f"{ingest.get('pagato_contanti')} €, elettronico "
                            f"{ingest.get('pagato_elettronico')} €, non riscosso dichiarato "
                            f"{ingest.get('pagato_non_riscosso')} €"
                        )
                    elif ingest["action"] == "duplicate":
                        result["success"] = False
                        result["duplicate"] = True
                        result["message"] = (
                            f"Corrispettivo già presente; Prima Nota Cassa ripristinata: {data_str} — totale {tot_str}€"
                            if ingest.get("accounting_repaired")
                            else f"Corrispettivo duplicato ignorato: {data_str} — totale {tot_str}€"
                        )
                        result["imported"] = 0
                    elif ingest["action"] == "updated":
                        result["message"] = f"Corrispettivo aggiornato: {data_str} — totale {tot_str}€"
                        result["imported"] = 1
                    else:
                        result["message"] = f"Corrispettivo importato: {data_str} — totale {tot_str}€ (Prima Nota aggiornata)"
                        result["imported"] = 1

        elif tipo_rilevato == 'anagrafica_clienti':
            from app.services.fatture_emesse import importa_report_clienti

            esito = await importa_report_clienti(db, content, filename)
            result["data"] = esito
            result["imported"] = esito.get("nuovi", 0)
            result["duplicate"] = not esito.get("nuovi") and bool(esito.get("gia_presenti"))
            result["message"] = (
                f"Anagrafica clienti: {esito.get('nuovi', 0)} nuovi, "
                f"{esito.get('gia_presenti', 0)} gia' presenti"
                + (f", {esito['senza_identita']} senza P.IVA ne' codice fiscale"
                   if esito.get("senza_identita") else ""))

        elif tipo_rilevato == 'fattura' and content[:5] == b"%PDF-":
            # Fattura in PDF: solo i fornitori esteri (SumUp Limited, Irlanda)
            # la mandano cosi', lo SDI e' solo italiano. Stesso lettore unico
            # delle fatture estere via email, che la lascia nella coda
            # «Fatture estere da verificare» finche' il titolare non conferma.
            import base64 as _b64
            from app.routers.invoices.fatture_upload import process_fattura_estera_pdf

            # Nella radice Drive ci sono migliaia di PDF: una copia di cortesia
            # di una fattura italiana non va letta dall'AI (costo, doppione
            # dell'XML). Passa solo un PDF che porta una partita IVA estera.
            if not partita_iva_estera_nel_testo(
                await asyncio.to_thread(_pdf_text_for_detection, content)
            ):
                result["success"] = False
                result["tipo_rilevato"] = "fattura_pdf"
                # Decisione del titolare (28/09/2026): la stampa PDF di una fattura che arriva
                # dall'XML non e' un errore da guardare; la cartella unica la manda in ARRETRATO.
                result["fuori_contabilita"] = (
                    "copia PDF di una fattura italiana: la fattura entra dall'XML dello SDI")
                result["message"] = (
                    "Fattura PDF senza partita IVA estera: le fatture italiane "
                    "arrivano come XML dallo SDI, il PDF non si importa")
                return result

            esito = await process_fattura_estera_pdf(
                db, _b64.b64encode(content).decode("ascii"), filename,
                source="documenti_upload_auto",
            )
            result["tipo_rilevato"] = "fattura_estera_pdf"
            result["data"] = esito
            stato = esito.get("status")
            if stato == "imported":
                result["imported"] = 1
                result["message"] = (
                    f"Fattura estera {esito.get('invoice_number') or ''} di "
                    f"{esito.get('supplier') or 'fornitore estero'} registrata: "
                    "da confermare in Fatture estere da verificare")
            elif stato == "duplicate":
                result["duplicate"] = True
                result["action"] = "duplicate"
                result["imported"] = 0
                result["message"] = "Fattura estera gia' in archivio"
            else:
                result["success"] = False
                result["message"] = (
                    "Fattura PDF non letta: "
                    f"{esito.get('error') or stato or 'esito sconosciuto'}")
            return result

        elif tipo_rilevato == 'fattura':
            # Import fattura XML
            from fastapi import HTTPException as _HTTPException
            from app.routers.invoices.fatture_upload import parse_fattura_xml, process_fattura_to_db

            invoice_content = content
            if filename.lower().endswith('.p7m'):
                from app.services.xml_invoice_processor import extract_xml_from_p7m

                extracted = extract_xml_from_p7m(content)
                if extracted is None:
                    result["success"] = False
                    result["message"] = "Impossibile estrarre l'XML dalla busta firmata P7M"
                    return result
                invoice_content = extracted

            # Stesso fallback multi-encoding di process_xml_bytes (mai
            # 'utf-8' con errors='ignore': su un file non-UTF-8, es.
            # ISO-8859-1 con testo accentato in fornitore/righe, quello
            # cancella silenziosamente i byte non validi — corruzione dati
            # che ora è visibile perché xml_raw viene anche persistito e
            # riservito da /xml-originale, bug reale, review Codex PR #71).
            xml_content = None
            for _enc in ('utf-8', 'utf-8-sig', 'latin-1', 'iso-8859-1'):
                try:
                    xml_content = invoice_content.decode(_enc)
                    break
                except (UnicodeDecodeError, LookupError):
                    continue
            if not xml_content:
                xml_content = invoice_content.decode('utf-8', errors='ignore')
            parsed = parse_fattura_xml(xml_content)

            from app.services.fatture_emesse import e_fattura_emessa, registra_fattura_emessa

            if parsed and not parsed.get("error") and e_fattura_emessa(parsed):
                # Emessa da noi: non e' un acquisto, va fra le fatture emesse.
                esito = await registra_fattura_emessa(
                    db, parsed, xml_raw=xml_content, filename=filename,
                    source="documenti_upload_auto")
                result["tipo_rilevato"] = "fattura_emessa"
                result["data"] = esito
                if esito.get("status") == "error":
                    result["success"] = False
                    result["message"] = esito.get("error")
                elif esito.get("status") == "duplicate":
                    result["duplicate"] = True
                    result["action"] = "duplicate"
                    result["imported"] = 0
                    result["message"] = f"Fattura emessa {esito.get('numero')} gia' in archivio"
                else:
                    result["imported"] = 1
                    result["message"] = (
                        f"Fattura emessa {esito.get('numero')} a {esito.get('cliente')}: "
                        "archiviata, non aumenta i ricavi (gia' nel corrispettivo)")
                return result

            if parsed:
                # Un file FatturaPA può raggruppare più fatture sotto lo
                # stesso header (più <FatturaElettronicaBody>): "_altri_body"
                # contiene le fatture aggiuntive, vanno TUTTE tentate — anche
                # quando la PRIMA è già presente (409) ma una successiva è
                # nuova (bug reale, review Codex PR #71, 2° giro: prima il
                # 409 sulla prima interrompeva subito, senza mai raggiungere
                # il ciclo sulle altre). xml_raw passato a ognuna così
                # /xml-originale può servirlo (prima non veniva mai salvato
                # da questo percorso).
                altri_body = parsed.pop("_altri_body", None) or []
                importati = []
                ultimo_errore_duplicato = None
                # Stessa regola del giro Drive (process_xml_bytes): nel
                # gestionale entra solo l'anno attivo, l'originale di un altro
                # anno resta su Drive (decisione del titolare, 20/09/2026).
                from app.services.config_import import get_anno_importazione_attivo

                anno_attivo = await get_anno_importazione_attivo(db)
                altro_anno = []
                for body in [parsed] + altri_body:
                    data_fattura = str(body.get("invoice_date") or "")
                    anno_fattura = int(data_fattura[:4]) if data_fattura[:4].isdigit() else None
                    if (anno_fattura and anno_fattura != anno_attivo
                            and not _e_parcella_con_ritenuta(body)):
                        altro_anno.append(anno_fattura)
                        continue
                    try:
                        saved = await process_fattura_to_db(db, body, filename, xml_raw=xml_content)
                        importati.append(saved)
                    except _HTTPException as exc:
                        if exc.status_code != 409:
                            raise
                        ultimo_errore_duplicato = exc

                if importati:
                    result["message"] = f"Fattura importata: {importati[0].get('invoice_number', 'N/A')}"
                    result["imported"] = len(importati)
                    if len(importati) > 1:
                        result["message"] += f" (+{len(importati) - 1} fatture aggiuntive nello stesso file)"
                    collisioni = [f for f in importati if f.get("collisione_identita")]
                    if collisioni:
                        # Stessa chiave di una fattura in archivio ma originale
                        # diverso: entrata «da verificare», con alert, non scartata.
                        result["collisione_identita"] = len(collisioni)
                        result["message"] += (
                            ": stesso numero, fornitore e data di una fattura gia' in archivio "
                            "ma contenuto diverso, da verificare (alert aperto)")
                elif altro_anno and ultimo_errore_duplicato is None:
                    result["imported"] = 0
                    result["skipped_altro_anno"] = len(altro_anno)
                    result["message"] = (
                        f"Fattura del {altro_anno[0]}: l'anno attivo e' il {anno_attivo}, "
                        "non entra nel gestionale e l'originale resta su Drive"
                    )
                else:
                    # Tutte le fatture del file sono gia' in archivio: e' un
                    # doppione, non un errore (chi smista l'esito lo archivia).
                    result["success"] = False
                    result["duplicate"] = True
                    result["action"] = "duplicate"
                    result["imported"] = 0
                    result["message"] = str(ultimo_errore_duplicato.detail)
            else:
                result["success"] = False
                result["message"] = "Errore parsing XML fattura"

        elif tipo_rilevato == 'f24':
            from app.services.f24_canonico import importa_modello_bytes

            f24_result = await importa_modello_bytes(
                db, content, filename, source="documenti_upload_auto"
            )
            result["data"] = f24_result
            result["workflow"] = "F24_CANONICO"
            result["duplicate"] = bool(f24_result.get("duplicate"))
            if f24_result.get("success"):
                result["imported"] = 0 if f24_result.get("duplicate") else 1
                result["message"] = (
                    "F24 già importato"
                    if f24_result.get("duplicate")
                    else "F24 importato nel registro canonico"
                )
            else:
                result["success"] = False
                result["imported"] = 0
                result["message"] = f"Errore import F24: {f24_result.get('error', 'parsing fallito')}"

        elif tipo_rilevato == 'quietanza_f24':
            # Tutti i canali passano dallo stesso servizio: validazione dei
            # totali, deduplica, righe/crediti e collegamenti bidirezionali.
            from app.services.f24_canonico import importa_quietanza

            quietanza = await importa_quietanza(
                db, content, filename, source="documenti_upload_auto"
            )
            result["data"] = quietanza
            result["workflow"] = "F24_CANONICO"
            result["duplicate"] = bool(quietanza.get("duplicate"))
            if quietanza.get("success"):
                result["imported"] = 0 if quietanza.get("duplicate") else 1
                result["message"] = (
                    "Quietanza F24 già importata"
                    if quietanza.get("duplicate")
                    else "Quietanza F24 importata e riconciliata"
                )
            else:
                result["success"] = False
                result["imported"] = 0
                result["message"] = f"Errore import Quietanza F24: {quietanza.get('error', 'parsing fallito')}"

        elif tipo_rilevato == 'dichiarazione_fiscale':
            # Servizio unico, idempotente per sha256: popola
            # fiscal_documents sia dall'upload manuale sia dalla cartella
            # unica Drive (che passa da qui).
            from app.services.fiscal_document_ingestion import FiscalDocumentIngestionService

            registered = await FiscalDocumentIngestionService(db).ingest(
                content=content, filename=filename, source="documenti_upload_auto",
            )
            is_duplicate = registered.get("status") == "duplicate"
            result["data"] = registered
            result["workflow"] = "FISCAL_DOCUMENT_INGESTION"
            # Una LIPE e' anche la fonte dell'IVA mensile: i suoi periodi vanno
            # in `lipe_periodi`, l'unica collezione che il confronto col
            # commercialista legge. Anche su un duplicato: il deposito e'
            # idempotente per periodo e recupera le LIPE archiviate prima.
            from app.services import lipe_deposito

            if lipe_deposito.e_una_lipe(filename):
                try:
                    result["lipe"] = await lipe_deposito.deposita_lipe(
                        db, content, nome_file=filename, origine="documenti_upload_auto",
                        drive_file_id=source_context.get("drive_file_id"), dry_run=False,
                    )
                except Exception as exc:  # noqa: BLE001 — l'archiviazione resta valida
                    logger.error("LIPE %s archiviata ma periodi non depositati: %s: %s",
                                 filename, type(exc).__name__, exc)
                    result["lipe"] = {"errore": f"{type(exc).__name__}: {exc}"[:300]}
            result["duplicate"] = is_duplicate
            result["imported"] = 0 if is_duplicate else 1
            result["message"] = (
                "Dichiarazione fiscale già archiviata"
                if is_duplicate
                else "Dichiarazione fiscale archiviata e agganciata a F24/quietanze"
            )

        elif tipo_rilevato == 'dilazione_inps':
            from app.services.dilazioni_inps import archivia_dilazione

            return await archivia_dilazione(
                db, filename=filename, content=content,
                testo=await asyncio.to_thread(_pdf_text_for_detection, content),
                source_context=source_context,
            )

        elif tipo_rilevato == 'elenco_netti':
            from app.services.elenchi_netti import archivia_elenco

            return await archivia_elenco(
                db, filename=filename, content=content,
                testo=await asyncio.to_thread(_pdf_text_for_detection, content),
                source_context=source_context,
            )

        elif tipo_rilevato == 'prospetto_contabile':
            from app.services.prospetti_contabili import archivia_prospetto

            return await archivia_prospetto(
                db, filename=filename, content=content,
                testo=await asyncio.to_thread(_pdf_text_for_detection, content),
                source_context=source_context,
            )

        elif tipo_rilevato == 'componente_770':
            from app.services.componenti_770 import metadati as metadati_770

            metadata = await metadati_770(
                db, filename=filename,
                testo=await asyncio.to_thread(_pdf_text_for_detection, content),
            )
            # Se lo stesso file e' gia' in coda come «da classificare» si
            # riclassifica quella riga: niente seconda copia dell'originale.
            from app.services.document_hash_lookup import find_one_by_hashes

            digest = hashlib.sha256(content).hexdigest()
            gia = await find_one_by_hashes(
                db, "documents_inbox",
                (("sha256", digest), ("file_hash", digest), ("file_hash", hashlib.md5(content).hexdigest())),
                {"_id": 0, "id": 1, "filename": 1, "category": 1},
            )
            if gia:
                await db["documents_inbox"].update_one({"id": gia["id"]}, {"$set": {
                    "category": "componente_770", "document_type": "componente_770",
                    "category_label": "Quadro del 770", "evidence_role": "componente_dichiarazione",
                    "parsed_metadata": metadata, "obligation_status": "NON_APPLICABILE",
                    "relation_keys": metadata["relation_keys"], "sha256": digest,
                    "status": "archiviato" if metadata["dichiarazione_id"] else "da_verificare",
                }})
                return {
                    "success": True, "duplicate": False, "imported": 0, "action": "riclassificato",
                    "tipo_rilevato": tipo_rilevato, "doc_id": gia["id"], "filename": filename,
                    "workflow": "COMPONENTE_DICHIARAZIONE", "payment_evidence": False,
                    "parsed_metadata": metadata,
                    "message": _messaggio_componente_770(metadata, gia_presente=True),
                }
            archived = await _archive_non_payment_document(
                db, filename=filename, content=content, document_type=tipo_rilevato,
                source_context=source_context, metadata=metadata,
            )
            if archived.get("success"):
                archived["workflow"] = "COMPONENTE_DICHIARAZIONE"
                archived["message"] = _messaggio_componente_770(metadata, gia_presente=False)
            return archived

        elif tipo_rilevato in {
            'avviso_pagopa', 'nota_rettifica_inps', 'tari_avviso',
            'tari_istanza_compensazione', 'visura_camerale', 'documento_identita',
            'ader_sospensione', 'ader_definizione_agevolata',
            'dimissioni_telematiche',
        }:
            metadata = None
            if tipo_rilevato == "avviso_pagopa":
                from app.services.pagopa_receipts import parse_receipt_pdf
                from app.services.fiscal_accounting_policy import build_journal_proposal

                metadata = await asyncio.to_thread(parse_receipt_pdf, content, filename=filename)
                metadata["obligation_status"] = "APERTO"
                metadata["journal_proposal"] = build_journal_proposal(
                    metadata, document_type="AVVISO_PAGOPA"
                )
                metadata["relation_keys"] = {
                    "codice_avviso": metadata.get("codice_avviso"),
                    "numero_verbale": metadata.get("numero_verbale"),
                    "targa": metadata.get("targa"),
                    "data_violazione": metadata.get("data_violazione"),
                }
            elif tipo_rilevato == "nota_rettifica_inps":
                from app.services.inps_adjustment_parser import parse_nota_rettifica_inps
                from app.services.fiscal_accounting_policy import build_journal_proposal

                metadata = parse_nota_rettifica_inps(content)
                metadata["journal_proposal"] = build_journal_proposal(
                    metadata, document_type="NOTA_RETTIFICA_INPS"
                )

            archived = await _archive_non_payment_document(
                db, filename=filename, content=content,
                document_type=tipo_rilevato,
                source_context=source_context,
                metadata=metadata,
            )
            if tipo_rilevato == "avviso_pagopa" and archived.get("success"):
                from app.services.verbali_document_import import process_verbale_document

                archived["association"] = await process_verbale_document(
                    db, document_id=archived["doc_id"], content=content,
                    filename=filename, source="documenti_upload_auto",
                    parsed_metadata=metadata,
                )
                archived["workflow"] = "AVVISO_VERBALE_DOCUMENTALE"
            return archived

        elif tipo_rilevato == 'verbale_codice_strada':
            from app.services.verbali_document_import import metadata_da_proposta, process_verbale_document

            # I campi della proposta dell'agente confermata dal titolare: il lettore
            # li usa dove il contenuto non si legge (scansione). Col doppione (verbale
            # gia' archiviato «da revisionare») il motore gira lo stesso sulla riga che c'e'.
            campi_confermati = metadata_da_proposta(source_context.get("campi_proposta"))
            archived = await _archive_non_payment_document(
                db, filename=filename, content=content,
                document_type=tipo_rilevato,
                source_context=source_context,
            )
            if archived.get("duplicate") and not (campi_confermati and archived.get("doc_id")):
                return archived

            association = await process_verbale_document(
                db, document_id=archived["doc_id"], content=content,
                filename=filename, source="documenti_upload_auto",
                parsed_metadata=campi_confermati or None,
            )
            archived["association"] = association
            archived["workflow"] = "VERBALE_DOCUMENTALE"
            archived["message"] = "Verbale archiviato e associato per numero/IUV"
            return archived

        elif tipo_rilevato in {
            'ricevuta_pagopa', 'ricevuta_cbill', 'ricevuta_mav',
            'ricevuta_rav', 'ricevuta_bollettino_postale',
        }:
            from app.config import settings
            from app.services.pagopa_receipts import import_receipt

            receipt = await import_receipt(
                db, content=content, filename=filename,
                company_id=settings.FISCAL_COMPANY_ID,
                source="documenti_upload_auto",
            )
            result["data"] = receipt
            receipt_kind = (receipt.get("receipt") or {}).get("document_kind")
            result["workflow"] = (
                "PAGOPA_CBILL_CANONICO"
                if receipt_kind in (None, "RICEVUTA_PAGOPA", "RICEVUTA_CBILL")
                else "PAGAMENTO_DOCUMENTALE_CANONICO"
            )
            result["duplicate"] = bool(receipt.get("duplicate"))
            if receipt.get("success"):
                result["imported"] = 0 if receipt.get("duplicate") else 1
                fiscal_match = receipt.get("riconciliazione_fiscale") or {}
                result["message"] = (
                    "Ricevuta di pagamento gia importata"
                    if receipt.get("duplicate")
                    else "Ricevuta di pagamento importata"
                )
                if fiscal_match.get("matched"):
                    result["message"] += ", rata e cartelle AdeR collegate"
            else:
                if receipt.get("document_kind") == "ESITO_PAGOPA_NEGATIVO":
                    return await _archive_non_payment_document(
                        db, filename=filename, content=content,
                        document_type="esito_pagopa_negativo",
                        metadata=receipt.get("parsed"),
                        source_context=source_context,
                    )
                result["success"] = False
                result["imported"] = 0
                result["message"] = receipt.get(
                    "error", "Parsing ricevuta PagoPA/CBILL fallito"
                )

        elif tipo_rilevato == 'cedolino':
            # Un solo motore per ogni cedolino (busta Zucchetti, Libro Unico,
            # Teamsystem, CSC): lo stesso della posta e di Drive.
            from base64 import b64encode

            from app.services.cedolini_manager import processa_tutti_cedolini_pdf

            db = Database.get_db()
            esito = await processa_tutti_cedolini_pdf(
                db, b64encode(content).decode("ascii"), filename,
                source_path=filename,
                source_file_hash=hashlib.sha256(content).hexdigest(),
                drive_file_id=source_context.get("drive_file_id") or "",
                fonte="drive" if source_context.get("drive_file_id") else "documenti_upload_auto",
            )
            result["workflow"] = "MOTORE_UNICO_CEDOLINI"
            result["data"] = {k: esito.get(k) for k in (
                "esito", "cedolini_processati", "buste_senza_netto", "fogli_presenze",
                "prima_nota_create", "gia_presenti", "errori",
            )}
            scritte = (esito.get("cedolini_processati") or 0) + (esito.get("buste_senza_netto") or 0)
            if scritte:
                result["imported"] = 1
                result["message"] = f"Cedolino: {scritte} buste registrate"
            elif esito.get("gia_presenti"):
                result["imported"] = 0
                result["duplicate"] = True
                result["message"] = f"Cedolino gia' in archivio: {esito['gia_presenti']} buste"
            elif esito.get("esito") in ("presenze", "fuori_periodo"):
                # Riconosciuto e letto, ma non e' una busta da registrare: il
                # foglio presenze non ha netto, lo storico e' fuori periodo.
                result["imported"] = 0
                result["message"] = f"Cedolino letto, niente da registrare: {esito.get('motivo')}"
            else:
                result["success"] = False
                result["imported"] = 0
                errori = "; ".join(str(e) for e in (esito.get("errori") or [])[:3])
                result["message"] = (
                    f"Cedolino non registrato: {esito.get('motivo') or 'nessuna busta letta'}"
                    + (f" ({errori})" if errori else "")
                )

        elif tipo_rilevato == 'distinte_bpm':
            # Import distinte stipendi BPM - riconcilia con buste paga
            from app.services.distinte_bpm import import_distinte_bpm
            import io

            file_obj = io.BytesIO(content)
            new_upload = UploadFile(filename=filename, file=file_obj)

            try:
                bpm_result = await import_distinte_bpm(file=new_upload, solo_anteprima=False)
                stats = bpm_result.get("stats", {})
                result["message"] = f"Distinte BPM: {stats.get('riconciliati', 0)} pagamenti riconciliati"
                result["workflow"] = "DISTINTE_BPM"
                result["data"] = bpm_result
                result["imported"] = stats.get('riconciliati', 0)
            except HTTPException as he:
                result["success"] = False
                result["message"] = f"Errore import distinte: {he.detail}"
            except Exception as e:
                result["success"] = False
                result["message"] = f"Errore import distinte: {str(e)}"

        elif tipo_rilevato == 'report_fatture_ricevute':
            # L'export del portale fiscale e' un indice ufficiale, non contiene
            # gli XML. Lo conserviamo separato dalle fatture canoniche e lo
            # usiamo per rendere visibili gli XML realmente mancanti.
            from app.services.fatture_report_ae import importa_report_fatture_ricevute

            report_result = await importa_report_fatture_ricevute(
                db, content, filename,
            )
            result.update(report_result)
            result["tipo_rilevato"] = "report_fatture_ricevute"
            if report_result.get("pagamenti_dichiarati"):
                # Il titolare ha scritto come ha pagato: le Prime Note si
                # aggiornano in background (sono centinaia di fatture).
                from app.services import pagamenti_dichiarati_titolare

                result["pagamenti_dichiarati_job"] = await pagamenti_dichiarati_titolare.avvia(db)
                result["message"] += (
                    f"; {report_result['pagamenti_dichiarati']} pagamenti dichiarati "
                    "in registrazione su Prima Nota (esito: GET "
                    "/api/admin/fatture/pagamenti-dichiarati/stato)"
                )

        elif tipo_rilevato == 'corrispettivi_csv_ade':
            # CSV «Corrispettivi» del portale AdE: dato provvisorio in attesa dell'XML del
            # registratore, che lo sovrascrive (corrispettivi_service.importa_csv_ade).
            from app.services.corrispettivi_service import importa_csv_ade

            try:
                testo_csv = content.decode("utf-8-sig")
            except UnicodeDecodeError:
                testo_csv = content.decode("latin-1")
            esito_csv = await importa_csv_ade(db, testo_csv, filename)
            result.update({
                "workflow": "CORRISPETTIVI_CSV_PROVVISORIO",
                "imported": esito_csv["nuovi"],
                "duplicate": esito_csv["nuovi"] == 0 and esito_csv["aggiornati"] == 0,
                "data": esito_csv,
                "message": (
                    f"Corrispettivi CSV AdE: {esito_csv['nuovi']} giornate provvisorie nuove, "
                    f"{esito_csv['aggiornati']} aggiornate, {esito_csv['gia_definitivi']} già coperte dall'XML"
                    + (f", {len(esito_csv['discordanze_con_xml'])} con imponibile diverso dall'XML" if esito_csv["discordanze_con_xml"] else "")
                    + (f", {len(esito_csv['conflitti'])} in conflitto con una riga manuale" if esito_csv["conflitti"] else "")
                    + (f", {esito_csv['fuori_anno']} righe di un anno diverso dal {esito_csv['anno_attivo']} non importate" if esito_csv["fuori_anno"] else "")
                    + (f", {len(esito_csv['errori'])} righe da controllare" if esito_csv["errori"] else "")
                    + ": l'XML del registratore le sostituirà"
                ),
            })

        elif tipo_rilevato == 'pagamenti_buoni':
            # Registro dedicato: resta dietro Documenti e deduplica per
            # riferimento operazione, senza creare movimenti contabili o
            # associazioni a dipendenti in assenza di prova.
            import base64 as b64
            from app.services.pagamenti_buoni import import_rows, parse_csv

            file_hash = hashlib.md5(content).hexdigest()
            existing = await db["documents_inbox"].find_one(
                {"file_hash": file_hash, "category": "pagamenti_buoni"},
                {"_id": 0, "id": 1, "filename": 1},
            )
            if existing:
                result.update({
                    "success": False,
                    "duplicate": True,
                    "action": "duplicate",
                    "imported": 0,
                    "message": f"Registro Pagamenti buoni gia acquisito: {existing.get('filename') or filename}",
                })
            else:
                rows, errors = parse_csv(content)
                import_result = await import_rows(db, rows, filename, errors)
                doc_id = f"pagamenti_buoni_{uuid.uuid4()}"
                source_doc = {
                    "id": doc_id,
                    "filename": filename,
                    "pdf_data": b64.b64encode(content).decode("ascii"),
                    "file_hash": file_hash,
                    "file_size": len(content),
                    "category": "pagamenti_buoni",
                    "category_label": "Pagamenti buoni",
                    "status": "elaborato",
                    "processed": True,
                    "source": "upload_automatico_documenti",
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "import_result": import_result,
                }
                await db["documents_inbox"].insert_one(dict(source_doc).copy())
                result.update(import_result)
                result.update({
                    "doc_id": doc_id,
                    "workflow": "PAGAMENTI_BUONI_DEDUP_RIFERIMENTO",
                    "message": (
                        f"Pagamenti buoni: {import_result['imported']} importati, "
                        f"{import_result['duplicates']} duplicati, "
                        f"{import_result['invalid']} righe non valide"
                    ),
                })

        elif tipo_rilevato == 'pos_terminal':
            if "commissioni_" in filename.lower():
                from app.services.pos_commissioni_import import importa_pos_commissioni_file

                pos_result = await importa_pos_commissioni_file(db, content, filename)
                result.update({
                    "workflow": "POS_NUMIA_COMMISSIONI",
                    "imported": pos_result.get("inserted", 0),
                    "duplicates": pos_result.get("duplicates", 0),
                    "data": pos_result,
                    "message": (
                        f"Commissioni POS importate: {pos_result.get('inserted', 0)} nuove, "
                        f"{pos_result.get('updated', 0)} aggiornate, "
                        f"{pos_result.get('duplicates', 0)} già presenti."
                    ),
                })
            else:
                from app.services.pos_terminal_import import importa_pos_terminal_file

                pos_result = await importa_pos_terminal_file(db, content, filename)
                result.update({
                    "workflow": "POS_NUMIA_OPERATION_ID_V2",
                    "imported": pos_result.get("inserted", 0),
                    "duplicates": pos_result.get("unchanged", 0),
                    "data": pos_result,
                    "message": (
                        f"POS Numia importato: {pos_result.get('inserted', 0)} operazioni nuove, "
                        f"{pos_result.get('updated', 0)} aggiornate, "
                        f"{pos_result.get('unchanged', 0)} già presenti."
                    ),
                })

        elif tipo_rilevato == 'estratto_conto_nexi':
            from app.services.nexi_carta import importa_estratto_nexi_pdf

            nexi_result = await importa_estratto_nexi_pdf(
                db, filename, content, source="documenti_upload_auto_nexi",
                drive_file_id=source_context.get("drive_file_id"),
            )
            if not nexi_result.get("success"):
                raise ValueError(nexi_result.get("message") or "Parsing Nexi fallito")
            result.update({
                "workflow": "NEXI_STATEMENT_CANONICO",
                "duplicate": bool(nexi_result.get("duplicate")),
                "imported": 0 if nexi_result.get("duplicate") else nexi_result.get("operazioni", 0),
                "data": nexi_result,
                "message": (
                    "Estratto Nexi già presente; verifica aggiornata."
                    if nexi_result.get("duplicate")
                    else f"Estratto Nexi importato: {nexi_result.get('operazioni', 0)} operazioni."
                ),
            })

        elif tipo_rilevato == 'spese_sumup':
            # Export «Spese» di SumUp: fornitore, categoria e IVA dei movimenti della carta che
            # l'estratto ha gia' (sumup_conto.arricchisci_da_spese_sumup). Mai un estratto BPM.
            from app.services.sumup_conto import arricchisci_da_spese_sumup

            esito_spese = await arricchisci_da_spese_sumup(db, content, filename)
            result.update({
                "workflow": "SPESE_SUMUP_ARRICCHIMENTO",
                "imported": esito_spese["arricchiti"],
                "duplicate": esito_spese["arricchiti"] == 0 and esito_spese["gia_arricchiti"] > 0,
                "data": esito_spese,
                "message": (
                    f"Spese SumUp: {esito_spese['arricchiti']} movimenti arricchiti con fornitore e IVA, "
                    f"{esito_spese['gia_arricchiti']} già arricchiti"
                    + (f", {len(esito_spese['senza_movimento'])} senza movimento nell'estratto SumUp (carica l'estratto del periodo)"
                       if esito_spese["senza_movimento"] else "")
                    + (f", {len(esito_spese['ambigui'])} ambigui" if esito_spese["ambigui"] else "")
                ),
            })

        elif tipo_rilevato == 'estratto_conto_sumup':
            from app.services.sumup_conto import accoda_abbinamento, importa_estratto_sumup

            sumup_result = await importa_estratto_sumup(db, filename, content)
            # Anche un estratto gia' presente riaccoda l'abbinamento: le righe
            # importate prima di un motore nuovo (o in attesa di una busta,
            # di una fattura) si ripassano senza aspettare il giro dei 30 minuti.
            accoda_abbinamento(db)
            result.update({
                "workflow": "SUMUP_CONTO_CANONICO",
                "duplicate": bool(sumup_result.get("duplicate")),
                "imported": sumup_result.get("nuovi", 0),
                "data": sumup_result,
                "message": (
                    "Estratto SumUp già presente."
                    if sumup_result.get("duplicate")
                    else f"Estratto SumUp importato: {sumup_result.get('nuovi', 0)} movimenti nuovi, "
                         f"{sumup_result.get('gia_presenti', 0)} già presenti."
                ),
            })

        elif tipo_rilevato == 'contabile_filiale':
            from app.services.contabili_filiale import registra as registra_contabile

            contabile = await registra_contabile(
                db, filename, content, await asyncio.to_thread(_pdf_text_for_detection, content),
                drive_file_id=source_context.get("drive_file_id"),
            )
            if not contabile.get("success"):
                raise ValueError(contabile.get("message") or "Contabile di filiale non leggibile")
            stati = {
                "collegata": "collegata al movimento dell'estratto conto",
                "in_attesa_estratto": "in attesa del movimento nell'estratto conto",
                "da_verificare": "da verificare: piu' movimenti compatibili",
            }
            result.update({
                "workflow": "CONTABILE_FILIALE",
                "duplicate": bool(contabile.get("duplicate")),
                "imported": 0 if contabile.get("duplicate") else 1,
                "data": contabile,
                "message": (
                    f"Contabile di filiale del {contabile.get('data_operazione')} "
                    f"({contabile.get('importo')} EUR)"
                    + (" già presente" if contabile.get("duplicate") else "")
                    + f": {stati.get(contabile.get('stato'), contabile.get('stato'))}."
                ),
            })

        elif tipo_rilevato == 'atto_giudiziario':
            from app.services.atti_giudiziari import collega_e_registra, registra_atto

            atto = await registra_atto(
                db, filename, content, drive_file_id=source_context.get("drive_file_id"),
            )
            if not atto.get("success"):
                raise ValueError(atto.get("message") or "Atto giudiziario non leggibile")
            # Il secondo pezzo arriva: i bonifici che citano la sentenza (o che
            # il titolare vi ha messo) entrano subito nel fascicolo.
            pagamenti = await collega_e_registra(db)
            result.update({
                "workflow": "ATTO_GIUDIZIARIO",
                "duplicate": bool(atto.get("duplicate")),
                "imported": 0 if atto.get("duplicate") else 1,
                "data": {**atto, "pagamenti": pagamenti},
                "message": (
                    f"{atto['etichetta']} della sentenza {atto['numero_sentenza']}"
                    + (" già presente" if atto.get("duplicate") else " archiviata")
                    + f"; pagamenti collegati: {pagamenti.get('collegati', 0) + pagamenti.get('gia_collegati', 0)}."
                ),
            })

        elif tipo_rilevato == 'cartella_pagamento':
            from app.services.cartelle_pagamento import registra_cartella

            cartella = await registra_cartella(
                db, filename, content, drive_file_id=source_context.get("drive_file_id"),
            )
            if not cartella.get("success"):
                raise ValueError(cartella.get("message") or "Cartella di pagamento non leggibile")
            result.update({
                "workflow": "CARTELLA_PAGAMENTO",
                "duplicate": bool(cartella.get("duplicate")),
                "imported": 0 if cartella.get("duplicate") else 1,
                "data": cartella,
                "message": (
                    f"Cartella {cartella['numero_cartella']} di {cartella.get('ente_creditore') or 'ente non letto'}"
                    f" da {cartella.get('totale')} EUR"
                    + (" già presente" if cartella.get("duplicate") else " registrata: da pagare entro 60 giorni dalla notifica")
                    + ("" if cartella.get("importi_quadrano") else " (importi da verificare)")
                ),
            })

        elif tipo_rilevato == 'estratto_conto_paypal':
            from app.services.paypal_statement_import import import_paypal_statement_pdf
            from app.services.paypal_reconciliation_pipeline import riconcilia_paypal_importato

            paypal_result = await import_paypal_statement_pdf(
                db, content, filename, source="documenti_upload_auto_paypal",
            )
            collegamenti = await riconcilia_paypal_importato(
                db,
                start_date=paypal_result.get("periodo_inizio"),
                end_date=paypal_result.get("periodo_fine"),
            )
            result.update({
                "workflow": "PAYPAL_STATEMENT_CANONICO",
                "imported": paypal_result.get("transazioni_inserite", 0),
                "duplicates": paypal_result.get("transazioni_duplicate", 0),
                "data": {**paypal_result, "riconciliazione": collegamenti},
                "message": (
                    f"Estratto PayPal importato: "
                    f"{paypal_result.get('transazioni_inserite', 0)} operazioni nuove, "
                    f"{paypal_result.get('transazioni_duplicate', 0)} già presenti."
                ),
            })

        elif tipo_rilevato == 'estratto_conto_mutuo':
            from app.services.mutui_document_import import importa_documento_mutuo

            mutuo_result = await importa_documento_mutuo(db, content, filename)
            result.update({
                "workflow": "MUTUO_DOCUMENTO_CANONICO",
                "duplicate": bool(mutuo_result.get("duplicate")),
                "imported": 0 if mutuo_result.get("duplicate") else mutuo_result.get("records", 0),
                "data": mutuo_result,
                "message": (
                    "Documento mutuo già presente."
                    if mutuo_result.get("duplicate")
                    else "Documento mutuo importato."
                ),
            })

        elif tipo_rilevato == 'estratto_conto':
            # Import diretto estratto conto CSV Banco BPM → estratto_conto_movimenti
            result.update(await _importa_estratto_conto_file(filename, content))

        elif tipo_rilevato == 'bonifici':
            # Salva e processa nello stesso flusso canonico dell'Archivio
            # Bonifici. Prima di questa correzione il file restava soltanto
            # in ``documents_inbox`` con il messaggio "vai all'archivio": i
            # dati non venivano letti ne' associati al dipendente.
            import base64 as b64
            from app.services.bonifici_pdf_ingest import STATO_NON_REGISTRATO, importa_pdf_bonifico

            doc_id = f"bonifici_{uuid.uuid4()}"
            bonifici_doc = {
                "id": doc_id,
                "filename": filename,
                "pdf_data": b64.b64encode(content).decode('utf-8'),  # Drive/Supabase
                "category": "bonifico",
                "status": "da_processare",
                "processed": False,
                "source": "upload_manuale",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db["documents_inbox"].insert_one(dict(bonifici_doc).copy())

            ingest = await importa_pdf_bonifico(
                db, content, filename, source="upload_manuale_import_documenti"
            )
            if ingest.get("status") in {STATO_NON_REGISTRATO, "duplicate"}:
                # Accredito di un anno che non si registra, o ricevuta gia' in
                # archivio: la copia appena messa in inbox non serve a nessuno,
                # e ricaricare lo stesso ZIP la rimetterebbe ogni volta.
                await db["documents_inbox"].delete_one({"id": doc_id})
            else:
                await db["documents_inbox"].update_one(
                    {"id": doc_id},
                    {"$set": {
                        "processed": ingest.get("status") in {"saved", "duplicate"},
                        "status": "elaborato" if ingest.get("status") in {"saved", "duplicate"} else "da_verificare",
                        "bonifico_transfer_id": ingest.get("transfer_id"),
                        "processed_at": datetime.now(timezone.utc).isoformat(),
                    }},
                )

            if ingest.get("status") == STATO_NON_REGISTRATO:
                result["non_registrato"] = True
                result["message"] = "Accredito in entrata del 2023: non si registra (decisione del titolare)."
            elif ingest.get("associato"):
                result["message"] = "Bonifico letto e associato al dipendente per nome e importo esatti."
            elif ingest.get("status") == "duplicate":
                # Contato fra i doppioni, non fra gli importati: dentro uno ZIP
                # il riepilogo dice quanti documenti erano gia' in archivio.
                result["duplicate"] = True
                result["action"] = "duplicate"
                result["message"] = "Bonifico gia' presente: duplicato saltato senza creare associazioni casuali."
            else:
                result["message"] = "Bonifico letto e archiviato; associazione lasciata da verificare perche' nome e importo non sono univoci."
            result["doc_id"] = doc_id
            result["bonifico_transfer_id"] = ingest.get("transfer_id")
            result["associato_dipendente"] = bool(ingest.get("associato"))

    except Exception as e:
        logger.error(f"Errore processing {tipo_rilevato}: {e}")
        result["success"] = False
        result["message"] = f"Errore durante l'importazione: {str(e)}"

    return result


# Import che superano i 2 minuti del browser e i 5 del proxy Render: vanno in
# coda (`document_import_jobs`) con lo stesso motore dell'upload diretto.
ELABORATORI_IN_CODA = {
    "archivio_zip": _process_zip_upload_a_blocchi,
    "estratto_conto": _importa_estratto_conto_file,
}


@router.post("/upload-auto/queue", status_code=202)
@handle_errors
async def accoda_upload_documento_voluminoso(
    file: UploadFile = File(...),
    preview_token: Optional[str] = Header(None, alias="X-Document-Preview-Token"),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Accoda gli import voluminosi (export POS, archivi ZIP) senza tenere
    aperto il gateway HTTP: la pagina ne segue l'esito su /upload-auto/jobs."""
    filename = Path(file.filename or "documento").name
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail=f"File vuoto: {filename}")
    limite = MAX_ZIP_UPLOAD_BYTES if filename.lower().endswith(".zip") else MAX_UPLOAD_BYTES
    if len(content) > limite:
        raise HTTPException(
            status_code=413,
            detail=f"File oltre il limite di {limite // (1024 * 1024)} MB: {filename}",
        )

    tipo_rilevato = await rileva_tipo_documento(filename, content)
    pos = tipo_rilevato == "pos_terminal" and "commissioni_" not in filename.lower()
    if not pos and tipo_rilevato not in ELABORATORI_IN_CODA:
        raise HTTPException(
            status_code=400,
            detail="La coda asincrona e' riservata a export POS, archivi ZIP ed estratti conto.",
        )

    from app.services.document_import_preview import verify_confirmation_token

    digest = hashlib.sha256(content).hexdigest()
    if not preview_token or not verify_confirmation_token(
        preview_token, digest, tipo_rilevato,
    ):
        raise HTTPException(
            status_code=428,
            detail="Anteprima obbligatoria mancante, scaduta o riferita a un file diverso.",
        )

    if tipo_rilevato in ELABORATORI_IN_CODA:
        from app.services.document_import_jobs import enqueue_import

        job = await enqueue_import(
            Database.get_db(), content=content, filename=filename,
            document_type=tipo_rilevato,
            process=ELABORATORI_IN_CODA[tipo_rilevato],
        )
        return {
            "success": True,
            "tipo_rilevato": tipo_rilevato,
            "workflow": "IMPORT_IN_CODA",
            "message": (
                "Import completato."
                if job.get("status") == "completed"
                else "Import in elaborazione; la pagina controlla automaticamente l'esito."
            ),
            **job,
        }

    from app.services.document_import_jobs import enqueue_pos_import

    job = await enqueue_pos_import(
        Database.get_db(), content=content, filename=filename,
    )
    return {
        "success": True,
        "tipo_rilevato": tipo_rilevato,
        "workflow": "POS_NUMIA_ASYNC_OPERATION_ID_V2",
        "message": (
            "Import POS completato."
            if job.get("status") == "completed"
            else "Import POS avviato in coda; la pagina controlla automaticamente l'esito."
        ),
        **job,
    }


@router.get("/upload-auto/jobs/{job_id}")
@handle_errors
async def stato_upload_documento_voluminoso(
    job_id: str,
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Espone soltanto stato ed esito del job autenticato, mai il file sorgente."""
    from app.services.document_import_jobs import get_import_job

    job = await get_import_job(Database.get_db(), job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Import non trovato")
    return {
        "success": job.get("status") == "completed",
        "workflow": (
            "IMPORT_IN_CODA" if job.get("document_type") in ELABORATORI_IN_CODA
            else "POS_NUMIA_ASYNC_OPERATION_ID_V2"
        ),
        **job,
    }
