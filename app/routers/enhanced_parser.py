"""
Router API per Enhanced Document Parser
Endpoint per parsing migliorato di F24 e Cedolini
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query
from typing import Dict, Any, Optional
import logging

from app.services.enhanced_document_parser import (
    parse_document_enhanced,
    parse_f24_enhanced,
    parse_cedolino_enhanced
)

router = APIRouter(prefix="/enhanced-parser", tags=["Enhanced Parser"])
logger = logging.getLogger(__name__)


@router.post("/f24")
async def parse_f24_document(
    file: UploadFile = File(..., description="PDF o immagine del modello F24")
) -> Dict[str, Any]:
    """
    Parse un modello F24 con estrazione completa di TUTTI i tributi.
    
    Estrae:
    - Tutti i codici tributo da ogni sezione (Erario, INPS, Regioni, IMU, INAIL)
    - Importi a debito e credito per ogni tributo
    - Totali e saldi
    - Validazione incrociata
    
    Returns:
        JSON strutturato con tutti i dati del F24
    """
    try:
        content = await file.read()
        
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="File vuoto")
        
        if len(content) > 20 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File troppo grande (max 20MB)")
        
        # Determina mime type
        mime_type = file.content_type or "application/pdf"
        if file.filename:
            if file.filename.lower().endswith(".pdf"):
                mime_type = "application/pdf"
            elif file.filename.lower().endswith((".png", ".jpg", ".jpeg")):
                mime_type = f"image/{file.filename.split('.')[-1].lower()}"
        
        result = await parse_f24_enhanced(content, mime_type)
        result["filename"] = file.filename
        result["file_size"] = len(content)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore parsing F24: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cedolino")
async def parse_cedolino_document(
    file: UploadFile = File(..., description="PDF della busta paga/cedolino")
) -> Dict[str, Any]:
    """
    Parse un cedolino/busta paga con supporto multi-formato.
    
    Formati supportati:
    - Zucchetti
    - Paghe Web
    - TeamSystem
    - ADP
    - CSC
    - Altri formati standard
    
    Estrae:
    - Dati dipendente (nome, CF, qualifica, livello)
    - Competenze e trattenute dettagliate
    - NETTO IN BUSTA (con validazione)
    - TFR e ferie/permessi
    - Costi azienda
    
    Returns:
        JSON strutturato con tutti i dati del cedolino
    """
    try:
        content = await file.read()
        
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="File vuoto")
        
        if len(content) > 20 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File troppo grande (max 20MB)")
        
        mime_type = file.content_type or "application/pdf"
        if file.filename and file.filename.lower().endswith(".pdf"):
            mime_type = "application/pdf"
        
        result = await parse_cedolino_enhanced(content, mime_type)
        result["filename"] = file.filename
        result["file_size"] = len(content)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore parsing cedolino: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/auto")
async def parse_document_auto(
    file: UploadFile = File(..., description="PDF o immagine del documento"),
    document_type: Optional[str] = Form(default="auto", description="Tipo: f24, cedolino, auto")
) -> Dict[str, Any]:
    """
    Parse automatico di documenti (F24 o Cedolini).
    
    Se document_type è "auto", il sistema tenta di rilevare automaticamente il tipo.
    
    Args:
        file: PDF o immagine del documento
        document_type: "f24", "cedolino", o "auto" per rilevamento automatico
    
    Returns:
        JSON strutturato con i dati estratti
    """
    try:
        content = await file.read()
        
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="File vuoto")
        
        mime_type = file.content_type or "application/pdf"
        if file.filename:
            if file.filename.lower().endswith(".pdf"):
                mime_type = "application/pdf"
            elif file.filename.lower().endswith((".png", ".jpg", ".jpeg")):
                mime_type = f"image/{file.filename.split('.')[-1].lower()}"
        
        result = await parse_document_enhanced(content, document_type, mime_type)
        result["filename"] = file.filename
        result["file_size"] = len(content)
        result["requested_type"] = document_type
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore parsing documento: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/info")
async def get_parser_info() -> Dict[str, Any]:
    """
    Informazioni sul parser migliorato.
    """
    return {
        "name": "Enhanced Document Parser v2",
        "version": "2.0.0",
        "description": "Parser migliorato per F24 e Cedolini con estrazione completa",
        "features": {
            "f24": [
                "Estrazione completa di TUTTI i codici tributo",
                "Supporto tutte le sezioni: Erario, INPS, Regioni, IMU, INAIL",
                "Validazione incrociata dei totali",
                "Riconoscimento codici ravvedimento"
            ],
            "cedolino": [
                "Supporto multi-formato (Zucchetti, Paghe Web, TeamSystem, ADP, CSC)",
                "Estrazione NETTO IN BUSTA con validazione",
                "Dettaglio competenze e trattenute",
                "Dati TFR, ferie, permessi"
            ]
        },
        "supported_formats": ["PDF", "PNG", "JPG", "JPEG"],
        "max_file_size": "20MB",
        "model": "Claude Sonnet 4.5"
    }
