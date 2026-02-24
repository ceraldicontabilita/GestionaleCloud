"""
F24 Router - Modelli F24
API endpoints per gestione modelli F24
"""
from fastapi import APIRouter, Depends, Query, Path, status
from typing import List, Dict, Any, Optional
import logging

from app.database import Database, Collections
from app.repositories.vat_f24_repository import F24Repository
from app.services.vat_f24_service import F24Service
from app.models.accounting_advanced import F24Create, F24Update, F24Response
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


async def get_f24_service() -> F24Service:
    """Get F24 service with dependencies."""
    db = Database.get_db()
    f24_repo = F24Repository(db[Collections.F24_MODELS])
    return F24Service(f24_repo)


# ==================== ENDPOINT 9: Lista F24 ====================
@router.get(
    "/f24/list",
    response_model=List[F24Response],
    summary="Lista F24",
    description="Lista modelli F24 con filtri opzionali"
)
async def list_f24_models(
    month: Optional[int] = Query(None, ge=1, le=12, description="Mese"),
    year: Optional[int] = Query(None, description="Anno"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: F24Service = Depends(get_f24_service)
) -> List[Dict[str, Any]]:
    """
    Lista modelli F24.
    
    **Filtri:**
    - month: Filtra per mese riferimento
    - year: Filtra per anno riferimento
    
    Se non specificato, ritorna F24 dell'anno corrente.
    """
    f24s = await service.list_f24s(month, year)
    return f24s


# ==================== ENDPOINT 10: Crea F24 ====================
@router.post(
    "/f24",
    response_model=F24Response,
    status_code=status.HTTP_201_CREATED,
    summary="Crea F24",
    description="Crea nuovo modello F24 per pagamento tributi"
)
async def create_f24_model(
    f24: F24Create,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: F24Service = Depends(get_f24_service)
) -> Dict[str, Any]:
    """
    Crea modello F24.
    
    **Tributi supportati:**
    - 6001: IVA mensile
    - 6002: IVA trimestrale
    - inps: Contributi INPS
    - irpef: Imposta sui redditi
    - irap: Imposta attività produttive
    - imu: Imposta municipale
    
    **Esempio:**
    ```json
    {
        "reference_month": 12,
        "reference_year": 2024,
        "payment_date": "2025-01-16",
        "tributes": [
            {
                "code": "6001",
                "description": "IVA Dicembre 2024",
                "amount": 5000.00
            }
        ],
        "total_amount": 5000.00,
        "paid": false
    }
    ```
    """
    f24_data = f24.model_dump()
    result = await service.create_f24(f24_data, current_user['user_id'])
    return result


# ==================== ENDPOINT 11: Dettaglio F24 ====================
@router.get(
    "/f24/{f24_id}",
    response_model=F24Response,
    summary="Dettaglio F24",
    description="Recupera dettaglio completo di un modello F24"
)
async def get_f24_detail(
    f24_id: str = Path(..., description="ID F24"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: F24Service = Depends(get_f24_service)
) -> Dict[str, Any]:
    """
    Dettaglio modello F24.
    
    Ritorna tutte le informazioni del modello F24 inclusi:
    - Periodo di riferimento
    - Tributi dettagliati
    - Importi
    - Stato pagamento
    """
    f24 = await service.get_f24(f24_id)
    return f24


# ==================== ENDPOINT 12: Aggiorna F24 ====================
@router.put(
    "/f24/{f24_id}",
    response_model=F24Response,
    summary="Aggiorna F24",
    description="Aggiorna modello F24 esistente"
)
async def update_f24_model(
    f24_id: str = Path(..., description="ID F24"),
    f24_update: F24Update = ...,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: F24Service = Depends(get_f24_service)
) -> Dict[str, Any]:
    """
    Aggiorna modello F24.
    
    **Campi modificabili:**
    - payment_date: Data pagamento
    - paid: Stato pagamento
    - payment_reference: Riferimento pagamento
    - notes: Note
    """
    update_data = f24_update.model_dump(exclude_unset=True)
    result = await service.update_f24(f24_id, update_data)
    return result


# ==================== ENDPOINT 13: Export PDF F24 ====================
@router.get(
    "/f24/export/pdf",
    summary="Genera PDF F24",
    description="Genera modello F24 in formato PDF per pagamento"
)
async def export_f24_pdf(
    f24_id: str = Query(..., description="ID F24"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: F24Service = Depends(get_f24_service)
):
    """
    Genera PDF F24.
    
    Crea modello F24 stampabile in formato PDF
    conforme agli standard dell'Agenzia delle Entrate.
    
    **Nota:** Implementazione completa PDF disponibile prossimamente.
    Per ora ritorna informazioni per generazione manuale.
    """
    f24 = await service.get_f24(f24_id)
    
    return {
        "message": "PDF generation available soon",
        "f24_data": f24,
        "manual_filling_guide": {
            "step1": "Scarica modello F24 vuoto da agenziaentrate.gov.it",
            "step2": "Compila con i dati forniti in f24_data",
            "step3": "Usa payment_date come scadenza"
        },
        "alternative": "Use third-party F24 generation service with provided data"
    }



# ==================== ENDPOINT 14: Upload F24 PDF ====================
from fastapi import UploadFile, File
import uuid
from datetime import datetime as dt

@router.post(
    "/upload-pdf",
    summary="Carica PDF F24",
    description="Carica modello F24 in formato PDF per estrazione automatica dati"
)
async def upload_f24_pdf(
    file: UploadFile = File(..., description="File PDF F24")
):
    """
    Carica PDF F24 ed estrae automaticamente i dati.
    
    **Supporta:**
    - F24 Ordinario
    - F24 Semplificato
    - F24 contributi INPS
    
    Estrae: codice tributo, importo, periodo riferimento, scadenza
    
    Usa Document AI come prima scelta (più accurato), con fallback al parser regex.
    """
    if not file.filename.lower().endswith('.pdf'):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Solo file PDF supportati")
    
    pdf_bytes = await file.read()
    parsed = None
    metodo = "document_ai"
    
    # PRIMA SCELTA: Document AI (più accurato)
    try:
        from app.services.document_ai_extractor import extract_document_data
        
        ai_result = await extract_document_data(
            file_content=pdf_bytes,
            filename=file.filename,
            document_type="f24"
        )
        
        if ai_result.get("structured_data", {}).get("success"):
            data = ai_result["structured_data"].get("data", {})
            # Converti formato Document AI a formato legacy parser
            parsed = {
                "codice_fiscale": data.get("contribuente", {}).get("codice_fiscale"),
                "contribuente": data.get("contribuente", {}).get("denominazione"),
                "scadenza": data.get("data_versamento"),
                "tributi_erario": data.get("tributi_erario", []),
                "tributi_inps": data.get("tributi_inps", []),
                "tributi_regioni": data.get("tributi_regioni", []),
                "tributi_imu": data.get("tributi_imu", []),
                "totale_debito": data.get("totale_versato") or data.get("importo_totale"),
                "totale_credito": 0,
                "saldo_finale": data.get("totale_versato") or data.get("importo_totale"),
                "banca": data.get("banca_delegata")
            }
            logger.info(f"F24 estratto con Document AI: {parsed.get('contribuente')}")
    except Exception as e:
        logger.warning(f"Document AI fallito per {file.filename}: {e}, uso fallback regex")
        metodo = "regex_fallback"
    
    # FALLBACK: Parser regex legacy
    if not parsed:
        from app.parsers.f24_parser import parse_f24_pdf
        parsed = parse_f24_pdf(pdf_bytes)
        metodo = "regex_fallback"
    
    if "error" in parsed and parsed["error"]:
        return {
            "success": False,
            "error": parsed["error"],
            "filename": file.filename
        }
    
    # Get database
    db = Database.get_db()
    
    # Convert scadenza to ISO format
    data_scadenza = None
    if parsed.get("scadenza"):
        try:
            dt_obj = dt.strptime(parsed["scadenza"], "%d/%m/%Y")
            data_scadenza = dt_obj.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            pass
    
    # Create F24 record
    f24_id = str(uuid.uuid4())
    f24_record = {
        "id": f24_id,
        "data_scadenza": data_scadenza,
        "scadenza_display": parsed.get("scadenza"),
        "codice_fiscale": parsed.get("codice_fiscale"),
        "contribuente": parsed.get("contribuente"),
        "banca": parsed.get("banca"),
        "tributi_erario": parsed.get("tributi_erario", []),
        "tributi_inps": parsed.get("tributi_inps", []),
        "tributi_regioni": parsed.get("tributi_regioni", []),
        "tributi_imu": parsed.get("tributi_imu", []),
        "totale_debito": parsed.get("totale_debito", 0),
        "totale_credito": parsed.get("totale_credito", 0),
        "saldo_finale": parsed.get("saldo_finale", 0),
        "pagato": False,
        "filename": file.filename,
        "source": "pdf_upload",
        "created_at": dt.utcnow().isoformat()
    }
    
    # Check for duplicates
    existing = await db["f24_unificato"].find_one({
        "data_scadenza": data_scadenza,
        "codice_fiscale": parsed.get("codice_fiscale"),
        "saldo_finale": parsed.get("saldo_finale")
    })
    
    if existing:
        return {
            "success": False,
            "error": "F24 già presente nel sistema",
            "existing_id": existing.get("id"),
            "filename": file.filename
        }
    
    # Insert into database
    await db["f24_unificato"].insert_one(f24_record.copy())
    
    logger.info(f"F24 importato: {f24_id} - Scadenza {data_scadenza} - €{parsed.get('saldo_finale', 0):.2f}")
    
    return {
        "success": True,
        "id": f24_id,
        "scadenza": data_scadenza,
        "contribuente": parsed.get("contribuente"),
        "saldo_finale": parsed.get("saldo_finale"),
        "tributi": {
            "erario": len(parsed.get("tributi_erario", [])),
            "inps": len(parsed.get("tributi_inps", [])),
            "regioni": len(parsed.get("tributi_regioni", [])),
            "imu": len(parsed.get("tributi_imu", []))
        },
        "filename": file.filename
    }


# ==================== ENDPOINT 15: Lista F24 (senza autenticazione) ====================
@router.get(
    "/all",
    summary="Lista tutti F24",
    description="Lista tutti i modelli F24 senza autenticazione"
)
async def list_all_f24():
    """Lista tutti i modelli F24."""
    db = Database.get_db()
    
    f24s = await db["f24_unificato"].find({}, {"_id": 0}).sort("data_scadenza", -1).to_list(500)
    
    return {
        "f24s": f24s,
        "count": len(f24s),
        "totale_da_pagare": sum(f.get("saldo_finale", 0) for f in f24s if not f.get("pagato")),
        "totale_pagato": sum(f.get("saldo_finale", 0) for f in f24s if f.get("pagato"))
    }
