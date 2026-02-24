"""
Buste Paga API - Upload e parsing PDF Libro Unico del Lavoro.

Permette di:
- Caricare PDF buste paga (formato Zucchetti)
- Estrarre automaticamente stipendi e presenze
- Salvare i dati nel database dipendenti
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import logging

from app.database import Database
from app.services.libro_unico_parser import parse_libro_unico_pdf, ParsingError
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/buste-paga", tags=["Buste Paga"])


@router.post("/upload")
@handle_errors
async def upload_busta_paga(
    file: UploadFile = File(...),
    competenza_month: Optional[str] = Query(None, description="Mese competenza YYYY-MM (opzionale, auto-detect)")
):
    """
    Carica e parsifica un PDF di busta paga (Libro Unico).
    
    Il sistema rileva automaticamente:
    - Mese di competenza (con confidenza alta/bassa)
    - Tipo busta paga (dipendente/amministratore/tirocinante)
    - Stipendi (netto, acconto, differenza)
    - Presenze (ore ordinarie)
    - Dati contratto (mansione, scadenza)
    
    Args:
        file: File PDF da caricare
        competenza_month: Mese competenza manuale (formato YYYY-MM), se non specificato viene auto-rilevato
    
    Returns:
        Dati estratti dal PDF
    """
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Il file deve essere un PDF")
    
    try:
        # Leggi contenuto PDF
        pdf_bytes = await file.read()
        
        if len(pdf_bytes) == 0:
            raise HTTPException(status_code=400, detail="File PDF vuoto")
        
        logger.info(f"📄 Parsing busta paga: {file.filename} ({len(pdf_bytes)} bytes)")
        
        # Parsifica PDF
        result = parse_libro_unico_pdf(pdf_bytes)
        
        # Override mese competenza se specificato manualmente
        if competenza_month:
            result['competenza_month_year'] = competenza_month
            result['competenza_detected'] = True
            result['competenza_manual'] = True
        
        # Aggiungi metadata
        result['filename'] = file.filename
        result['uploaded_at'] = datetime.now(timezone.utc).isoformat()
        result['pdf_size_bytes'] = len(pdf_bytes)
        
        return {
            "success": True,
            "message": f"Estratti {len(result.get('salaries', []))} dipendenti",
            "data": result
        }
        
    except ParsingError as e:
        logger.error(f"Parsing error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing PDF: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Errore elaborazione PDF: {str(e)}")


@router.post("/salva")
@handle_errors
async def salva_buste_paga(
    competenza_month: str,
    salaries: List[Dict[str, Any]],
    presenze: Optional[List[Dict[str, Any]]] = None
):
    """
    Salva i dati delle buste paga nel database.
    
    Args:
        competenza_month: Mese competenza (YYYY-MM)
        salaries: Lista stipendi estratti
        presenze: Lista presenze estratte (opzionale)
    """
    try:
        db = Database.get_db()
        
        # Crea record per ogni dipendente
        saved_count = 0
        for salary in salaries:
            nome = salary.get('nome', '')
            if not nome:
                continue
            
            # Trova presenze corrispondenti
            presenza = None
            if presenze:
                presenza = next((p for p in presenze if p.get('nome') == nome), None)
            
            # Documento da salvare
            doc = {
                "competenza": competenza_month,
                "nome": nome,
                "netto": salary.get('netto', 0),
                "acconto": salary.get('acconto', 0),
                "differenza": salary.get('differenza', 0),
                "note": salary.get('note', ''),
                "ore_ordinarie": presenza.get('ore_ordinarie', 0) if presenza else 0,
                "ferie": presenza.get('ferie', 0) if presenza else 0,
                "permessi": presenza.get('permessi', 0) if presenza else 0,
                "malattia": presenza.get('malattia', 0) if presenza else 0,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Upsert per evitare duplicati
            await db.buste_paga.update_one(
                {"competenza": competenza_month, "nome": nome},
                {"$set": doc},
                upsert=True
            )
            saved_count += 1
        
        return {
            "success": True,
            "message": f"Salvate {saved_count} buste paga per {competenza_month}",
            "saved_count": saved_count
        }
        
    except Exception as e:
        logger.error(f"Error saving buste paga: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/lista")
@handle_errors
async def lista_buste_paga(
    competenza: Optional[str] = None,
    nome: Optional[str] = None,
    limit: int = Query(100, le=500)
):
    """
    Ottieni lista buste paga salvate.
    
    Args:
        competenza: Filtro per mese competenza (YYYY-MM)
        nome: Filtro per nome dipendente
        limit: Limite risultati
    """
    try:
        db = Database.get_db()
        
        query = {}
        if competenza:
            query["competenza"] = competenza
        if nome:
            query["nome"] = {"$regex": nome, "$options": "i"}
        
        buste = await db.buste_paga.find(query, {"_id": 0}).sort("competenza", -1).limit(limit).to_list(length=limit)
        
        return {"buste_paga": buste, "count": len(buste)}
        
    except Exception as e:
        logger.error(f"Error fetching buste paga: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/riepilogo-mensile/{competenza}")
@handle_errors
async def riepilogo_mensile(competenza: str):
    """
    Ottieni riepilogo mensile buste paga.
    
    Args:
        competenza: Mese competenza (YYYY-MM)
    """
    try:
        db = Database.get_db()
        
        buste = await db.buste_paga.find(
            {"competenza": competenza}, 
            {"_id": 0}
        ).to_list(length=None)
        
        if not buste:
            return {
                "competenza": competenza,
                "dipendenti": 0,
                "totale_netto": 0,
                "totale_acconti": 0,
                "totale_differenza": 0,
                "totale_ore": 0,
                "buste": []
            }
        
        totale_netto = sum(b.get('netto', 0) for b in buste)
        totale_acconti = sum(b.get('acconto', 0) for b in buste)
        totale_differenza = sum(b.get('differenza', 0) for b in buste)
        totale_ore = sum(b.get('ore_ordinarie', 0) for b in buste)
        
        return {
            "competenza": competenza,
            "dipendenti": len(buste),
            "totale_netto": round(totale_netto, 2),
            "totale_acconti": round(totale_acconti, 2),
            "totale_differenza": round(totale_differenza, 2),
            "totale_ore": round(totale_ore, 2),
            "buste": buste
        }
        
    except Exception as e:
        logger.error(f"Error fetching riepilogo: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/competenze")
@handle_errors
async def lista_competenze():
    """Ottieni lista di tutti i mesi di competenza disponibili."""
    try:
        db = Database.get_db()
        competenze = await db.buste_paga.distinct("competenza")
        competenze.sort(reverse=True)
        return {"competenze": competenze}
    except Exception as e:
        logger.error(f"Error fetching competenze: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{competenza}/{nome}")
@handle_errors
async def elimina_busta_paga(competenza: str, nome: str):
    """Elimina una busta paga specifica."""
    try:
        db = Database.get_db()
        result = await db.buste_paga.delete_one({"competenza": competenza, "nome": nome})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Busta paga non trovata")
        
        return {"success": True, "message": f"Busta paga di {nome} per {competenza} eliminata"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting busta paga: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
