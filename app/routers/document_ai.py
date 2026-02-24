"""
Router per Document AI Extractor
API per estrarre dati strutturati da documenti (F24, buste paga, estratti conto)
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from typing import Optional
import base64
from datetime import datetime, timezone

from app.services.document_ai_extractor import (
    process_document,
    process_document_from_base64,
    extract_text_from_pdf,
    detect_document_type,
    PROMPTS
)
from app.database import get_database

router = APIRouter()


@router.post("/extract")
async def extract_from_file(
    file: UploadFile = File(...),
    document_type: Optional[str] = Form(None),
    model: str = Form("claude-sonnet-4-5-20250929"),
    save_to_db: bool = Form(False)
):
    """
    Estrae dati strutturati da un documento caricato.
    
    - **file**: File PDF o immagine
    - **document_type**: Tipo documento (f24, busta_paga, estratto_conto, fattura, generico). Auto-detect se non specificato.
    - **model**: Modello LLM (default: gpt-4o)
    - **save_to_db**: Se True, salva il risultato nel database
    """
    try:
        # Leggi file
        content = await file.read()
        
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="File vuoto")
        
        if len(content) > 20 * 1024 * 1024:  # 20MB max
            raise HTTPException(status_code=400, detail="File troppo grande (max 20MB)")
        
        # Processa documento
        result = await process_document(
            file_data=content,
            filename=file.filename,
            document_type=document_type,
            model=model
        )
        
        # Salva nel DB se richiesto
        if save_to_db and result.get("structured_data", {}).get("success"):
            db = await get_database()
            
            # Controllo duplicati: verifica se esiste già un documento con lo stesso filename
            existing = await db["extracted_documents"].find_one({"filename": file.filename})
            if existing:
                result["saved_to_db"] = False
                result["duplicate"] = True
                result["message"] = f"Documento '{file.filename}' già presente nel database"
                return result
            
            # Salva in extracted_documents (archivio) - include file_base64 per visualizzazione
            doc = {
                "filename": file.filename,
                "document_type": result.get("structured_data", {}).get("document_type"),
                "extracted_data": result.get("structured_data", {}).get("data"),
                "text_preview": result.get("text", "")[:1000],
                "ocr_used": result.get("ocr_used"),
                "model_used": model,
                "file_base64": base64.b64encode(content).decode('utf-8'),
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db["extracted_documents"].insert_one(doc)
            result["saved_to_db"] = True
            
            # Salva ANCHE nelle collection del gestionale
            from app.services.document_data_saver import save_extracted_data_to_gestionale
            source_info = {"filename": file.filename, "upload_type": "manual"}
            gestionale_result = await save_extracted_data_to_gestionale(
                db, result.get("structured_data", {}), source_info
            )
            result["gestionale_save"] = gestionale_result
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/extract-base64")
async def extract_from_base64(
    base64_data: str,
    filename: str,
    document_type: Optional[str] = None,
    model: str = "claude-sonnet-4-5-20250929",
    save_to_db: bool = False
):
    """
    Estrae dati strutturati da un documento in formato base64.
    Utile per processare documenti già salvati nel database.
    """
    try:
        result = await process_document_from_base64(
            base64_data=base64_data,
            filename=filename,
            document_type=document_type,
            model=model
        )
        
        if save_to_db and result.get("structured_data", {}).get("success"):
            db = await get_database()
            doc = {
                "filename": filename,
                "document_type": result.get("structured_data", {}).get("document_type"),
                "extracted_data": result.get("structured_data", {}).get("data"),
                "text_preview": result.get("text", "")[:1000],
                "ocr_used": result.get("ocr_used"),
                "model_used": model,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db["extracted_documents"].insert_one(doc)
            result["saved_to_db"] = True
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/extract-text-only")
async def extract_text_only(file: UploadFile = File(...)):
    """
    Estrae solo il testo da un PDF (senza analisi LLM).
    Utile per debug o per vedere cosa viene estratto.
    """
    try:
        content = await file.read()
        
        if not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Solo file PDF supportati")
        
        text = extract_text_from_pdf(content)
        doc_type = detect_document_type(text)
        
        return {
            "filename": file.filename,
            "text": text,
            "text_length": len(text),
            "detected_type": doc_type,
            "ocr_used": "OCR" in text
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/document-types")
async def get_document_types():
    """
    Ritorna i tipi di documento supportati e i relativi prompt.
    """
    return {
        "types": list(PROMPTS.keys()),
        "descriptions": {
            "f24": "Modello F24 - Versamenti fiscali e contributivi",
            "busta_paga": "Busta paga / Cedolino dipendente",
            "estratto_conto": "Estratto conto bancario",
            "bonifico": "Ricevuta bonifico bancario",
            "verbale": "Verbale / Multa stradale",
            "cartella_esattoriale": "Cartella esattoriale AdER",
            "delibera_inps": "Delibera / Comunicazione INPS",
            "fattura": "Fattura commerciale",
            "generico": "Documento generico (auto-detect)"
        }
    }


@router.get("/extracted-documents")
async def get_extracted_documents(
    document_type: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
    include_file: bool = False
):
    """
    Recupera i documenti estratti salvati nel database.
    
    - **include_file**: Se True, include il file_base64 (più pesante)
    """
    db = await get_database()
    
    query = {}
    if document_type:
        query["document_type"] = document_type
    
    # Definisci la proiezione - include sempre _id per poter eliminare
    projection = {
        "_id": 1,
        "filename": 1,
        "document_type": 1,
        "extracted_data": 1,
        "text_preview": 1,
        "ocr_used": 1,
        "model_used": 1,
        "created_at": 1
    }
    
    if include_file:
        projection["file_base64"] = 1
    
    cursor = db["extracted_documents"].find(query, projection).sort("created_at", -1).skip(skip).limit(limit)
    
    documents = await cursor.to_list(length=limit)
    
    # Converti ObjectId in stringa
    for doc in documents:
        if "_id" in doc:
            doc["id"] = str(doc["_id"])
            del doc["_id"]
    
    total = await db["extracted_documents"].count_documents(query)
    
    return {
        "documents": documents,
        "total": total,
        "limit": limit,
        "skip": skip
    }



@router.delete("/extracted-documents/{doc_id}")
async def delete_extracted_document(doc_id: str):
    """
    Elimina un documento estratto dal database.
    """
    from bson import ObjectId
    from bson.errors import InvalidId
    
    db = await get_database()
    
    try:
        result = await db["extracted_documents"].delete_one({"_id": ObjectId(doc_id)})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Documento non trovato")
        
        return {"success": True, "message": "Documento eliminato"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process-classified-email")
async def process_classified_email(
    email_id: str,
    model: str = "claude-sonnet-4-5-20250929"
):
    """
    Processa un documento classificato dal sistema email.
    Legge il PDF da documents_classified e estrae i dati.
    """
    db = await get_database()
    
    # Trova il documento classificato
    from bson import ObjectId
    from bson.errors import InvalidId
    try:
        doc = await db["documents_classified"].find_one({"_id": ObjectId(email_id)})
    except Exception:
        doc = await db["documents_classified"].find_one({"msg_id": email_id})
    
    if not doc:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    
    if "pdf_base64" not in doc:
        raise HTTPException(status_code=400, detail="Documento senza PDF allegato")
    
    # Determina tipo documento dalla categoria email
    category_to_type = {
        "f24": "f24",
        "buste_paga": "busta_paga",
        "estratti_conto": "estratto_conto",
        "fatture": "fattura"
    }
    doc_type = category_to_type.get(doc.get("tipo"), None)
    
    # Processa
    result = await process_document_from_base64(
        base64_data=doc["pdf_base64"],
        filename=doc.get("filename", "documento.pdf"),
        document_type=doc_type,
        model=model
    )
    
    # Aggiorna il documento classificato con i dati estratti
    if result.get("structured_data", {}).get("success"):
        await db["documents_classified"].update_one(
            {"_id": doc["_id"]},
            {
                "$set": {
                    "extracted_data": result["structured_data"]["data"],
                    "extraction_model": model,
                    "extracted_at": datetime.now(timezone.utc).isoformat(),
                    "processed": True
                }
            }
        )
        result["document_updated"] = True
    
    return result


@router.post("/process-all-classified")
async def process_all_classified_documents(
    process_all: bool = False,
    document_types: Optional[str] = None,
    save_to_gestionale: bool = True,
    model: str = "claude-sonnet-4-5-20250929"
):
    """
    Processa TUTTI i documenti classificati usando Document AI.
    Estrae dati strutturati e li salva nelle collection del gestionale.
    
    - **process_all**: Se True, riprocessa anche documenti già processati
    - **document_types**: Tipi da processare separati da virgola (es: "f24,buste_paga")
    - **save_to_gestionale**: Se True, salva i dati estratti nelle collection appropriate
    - **model**: Modello LLM da usare
    """
    from app.services.email_classifier_service import process_documents_with_ai
    
    db = await get_database()
    
    # Parse document_types se fornito
    types_list = None
    if document_types:
        types_list = [t.strip() for t in document_types.split(",")]
    
    result = await process_documents_with_ai(
        db=db,
        process_all=process_all,
        document_types=types_list,
        save_to_gestionale=save_to_gestionale,
        model=model
    )
    
    return result


@router.get("/classified-documents-stats")
async def get_classified_documents_stats():
    """
    Statistiche sui documenti classificati e il loro stato di processamento AI.
    """
    db = await get_database()
    
    # Pipeline aggregazione
    pipeline = [
        {
            "$group": {
                "_id": "$tipo",
                "totale": {"$sum": 1},
                "con_pdf": {"$sum": {"$cond": [{"$ne": ["$pdf_base64", None]}, 1, 0]}},
                "ai_processati": {"$sum": {"$cond": [{"$eq": ["$ai_processed", True]}, 1, 0]}},
                "ai_non_processati": {"$sum": {"$cond": [{"$ne": ["$ai_processed", True]}, 1, 0]}},
                "salvati_gestionale": {"$sum": {"$cond": [{"$ne": ["$ai_extracted_data", None]}, 1, 0]}}
            }
        },
        {"$sort": {"totale": -1}}
    ]
    
    stats = await db["documents_classified"].aggregate(pipeline).to_list(length=100)
    
    # Totali
    totale_docs = sum(s["totale"] for s in stats)
    totale_con_pdf = sum(s["con_pdf"] for s in stats)
    totale_processati = sum(s["ai_processati"] for s in stats)
    totale_da_processare = sum(s["ai_non_processati"] for s in stats)
    
    return {
        "totali": {
            "documenti": totale_docs,
            "con_pdf": totale_con_pdf,
            "ai_processati": totale_processati,
            "da_processare": totale_da_processare
        },
        "per_tipo": stats
    }


@router.post("/reprocess-and-save")
async def reprocess_and_save_all(
    model: str = "claude-sonnet-4-5-20250929"
):
    """
    Riprocessa TUTTI i documenti in memoria e salva i dati nelle collection del gestionale.
    Utile dopo aggiornamenti ai prompt o per riassociare i dati.
    """
    from app.services.email_classifier_service import process_documents_with_ai
    
    db = await get_database()
    
    result = await process_documents_with_ai(
        db=db,
        process_all=True,  # Riprocessa tutto
        document_types=None,  # Tutti i tipi
        save_to_gestionale=True,
        model=model
    )
    
    return result
