"""Analytics router - Business analytics.

LOGICA CONTABILE CORRETTA (Contabilità Italiana):
- RICAVI: dalla collezione 'corrispettivi' (vendite al pubblico, imponibile)
- COSTI: dalla collezione 'invoices' (fatture ricevute da fornitori, imponibile - NC)

Il sistema NON è multi-utente, le collezioni non hanno user_id.
"""
from fastapi import APIRouter, Depends, Query
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import calendar

import logging

from app.database import Database, Collections
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/dashboard",
    summary="Get analytics dashboard"
)
async def get_analytics_dashboard(
    current_user: Dict[str, Any] = Depends(get_current_user),
    year: Optional[int] = Query(None, description="Filter by year")
) -> Dict[str, Any]:
    """
    Get analytics dashboard data.
    
    RICAVI = Corrispettivi (totale_imponibile, al netto IVA)
    COSTI = Fatture Ricevute (imponibile, escluse note credito)
    """
    db = Database.get_db()
    
    # Date ranges
    today = datetime.now(timezone.utc)
    current_year = year or today.year
    
    # Define date range
    start_date = f"{current_year}-01-01"
    end_date = f"{current_year}-12-31"
    
    # === RICAVI (Corrispettivi - vendite al pubblico) ===
    revenue_cursor = db["corrispettivi"].aggregate([
        {"$match": {
            "data": {"$gte": start_date, "$lte": end_date}
        }},
        {"$group": {
            "_id": None, 
            "totale_imponibile": {"$sum": {"$ifNull": ["$totale_imponibile", 0]}},
            "totale_lordo": {"$sum": {"$ifNull": ["$totale", 0]}},
            "count": {"$sum": 1}
        }}
    ])
    revenue_res = await revenue_cursor.to_list(1)
    revenue = revenue_res[0]["totale_imponibile"] if revenue_res else 0.0
    revenue_lordo = revenue_res[0]["totale_lordo"] if revenue_res else 0.0
    num_corrispettivi = revenue_res[0]["count"] if revenue_res else 0
    
    # === COSTI (Fatture Ricevute - escluse NC) ===
    expenses_cursor = db[Collections.INVOICES].aggregate([
        {"$match": {
            "tipo_documento": {"$nin": ["TD04", "TD08"]},  # Escludi Note Credito
            "$or": [
                {"invoice_date": {"$gte": start_date, "$lte": end_date}},
                {"data_ricezione": {"$gte": start_date, "$lte": end_date}}
            ]
        }},
        {"$group": {
            "_id": None, 
            "totale_imponibile": {"$sum": {"$ifNull": ["$imponibile", {"$subtract": ["$total_amount", {"$ifNull": ["$iva", 0]}]}]}},
            "totale_lordo": {"$sum": "$total_amount"},
            "count": {"$sum": 1}
        }}
    ])
    expenses_res = await expenses_cursor.to_list(1)
    expenses = expenses_res[0]["totale_imponibile"] if expenses_res else 0.0
    num_fatture = expenses_res[0]["count"] if expenses_res else 0
    
    # === Note Credito (riducono i costi) ===
    nc_cursor = db[Collections.INVOICES].aggregate([
        {"$match": {
            "tipo_documento": {"$in": ["TD04", "TD08"]},
            "$or": [
                {"invoice_date": {"$gte": start_date, "$lte": end_date}},
                {"data_ricezione": {"$gte": start_date, "$lte": end_date}}
            ]
        }},
        {"$group": {
            "_id": None, 
            "totale": {"$sum": {"$ifNull": ["$imponibile", {"$subtract": ["$total_amount", {"$ifNull": ["$iva", 0]}]}]}},
            "count": {"$sum": 1}
        }}
    ])
    nc_res = await nc_cursor.to_list(1)
    note_credito = nc_res[0]["totale"] if nc_res else 0.0
    num_nc = nc_res[0]["count"] if nc_res else 0
    
    # Costi netti
    expenses_netti = expenses - note_credito
    profit = revenue - expenses_netti
    margine_pct = round((profit / revenue * 100), 1) if revenue > 0 else 0
    
    # === TREND MENSILE ===
    trend = []
    for month in range(1, 13):
        month_str = f"{current_year}-{month:02d}"
        month_label = calendar.month_abbr[month]
        
        # Ricavi mensili (corrispettivi)
        rev_agg = await db["corrispettivi"].aggregate([
            {"$match": {"data": {"$regex": f"^{month_str}"}}},
            {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$totale_imponibile", 0]}}}}
        ]).to_list(1)
        m_rev = rev_agg[0]["total"] if rev_agg else 0.0
        
        # Costi mensili (fatture - NC)
        exp_agg = await db[Collections.INVOICES].aggregate([
            {"$match": {
                "tipo_documento": {"$nin": ["TD04", "TD08"]},
                "$or": [
                    {"invoice_date": {"$regex": f"^{month_str}"}},
                    {"data_ricezione": {"$regex": f"^{month_str}"}}
                ]
            }},
            {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$imponibile", {"$subtract": ["$total_amount", {"$ifNull": ["$iva", 0]}]}]}}}}
        ]).to_list(1)
        m_exp = exp_agg[0]["total"] if exp_agg else 0.0
        
        # NC mensili
        nc_agg = await db[Collections.INVOICES].aggregate([
            {"$match": {
                "tipo_documento": {"$in": ["TD04", "TD08"]},
                "$or": [
                    {"invoice_date": {"$regex": f"^{month_str}"}},
                    {"data_ricezione": {"$regex": f"^{month_str}"}}
                ]
            }},
            {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$imponibile", {"$subtract": ["$total_amount", {"$ifNull": ["$iva", 0]}]}]}}}}
        ]).to_list(1)
        m_nc = nc_agg[0]["total"] if nc_agg else 0.0
        
        trend.append({
            "month": month_label,
            "entrate": round(m_rev, 2),
            "uscite": round(m_exp - m_nc, 2),
            "saldo": round(m_rev - (m_exp - m_nc), 2)
        })
    
    # === TOP FORNITORI ===
    match_query = {}
    if year:
        match_query["$or"] = [
            {"invoice_date": {"$regex": f"^{year}-"}},
            {"data_ricezione": {"$regex": f"^{year}-"}}
        ]
        
    top_suppliers = await db[Collections.INVOICES].aggregate([
        {"$match": match_query} if match_query else {"$match": {}},
        {"$group": {
            "_id": "$supplier_name", 
            "amount": {"$sum": {"$ifNull": ["$imponibile", {"$subtract": ["$total_amount", {"$ifNull": ["$iva", 0]}]}]}}, 
            "count": {"$sum": 1}
        }},
        {"$sort": {"amount": -1}},
        {"$limit": 5},
        {"$project": {"name": "$_id", "amount": {"$round": ["$amount", 2]}, "count": 1, "_id": 0}}
    ]).to_list(5)
    
    # === DISTRIBUZIONE PER CATEGORIA ===
    cat_dist = await db[Collections.INVOICES].aggregate([
        {"$match": match_query} if match_query else {"$match": {}},
        {"$group": {
            "_id": "$category", 
            "amount": {"$sum": {"$ifNull": ["$imponibile", {"$subtract": ["$total_amount", {"$ifNull": ["$iva", 0]}]}]}}
        }},
        {"$project": {"category": {"$ifNull": ["$_id", "Non categorizzato"]}, "amount": {"$round": ["$amount", 2]}, "_id": 0}},
        {"$sort": {"amount": -1}},
        {"$limit": 8}
    ]).to_list(8)

    return {
        "anno": current_year,
        "revenue": round(revenue, 2),
        "revenue_lordo": round(revenue_lordo, 2),
        "expenses": round(expenses_netti, 2),
        "note_credito": round(note_credito, 2),
        "profit": round(profit, 2),
        "margine_percentuale": margine_pct,
        "monthly_trend": trend,
        "top_suppliers": top_suppliers,
        "category_distribution": cat_dist,
        "statistiche": {
            "num_corrispettivi": num_corrispettivi,
            "num_fatture": num_fatture,
            "num_note_credito": num_nc
        },
        "note": "Ricavi = Corrispettivi (imponibile). Costi = Fatture ricevute - Note credito (imponibile)."
    }


@router.get(
    "/suppliers",
    summary="Get supplier analytics"
)
async def get_supplier_analytics(
    current_user: Dict[str, Any] = Depends(get_current_user),
    year: Optional[int] = Query(None, description="Filter by year")
) -> Dict[str, Any]:
    """Get supplier analytics."""
    db = Database.get_db()
    
    # Match query per anno
    match_query = {}
    if year:
        match_query["$or"] = [
            {"invoice_date": {"$regex": f"^{year}-"}},
            {"data_ricezione": {"$regex": f"^{year}-"}}
        ]
    
    # Conta fornitori unici
    unique_suppliers = await db[Collections.INVOICES].distinct("supplier_name", match_query if match_query else None)
    count = len([s for s in unique_suppliers if s])
    
    # Top fornitori
    top = await db[Collections.INVOICES].aggregate([
        {"$match": match_query} if match_query else {"$match": {}},
        {"$group": {
            "_id": "$supplier_name", 
            "total": {"$sum": {"$ifNull": ["$imponibile", {"$subtract": ["$total_amount", {"$ifNull": ["$iva", 0]}]}]}}, 
            "count": {"$sum": 1}
        }},
        {"$match": {"_id": {"$ne": None}}},
        {"$sort": {"total": -1}},
        {"$limit": 10},
        {"$project": {"name": "$_id", "total": {"$round": ["$total", 2]}, "count": 1, "_id": 0}}
    ]).to_list(10)
    
    return {
        "total_suppliers": count,
        "top_suppliers": top,
        "year": year
    }


@router.get(
    "/kpi",
    summary="Get KPI summary"
)
async def get_kpi_summary(
    current_user: Dict[str, Any] = Depends(get_current_user),
    year: Optional[int] = Query(None, description="Filter by year")
) -> Dict[str, Any]:
    """Get key performance indicators."""
    db = Database.get_db()
    
    today = datetime.now(timezone.utc)
    current_year = year or today.year
    start_date = f"{current_year}-01-01"
    end_date = f"{current_year}-12-31"
    
    # Corrispettivi (Ricavi)
    corr = await db["corrispettivi"].aggregate([
        {"$match": {"data": {"$gte": start_date, "$lte": end_date}}},
        {"$group": {
            "_id": None,
            "totale": {"$sum": {"$ifNull": ["$totale_imponibile", 0]}},
            "count": {"$sum": 1}
        }}
    ]).to_list(1)
    ricavi = corr[0]["totale"] if corr else 0
    num_corr = corr[0]["count"] if corr else 0
    
    # Fatture (Costi)
    fatt = await db[Collections.INVOICES].aggregate([
        {"$match": {
            "tipo_documento": {"$nin": ["TD04", "TD08"]},
            "$or": [
                {"invoice_date": {"$gte": start_date, "$lte": end_date}},
                {"data_ricezione": {"$gte": start_date, "$lte": end_date}}
            ]
        }},
        {"$group": {
            "_id": None,
            "totale": {"$sum": {"$ifNull": ["$imponibile", {"$subtract": ["$total_amount", {"$ifNull": ["$iva", 0]}]}]}},
            "count": {"$sum": 1}
        }}
    ]).to_list(1)
    costi = fatt[0]["totale"] if fatt else 0
    num_fatt = fatt[0]["count"] if fatt else 0
    
    # Note Credito
    nc = await db[Collections.INVOICES].aggregate([
        {"$match": {
            "tipo_documento": {"$in": ["TD04", "TD08"]},
            "$or": [
                {"invoice_date": {"$gte": start_date, "$lte": end_date}},
                {"data_ricezione": {"$gte": start_date, "$lte": end_date}}
            ]
        }},
        {"$group": {"_id": None, "totale": {"$sum": {"$ifNull": ["$imponibile", {"$subtract": ["$total_amount", {"$ifNull": ["$iva", 0]}]}]}}}}
    ]).to_list(1)
    note_credito = nc[0]["totale"] if nc else 0
    
    # Calcoli
    costi_netti = costi - note_credito
    utile = ricavi - costi_netti
    margine = round((utile / ricavi * 100), 1) if ricavi > 0 else 0
    
    # Media mensile
    mesi_passati = today.month if current_year == today.year else 12
    media_ricavi = ricavi / mesi_passati if mesi_passati > 0 else 0
    media_costi = costi_netti / mesi_passati if mesi_passati > 0 else 0
    
    return {
        "anno": current_year,
        "ricavi_totali": round(ricavi, 2),
        "costi_totali": round(costi_netti, 2),
        "utile": round(utile, 2),
        "margine_percentuale": margine,
        "media_ricavi_mensile": round(media_ricavi, 2),
        "media_costi_mensile": round(media_costi, 2),
        "num_corrispettivi": num_corr,
        "num_fatture": num_fatt,
        "mesi_analizzati": mesi_passati
    }


@router.get(
    "/self-repair",
    summary="Run self-repair diagnostics"
)
async def run_self_repair(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Run self-repair diagnostics on the database."""
    db = Database.get_db()
    risultati = {
        "status": "ok",
        "controlli": [],
        "errori": []
    }
    
    try:
        # 1. Verifica corrispettivi
        corr_count = await db["corrispettivi"].count_documents({})
        corr_no_imponibile = await db["corrispettivi"].count_documents({"totale_imponibile": {"$exists": False}})
        risultati["controlli"].append({
            "nome": "Corrispettivi",
            "totale": corr_count,
            "senza_imponibile": corr_no_imponibile,
            "status": "warning" if corr_no_imponibile > 0 else "ok"
        })
        
        # 2. Verifica fatture
        fatt_count = await db[Collections.INVOICES].count_documents({})
        fatt_no_imponibile = await db[Collections.INVOICES].count_documents({"imponibile": {"$exists": False}})
        risultati["controlli"].append({
            "nome": "Fatture",
            "totale": fatt_count,
            "senza_imponibile": fatt_no_imponibile,
            "status": "warning" if fatt_no_imponibile > fatt_count * 0.5 else "ok"
        })
        
        # 3. Verifica tipi documento
        tipi = await db[Collections.INVOICES].aggregate([
            {"$group": {"_id": "$tipo_documento", "count": {"$sum": 1}}}
        ]).to_list(20)
        risultati["controlli"].append({
            "nome": "Tipi Documento",
            "dettaglio": {t["_id"] or "null": t["count"] for t in tipi}
        })
        
    except Exception as e:
        risultati["status"] = "error"
        risultati["errori"].append(str(e))
    
    return risultati
