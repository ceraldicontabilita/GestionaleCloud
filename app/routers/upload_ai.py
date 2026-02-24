"""
Router per Upload Diretto con Parsing AI Automatico
Gestisce upload di F24, Cedolini e Fatture PDF con processing automatico.
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import logging

from app.database import Database
from app.services.upload_ai_processor import (
    process_upload_f24,
    process_upload_cedolino,
    process_upload_fattura_pdf,
    process_document_auto,
    COLL_FATTURE_PDF_ARCHIVIO
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/upload-f24")
async def upload_f24_con_parsing(
    file: UploadFile = File(...),
    source: str = Form(default="upload_diretto")
) -> Dict[str, Any]:
    """
    Upload di un F24 con parsing AI automatico.
    
    Il documento viene:
    1. Parsato con AI (Claude Vision)
    2. Controllato per duplicati (data + CF + importo)
    3. Salvato in f24_unificato
    
    Returns:
        Risultato con dati estratti
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nome file mancante")
    
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo file PDF supportati")
    
    try:
        content = await file.read()
        
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="File vuoto")
        
        db = Database.get_db()
        
        result = await process_upload_f24(
            db=db,
            pdf_content=content,
            filename=file.filename,
            source=source
        )
        
        if not result.get("success") and result.get("errors"):
            raise HTTPException(status_code=400, detail=result["errors"][0])
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore upload F24: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload-cedolino")
async def upload_cedolino_con_parsing(
    file: UploadFile = File(...),
    dipendente_id: Optional[str] = Form(default=None),
    source: str = Form(default="upload_diretto")
) -> Dict[str, Any]:
    """
    Upload di un cedolino/busta paga con parsing AI automatico.
    
    Il documento viene:
    1. Parsato con AI (Claude Vision)
    2. Identificato il dipendente (per CF o ID fornito)
    3. Aggiornati automaticamente i progressivi (ferie, permessi, ROL, TFR)
    4. Salvato in cedolini
    
    Args:
        file: File PDF del cedolino
        dipendente_id: ID dipendente (opzionale, se noto)
        
    Returns:
        Risultato con dati estratti e progressivi aggiornati
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nome file mancante")
    
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo file PDF supportati")
    
    try:
        content = await file.read()
        
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="File vuoto")
        
        db = Database.get_db()
        
        result = await process_upload_cedolino(
            db=db,
            pdf_content=content,
            filename=file.filename,
            dipendente_id=dipendente_id,
            source=source
        )
        
        if not result.get("success") and result.get("errors"):
            # Controllo se è errore critico o solo warning
            if "Dipendente non trovato" in result["errors"][0]:
                # È un warning, il cedolino è stato salvato
                pass
            else:
                raise HTTPException(status_code=400, detail=result["errors"][0])
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore upload cedolino: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload-fattura-pdf")
async def upload_fattura_pdf_con_parsing(
    file: UploadFile = File(...),
    source: str = Form(default="upload_diretto")
) -> Dict[str, Any]:
    """
    Upload di una fattura PDF con parsing AI automatico.
    
    Il documento viene:
    1. Parsato con AI (Claude Vision)
    2. Verificato se esiste già un XML corrispondente
    3. Se XML esiste: il PDF viene associato
    4. Se XML non esiste: il PDF viene archiviato in attesa
    
    NOTA: Le fatture PDF vengono archiviate per evitare duplicati.
    Quando arriva l'XML corrispondente, il PDF viene associato automaticamente.
    
    Returns:
        Risultato con stato (archiviato o associato a XML)
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nome file mancante")
    
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo file PDF supportati")
    
    try:
        content = await file.read()
        
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="File vuoto")
        
        db = Database.get_db()
        
        result = await process_upload_fattura_pdf(
            db=db,
            pdf_content=content,
            filename=file.filename,
            source=source
        )
        
        if not result.get("success") and result.get("errors"):
            raise HTTPException(status_code=400, detail=result["errors"][0])
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore upload fattura PDF: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload-documento")
async def upload_documento_auto(
    file: UploadFile = File(...),
    document_type: str = Form(default="auto"),
    dipendente_id: Optional[str] = Form(default=None),
    source: str = Form(default="upload_diretto")
) -> Dict[str, Any]:
    """
    Upload generico con rilevamento automatico del tipo documento.
    
    Args:
        file: File PDF
        document_type: "auto", "f24", "busta_paga", "fattura"
        dipendente_id: ID dipendente (per cedolini)
        
    Returns:
        Risultato specifico per tipo documento
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nome file mancante")
    
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo file PDF supportati")
    
    try:
        content = await file.read()
        
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="File vuoto")
        
        db = Database.get_db()
        
        result = await process_document_auto(
            db=db,
            pdf_content=content,
            filename=file.filename,
            document_type=document_type,
            source=source,
            dipendente_id=dipendente_id
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Errore upload documento: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload-batch")
async def upload_batch_documenti(
    files: List[UploadFile] = File(...),
    document_type: str = Form(default="auto"),
    source: str = Form(default="upload_batch")
) -> Dict[str, Any]:
    """
    Upload batch di documenti con processing automatico.
    
    Args:
        files: Lista di file PDF
        document_type: "auto", "f24", "busta_paga", "fattura"
        
    Returns:
        Risultati aggregati
    """
    db = Database.get_db()
    
    results = {
        "total": len(files),
        "success": 0,
        "failed": 0,
        "duplicates": 0,
        "by_type": {},
        "details": []
    }
    
    for file in files:
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            results["failed"] += 1
            results["details"].append({
                "filename": file.filename or "unknown",
                "success": False,
                "error": "File non valido (richiesto PDF)"
            })
            continue
        
        try:
            content = await file.read()
            
            result = await process_document_auto(
                db=db,
                pdf_content=content,
                filename=file.filename,
                document_type=document_type,
                source=source
            )
            
            if result.get("is_duplicate"):
                results["duplicates"] += 1
            elif result.get("success"):
                results["success"] += 1
                tipo = result.get("tipo", "altro")
                results["by_type"][tipo] = results["by_type"].get(tipo, 0) + 1
            else:
                results["failed"] += 1
            
            results["details"].append({
                "filename": file.filename,
                "success": result.get("success", False),
                "tipo": result.get("tipo"),
                "message": result.get("message"),
                "is_duplicate": result.get("is_duplicate", False),
                "errors": result.get("errors", [])
            })
            
        except Exception as e:
            results["failed"] += 1
            results["details"].append({
                "filename": file.filename,
                "success": False,
                "error": str(e)
            })
    
    return results


# === ARCHIVIO FATTURE PDF ===

@router.get("/archivio-pdf")
async def get_archivio_fatture_pdf(
    status: Optional[str] = Query(default=None, description="Filtra per stato: in_attesa_xml, associato_xml, errore_parsing"),
    limit: int = Query(default=50, le=200)
) -> Dict[str, Any]:
    """
    Ottiene le fatture PDF in archivio.
    
    Args:
        status: Filtra per stato
        limit: Numero massimo di risultati
    """
    db = Database.get_db()
    
    query = {}
    if status:
        query["status"] = status
    
    docs = await db[COLL_FATTURE_PDF_ARCHIVIO].find(
        query,
        {"_id": 0, "pdf_data": 0}  # Escludi dati pesanti
    ).sort("created_at", -1).limit(limit).to_list(limit)
    
    # Statistiche
    stats = {
        "in_attesa_xml": await db[COLL_FATTURE_PDF_ARCHIVIO].count_documents({"status": "in_attesa_xml"}),
        "associati": await db[COLL_FATTURE_PDF_ARCHIVIO].count_documents({"status": "associato_xml"}),
        "errori": await db[COLL_FATTURE_PDF_ARCHIVIO].count_documents({"status": "errore_parsing"}),
        "totale": await db[COLL_FATTURE_PDF_ARCHIVIO].count_documents({})
    }
    
    return {
        "count": len(docs),
        "stats": stats,
        "documents": docs
    }


@router.get("/archivio-pdf/{document_id}")
async def get_fattura_pdf_archivio(document_id: str) -> Dict[str, Any]:
    """
    Ottiene dettagli di una fattura PDF in archivio.
    """
    db = Database.get_db()
    
    doc = await db[COLL_FATTURE_PDF_ARCHIVIO].find_one(
        {"id": document_id},
        {"_id": 0}
    )
    
    if not doc:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    
    return doc


@router.delete("/archivio-pdf/{document_id}")
async def delete_fattura_pdf_archivio(document_id: str) -> Dict[str, Any]:
    """
    Elimina una fattura PDF dall'archivio.
    """
    db = Database.get_db()
    
    result = await db[COLL_FATTURE_PDF_ARCHIVIO].delete_one({"id": document_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    
    return {"success": True, "message": "Documento eliminato"}


@router.post("/archivio-pdf/{document_id}/associa")
async def associa_pdf_manualmente(
    document_id: str,
    invoice_id: str = Form(...)
) -> Dict[str, Any]:
    """
    Associa manualmente un PDF archiviato a una fattura XML.
    
    Args:
        document_id: ID del PDF in archivio
        invoice_id: ID della fattura XML
    """
    db = Database.get_db()
    
    # Trova PDF
    pdf_doc = await db[COLL_FATTURE_PDF_ARCHIVIO].find_one({"id": document_id})
    if not pdf_doc:
        raise HTTPException(status_code=404, detail="PDF non trovato in archivio")
    
    # Trova XML
    xml_invoice = await db["invoices"].find_one({"id": invoice_id}, {"_id": 0, "id": 1, "invoice_number": 1})
    if not xml_invoice:
        raise HTTPException(status_code=404, detail="Fattura XML non trovata")
    
    # Associa
    await db["invoices"].update_one(
        {"id": invoice_id},
        {"$set": {
            "pdf_allegato": pdf_doc.get("pdf_data"),
            "pdf_filename": pdf_doc.get("filename"),
            "pdf_associato_at": datetime.now(timezone.utc).isoformat(),
            "pdf_associazione_manuale": True
        }}
    )
    
    # Aggiorna stato archivio
    await db[COLL_FATTURE_PDF_ARCHIVIO].update_one(
        {"id": document_id},
        {"$set": {
            "status": "associato_xml",
            "xml_invoice_id": invoice_id,
            "associato_at": datetime.now(timezone.utc).isoformat(),
            "associazione_manuale": True
        }}
    )
    
    return {
        "success": True,
        "message": f"PDF associato a fattura {xml_invoice.get('invoice_number')}"
    }
