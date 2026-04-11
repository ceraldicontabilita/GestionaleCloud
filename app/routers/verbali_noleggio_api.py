"""
Router per Verbali Noleggio - Endpoint dettaglio e gestione completa.
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import logging

from app.database import Database
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()

COLLECTION = "verbali_noleggio"


@router.get("/dettaglio/{numero_verbale:path}")
@handle_errors
async def get_verbale_dettaglio(numero_verbale: str) -> Dict[str, Any]:
    """
    Ottiene il dettaglio completo di un verbale.
    Cerca per numero_verbale in vari formati.
    Supporta numeri con slash come S/2259.
    """
    db = Database.get_db()
    
    # Normalizza il numero verbale
    numero_clean = numero_verbale.strip()
    
    # Cerca in vari modi (incluso vecchio numero)
    verbale = await db[COLLECTION].find_one({
        "$or": [
            {"numero_verbale": numero_clean},
            {"numero_verbale": numero_clean.upper()},
            {"numero_verbale_old": numero_clean},
            {"numero_verbale_old": numero_clean.upper()},
            {"id": numero_clean},
            {"numero_verbale": {"$regex": f"^{numero_clean}$", "$options": "i"}}
        ]
    })
    
    if not verbale:
        # Prova anche nella collection completi
        verbale = await db["verbali_noleggio_completi"].find_one({
            "$or": [
                {"numero_verbale": numero_verbale},
                {"numero_verbale": numero_verbale.upper()},
                {"id": numero_verbale}
            ]
        })
    
    if not verbale:
        raise HTTPException(status_code=404, detail=f"Verbale {numero_verbale} non trovato")
    
    # Rimuovi _id per serializzazione
    verbale.pop("_id", None)
    
    # Arricchisci con dati driver se disponibile
    if verbale.get("driver_id"):
        driver = await db.employees.find_one({"id": verbale["driver_id"]})
        if driver:
            verbale["driver_dettaglio"] = {
                "nome": driver.get("nome"),
                "cognome": driver.get("cognome"),
                "codice_fiscale": driver.get("codice_fiscale")
            }
    
    # Arricchisci con dati veicolo se disponibile
    if verbale.get("targa"):
        veicolo = await db.veicoli_noleggio.find_one({"targa": verbale["targa"]})
        if veicolo:
            veicolo.pop("_id", None)
            verbale["veicolo_dettaglio"] = veicolo
    
    # Costruisci pdf_disponibili dal pdf_data se non esiste pdf_allegati
    if not verbale.get("pdf_disponibili"):
        pdf_list = []
        if verbale.get("pdf_data"):
            pdf_list.append({
                "indice": 0,
                "filename": verbale.get("pdf_filename", "verbale.pdf"),
                "tipo": "verbale",
                "size": verbale.get("pdf_size", 0)
            })
        if verbale.get("quietanza_pdf"):
            pdf_list.append({
                "indice": 1,
                "filename": verbale.get("quietanza_filename", "quietanza.pdf"),
                "tipo": "quietanza",
                "size": 0
            })
        verbale["pdf_disponibili"] = pdf_list
    
    # Cerca fattura associata (per noleggiatori come ARVAL, Leasys, ALD)
    if not verbale.get("fattura_id") and verbale.get("targa"):
        targa = verbale["targa"]
        # Cerca fatture con questa targa nella descrizione
        fattura = await db["invoices"].find_one({
            "$or": [
                {"descrizione": {"$regex": targa, "$options": "i"}},
                {"xml_raw": {"$regex": targa, "$options": "i"} if "xml_raw" in (await db["invoices"].find_one({}, {"xml_raw": 1}) or {}) else None}
            ]
        }, {"_id": 1, "id": 1, "supplier_name": 1, "invoice_number": 1, "total_amount": 1, "invoice_date": 1})
        if fattura:
            # Usa l'id UUID se disponibile, altrimenti l'ObjectId come stringa
            fid = fattura.get("id") or str(fattura.get("_id", ""))
            verbale["fattura_id"] = fid
            verbale["fattura_fornitore"] = fattura.get("supplier_name")
            verbale["fattura_numero"] = fattura.get("invoice_number")
            verbale["fattura_importo"] = fattura.get("total_amount")
    
    # Non inviare pdf_data nel response (troppo grande)
    verbale.pop("pdf_data", None)
    verbale.pop("quietanza_pdf", None)
    
    return verbale


@router.get("/lista")
@handle_errors
async def get_verbali_lista(
    anno: Optional[int] = None,
    stato: Optional[str] = None,
    driver_id: Optional[str] = None,
    skip: int = 0,
    limit: int = 100
) -> Dict[str, Any]:
    """
    Lista verbali con filtri opzionali.
    """
    db = Database.get_db()
    
    query = {}
    
    if anno:
        query["$or"] = [
            {"data": {"$regex": f"^{anno}"}},
            {"data_verbale": {"$regex": f"^{anno}"}},
            {"anno": anno}
        ]
    
    if stato:
        query["stato"] = stato
    
    if driver_id:
        query["driver_id"] = driver_id
    
    verbali = await db[COLLECTION].find(query, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
    total = await db[COLLECTION].count_documents(query)
    
    return {
        "verbali": verbali,
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.get("/pdf/{numero_verbale}")
@handle_errors
async def get_verbale_pdf(
    numero_verbale: str,
    indice: int = Query(0, description="Indice del PDF: 0=verbale, 1=quietanza")
) -> Dict[str, Any]:
    """
    Ottiene il PDF allegato a un verbale.
    Gestisce sia pdf_allegati (vecchio formato) che pdf_data/quietanza_pdf.
    """
    db = Database.get_db()
    
    verbale = await db[COLLECTION].find_one({
        "$or": [
            {"numero_verbale": numero_verbale},
            {"numero_verbale_old": numero_verbale},
            {"id": numero_verbale}
        ]
    })
    
    if not verbale:
        raise HTTPException(status_code=404, detail=f"Verbale {numero_verbale} non trovato")
    
    # Vecchio formato: pdf_allegati array
    pdf_allegati = verbale.get("pdf_allegati", [])
    if pdf_allegati and indice < len(pdf_allegati):
        pdf = pdf_allegati[indice]
        return {
            "filename": pdf.get("filename"),
            "content_base64": pdf.get("content_base64"),
            "content_type": "application/pdf"
        }
    
    # Nuovo formato: pdf_data (verbale) e quietanza_pdf
    if indice == 0 and verbale.get("pdf_data"):
        return {
            "filename": verbale.get("pdf_filename", f"verbale_{numero_verbale}.pdf"),
            "content_base64": verbale["pdf_data"],
            "content_type": "application/pdf"
        }
    
    if indice == 1 and verbale.get("quietanza_pdf"):
        return {
            "filename": verbale.get("quietanza_filename", f"quietanza_{numero_verbale}.pdf"),
            "content_base64": verbale["quietanza_pdf"],
            "content_type": "application/pdf"
        }
    
    raise HTTPException(status_code=404, detail="PDF non trovato per questo verbale")


@router.post("/scarica-posta")
@handle_errors
async def scarica_posta_verbali() -> Dict[str, Any]:
    """
    Placeholder per il download verbali da email PEC.
    In futuro integrerà con il sistema email.
    """
    return {
        "message": "Funzionalità in sviluppo",
        "status": "pending"
    }


@router.put("/{verbale_id}")
@handle_errors
async def update_verbale(verbale_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Aggiorna un verbale.
    """
    db = Database.get_db()
    
    # Rimuovi campi non modificabili
    data.pop("_id", None)
    data.pop("id", None)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    result = await db[COLLECTION].update_one(
        {"$or": [{"id": verbale_id}, {"numero_verbale": verbale_id}]},
        {"$set": data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail=f"Verbale {verbale_id} non trovato")
    
    return {"message": "Verbale aggiornato", "modified": result.modified_count}


@router.post("/associa-driver")
@handle_errors
async def associa_driver_verbale(
    verbale_id: str = Query(...),
    driver_id: str = Query(...),
    driver_nome: str = Query(None)
) -> Dict[str, Any]:
    """
    Associa manualmente un driver a un verbale.
    """
    db = Database.get_db()
    
    # Verifica che il driver esista
    driver = await db.employees.find_one({"id": driver_id})
    if not driver:
        raise HTTPException(status_code=404, detail=f"Driver {driver_id} non trovato")
    
    driver_nome_completo = driver_nome or f"{driver.get('nome', '')} {driver.get('cognome', '')}".strip()
    
    result = await db[COLLECTION].update_one(
        {"$or": [{"id": verbale_id}, {"numero_verbale": verbale_id}]},
        {"$set": {
            "driver_id": driver_id,
            "driver": driver_nome_completo,
            "associazione_manuale": True,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail=f"Verbale {verbale_id} non trovato")
    
    return {"message": "Driver associato", "driver": driver_nome_completo}


@router.get("/stats")
@handle_errors
async def get_verbali_stats() -> Dict[str, Any]:
    """
    Statistiche sui verbali.
    """
    db = Database.get_db()
    
    totale = await db[COLLECTION].count_documents({})
    
    con_driver = await db[COLLECTION].count_documents({
        "driver": {"$exists": True, "$ne": None, "$ne": ""}
    })
    
    senza_driver = totale - con_driver
    
    # Per stato
    pipeline_stato = [
        {"$group": {"_id": "$stato", "count": {"$sum": 1}}}
    ]
    stati = await db[COLLECTION].aggregate(pipeline_stato).to_list(100)
    per_stato = {s["_id"] or "unknown": s["count"] for s in stati}
    
    # Importo totale
    pipeline_importo = [
        {"$group": {"_id": None, "totale": {"$sum": {"$toDouble": {"$ifNull": ["$importo", 0]}}}}}
    ]
    importo_result = await db[COLLECTION].aggregate(pipeline_importo).to_list(1)
    importo_totale = importo_result[0]["totale"] if importo_result else 0
    
    return {
        "totale": totale,
        "con_driver": con_driver,
        "senza_driver": senza_driver,
        "per_stato": per_stato,
        "importo_totale": round(importo_totale, 2),
        "health_score": round((con_driver / totale * 100) if totale > 0 else 0, 1)
    }
