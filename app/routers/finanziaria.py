"""Finanziaria router - Financial costs management."""
from fastapi import APIRouter, status, Query
from typing import Dict, Any, List, Optional
from datetime import datetime, date
from uuid import uuid4
import logging

from app.database import Database
from app.models.stati import STATI_PAGATI
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/summary", summary="Get financial summary")
@handle_errors
async def get_financial_summary(
    anno: Optional[int] = Query(None, description="Anno di riferimento")
) -> Dict[str, Any]:
    """Get financial summary from Prima Nota, Corrispettivi e Fatture."""
    db = Database.get_db()
    
    # Se anno non specificato, usa anno corrente
    if not anno:
        anno = date.today().year
    
    # Filtro data per anno - usa range invece di regex
    start_date = f"{anno}-01-01"
    end_date = f"{anno}-12-31"
    date_range = {"$gte": start_date, "$lte": end_date}
    
    try:
        # Get Prima Nota Cassa totals
        cassa_pipeline = [
            {"$match": {"data": date_range}},
            {"$group": {
                "_id": "$tipo",
                "total": {"$sum": "$importo"}
            }}
        ]
        cassa_result = await db["prima_nota_cassa"].aggregate(cassa_pipeline).to_list(100)
        cassa_entrate = sum(r["total"] for r in cassa_result if r["_id"] == "entrata")
        cassa_uscite = sum(r["total"] for r in cassa_result if r["_id"] == "uscita")
        
        # Get Prima Nota Banca totals
        banca_pipeline = [
            {"$match": {"data": date_range}},
            {"$group": {
                "_id": "$tipo",
                "total": {"$sum": "$importo"}
            }}
        ]
        banca_result = await db["prima_nota_banca"].aggregate(banca_pipeline).to_list(100)
        banca_entrate = sum(r["total"] for r in banca_result if r["_id"] == "entrata")
        banca_uscite = sum(r["total"] for r in banca_result if r["_id"] == "uscita")
        
        # Get Salari totals
        salari_pipeline = [
            {"$match": {"data": date_range}},
            {"$group": {
                "_id": None,
                "total": {"$sum": "$importo"}
            }}
        ]
        salari_result = await db["prima_nota_salari"].aggregate(salari_pipeline).to_list(1)
        salari_totale = salari_result[0]["total"] if salari_result else 0
        
        # ============ IVA DAI CORRISPETTIVI (DEBITO) ============
        corr_pipeline = [
            {"$match": {"data": date_range}},
            {"$group": {
                "_id": None,
                "totale_iva": {"$sum": "$totale_iva"},
                "totale_incassi": {"$sum": "$totale"},
                "count": {"$sum": 1}
            }}
        ]
        corr_result = await db["corrispettivi"].aggregate(corr_pipeline).to_list(1)
        iva_debito = float(corr_result[0].get("totale_iva", 0) or 0) if corr_result else 0
        totale_corrispettivi = float(corr_result[0].get("totale_incassi", 0) or 0) if corr_result else 0
        corr_count = corr_result[0].get("count", 0) if corr_result else 0
        
        # ============ IVA DALLE FATTURE (CREDITO) ============
        # Tipi documento Note Credito da SOTTRARRE
        NOTE_CREDITO_TYPES = ["TD04", "TD08"]
        
        # Fatture normali (escludendo Note Credito) - usa data_ricezione con fallback
        fatt_pipeline = [
            {"$match": {
                "$or": [
                    {"data_ricezione": date_range},
                    {"$and": [{"data_ricezione": {"$exists": False}}, {"invoice_date": date_range}]}
                ],
                "tipo_documento": {"$nin": NOTE_CREDITO_TYPES}
            }},
            {"$group": {
                "_id": None,
                "total_iva": {"$sum": "$iva"},
                "total_amount": {"$sum": "$total_amount"},
                "count": {"$sum": 1}
            }}
        ]
        fatt_result = await db["invoices"].aggregate(fatt_pipeline).to_list(1)
        
        if fatt_result:
            iva_credito = float(fatt_result[0].get("total_iva", 0) or 0)
            tot_fatture = float(fatt_result[0].get("total_amount", 0) or 0)
            fatt_count = fatt_result[0].get("count", 0)
        else:
            iva_credito, tot_fatture, fatt_count = 0, 0, 0
        
        # Note Credito (da sottrarre dal totale IVA credito)
        nc_pipeline = [
            {"$match": {
                "$or": [
                    {"data_ricezione": date_range},
                    {"$and": [{"data_ricezione": {"$exists": False}}, {"invoice_date": date_range}]}
                ],
                "tipo_documento": {"$in": NOTE_CREDITO_TYPES}
            }},
            {"$group": {
                "_id": None,
                "total_iva": {"$sum": "$iva"},
                "total_amount": {"$sum": "$total_amount"},
                "count": {"$sum": 1}
            }}
        ]
        nc_result = await db["invoices"].aggregate(nc_pipeline).to_list(1)
        
        if nc_result:
            iva_note_credito = float(nc_result[0].get("total_iva", 0) or 0)
        else:
            iva_note_credito = 0
        
        # IVA Credito Netta = Fatture - Note Credito (stessa logica di iva_calcolo.py)
        iva_credito = iva_credito - iva_note_credito
        
        # ============ FATTURE DA PAGARE (non pagate) ============
        fatture_da_pagare = await db["invoices"].aggregate([
            {"$match": {
                "invoice_date": date_range,
                "status": {"$nin": STATI_PAGATI}
            }},
            {"$group": {"_id": None, "total": {"$sum": "$total_amount"}}}
        ]).to_list(1)
        payables = float(fatture_da_pagare[0]["total"]) if fatture_da_pagare else 0
        
        # ============ CALCOLO TOTALI (evitando doppie contabilizzazioni) ============
        # I salari sono GIÀ inclusi nelle uscite banca (sono partite di giro)
        # Quindi NON li sommiamo di nuovo
        # 
        # Logica corretta:
        # - Entrate totali = Entrate Cassa + Entrate Banca (no duplicazioni)
        # - Uscite totali = Uscite Cassa + Uscite Banca (salari già inclusi in banca)
        #
        # Nota: I versamenti da Cassa a Banca sono partite di giro interne
        # e non modificano il totale complessivo
        
        total_income = cassa_entrate + banca_entrate
        # NON sommare salari perché sono già in banca_uscite
        total_expenses = cassa_uscite + banca_uscite
        saldo_iva = iva_debito - iva_credito
        
        return {
            "anno": anno,
            "total_income": round(total_income, 2),
            "total_expenses": round(total_expenses, 2),
            "balance": round(total_income - total_expenses, 2),
            "cassa": {
                "entrate": round(cassa_entrate, 2),
                "uscite": round(cassa_uscite, 2),
                "saldo": round(cassa_entrate - cassa_uscite, 2)
            },
            "banca": {
                "entrate": round(banca_entrate, 2),
                "uscite": round(banca_uscite, 2),  # Include già salari e F24
                "saldo": round(banca_entrate - banca_uscite, 2)
            },
            "salari": {
                "totale": round(salari_totale, 2),
                "nota": "Già inclusi in uscite Banca"
            },
            # IVA Section
            "vat_debit": round(iva_debito, 2),
            "vat_credit": round(iva_credito, 2),
            "vat_balance": round(saldo_iva, 2),
            "vat_status": "Da versare" if saldo_iva > 0 else "A credito",
            # Corrispettivi (incassi giornalieri)
            "corrispettivi": {
                "totale": round(totale_corrispettivi, 2),
                "count": corr_count,
                "iva": round(iva_debito, 2)
            },
            # Fatture (acquisti)
            "fatture": {
                "totale": round(tot_fatture, 2),
                "count": fatt_count,
                "iva": round(iva_credito, 2)
            },
            # Campi H1 richiesti dalla specifica
            "saldo_cassa": round(cassa_entrate - cassa_uscite, 2),
            "saldo_banca": round(banca_entrate - banca_uscite, 2),
            "saldo_totale": round((cassa_entrate - cassa_uscite) + (banca_entrate - banca_uscite), 2),
            # Payables/Receivables
            "payables": round(payables, 2),
            "receivables": 0  # Non gestiamo fatture attive per ora
        }
    except Exception as e:
        logger.error(f"Errore financial summary: {e}")
        # Ritorna dati parziali in caso di errore
        return {
            "anno": anno,
            "total_income": 0,
            "total_expenses": 0,
            "balance": 0,
            "error": str(e)
        }


@router.get(
    "/costi",
    summary="Get financial costs"
)
async def get_costi() -> Dict[str, List[Dict[str, Any]]]:
    """Get list of financial costs."""
    db = Database.get_db()
    costi = await db["costi_finanziari"].find({}, {"_id": 0}).sort("data", -1).to_list(500)
    return {"costi": costi}


@router.get(
    "/cost-categories",
    summary="Get cost categories"
)
async def get_cost_categories() -> Dict[str, List[Dict[str, str]]]:
    """Get cost categories."""
    categories = [
        {"key": "personale", "label": "Personale"},
        {"key": "utenze", "label": "Utenze"},
        {"key": "affitto", "label": "Affitto"},
        {"key": "manutenzione", "label": "Manutenzione"},
        {"key": "materie_prime", "label": "Materie Prime"},
        {"key": "marketing", "label": "Marketing"},
        {"key": "consulenze", "label": "Consulenze"},
        {"key": "imposte", "label": "Imposte & Tasse"},
        {"key": "altro", "label": "Altro"},
        {"key": "da_classificare", "label": "Da Classificare"}
    ]
    return {"categories": categories}


@router.post(
    "/costo",
    status_code=status.HTTP_201_CREATED,
    summary="Create financial cost"
)
async def create_costo(
    data: Dict[str, Any]
) -> Dict[str, str]:
    """Create a financial cost entry."""
    db = Database.get_db()
    data["id"] = str(uuid4())
    data["created_at"] = datetime.now(timezone.utc)
    
    await db["costi_finanziari"].insert_one(data.copy())
    
    return {"message": "Cost created", "id": data["id"]}
