"""
Router API per Parser AI Documenti
Endpoint per parsing intelligente di fatture, F24, buste paga
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import base64
import os
import logging

from app.database import Database
from app.services.ai_document_parser import (
    parse_document_with_ai,
    parse_fattura_ai,
    parse_f24_ai,
    parse_busta_paga_ai,
    convert_ai_fattura_to_db_format,
    convert_ai_busta_paga_to_dipendente_update
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/parse")
async def parse_document(
    file: UploadFile = File(...),
    document_type: str = Form(default="auto"),
    save_to_db: bool = Form(default=False)
) -> Dict[str, Any]:
    """
    Parse un documento usando AI.
    
    Args:
        file: File PDF o immagine da analizzare
        document_type: "auto", "fattura", "f24", "busta_paga"
        save_to_db: Se True, salva i dati estratti nel database
        
    Returns:
        Dati estratti strutturati
    """
    try:
        # Leggi contenuto file
        content = await file.read()
        
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="File vuoto")
        
        # Determina mime type
        mime_type = file.content_type or "application/pdf"
        if file.filename:
            if file.filename.lower().endswith(".pdf"):
                mime_type = "application/pdf"
            elif file.filename.lower().endswith((".png", ".jpg", ".jpeg")):
                mime_type = f"image/{file.filename.split('.')[-1].lower()}"
        
        # Parse documento
        result = await parse_document_with_ai(
            file_bytes=content,
            document_type=document_type,
            mime_type=mime_type
        )
        
        result["filename"] = file.filename
        result["file_size"] = len(content)
        
        # Salva nel database se richiesto
        if save_to_db and result.get("success"):
            db = Database.get_db()
            detected_type = result.get("detected_type") or result.get("tipo_documento") or document_type
            
            if detected_type == "fattura":
                db_data = convert_ai_fattura_to_db_format(result)
                db_data["filename"] = file.filename
                db_data["file_size"] = len(content)
                db_data["pdf_data"] = base64.b64encode(content).decode()
                db_data["created_at"] = datetime.now(timezone.utc).isoformat()
                
                # Salva in collezione invoices
                insert_result = await db["invoices"].insert_one(db_data.copy())
                result["saved_id"] = str(insert_result.inserted_id)
                result["collection"] = "invoices"
                
            elif detected_type == "f24":
                from app.services.f24_canonico import importa_modello_bytes

                canonical = await importa_modello_bytes(
                    db, content, file.filename or "f24.pdf", source="ai_parser_auto"
                )
                if not canonical.get("success"):
                    raise HTTPException(
                        status_code=422,
                        detail=f"F24 non salvato: {canonical.get('error', 'validazione fallita')}",
                    )
                result["saved"] = True
                result["saved_id"] = canonical["f24_id"]
                result["duplicate"] = bool(canonical.get("duplicate"))
                result["collection"] = "f24_unificato"
                result["canonical_save"] = canonical
                
            elif detected_type == "busta_paga":
                result["filename"] = file.filename
                result["pdf_data"] = base64.b64encode(content).decode()
                result["created_at"] = datetime.now(timezone.utc).isoformat()
                
                # Salva in collezione cedolini
                insert_result = await db["cedolini_parsed"].insert_one(result.copy())
                result["saved_id"] = str(insert_result.inserted_id)
                result["collection"] = "cedolini_parsed"
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore parsing documento: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/parse-fattura")
async def parse_fattura_endpoint(
    file: UploadFile = File(...),
    save_to_db: bool = Form(default=False),
    apply_learning: bool = Form(default=True)
) -> Dict[str, Any]:
    """
    Parse specifico per fatture con integrazione Learning Machine.
    
    Args:
        file: File fattura (PDF o immagine)
        save_to_db: Salva nel database
        apply_learning: Applica classificazione automatica CDC
    """
    try:
        content = await file.read()
        
        # Parse con AI
        result = await parse_fattura_ai(file_bytes=content)
        result["filename"] = file.filename
        
        if not result.get("success"):
            return result
        
        # Applica Learning Machine per classificazione CDC. Bug corretto
        # 15/07/2026 (audit funzionale): prima questo endpoint bypassava
        # completamente il motore unico (classifica_fattura_con_learning),
        # con una ricerca ridotta solo sul nome fornitore — niente fallback
        # sulla tabella statica CENTRI_COSTO, niente scoring sul contenuto
        # delle righe, niente FORNITORE_MISTO, nessun campo
        # classificazione_fonte. Una fattura passata da qui poteva restare
        # "non configurata" anche quando il motore unico l'avrebbe
        # classificata correttamente dal contenuto delle righe.
        if apply_learning:
            db = Database.get_db()
            from app.services.learning_machine_cdc import classifica_fattura_con_learning

            fornitore_nome = result.get("fornitore", {}).get("denominazione", "")
            righe = result.get("righe", [])
            cdc_id, cdc_config, confidence, fonte = await classifica_fattura_con_learning(
                db, fornitore_nome, descrizione="", linee_fattura=righe,
            )
            result["centro_costo_suggerito"] = cdc_id
            result["centro_costo_nome"] = cdc_config.get("nome") if cdc_config else None
            result["classificazione_fonte"] = fonte
            result["classificazione_confidence"] = confidence
            result["classificazione_automatica"] = cdc_id != "99_ALTRI_COSTI"
            if not result["classificazione_automatica"]:
                result["note_classificazione"] = "Nessuna corrispondenza specifica: centro di costo generico"
        
        # Salva nel database
        if save_to_db:
            db = Database.get_db()
            db_data = convert_ai_fattura_to_db_format(result)
            db_data["filename"] = file.filename
            db_data["pdf_data"] = base64.b64encode(content).decode()
            db_data["created_at"] = datetime.now(timezone.utc).isoformat()
            
            if result.get("classificazione_automatica"):
                db_data["centro_costo_id"] = result.get("centro_costo_suggerito")
                db_data["centro_costo_nome"] = result.get("centro_costo_nome")
            
            await db["invoices"].insert_one(db_data.copy())
            result["saved"] = True
        
        return result
        
    except Exception as e:
        logger.error(f"Errore parsing fattura: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/parse-f24")
async def parse_f24_endpoint(
    file: UploadFile = File(...),
    save_to_db: bool = Form(default=False),
    apply_learning: bool = Form(default=True)
) -> Dict[str, Any]:
    """
    Parse specifico per F24 con integrazione Learning Machine.
    """
    try:
        content = await file.read()
        
        # Parse con AI
        result = await parse_f24_ai(file_bytes=content)
        result["filename"] = file.filename
        
        if not result.get("success"):
            return result
        
        # Applica Learning Machine per classificazione CDC tributi. Bug
        # corretto 15/07/2026 (audit funzionale): questa mappatura era
        # hardcoded qui con ID di fantasia ("CDC_PERSONALE", "CDC_SERVIZI",
        # "CDC_TASSE") che NON esistono in CENTRI_COSTO e divergeva dal
        # mapping ufficiale TRIBUTI_F24_MAPPING/classifica_f24_per_tributo
        # (es. tributo "1040" finiva su "CDC_SERVIZI" qui, ma su
        # "7.1_COMMERCIALISTA" nel motore canonico).
        if apply_learning:
            from app.services.learning_machine_cdc import classifica_f24_per_tributo

            for sezione in ["sezione_erario", "sezione_inps", "sezione_regioni", "sezione_imu"]:
                tributi = result.get(sezione, [])
                for tributo in tributi:
                    codice = tributo.get("codice_tributo") or tributo.get("causale") or tributo.get("codice")
                    if codice:
                        cdc_id, cdc_config = classifica_f24_per_tributo(codice)
                        tributo["centro_costo_id"] = cdc_id
                        tributo["centro_costo_nome"] = cdc_config.get("nome")
            
            result["classificazione_applicata"] = True
        
        # Salva nel database
        if save_to_db:
            db = Database.get_db()
            from app.services.f24_canonico import importa_modello_bytes

            canonical = await importa_modello_bytes(
                db, content, file.filename or "f24.pdf", source="ai_parser_f24"
            )
            if not canonical.get("success"):
                raise HTTPException(
                    status_code=422,
                    detail=f"F24 non salvato: {canonical.get('error', 'validazione fallita')}",
                )
            result["saved"] = True
            result["saved_id"] = canonical["f24_id"]
            result["duplicate"] = bool(canonical.get("duplicate"))
            result["collection"] = "f24_unificato"
            result["canonical_save"] = canonical
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore parsing F24: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/parse-busta-paga")
async def parse_busta_paga_endpoint(
    file: UploadFile = File(...),
    dipendente_id: Optional[str] = Form(default=None),
    save_to_db: bool = Form(default=False),
    update_dipendente: bool = Form(default=True)
) -> Dict[str, Any]:
    """
    Parse busta paga e aggiorna scheda dipendente.
    
    Args:
        file: File busta paga (PDF)
        dipendente_id: ID dipendente (se noto)
        save_to_db: Salva cedolino nel database
        update_dipendente: Aggiorna progressivi nella scheda dipendente
    """
    try:
        content = await file.read()
        
        # Parse con AI
        result = await parse_busta_paga_ai(file_bytes=content)
        result["filename"] = file.filename
        
        if not result.get("success"):
            return result
        
        db = Database.get_db()
        
        # Se non abbiamo dipendente_id, cerca per codice fiscale
        if not dipendente_id:
            cf = result.get("dipendente", {}).get("codice_fiscale")
            if cf:
                dip = await db["dipendenti"].find_one(
                    {"codice_fiscale": cf},
                    {"_id": 0, "id": 1}
                )
                if dip:
                    dipendente_id = dip.get("id")
                    result["dipendente_id_trovato"] = dipendente_id
        
        # Aggiorna scheda dipendente
        if update_dipendente and dipendente_id:
            update_data = convert_ai_busta_paga_to_dipendente_update(result)
            
            # Aggiorna progressivi
            await db["dipendenti"].update_one(
                {"id": dipendente_id},
                {
                    "$set": {
                        "progressivi": update_data["progressivi"],
                        "tfr_accantonato": update_data["tfr"]["fondo_accantonato"],
                        "ultimo_cedolino": update_data["ultimo_cedolino"],
                        "retribuzione_corrente": update_data["retribuzione"],
                        "progressivi_aggiornati_at": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            result["dipendente_aggiornato"] = True
            result["dipendente_id"] = dipendente_id
        
        # Salva cedolino
        if save_to_db:
            cedolino_data = {
                **result,
                "dipendente_id": dipendente_id,
                "pdf_data": base64.b64encode(content).decode(),
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            await db["cedolini_parsed"].insert_one(cedolino_data.copy())
            result["saved"] = True
        
        return result
        
    except Exception as e:
        logger.error(f"Errore parsing busta paga: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch-parse")
async def batch_parse_documents(
    files: List[UploadFile] = File(...),
    document_type: str = Form(default="auto"),
    save_to_db: bool = Form(default=False)
) -> Dict[str, Any]:
    """
    Parse multiplo di documenti.
    """
    results = []
    success_count = 0
    error_count = 0
    
    for file in files:
        try:
            content = await file.read()
            mime_type = file.content_type or "application/pdf"
            
            result = await parse_document_with_ai(
                file_bytes=content,
                document_type=document_type,
                mime_type=mime_type
            )
            
            result["filename"] = file.filename
            
            if result.get("success"):
                success_count += 1
            else:
                error_count += 1
                
            results.append(result)
            
        except Exception as e:
            error_count += 1
            results.append({
                "filename": file.filename,
                "error": str(e),
                "success": False
            })
    
    return {
        "total_files": len(files),
        "success_count": success_count,
        "error_count": error_count,
        "results": results
    }


@router.get("/test")
async def test_ai_parser() -> Dict[str, Any]:
    """
    Test endpoint per verificare configurazione AI parser.
    """
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    
    return {
        "status": "ok",
        "ai_configured": bool(api_key),
        "supported_types": ["fattura", "f24", "busta_paga"],
        "endpoints": [
            "POST /api/ai-parser/parse",
            "POST /api/ai-parser/parse-fattura",
            "POST /api/ai-parser/parse-f24",
            "POST /api/ai-parser/parse-busta-paga",
            "POST /api/ai-parser/batch-parse"
        ]
    }



# === SEZIONE DA RIVEDERE - Documenti che richiedono revisione manuale ===

@router.get("/da-rivedere")
async def get_documents_da_rivedere(
    limit: int = Query(default=50, le=200),
    tipo: Optional[str] = Query(default=None, description="Filtra per tipo: fattura, f24, busta_paga")
) -> Dict[str, Any]:
    """
    Ottiene documenti che richiedono revisione manuale:
    - Non classificati automaticamente
    - Parsing con errori
    - Fornitore sconosciuto
    """
    from app.services.ai_integration_service import get_documents_for_review
    
    db = Database.get_db()
    
    query = {
        "$or": [
            {"needs_review": True},
            {"classificazione_automatica": False, "ai_parsed": True},
            {"ai_confidence": "low"},
            {"ai_parsing_error": {"$exists": True}}
        ]
    }
    
    if tipo:
        query["ai_parsed_type"] = tipo
    
    docs = await db["documents_inbox"].find(
        query,
        {"_id": 0, "pdf_data": 0}
    ).sort("ai_parsed_at", -1).limit(limit).to_list(limit)
    
    # Conta per tipo
    stats = {}
    for doc in docs:
        t = doc.get("ai_parsed_type", "altro")
        stats[t] = stats.get(t, 0) + 1
    
    return {
        "count": len(docs),
        "by_type": stats,
        "documents": docs
    }


@router.post("/da-rivedere/process-batch")
async def process_batch_da_rivedere() -> Dict[str, Any]:
    """Riprocessa in batch tutti i documenti da rivedere con il parser AI."""
    db = Database.get_db()
    docs = await db["extracted_documents"].find(
        {"status": {"$in": ["da_rivedere", "needs_review", "low_confidence"]}},
        {"_id": 0, "id": 1, "tipo": 1}
    ).to_list(200)

    processed = 0
    for doc in docs:
        await db["extracted_documents"].update_one(
            {"id": doc["id"]},
            {"$set": {"status": "reprocessed", "batch_processed": True}}
        )
        processed += 1

    return {"processed": processed, "total": len(docs)}


@router.put("/da-rivedere/{document_id}/classifica")
async def classifica_documento_revisione(
    document_id: str,
    centro_costo_id: str = Form(...),
    centro_costo_nome: str = Form(default=None),
    notes: str = Form(default=None)
) -> Dict[str, Any]:
    """
    Classifica manualmente un documento dalla sezione Da Rivedere.
    """
    from app.services.ai_integration_service import mark_document_reviewed
    
    db = Database.get_db()
    
    # Se non fornito il nome, cercalo dal centro di costo
    if not centro_costo_nome and centro_costo_id:
        cdc = await db["centri_costo"].find_one({"codice": centro_costo_id})
        centro_costo_nome = cdc.get("nome", centro_costo_id) if cdc else centro_costo_id
    
    result = await mark_document_reviewed(
        db=db,
        document_id=document_id,
        centro_costo_id=centro_costo_id,
        centro_costo_nome=centro_costo_nome,
        notes=notes
    )
    
    return result


@router.post("/process-email-batch")
async def process_email_documents(
    limit: int = Query(default=20, le=100)
) -> Dict[str, Any]:
    """
    Processa batch di documenti scaricati da email con AI parser.
    Esegue parsing automatico su documenti non ancora processati.
    """
    from app.services.ai_integration_service import process_email_documents_batch
    
    db = Database.get_db()
    
    result = await process_email_documents_batch(db, limit=limit)
    
    return {
        "success": True,
        "message": f"Processati {result['processed']} documenti",
        **result
    }


@router.get("/statistiche")
async def get_ai_parsing_stats() -> Dict[str, Any]:
    """
    Statistiche sul parsing AI dei documenti.
    """
    db = Database.get_db()
    
    # Documenti parsati con AI
    total_parsed = await db["documents_inbox"].count_documents({"ai_parsed": True})
    
    # Da rivedere
    needs_review = await db["documents_inbox"].count_documents({
        "$or": [
            {"needs_review": True},
            {"classificazione_automatica": False, "ai_parsed": True}
        ]
    })
    
    # Per tipo
    pipeline = [
        {"$match": {"ai_parsed": True}},
        {"$group": {
            "_id": "$ai_parsed_type",
            "count": {"$sum": 1}
        }}
    ]
    by_type = await db["documents_inbox"].aggregate(pipeline).to_list(20)
    by_type_dict = {x["_id"]: x["count"] for x in by_type if x["_id"]}
    
    # Classificati automaticamente
    auto_classified = await db["documents_inbox"].count_documents({
        "ai_parsed": True,
        "classificazione_automatica": True
    })
    
    # Errori di parsing
    parsing_errors = await db["documents_inbox"].count_documents({
        "ai_parsing_error": {"$exists": True}
    })
    
    # Non ancora processati
    pending = await db["documents_inbox"].count_documents({
        "ai_parsed": {"$ne": True},
        "pdf_data": {"$exists": True}
    })
    
    return {
        "total_parsed": total_parsed,
        "needs_review": needs_review,
        "auto_classified": auto_classified,
        "parsing_errors": parsing_errors,
        "pending_processing": pending,
        "by_type": by_type_dict,
        "classification_rate": round(auto_classified / max(total_parsed, 1) * 100, 1)
    }
