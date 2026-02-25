"""
Router per Download Completo Email e Gestione Documenti Non Associati
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import logging
import asyncio

from app.database import Database
from app.services.email_full_download import (
    EmailFullDownloader,
    get_documenti_non_associati,
    associate_pdf_to_document,
    smart_auto_associate,
    smart_auto_associate_v2,
    populate_payslips_pdf_data,
    get_documents_inbox_stats,
    sync_filesystem_pdfs_to_db,
    associate_f24_from_filesystem,
    process_cedolini_to_prima_nota,
    CATEGORY_COLLECTIONS
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/email-download", tags=["Email Download"])

# Stato del download in corso
download_status = {
    "in_progress": False,
    "started_at": None,
    "stats": None,
    "error": None
}


@router.get("/status")
async def get_download_status() -> Dict[str, Any]:
    """Ottiene lo stato del download in corso."""
    return download_status


@router.post("/start-full-download")
async def start_full_download(
    background_tasks: BackgroundTasks,
    days_back: int = Query(default=1, description="Giorni indietro da scaricare (default 1 giorno)"),
    folder: str = Query(default="INBOX", description="Cartella IMAP"),
    process_aruba: bool = Query(default=True, description="Processa anche email fatture Aruba")
) -> Dict[str, Any]:
    """
    Avvia il download completo di tutte le email con PDF.
    Il processo viene eseguito in background.
    Dopo il download, processa automaticamente le email Aruba per le fatture.
    """
    global download_status
    
    if download_status["in_progress"]:
        raise HTTPException(status_code=400, detail="Download già in corso")
    
    download_status["in_progress"] = True
    download_status["started_at"] = datetime.now(timezone.utc).isoformat()
    download_status["stats"] = None
    download_status["error"] = None
    
    async def run_download():
        global download_status
        try:
            db = Database.get_db()
            downloader = EmailFullDownloader(db)
            result = await downloader.download_all_emails(
                folder=folder,
                days_back=days_back
            )
            download_status["stats"] = result.get("stats")
            if not result.get("success"):
                download_status["error"] = result.get("error")
            
            # AUTOMAZIONE ARUBA: Processa email fatture dopo il download
            if process_aruba and result.get("success"):
                try:
                    from app.services.aruba_automation import process_aruba_emails
                    from app.config import settings
                    
                    email_user = settings.EMAIL_USER or settings.GMAIL_EMAIL or ""
                    email_pass = settings.EMAIL_APP_PASSWORD or settings.GMAIL_APP_PASSWORD or ""
                    
                    if email_user and email_pass:
                        logger.info("🚀 Avvio automazione fatture Aruba...")
                        aruba_result = await process_aruba_emails(
                            db=db,
                            email_user=email_user,
                            email_password=email_pass,
                            since_days=days_back,
                            auto_insert_prima_nota=True
                        )
                        
                        if download_status.get("stats"):
                            download_status["stats"]["aruba_automation"] = aruba_result.get("stats", {})
                            download_status["stats"]["aruba_fatture"] = aruba_result.get("fatture", [])
                        
                        logger.info(f"✅ Automazione Aruba completata: {aruba_result.get('stats', {})}")
                except Exception as e:
                    logger.error(f"Errore automazione Aruba: {e}")
                    if download_status.get("stats"):
                        download_status["stats"]["aruba_error"] = str(e)
                        
        except Exception as e:
            logger.error(f"Errore download: {e}")
            download_status["error"] = str(e)
        finally:
            download_status["in_progress"] = False
    
    background_tasks.add_task(run_download)
    
    return {
        "message": "Download avviato in background",
        "days_back": days_back,
        "folder": folder
    }


@router.post("/download-single-day")
async def download_single_day(
    date: str = Query(..., description="Data nel formato YYYY-MM-DD")
) -> Dict[str, Any]:
    """
    Scarica email di un singolo giorno.
    """
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato data non valido. Usa YYYY-MM-DD")
    
    db = Database.get_db()
    downloader = EmailFullDownloader(db)
    result = await downloader.download_single_day(target_date)
    
    return result


@router.get("/documenti-non-associati")
async def list_documenti_non_associati(
    category: Optional[str] = Query(default=None, description="Filtra per categoria"),
    limit: int = Query(default=100, le=500)
) -> Dict[str, Any]:
    """
    Lista i documenti PDF scaricati ma non ancora associati.
    """
    db = Database.get_db()
    docs = await get_documenti_non_associati(db, category, limit)
    
    return {
        "count": len(docs),
        "documenti": docs
    }


@router.post("/associa-documento")
async def associa_documento(
    pdf_id: str,
    source_collection: str,
    target_document_id: str,
    target_collection: str
) -> Dict[str, Any]:
    """
    Associa manualmente un PDF a un documento esistente.
    """
    db = Database.get_db()
    
    success = await associate_pdf_to_document(
        db,
        pdf_id,
        source_collection,
        target_document_id,
        target_collection
    )
    
    if success:
        return {"success": True, "message": "PDF associato con successo"}
    else:
        raise HTTPException(status_code=400, detail="Associazione fallita")


@router.post("/auto-associa")
async def auto_associa_documenti() -> Dict[str, Any]:
    """
    Tenta di associare automaticamente i PDF ai documenti esistenti
    usando logica intelligente.
    """
    db = Database.get_db()
    stats = await smart_auto_associate(db)
    
    return {
        "success": True,
        "stats": stats
    }


@router.post("/auto-associa-v2")
async def auto_associa_documenti_v2() -> Dict[str, Any]:
    """
    Versione migliorata dell'auto-associazione che:
    1. Popola pdf_data nei payslips dal filesystem
    2. Associa documenti di documents_inbox
    3. Gestisce fatture, F24 e buste paga
    """
    db = Database.get_db()
    stats = await smart_auto_associate_v2(db)
    
    return {
        "success": True,
        "message": "Auto-associazione v2 completata",
        "stats": stats
    }


@router.post("/processa-fatture-email")
async def processa_fatture_email_ai(
    limit: int = Query(default=10, le=50, description="Numero massimo di fatture da processare"),
    background_tasks: BackgroundTasks = None
) -> Dict[str, Any]:
    """
    Processa le fatture ricevute via email usando AI per estrarre i dati
    e le inserisce automaticamente in invoices.
    
    Flusso:
    1. Prende PDF da fatture_email_attachments non ancora processati
    2. Usa AI per estrarre dati (fornitore, numero, importo, data)
    3. Inserisce in invoices
    4. Marca come processato
    """
    import base64
    import uuid
    from app.services.ai_document_parser import parse_fattura_ai, convert_ai_fattura_to_db_format
    
    db = Database.get_db()
    stats = {
        "processate": 0,
        "errori": 0,
        "già_esistenti": 0,
        "non_pdf_saltati": 0,
        "fatture_inserite": []
    }
    
    # Estensioni da escludere (non sono PDF validi)
    EXCLUDED_EXTENSIONS = {'.p7s', '.p7m', '.p7c', '.sig', '.xml', '.txt', '.html'}
    
    # Trova fatture non ancora processate
    cursor = db["fatture_email_attachments"].find({
        "$or": [
            {"processed": {"$exists": False}},
            {"processed": False}
        ],
        "pdf_data": {"$exists": True, "$ne": None}
    }).limit(limit * 2)  # Prendiamo di più per compensare i saltati
    
    processed_count = 0
    async for doc in cursor:
        if processed_count >= limit:
            break
            
        try:
            filename = doc.get("filename", "fattura.pdf")
            
            # Salta file non PDF
            ext = filename.lower().split('.')[-1] if '.' in filename else ''
            if f'.{ext}' in EXCLUDED_EXTENSIONS or ext in ['p7s', 'p7m', 'xml', 'txt', 'html']:
                stats["non_pdf_saltati"] += 1
                # Marca come processato per non riprocessarlo
                await db["fatture_email_attachments"].update_one(
                    {"id": doc["id"]},
                    {"$set": {"processed": True, "skip_reason": "non_pdf_file"}}
                )
                continue
            
            # Verifica che sia effettivamente un PDF
            pdf_data = doc.get("pdf_data")
            if isinstance(pdf_data, str):
                try:
                    pdf_bytes = base64.b64decode(pdf_data)
                except Exception:
                    pdf_bytes = pdf_data.encode()
            else:
                pdf_bytes = pdf_data
            
            # Verifica magic bytes PDF
            if not pdf_bytes[:4] == b'%PDF':
                stats["non_pdf_saltati"] += 1
                await db["fatture_email_attachments"].update_one(
                    {"id": doc["id"]},
                    {"$set": {"processed": True, "skip_reason": "not_pdf_format"}}
                )
                continue
            
            # Estrai dati con AI
            ai_result = await parse_fattura_ai(file_bytes=pdf_bytes)
            
            if not ai_result.get("success"):
                stats["errori"] += 1
                logger.warning(f"AI parsing fallito per {filename}: {ai_result.get('error')}")
                continue
            
            # Converti in formato DB
            invoice_data = convert_ai_fattura_to_db_format(ai_result.get("data", {}))
            
            # Verifica duplicati
            numero_fattura = invoice_data.get("numero_fattura") or invoice_data.get("invoice_number")
            if numero_fattura:
                existing = await db["invoices"].find_one({
                    "$or": [
                        {"invoice_number": numero_fattura},
                        {"numero_fattura": numero_fattura}
                    ]
                })
                if existing:
                    stats["già_esistenti"] += 1
                    # Marca come processato comunque
                    await db["fatture_email_attachments"].update_one(
                        {"id": doc["id"]},
                        {"$set": {"processed": True, "existing_invoice_id": existing.get("id")}}
                    )
                    processed_count += 1
                    continue
            
            # Inserisci nuova fattura
            new_invoice = {
                "id": str(uuid.uuid4()),
                **invoice_data,
                "pdf_data": pdf_data,
                "pdf_filename": filename,
                "source": "email_attachment",
                "email_attachment_id": doc.get("id"),
                "email_subject": doc.get("email_subject"),
                "email_from": doc.get("email_from"),
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            await db["invoices"].insert_one(new_invoice.copy())
            
            # Marca come processato
            await db["fatture_email_attachments"].update_one(
                {"id": doc["id"]},
                {"$set": {
                    "processed": True,
                    "invoice_id": new_invoice["id"],
                    "processed_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            
            stats["processate"] += 1
            processed_count += 1
            stats["fatture_inserite"].append({
                "filename": filename,
                "fornitore": invoice_data.get("supplier_name") or invoice_data.get("fornitore"),
                "numero": numero_fattura,
                "totale": invoice_data.get("total_amount") or invoice_data.get("totale")
            })
            
            logger.info(f"Fattura inserita: {filename} -> {new_invoice['id']}")
            
        except Exception as e:
            logger.error(f"Errore processing fattura {doc.get('filename')}: {e}")
            stats["errori"] += 1
    
    return {
        "success": True,
        "stats": stats
    }


# === PROCESSO BATCH FATTURE EMAIL (evita timeout) ===
# Stato globale per tracciare il progresso
_batch_processing_status = {
    "running": False,
    "progress": 0,
    "total": 0,
    "processate": 0,
    "errori": 0,
    "started_at": None,
    "completed_at": None,
    "last_error": None
}

@router.get("/processa-fatture-email/status")
async def get_batch_status() -> Dict[str, Any]:
    """Restituisce lo stato corrente del processo batch."""
    return _batch_processing_status


@router.post("/processa-fatture-email/batch")
async def processa_fatture_email_batch(
    background_tasks: BackgroundTasks,
    batch_size: int = Query(default=10, le=20, description="Dimensione batch"),
    total_limit: int = Query(default=50, le=200, description="Limite totale fatture")
) -> Dict[str, Any]:
    """
    Avvia il processo di fatture email in background con batch.
    Controlla lo stato con GET /processa-fatture-email/status
    """
    global _batch_processing_status
    
    if _batch_processing_status["running"]:
        return {
            "success": False,
            "message": "Processo già in esecuzione",
            "status": _batch_processing_status
        }
    
    # Reset status
    _batch_processing_status = {
        "running": True,
        "progress": 0,
        "total": total_limit,
        "processate": 0,
        "errori": 0,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "last_error": None
    }
    
    # Avvia in background
    background_tasks.add_task(_run_batch_processing, batch_size, total_limit)
    
    return {
        "success": True,
        "message": f"Processo avviato in background. Elaborazione di {total_limit} fatture in batch da {batch_size}.",
        "status": _batch_processing_status
    }


async def _run_batch_processing(batch_size: int, total_limit: int):
    """Task background per elaborazione batch."""
    global _batch_processing_status
    import base64
    import uuid
    from app.services.ai_document_parser import parse_fattura_ai, convert_ai_fattura_to_db_format
    
    db = Database.get_db()
    processed_total = 0
    
    try:
        # Estensioni da escludere
        EXCLUDED_EXTENSIONS = {'.p7s', '.p7m', '.p7c', '.sig', '.xml', '.txt', '.html'}
        
        # Conta totale da processare
        total_pending = await db["fatture_email_attachments"].count_documents({
            "$or": [{"processed": {"$exists": False}}, {"processed": False}],
            "pdf_data": {"$exists": True, "$ne": None}
        })
        
        _batch_processing_status["total"] = min(total_pending, total_limit)
        
        while processed_total < total_limit:
            # Prendi un batch
            cursor = db["fatture_email_attachments"].find({
                "$or": [{"processed": {"$exists": False}}, {"processed": False}],
                "pdf_data": {"$exists": True, "$ne": None}
            }).limit(batch_size)
            
            batch_count = 0
            async for doc in cursor:
                try:
                    filename = doc.get("filename", "fattura.pdf")
                    ext = filename.lower().split('.')[-1] if '.' in filename else ''
                    
                    if f'.{ext}' in EXCLUDED_EXTENSIONS:
                        await db["fatture_email_attachments"].update_one(
                            {"id": doc["id"]},
                            {"$set": {"processed": True, "skip_reason": "non_pdf_file"}}
                        )
                        batch_count += 1
                        processed_total += 1
                        continue
                    
                    pdf_data = doc.get("pdf_data")
                    if isinstance(pdf_data, str):
                        try:
                            pdf_bytes = base64.b64decode(pdf_data)
                        except Exception:
                            pdf_bytes = pdf_data.encode()
                    else:
                        pdf_bytes = pdf_data
                    
                    if not pdf_bytes[:4] == b'%PDF':
                        await db["fatture_email_attachments"].update_one(
                            {"id": doc["id"]},
                            {"$set": {"processed": True, "skip_reason": "not_pdf_format"}}
                        )
                        batch_count += 1
                        processed_total += 1
                        continue
                    
                    # Parsing AI
                    ai_result = await parse_fattura_ai(file_bytes=pdf_bytes)
                    
                    if not ai_result.get("success"):
                        _batch_processing_status["errori"] += 1
                        await db["fatture_email_attachments"].update_one(
                            {"id": doc["id"]},
                            {"$set": {"processed": True, "error": str(ai_result.get('error'))}}
                        )
                        batch_count += 1
                        processed_total += 1
                        continue
                    
                    invoice_data = convert_ai_fattura_to_db_format(ai_result.get("data", {}))
                    numero_fattura = invoice_data.get("numero_fattura") or invoice_data.get("invoice_number")
                    
                    # Check duplicati
                    if numero_fattura:
                        existing = await db["invoices"].find_one({
                            "$or": [{"invoice_number": numero_fattura}, {"numero_fattura": numero_fattura}]
                        })
                        if existing:
                            await db["fatture_email_attachments"].update_one(
                                {"id": doc["id"]},
                                {"$set": {"processed": True, "existing_invoice_id": existing.get("id")}}
                            )
                            batch_count += 1
                            processed_total += 1
                            continue
                    
                    # Inserisci fattura
                    new_invoice = {
                        "id": str(uuid.uuid4()),
                        **invoice_data,
                        "pdf_data": pdf_data,
                        "pdf_filename": filename,
                        "source": "email_attachment",
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }
                    
                    await db["invoices"].insert_one(new_invoice.copy())
                    await db["fatture_email_attachments"].update_one(
                        {"id": doc["id"]},
                        {"$set": {"processed": True, "invoice_id": new_invoice["id"]}}
                    )
                    
                    _batch_processing_status["processate"] += 1
                    batch_count += 1
                    processed_total += 1
                    
                except Exception as e:
                    _batch_processing_status["errori"] += 1
                    _batch_processing_status["last_error"] = str(e)
                    batch_count += 1
                    processed_total += 1
            
            # Aggiorna progresso
            _batch_processing_status["progress"] = processed_total
            
            # Se non abbiamo processato nulla nel batch, interrompi
            if batch_count == 0:
                break
            
            # Pausa tra batch per non sovraccaricare
            await asyncio.sleep(0.5)
        
    except Exception as e:
        _batch_processing_status["last_error"] = str(e)
        logger.error(f"Errore batch processing: {e}")
    
    finally:
        _batch_processing_status["running"] = False
        _batch_processing_status["completed_at"] = datetime.now(timezone.utc).isoformat()




@router.post("/popola-pdf-payslips")
async def popola_pdf_payslips() -> Dict[str, Any]:
    """
    Popola il campo pdf_data in tutti i payslips che hanno filepath
    ma non hanno ancora pdf_data.
    """
    db = Database.get_db()
    stats = await populate_payslips_pdf_data(db)
    
    return {
        "success": True,
        "message": "Popolazione PDF payslips completata",
        "stats": stats
    }


@router.get("/documents-inbox-stats")
async def get_inbox_stats() -> Dict[str, Any]:
    """
    Statistiche dettagliate sulla collezione documents_inbox.
    """
    db = Database.get_db()
    stats = await get_documents_inbox_stats(db)
    
    return stats


@router.post("/sync-filesystem")
async def sync_filesystem() -> Dict[str, Any]:
    """
    Sincronizza i PDF dal filesystem con documents_inbox.
    Scansiona /app/documents e aggiunge/aggiorna i record nel database.
    """
    db = Database.get_db()
    stats = await sync_filesystem_pdfs_to_db(db)
    
    return {
        "success": True,
        "message": "Sincronizzazione filesystem completata",
        "stats": stats
    }


@router.post("/associa-f24-filesystem")
async def associa_f24_filesystem() -> Dict[str, Any]:
    """
    Associa i PDF F24 dal filesystem ai record f24_commercialista.
    """
    db = Database.get_db()
    stats = await associate_f24_from_filesystem(db)
    
    return {
        "success": True,
        "message": "Associazione F24 completata",
        "stats": stats
    }


@router.post("/processa-cedolini")
async def processa_cedolini() -> Dict[str, Any]:
    """
    Processa i cedolini scaricati ed estrae i dati per prima_nota_salari.
    Legge i PDF, estrae nomi dipendenti, importi netti/lordi, e crea record automaticamente.
    """
    db = Database.get_db()
    stats = await process_cedolini_to_prima_nota(db)
    
    return {
        "success": True,
        "message": "Processamento cedolini completato",
        "stats": stats
    }


@router.get("/statistiche")
async def get_statistiche_allegati() -> Dict[str, Any]:
    """
    Statistiche sui PDF scaricati e associati.
    """
    db = Database.get_db()
    stats = {}
    
    for category, collection in CATEGORY_COLLECTIONS.items():
        total = await db[collection].count_documents({})
        associati = await db[collection].count_documents({"associato": True})
        non_associati = await db[collection].count_documents({"associato": False})
        
        if total > 0:
            stats[category] = {
                "totale": total,
                "associati": associati,
                "non_associati": non_associati,
                "percentuale_associati": round(associati / total * 100, 1)
            }
    
    return stats


@router.get("/pdf/{collection}/{pdf_id}")
async def get_pdf_content(collection: str, pdf_id: str):
    """
    Recupera il contenuto di un PDF specifico.
    """
    from fastapi.responses import Response
    import base64
    
    db = Database.get_db()
    
    # Verifica che la collezione sia valida
    valid_collections = list(CATEGORY_COLLECTIONS.values()) + ["documents_inbox"]
    if collection not in valid_collections:
        raise HTTPException(status_code=400, detail="Collezione non valida")
    
    doc = await db[collection].find_one({"id": pdf_id})
    if not doc:
        raise HTTPException(status_code=404, detail="PDF non trovato")
    
    pdf_data = doc.get("pdf_data")
    if not pdf_data:
        raise HTTPException(status_code=404, detail="Contenuto PDF non disponibile")
    
    pdf_bytes = base64.b64decode(pdf_data)
    filename = doc.get("filename", "documento.pdf")
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'}
    )


@router.get("/inbox-documents")
async def list_inbox_documents(
    category: str = Query(default=None),
    status: str = Query(default=None),
    limit: int = Query(default=50, le=200)
) -> Dict[str, Any]:
    """Lista documenti in documents_inbox con PDF salvato in MongoDB."""
    db = Database.get_db()
    
    query = {}
    if category:
        query["category"] = category
    if status:
        query["status"] = status
    
    # Solo documenti con pdf_data (salvati su MongoDB)
    query["pdf_data"] = {"$exists": True, "$ne": None}
    
    cursor = db["documents_inbox"].find(
        query,
        {"_id": 0, "pdf_data": 0}  # Escludi PDF dalla lista
    ).sort("downloaded_at", -1).limit(limit)
    
    docs = await cursor.to_list(limit)
    total = await db["documents_inbox"].count_documents({"pdf_data": {"$exists": True}})
    
    return {
        "count": len(docs),
        "total_in_mongodb": total,
        "documents": docs
    }


@router.delete("/pulisci-duplicati")
async def pulisci_duplicati() -> Dict[str, Any]:
    """
    Rimuove i PDF duplicati basandosi sull'hash.
    """
    db = Database.get_db()
    deleted_count = 0
    
    for collection in CATEGORY_COLLECTIONS.values():
        # Trova hash duplicati
        pipeline = [
            {"$group": {
                "_id": "$pdf_hash",
                "count": {"$sum": 1},
                "ids": {"$push": "$id"}
            }},
            {"$match": {"count": {"$gt": 1}}}
        ]
        
        async for group in db[collection].aggregate(pipeline):
            # Mantieni il primo, elimina gli altri
            ids_to_delete = group["ids"][1:]
            result = await db[collection].delete_many({"id": {"$in": ids_to_delete}})
            deleted_count += result.deleted_count
    
    return {
        "success": True,
        "duplicati_rimossi": deleted_count
    }


# ============================================
# Gestione Mittenti Email
# ============================================

@router.get("/mittenti")
async def list_mittenti() -> Dict[str, Any]:
    """Lista tutti i mittenti email configurati."""
    db = Database.get_db()
    mittenti = await db["mittenti_email"].find({}, {"_id": 0}).to_list(100)
    return {"mittenti": mittenti, "count": len(mittenti)}


@router.post("/mittenti")
async def add_mittente(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Aggiunge un nuovo mittente email."""
    db = Database.get_db()
    email = payload.get("email", "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email obbligatoria")
    
    existing = await db["mittenti_email"].find_one({"email": email})
    if existing:
        raise HTTPException(status_code=409, detail="Mittente già presente")
    
    doc = {
        "email": email,
        "categoria": payload.get("categoria", "altro"),
        "attivo": True,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db["mittenti_email"].insert_one(doc)
    return {"success": True, "message": f"Mittente {email} aggiunto"}


@router.delete("/mittenti/{email}")
async def delete_mittente(email: str) -> Dict[str, Any]:
    """Rimuove un mittente email."""
    db = Database.get_db()
    result = await db["mittenti_email"].delete_one({"email": email})
    return {"success": True, "deleted": result.deleted_count}


@router.put("/mittenti/{email}")
async def update_mittente(email: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Aggiorna un mittente email (attivo/categoria)."""
    db = Database.get_db()
    update = {}
    if "attivo" in payload:
        update["attivo"] = payload["attivo"]
    if "categoria" in payload:
        update["categoria"] = payload["categoria"]
    
    result = await db["mittenti_email"].update_one({"email": email}, {"$set": update})
    return {"success": True, "modified": result.modified_count}


@router.post("/sync-email-now")
async def trigger_email_sync(background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """Trigger manuale per il sync email."""
    db = Database.get_db()
    
    async def run_sync():
        from app.services.email_monitor_service import sync_email_documents
        return await sync_email_documents(db, giorni=30)
    
    background_tasks.add_task(run_sync)
    return {"success": True, "message": "Sync email avviato in background"}

