"""
Router Gestione Documenti
API per scaricare, visualizzare e processare documenti dalle email.
"""

from fastapi import APIRouter, Query, HTTPException, Depends
from app.utils.dependencies import get_current_admin_user
from fastapi.responses import StreamingResponse
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from pathlib import Path
import os
import re
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


@router.get("/drive/catalog")
async def catalogo_cartelle_drive() -> Dict[str, Any]:
    """Mappa pubblica delle cartelle Drive, senza ID o credenziali."""
    from app.services.drive_folder_registry import get_public_catalog

    return get_public_catalog()


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


@router.get("/lista")
@handle_errors
async def lista_documenti(
    categoria: Optional[str] = Query(None, description="Filtra per categoria"),
    status: Optional[str] = Query(None, description="Filtra per status: nuovo, processato, errore"),
    limit: int = Query(100, ge=1, le=500),
    skip: int = Query(0, ge=0)
) -> Dict[str, Any]:
    """Lista documenti scaricati dalle email."""
    db = Database.get_db()
    
    query = {}
    if categoria:
        query["category"] = categoria
    if status:
        query["status"] = status
    
    documents = await db["documents_inbox"].find(
        query,
        {"_id": 0}
    ).sort("downloaded_at", -1).skip(skip).limit(limit).to_list(limit)
    
    # Conta per categoria
    pipeline = [
        {"$group": {"_id": "$category", "count": {"$sum": 1}}}
    ]
    by_category = {doc["_id"]: doc["count"] async for doc in db["documents_inbox"].aggregate(pipeline)}
    
    # Conta per status
    pipeline_status = [
        {"$group": {"_id": "$status", "count": {"$sum": 1}}}
    ]
    by_status = {doc["_id"]: doc["count"] async for doc in db["documents_inbox"].aggregate(pipeline_status)}
    
    total = await db["documents_inbox"].count_documents(query)
    
    return {
        "documents": documents,
        "total": total,
        "by_category": by_category,
        "by_status": by_status,
        "categories": CATEGORIES
    }


# Store per tracciare task in background
import asyncio

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
        raise HTTPException(status_code=500, detail=str(e))


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
_COLLEZIONI_DOWNLOAD = [
    "documents_inbox",
    "documenti_non_associati",
    "f24_email_attachments",
    "fatture_email_attachments",
    "cedolini_email_attachments",
    "estratti_email_attachments",
    "quietanze_email_attachments",
    "bonifici_email_attachments",
    "verbali_email_attachments",
    "certificati_email_attachments",
    "cartelle_email_attachments",
    "avvisi_bonari_email_attachments",
    "dichiarazioni_iva_email_attachments",
]


async def _trova_documento_scaricabile(db, doc_id: str):
    """Cerca il documento per id nelle collezioni inbox + allegati email."""
    for coll in _COLLEZIONI_DOWNLOAD:
        doc = await db[coll].find_one({"id": doc_id}, {"_id": 0})
        if doc:
            return doc
    return None


@router.get("/documento/{doc_id}/download")
@handle_errors
async def download_documento(doc_id: str):
    """Scarica il file del documento da MongoDB (architettura MongoDB-only)."""
    db = Database.get_db()

    doc = await _trova_documento_scaricabile(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento non trovato")

    # Architettura MongoDB-only: usa solo pdf_data
    pdf_data = doc.get("pdf_data")
    if not pdf_data:
        raise HTTPException(status_code=404, detail="PDF non disponibile in MongoDB. Eseguire migrazione dati.")

    def _decode_chunks():
        # Niente più `base64.b64decode(pdf_data)` in un colpo solo: su file grandi
        # teneva in RAM contemporaneamente stringa base64 + bytes decodificati,
        # causando OOM-kill del processo (502 lato Render). Chunk multiplo di 4
        # perché ogni blocco base64 deve decodificarsi autonomamente.
        chunk_size = 1_048_576
        for i in range(0, len(pdf_data), chunk_size):
            yield base64.b64decode(pdf_data[i:i + chunk_size])

    # Filename sanificato: alcuni allegati email hanno un a-capo nel nome
    # ("Libro unico -\r\n 2026-...") e un header con CR/LF rende la risposta
    # HTTP invalida → 502 dal gateway (bug segnalato 18/07/2026).
    nome_sicuro = re.sub(r'[\r\n"]+', " ", doc.get("filename") or "documento.pdf").strip()
    return StreamingResponse(
        _decode_chunks(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nome_sicuro}"'}
    )


@router.post("/documento/{doc_id}/processa")
@handle_errors
async def processa_documento(
    doc_id: str,
    destinazione: str = Query(..., description="Dove caricare: f24, fatture, buste_paga, estratto_conto")
) -> Dict[str, Any]:
    """
    Processa un documento e lo carica nella sezione appropriata.
    Architettura MongoDB-only: usa solo pdf_data da MongoDB.
    """
    db = Database.get_db()
    
    doc = await db["documents_inbox"].find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    
    # Architettura MongoDB-only: usa solo pdf_data
    pdf_data = doc.get("pdf_data")
    if not pdf_data:
        raise HTTPException(status_code=404, detail="PDF non disponibile in MongoDB. Eseguire migrazione dati.")
    
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
    Architettura MongoDB-only: aggiorna solo i metadati nel database.
    """
    db = Database.get_db()
    
    if nuova_categoria not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Categoria non valida. Usa: {list(CATEGORIES.keys())}")
    
    doc = await db["documents_inbox"].find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    
    # Architettura MongoDB-only: aggiorna solo metadati, nessuna operazione su filesystem
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
    Architettura MongoDB-only: elimina solo dal database.
    """
    db = Database.get_db()
    
    doc = await db["documents_inbox"].find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    
    # Architettura MongoDB-only: elimina solo dal database
    await db["documents_inbox"].delete_one({"id": doc_id})
    
    return {"success": True, "deleted": doc_id}


@router.post("/elimina-processati")
@handle_errors
async def elimina_documenti_processati() -> Dict[str, Any]:
    """
    Elimina tutti i documenti già processati.
    Architettura MongoDB-only: elimina solo dal database.
    """
    db = Database.get_db()
    
    # Conta documenti da eliminare
    count_to_delete = await db["documents_inbox"].count_documents({"processed": True})
    
    # Elimina dal database (architettura MongoDB-only)
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
    """
    Sincronizza automaticamente F24 dalle email.
    - Scarica SOLO allegati F24
    - Li processa automaticamente
    - Li carica nella sezione F24
    Chiamato all'avvio dell'app.
    """
    db = Database.get_db()

    from app.services.gmail_search import get_gmail_credentials
    email_user, email_password, _imap = await get_gmail_credentials(db)

    if not email_user or not email_password:
        return {
            "success": False,
            "error": "Credenziali email non configurate",
            "f24_trovati": 0,
            "f24_caricati": 0,
            "dettagli": []
        }
    
    try:
        # Scarica documenti (solo F24) - max 30 email per velocità
        result = await download_documents_from_email(
            db=db,
            email_user=email_user,
            email_password=email_password,
            since_days=giorni,
            folder="INBOX",
            max_emails=30
        )
        
        if not result.get("success"):
            return {
                "success": False,
                "error": result.get("error", "Errore sconosciuto"),
                "f24_trovati": 0,
                "f24_caricati": 0,
                "dettagli": []
            }
        
        new_documents = result.get("documents", [])
        f24_docs = [d for d in new_documents if d.get("category") == "f24"]
        quietanze_docs = [d for d in new_documents if d.get("category") == "quietanza"]
        
        # Processa automaticamente gli F24 (architettura MongoDB-first)
        f24_caricati = []
        f24_errori = []
        
        for doc in f24_docs:
            try:
                # Architettura MongoDB-first: usa pdf_data
                pdf_data = doc.get("pdf_data")
                if not pdf_data:
                    f24_errori.append({"file": doc["filename"], "errore": "PDF non disponibile in MongoDB"})
                    continue
                
                # Decodifica PDF da base64
                import base64
                pdf_content = base64.b64decode(pdf_data)
                
                # Chiama il parser F24 con pdf_content (architettura MongoDB-first)
                from app.services.parser_f24 import parse_f24_commercialista
                
                parsed = parse_f24_commercialista(pdf_content=pdf_content)
                
                # Il parser restituisce direttamente il risultato (non un wrapper con 'success')
                # Verifica che non ci sia un errore e che ci siano dati
                if not parsed.get("error") and (parsed.get("sezione_erario") or parsed.get("sezione_inps") or parsed.get("totali")):
                    # Il parsed È già f24_data
                    f24_data = parsed
                    
                    # Aggiungi ID e filename
                    from uuid import uuid4
                    f24_data["id"] = str(uuid4())
                    f24_data["file_name"] = doc["filename"]
                    
                    # Rimuovi eventuali _id per evitare errori MongoDB
                    if "_id" in f24_data:
                        del f24_data["_id"]
                    
                    # Aggiungi info email
                    f24_data["email_source"] = {
                        "subject": doc.get("email_subject", ""),
                        "from": doc.get("email_from", ""),
                        "date": doc.get("email_date", ""),
                        "document_id": doc.get("id")
                    }
                    f24_data["auto_imported"] = True
                    f24_data["import_date"] = datetime.now(timezone.utc).isoformat()
                    
                    # Controlla se già esiste (per evitare duplicati)
                    existing = await db["f24_unificato"].find_one({
                        "file_name": f24_data.get("file_name")
                    })
                    
                    if existing:
                        f24_errori.append({"file": doc["filename"], "errore": "F24 già presente nel database"})
                        continue
                    
                    # Salva nel database f24_commercialista
                    await db["f24_unificato"].insert_one(f24_data.copy())
                    
                    # Salva anche in f24_models per la visualizzazione frontend
                    # Usa pdf_data già disponibile da MongoDB (architettura MongoDB-first)
                    pdf_base64 = pdf_data  # Già in base64
                    
                    # Converti formato tributi per f24_models
                    tributi_erario = []
                    for t in parsed.get("sezione_erario", []):
                        tributi_erario.append({
                            "codice_tributo": t.get("codice_tributo"),
                            "codice": t.get("codice_tributo"),
                            "rateazione": t.get("rateazione", ""),
                            "periodo_riferimento": t.get("periodo_riferimento", ""),
                            "anno_riferimento": t.get("anno", ""),
                            "anno": t.get("anno", ""),
                            "mese": t.get("mese", ""),
                            "importo_debito": t.get("importo_debito", 0),
                            "importo_credito": t.get("importo_credito", 0),
                            "importo": t.get("importo_debito", 0),
                            "descrizione": t.get("descrizione", ""),
                            "riferimento": t.get("periodo_riferimento", "")
                        })
                    
                    tributi_inps = []
                    for t in parsed.get("sezione_inps", []):
                        tributi_inps.append({
                            "codice_sede": t.get("codice_sede", ""),
                            "causale": t.get("causale", ""),
                            "causale_contributo": t.get("causale", ""),
                            "matricola": t.get("matricola", ""),
                            "periodo_da": t.get("mese", ""),
                            "periodo_a": t.get("anno", ""),
                            "periodo_riferimento": t.get("periodo_riferimento", ""),
                            "importo_debito": t.get("importo_debito", 0),
                            "importo_credito": t.get("importo_credito", 0),
                            "importo": t.get("importo_debito", 0),
                            "descrizione": t.get("descrizione", "")
                        })
                    
                    tributi_regioni = []
                    for t in parsed.get("sezione_regioni", []):
                        tributi_regioni.append({
                            "codice_tributo": t.get("codice_tributo"),
                            "codice": t.get("codice_tributo"),
                            "codice_regione": t.get("codice_regione", ""),
                            "codice_ente": t.get("codice_regione", ""),
                            "periodo_riferimento": t.get("periodo_riferimento", ""),
                            "importo_debito": t.get("importo_debito", 0),
                            "importo_credito": t.get("importo_credito", 0),
                            "importo": t.get("importo_debito", 0),
                            "descrizione": t.get("descrizione", "")
                        })
                    
                    tributi_imu = []
                    for t in parsed.get("sezione_tributi_locali", []):
                        tributi_imu.append({
                            "codice_tributo": t.get("codice_tributo"),
                            "codice": t.get("codice_tributo"),
                            "codice_comune": t.get("codice_comune", ""),
                            "codice_ente": t.get("codice_comune", ""),
                            "periodo_riferimento": t.get("periodo_riferimento", ""),
                            "importo_debito": t.get("importo_debito", 0),
                            "importo_credito": t.get("importo_credito", 0),
                            "importo": t.get("importo_debito", 0),
                            "descrizione": t.get("descrizione", "")
                        })
                    
                    totali = parsed.get("totali", {})
                    data_scadenza = parsed.get("dati_generali", {}).get("data_versamento")
                    
                    f24_model_record = {
                        "id": f24_data["id"],  # Usa lo stesso ID
                        "data_scadenza": data_scadenza,
                        "scadenza_display": data_scadenza,
                        "codice_fiscale": parsed.get("dati_generali", {}).get("codice_fiscale"),
                        "contribuente": parsed.get("dati_generali", {}).get("ragione_sociale"),
                        "banca": parsed.get("dati_generali", {}).get("banca"),
                        "tipo_f24": parsed.get("dati_generali", {}).get("tipo_f24", "F24"),
                        "tributi_erario": tributi_erario,
                        "tributi_inps": tributi_inps,
                        "tributi_regioni": tributi_regioni,
                        "tributi_imu": tributi_imu,
                        "totale_debito": totali.get("totale_debito", 0),
                        "totale_credito": totali.get("totale_credito", 0),
                        "saldo_finale": totali.get("saldo_netto", 0) or totali.get("saldo_finale", 0),
                        "has_ravvedimento": parsed.get("has_ravvedimento", False),
                        "pagato": False,
                        "filename": doc["filename"],
                        "pdf_data": pdf_base64,
                        "source": "email_sync",
                        "email_source": f24_data.get("email_source"),
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }
                    
                    # Controlla duplicati in f24_models
                    existing_model = await db["f24_unificato"].find_one({
                        "filename": doc["filename"]
                    })
                    
                    if not existing_model:
                        await db["f24_unificato"].insert_one(f24_model_record.copy())
                    
                    # Aggiorna stato documento
                    await db["documents_inbox"].update_one(
                        {"id": doc["id"]},
                        {"$set": {
                            "status": "processato",
                            "processed": True,
                            "processed_to": "f24_models",
                            "processed_at": datetime.now(timezone.utc).isoformat()
                        }}
                    )
                    
                    f24_caricati.append({
                        "file": doc["filename"],
                        "importo": totali.get("saldo_netto", 0) or totali.get("saldo_finale", 0),
                        "data_scadenza": data_scadenza or "",
                        "tributi": len(tributi_erario) + len(tributi_inps)
                    })
                else:
                    f24_errori.append({
                        "file": doc["filename"],
                        "errore": parsed.get("error", "Parsing fallito")
                    })
                    
            except Exception as e:
                f24_errori.append({"file": doc["filename"], "errore": str(e)})
        
        # Processa quietanze
        quietanze_caricate = 0
        for doc in quietanze_docs:
            try:
                await db["documents_inbox"].update_one(
                    {"id": doc["id"]},
                    {"$set": {
                        "status": "nuovo",
                        "ready_for": "quietanze_f24"
                    }}
                )
                quietanze_caricate += 1
            except Exception as e:
                logger.warning(f"Errore collegamento quietanza: {e}")
        
        return {
            "success": True,
            "f24_trovati": len(f24_docs),
            "f24_caricati": len(f24_caricati),
            "f24_errori": len(f24_errori),
            "quietanze_trovate": len(quietanze_docs),
            "dettagli": f24_caricati,
            "errori": f24_errori if f24_errori else None,
            "messaggio": f"Trovati {len(f24_docs)} F24, caricati {len(f24_caricati)} con successo" if f24_docs else "Nessun nuovo F24 trovato nelle email"
        }
        
    except Exception as e:
        logger.error(f"Errore sync F24: {e}")
        return {
            "success": False,
            "error": str(e),
            "f24_trovati": 0,
            "f24_caricati": 0,
            "dettagli": []
        }


@router.post("/processa-f24-scaricati")
@handle_errors
async def processa_f24_scaricati() -> Dict[str, Any]:
    """
    Processa tutti gli F24 già scaricati ma non ancora processati.
    Utile se il primo sync ha fallito.
    """
    db = Database.get_db()
    
    # Trova F24 non processati
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
    
    from app.services.parser_f24 import parse_f24_commercialista
    import base64
    
    for doc in f24_docs:
        try:
            # Architettura MongoDB-first: usa pdf_data
            pdf_data = doc.get("pdf_data")
            if not pdf_data:
                f24_errori.append({"file": doc["filename"], "errore": "PDF non disponibile in MongoDB"})
                continue
            
            pdf_content = base64.b64decode(pdf_data)
            parsed = parse_f24_commercialista(pdf_content=pdf_content)

            # Contratto reale del parser (P0.8): NON restituisce success/f24_data;
            # ritorna {"error": ...} in errore, altrimenti il dict F24 direttamente
            # (dati_generali/sezione_erario/sezione_inps/totali). Stesso contratto
            # usato da sync-f24-automatico.
            if not parsed.get("error") and (
                parsed.get("sezione_erario") or parsed.get("sezione_inps") or parsed.get("totali")
            ):
                f24_data = dict(parsed)
                f24_data["id"] = str(uuid4())
                # file_name è la chiave del controllo duplicati sotto: senza,
                # find_one({"file_name": None}) matcherebbe a vuoto e salterebbe
                # SEMPRE l'import (come fa sync_f24_automatico). Vedi P0.8.
                f24_data["file_name"] = doc.get("filename")

                # Rimuovi _id
                if "_id" in f24_data:
                    del f24_data["_id"]

                # Aggiungi info
                f24_data["email_source"] = {
                    "subject": doc.get("email_subject", ""),
                    "from": doc.get("email_from", ""),
                    "date": doc.get("email_date", ""),
                    "document_id": doc.get("id")
                }
                f24_data["auto_imported"] = True
                f24_data["import_date"] = datetime.now(timezone.utc).isoformat()
                
                # Controlla duplicati
                existing = await db["f24_unificato"].find_one({
                    "file_name": f24_data.get("file_name")
                })
                
                if existing:
                    # Aggiorna stato come processato ma non aggiungere
                    await db["documents_inbox"].update_one(
                        {"id": doc["id"]},
                        {"$set": {"status": "processato", "processed": True, "note": "Già presente"}}
                    )
                    continue
                
                await db["f24_unificato"].insert_one(f24_data.copy())
                
                await db["documents_inbox"].update_one(
                    {"id": doc["id"]},
                    {"$set": {
                        "status": "processato",
                        "processed": True,
                        "processed_to": "f24_commercialista",
                        "processed_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                
                f24_caricati.append({
                    "file": doc["filename"],
                    "importo": f24_data.get("totali", {}).get("saldo_netto", 0),
                    "tributi": len(f24_data.get("sezione_erario", []))
                              + len(f24_data.get("sezione_inps", [])),
                })
            else:
                f24_errori.append({
                    "file": doc["filename"],
                    "errore": parsed.get("error", "Parsing fallito")
                })
                
        except Exception as e:
            f24_errori.append({"file": doc["filename"], "errore": str(e)})
    
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
        
        # Architettura MongoDB-first: usa pdf_data
        pdf_data = doc.get("pdf_data")
        if not pdf_data:
            errori.append({"file": filename, "errore": "PDF non disponibile in MongoDB"})
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
                        "pdf_data": pdf_data,  # Architettura MongoDB-first
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
                            # Usa dict() per evitare ObjectId issue
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
            errori.append({"file": filename, "errore": "PDF non disponibile in MongoDB"})
            continue
        
        try:
            # Architettura MongoDB-only: decodifica da Base64
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
                    "pdf_data": pdf_data,  # Architettura MongoDB-only
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
    2. Processa buste paga
    3. Processa estratti conto Nexi
    4. Processa estratti conto BNL
    """
    risultati = {
        "ricategorizzazione": None,
        "buste_paga": None,
        "estratti_nexi": None,
        "estratti_bnl": None
    }
    
    try:
        # 1. Ricategorizza
        risultati["ricategorizzazione"] = await ricategorizza_documenti()
    except Exception as e:
        risultati["ricategorizzazione"] = {"error": str(e)}
    
    try:
        # 2. Buste paga
        risultati["buste_paga"] = await sync_buste_paga()
    except Exception as e:
        risultati["buste_paga"] = {"error": str(e)}
    
    try:
        # 3. Estratti Nexi
        risultati["estratti_nexi"] = await sync_estratti_conto()
    except Exception as e:
        risultati["estratti_nexi"] = {"error": str(e)}
    
    try:
        # 4. Estratti BNL
        risultati["estratti_bnl"] = await sync_estratti_bnl()
    except Exception as e:
        risultati["estratti_bnl"] = {"error": str(e)}
    
    return {
        "success": True,
        "risultati": risultati,
        "sommario": {
            "ricategorizzati": risultati.get("ricategorizzazione", {}).get("ricategorizzati", 0),
            "buste_paga_processate": risultati.get("buste_paga", {}).get("processati", 0),
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
    # Architettura MongoDB-only: legge file da disco e li salva come Base64 in MongoDB.
    
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
            
            # Architettura MongoDB-only: leggi file e codifica in Base64
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
            
            # Crea record documento con pdf_data (MongoDB-only)
            doc_record = {
                "id": str(uuid.uuid4()),
                "filename": filename,
                "pdf_data": pdf_base64,  # Architettura MongoDB-only
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

from fastapi import UploadFile, File
from app.utils.error_handler import handle_errors

def detect_document_type(filename: str, file_content: bytes) -> str:
    """
    Rileva automaticamente il tipo di documento dal nome file e contenuto.
    
    Returns: 'estratto_conto', 'f24', 'quietanza_f24', 'cedolino', 'bonifici', 'fattura', 'auto'
    """
    lower = filename.lower()
    
    # Controlla estensione
    if lower.endswith('.xml') or lower.endswith('.p7m') or lower.endswith('.xml.p7m'):
        # Estrai XML da P7M se necessario
        try:
            content_str = file_content.decode('utf-8', errors='ignore')
            
            # Se è P7M, cerca il contenuto XML all'interno del wrapper
            if lower.endswith('.p7m') and 'FatturaElettronica' not in content_str:
                # P7M: il contenuto XML può essere embedded — cerca i marker XML
                xml_start = content_str.find('<?xml')
                if xml_start == -1:
                    xml_start = content_str.find('<FatturaElettronica')
                if xml_start == -1:
                    xml_start = content_str.find('<DatiRT')
                if xml_start >= 0:
                    content_str = content_str[xml_start:]
            
            # Corrispettivi telematici COR10 (Registratore Telematico)
            # Contengono DatiRT, DataOraRilevazione o Trasmissione con CodiceFiscaleEsercente
            if ('DatiRT' in content_str or 
                'DataOraRilevazione' in content_str or
                'CodiceFiscaleEsercente' in content_str or
                'PIVAEsercente' in content_str or
                'RegistratoreTelematicoComp' in content_str):
                return 'corrispettivo'
            
            # Fattura elettronica standard
            if 'FatturaElettronica' in content_str or 'fatturaElettronicaHeader' in content_str.lower():
                return 'fattura'
        except Exception as e:
            logger.warning(f"Errore decodifica XML: {e}")
        return 'fattura'  # XML generico = fattura
    
    # Nomi che indicano tipo
    if any(kw in lower for kw in ['estratto', 'conto', 'movimenti', 'bpm', 'banco']):
        return 'estratto_conto'
    
    if any(kw in lower for kw in ['quietanza', 'ricevuta', 'pagamento_f24', 'receipt']):
        return 'quietanza_f24'
    
    if 'f24' in lower or 'delega' in lower:
        return 'f24'
    
    if any(kw in lower for kw in ['cedolin', 'busta', 'paga', 'libro_unico', 'lul', 'payslip']):
        return 'cedolino'
    
    if any(kw in lower for kw in ['bonifico', 'bonifici', 'sepa', 'transfer']):
        return 'bonifici'
    
    if any(kw in lower for kw in ['fattura', 'invoice', 'ft_']):
        return 'fattura'
    
    # Analizza contenuto PDF
    if lower.endswith('.pdf'):
        try:
            content_str = file_content[:5000].decode('latin-1', errors='ignore').upper()
            
            if 'QUIETANZA' in content_str or 'RICEVUTA DI VERSAMENTO' in content_str:
                return 'quietanza_f24'
            
            if 'DELEGA F24' in content_str or 'MODELLO DI PAGAMENTO' in content_str or 'AGENZIA DELLE ENTRATE' in content_str:
                return 'f24'
            
            if 'CEDOLINO' in content_str or 'BUSTA PAGA' in content_str or 'LIBRO UNICO' in content_str:
                return 'cedolino'
            
            if 'ESTRATTO CONTO' in content_str or 'SALDO INIZIALE' in content_str:
                return 'estratto_conto'
                
        except Exception as e:
            logger.warning(f"Errore analisi contenuto PDF: {e}")
    
    # Analizza contenuto Excel
    if lower.endswith('.xlsx') or lower.endswith('.xls') or lower.endswith('.csv'):
        # Verifica se è una distinta stipendi BPM
        if 'distint' in lower or 'stipend' in lower or 'elenco' in lower:
            try:
                content_str = file_content[:2000].decode('utf-8', errors='ignore')
                # Verifica intestazioni tipiche distinte BPM
                if 'Beneficiario' in content_str and ('Importo' in content_str or 'IBAN' in content_str):
                    return 'distinte_bpm'
            except Exception:
                pass
        return 'estratto_conto'  # CSV/Excel di default è estratto conto
    
    return 'auto'  # Non riconosciuto


@router.post("/upload-auto")
@handle_errors
async def upload_documento_automatico(
    file: UploadFile = File(...)
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
    
    filename = file.filename
    content = await file.read()
    
    # Rileva tipo
    tipo_rilevato = detect_document_type(filename, content)
    
    logger.info(f"Upload automatico: {filename} -> tipo rilevato: {tipo_rilevato}")
    
    # Se non riconosciuto, salva in inbox
    if tipo_rilevato == 'auto':
        db = Database.get_db()
        
        # Salva file in cartella temporanea
        import hashlib
        file_hash = hashlib.md5(content).hexdigest()
        
        doc_id = f"upload_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{file_hash[:8]}"
        
        # SALVA SU MONGODB - NIENTE FILESYSTEM
        import base64
        pdf_base64 = base64.b64encode(content).decode('utf-8')
        
        doc_record = {
            "id": doc_id,
            "filename": filename,
            "pdf_data": pdf_base64,  # Contenuto in MongoDB!
            "category": "altro",
            "category_label": "Da classificare",
            "status": "nuovo",
            "processed": False,
            "file_hash": file_hash,
            "file_size": len(content),
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "source": "upload_automatico"
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
                "hash_file": file_hash,
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
                else:
                    ingest = await ingest_corrispettivo_parsed(db, parsed, filename=filename, source="xml")
                    result["action"] = ingest["action"]
                    result["corrispettivo_id"] = ingest.get("corrispettivo_id")
                    result["prima_nota_cassa_id"] = ingest.get("prima_nota_cassa_id")
                    result["prima_nota_banca_id"] = ingest.get("prima_nota_banca_id")
                    result["tipo_documento"] = "corrispettivo"
                    data_str = ingest.get("data", "N/A")
                    tot_str = f"{ingest.get('totale', 0):.2f}"
                    if ingest["action"] == "duplicate":
                        result["success"] = False
                        result["duplicate"] = True
                        result["message"] = f"Corrispettivo duplicato ignorato: {data_str} — totale {tot_str}€"
                        result["imported"] = 0
                    elif ingest["action"] == "updated":
                        result["message"] = f"Corrispettivo aggiornato: {data_str} — totale {tot_str}€"
                        result["imported"] = 1
                    else:
                        result["message"] = f"Corrispettivo importato: {data_str} — totale {tot_str}€ (Prima Nota aggiornata)"
                        result["imported"] = 1
                    
        elif tipo_rilevato == 'fattura':
            # Import fattura XML
            from fastapi import HTTPException as _HTTPException
            from app.routers.invoices.fatture_upload import parse_fattura_xml, process_fattura_to_db

            # Stesso fallback multi-encoding di process_xml_bytes (mai
            # 'utf-8' con errors='ignore': su un file non-UTF-8, es.
            # ISO-8859-1 con testo accentato in fornitore/righe, quello
            # cancella silenziosamente i byte non validi — corruzione dati
            # che ora è visibile perché xml_raw viene anche persistito e
            # riservito da /xml-originale, bug reale, review Codex PR #71).
            xml_content = None
            for _enc in ('utf-8', 'utf-8-sig', 'latin-1', 'iso-8859-1'):
                try:
                    xml_content = content.decode(_enc)
                    break
                except (UnicodeDecodeError, LookupError):
                    continue
            if not xml_content:
                xml_content = content.decode('utf-8', errors='ignore')
            parsed = parse_fattura_xml(xml_content)

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
                for body in [parsed] + altri_body:
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
                else:
                    raise ultimo_errore_duplicato
            else:
                result["success"] = False
                result["message"] = "Errore parsing XML fattura"
                
        elif tipo_rilevato == 'f24':
            # Import F24 PDF - USA IL WORKFLOW COMPLETO
            from app.routers.f24_parser import import_f24
            import io
            
            # Crea un nuovo UploadFile per il workflow
            file_obj = io.BytesIO(content)
            new_upload = UploadFile(filename=filename, file=file_obj)
            
            try:
                f24_result = await import_f24(file=new_upload, aggiorna_esistente=True)
                result["message"] = f24_result.get("message", "F24 importato con workflow completo")
                result["data"] = f24_result.get("data", {})
                result["workflow"] = "F24_COMPLETO"
                result["imported"] = 1
            except HTTPException as he:
                result["success"] = False
                result["message"] = f"Errore import F24: {he.detail}"
            except Exception as e:
                result["success"] = False
                result["message"] = f"Errore import F24: {str(e)}"
                
        elif tipo_rilevato == 'quietanza_f24':
            # Import Quietanza F24
            from app.services.parser_f24 import parse_f24_pdf_bytes
            
            parsed = await parse_f24_pdf_bytes(content, filename, is_quietanza=True)
            
            if parsed:
                quietanza_doc = {
                    "id": f"quietanza_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
                    "filename": filename,
                    **parsed,
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
                await db["quietanze_f24"].insert_one(dict(quietanza_doc).copy())
                result["message"] = "Quietanza F24 importata"
                result["imported"] = 1
            else:
                result["success"] = False
                result["message"] = "Errore parsing PDF Quietanza"
                
        elif tipo_rilevato == 'cedolino':
            # Import cedolino / Libro Unico - USA IL WORKFLOW COMPLETO
            from app.routers.libro_unico_parser import import_libro_unico
            import io
            
            # Crea un nuovo UploadFile per il workflow
            file_obj = io.BytesIO(content)
            new_upload = UploadFile(filename=filename, file=file_obj)
            
            try:
                lul_result = await import_libro_unico(file=new_upload, aggiorna_esistenti=True)
                result["message"] = lul_result.get("message", "Libro Unico importato con workflow completo")
                result["data"] = lul_result.get("data", {})
                result["workflow"] = "LUL_COMPLETO"
                result["imported"] = 1
            except HTTPException as he:
                result["success"] = False
                result["message"] = f"Errore import LUL: {he.detail}"
            except Exception as e:
                result["success"] = False
                result["message"] = f"Errore import LUL: {str(e)}"
        
        elif tipo_rilevato == 'distinte_bpm':
            # Import distinte stipendi BPM - riconcilia con buste paga
            from app.routers.distinte_bpm import import_distinte_bpm
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
                
        elif tipo_rilevato == 'estratto_conto':
            # Import diretto estratto conto CSV Banco BPM → estratto_conto_movimenti
            from app.routers.bank.estratto_conto import import_estratto_conto

            _orig_filename = filename
            _orig_content  = content

            class _FakeUpload:
                filename = _orig_filename
                async def read(self):
                    return _orig_content

            try:
                ec_result = await import_estratto_conto(_FakeUpload())
                stats = ec_result.get("stats", {})
                nuovi = stats.get("nuovi", 0)
                dup   = stats.get("duplicati", 0)
                result["message"] = (
                    f"Estratto conto importato: {nuovi} movimenti nuovi, "
                    f"{dup} duplicati saltati."
                )
                result["movimenti_nuovi"]     = nuovi
                result["duplicati_saltati"]   = dup
                result["totale_letti"]        = stats.get("totale_letti", nuovi + dup)
                result["riconciliazione"]     = ec_result.get("riconciliazione_summary")
            except Exception as ec_err:
                logger.error(f"Import estratto conto fallito: {ec_err}")
                result["success"] = False
                result["message"] = f"Errore import estratto conto: {str(ec_err)}"
            
        elif tipo_rilevato == 'bonifici':
            # Salva e processa nello stesso flusso canonico dell'Archivio
            # Bonifici. Prima di questa correzione il file restava soltanto
            # in ``documents_inbox`` con il messaggio "vai all'archivio": i
            # dati non venivano letti ne' associati al dipendente.
            import base64 as b64
            from app.services.bonifici_pdf_ingest import importa_pdf_bonifico
            
            doc_id = f"bonifici_{uuid.uuid4()}"
            bonifici_doc = {
                "id": doc_id,
                "filename": filename,
                "pdf_data": b64.b64encode(content).decode('utf-8'),  # MongoDB-only
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
            await db["documents_inbox"].update_one(
                {"id": doc_id},
                {"$set": {
                    "processed": ingest.get("status") in {"saved", "duplicate"},
                    "status": "elaborato" if ingest.get("status") in {"saved", "duplicate"} else "da_verificare",
                    "bonifico_transfer_id": ingest.get("transfer_id"),
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                }},
            )

            if ingest.get("associato"):
                result["message"] = "Bonifico letto e associato al dipendente per nome e importo esatti."
            elif ingest.get("status") == "duplicate":
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
