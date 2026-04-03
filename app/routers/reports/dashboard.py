"""Dashboard router - KPI and statistics endpoints."""
from fastapi import APIRouter, Depends, Query
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import logging

from app.database import Database, Collections
from app.utils.dependencies import get_optional_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/summary",
    summary="Get dashboard summary",
    description="Get summary data for dashboard - no auth required"
)
async def get_summary(
    anno: int = Query(None, description="Anno di riferimento")
) -> Dict[str, Any]:
    """Get summary data for dashboard - public endpoint. OTTIMIZZATO con cache."""
    from app.middleware.performance import cache
    
    db = Database.get_db()
    
    if not anno:
        anno = datetime.now().year
    
    # Prova cache
    cache_key = f"dashboard_summary_{anno}"
    cached = await cache.get(cache_key)
    if cached:
        return cached
    
    data_inizio = f"{anno}-01-01"
    data_fine = f"{anno}-12-31"
    
    try:
        # Get counts in parallelo per velocità
        invoices_filter = {
            "$or": [
                {"invoice_date": {"$gte": data_inizio, "$lte": data_fine}},
                {"data": {"$gte": data_inizio, "$lte": data_fine}}
            ]
        }
        
        # Esegui tutte le query in parallelo
        import asyncio
        
        async def get_invoices_count():
            return await db[Collections.INVOICES].count_documents(invoices_filter)
        
        async def get_invoices_amount():
            pipeline = [
                {"$match": invoices_filter},
                {"$group": {"_id": None, "total": {"$sum": "$total_amount"}}}
            ]
            result = await db[Collections.INVOICES].aggregate(pipeline).to_list(1)
            return result[0]["total"] if result else 0
        
        async def get_suppliers_count():
            return await db[Collections.SUPPLIERS].count_documents({})
        
        async def get_products_count():
            return await db[Collections.WAREHOUSE_PRODUCTS].count_documents({})
        
        async def get_haccp_count():
            return await db[Collections.HACCP_TEMPERATURES].count_documents({})
        
        async def get_employees_count():
            return await db[Collections.EMPLOYEES].count_documents({})
        
        # Esegui in parallelo
        async def get_reconciled_count():
            return await db["estratto_conto_movimenti"].count_documents({
                "riconciliato": True,
                "$or": [
                    {"data": {"$gte": data_inizio, "$lte": data_fine}},
                    {"data_operazione": {"$gte": data_inizio, "$lte": data_fine}}
                ]
            })

        results = await asyncio.gather(
            get_invoices_count(),
            get_invoices_amount(),
            get_suppliers_count(),
            get_products_count(),
            get_haccp_count(),
            get_employees_count(),
            get_reconciled_count()
        )

        response = {
            "anno": anno,
            "invoices_total": results[0],
            "invoices_amount": round(results[1] or 0, 2),
            "reconciled": results[6],
            "products": results[3],
            "haccp_items": results[4],
            "suppliers": results[2],
            "employees": results[5]
        }
        
        # Salva in cache per 60 secondi
        await cache.set(cache_key, response, 60)
        
        return response
        
    except Exception as e:
        logger.error(f"Error getting dashboard summary: {e}")
        return {
            "anno": anno,
            "invoices_total": 0,
            "invoices_amount": 0,
            "reconciled": 0,
            "products": 0,
            "haccp_items": 0,
            "suppliers": 0,
            "employees": 0
        }


@router.get(
    "/kpi",
    summary="Get dashboard KPIs",
    description="Get key performance indicators for dashboard"
)
async def get_kpi(
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user)
) -> Dict[str, Any]:
    """Get KPI data for dashboard."""
    db = Database.get_db()
    
    try:
        # Get counts
        invoices_count = await db[Collections.INVOICES].count_documents({})
        suppliers_count = await db[Collections.SUPPLIERS].count_documents({})
        
        # Calculate totals
        pipeline = [
            {"$group": {"_id": None, "total": {"$sum": "$total_amount"}}}
        ]
        result = await db[Collections.INVOICES].aggregate(pipeline).to_list(1)
        total_invoices = result[0]["total"] if result else 0
        
        return {
            "invoices_count": invoices_count,
            "suppliers_count": suppliers_count,
            "total_invoices_amount": total_invoices,
            "pending_payments": 0,
            "monthly_revenue": 0,
            "monthly_expenses": total_invoices
        }
    except Exception as e:
        logger.error(f"Error getting KPIs: {e}")
        return {
            "invoices_count": 0,
            "suppliers_count": 0,
            "total_invoices_amount": 0,
            "pending_payments": 0,
            "monthly_revenue": 0,
            "monthly_expenses": 0
        }


@router.get(
    "/stats",
    summary="Get dashboard statistics",
    description="Get detailed statistics for dashboard"
)
async def get_stats(
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user)
) -> Dict[str, Any]:
    """Get statistics for dashboard."""
    db = Database.get_db()
    
    try:
        # Monthly stats
        now = datetime.now(timezone.utc)
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        monthly_invoices = await db[Collections.INVOICES].count_documents({
            "created_at": {"$gte": start_of_month}
        })
        
        return {
            "monthly_invoices": monthly_invoices,
            "monthly_suppliers": 0,
            "overdue_invoices": 0,
            "pending_reconciliations": 0,
            "chart_data": {
                "labels": [],
                "values": []
            }
        }
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return {
            "monthly_invoices": 0,
            "monthly_suppliers": 0,
            "overdue_invoices": 0,
            "pending_reconciliations": 0,
            "chart_data": {
                "labels": [],
                "values": []
            }
        }



@router.get(
    "/trend-mensile",
    summary="Trend mensile entrate/uscite",
    description="Dati per grafici trend mensili - OTTIMIZZATO"
)
async def get_trend_mensile(
    anno: int = Query(None, description="Anno di riferimento")
) -> Dict[str, Any]:
    """
    Ottiene i dati per i grafici di trend mensile.
    Include entrate (corrispettivi), uscite (fatture) e saldo mensile.
    VERSIONE OTTIMIZZATA: usa 4 query aggregate invece di 48.
    """
    db = Database.get_db()
    
    if not anno:
        anno = datetime.now().year
    
    mesi_nomi = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]
    data_inizio_anno = f"{anno}-01-01"
    data_fine_anno = f"{anno}-12-31"
    
    # Inizializza dati per tutti i mesi
    trend_data = {m: {"mese": m, "mese_nome": mesi_nomi[m-1], "entrate": 0, "uscite": 0, "iva_debito": 0, "iva_credito": 0} for m in range(1, 13)}
    
    # QUERY 1: Corrispettivi (entrate + IVA debito) raggruppati per mese
    try:
        corr_pipeline = [
            {"$match": {"data": {"$gte": data_inizio_anno, "$lte": data_fine_anno}}},
            {"$addFields": {
                "mese": {"$toInt": {"$substr": ["$data", 5, 2]}}
            }},
            {"$group": {
                "_id": "$mese",
                "totale": {"$sum": {"$toDouble": {"$ifNull": ["$totale", 0]}}},
                "totale_iva": {"$sum": {"$toDouble": {"$ifNull": ["$totale_iva", 0]}}}
            }}
        ]
        corr_results = await db["corrispettivi"].aggregate(corr_pipeline).to_list(12)
        for r in corr_results:
            mese = r["_id"]
            if mese and 1 <= mese <= 12:
                trend_data[mese]["entrate"] = round(r["totale"] or 0, 2)
                trend_data[mese]["iva_debito"] = round(r["totale_iva"] or 0, 2)
    except Exception as e:
        logger.warning(f"Errore aggregazione corrispettivi: {e}")
    
    # QUERY 2: Fatture (uscite + IVA credito) raggruppate per mese
    try:
        fatt_pipeline = [
            {"$match": {
                "$or": [
                    {"invoice_date": {"$gte": data_inizio_anno, "$lte": data_fine_anno}},
                    {"data_ricezione": {"$gte": data_inizio_anno, "$lte": data_fine_anno}}
                ]
            }},
            {"$addFields": {
                "data_ref": {"$ifNull": ["$data_ricezione", "$invoice_date"]},
            }},
            {"$addFields": {
                "mese": {"$toInt": {"$substr": ["$data_ref", 5, 2]}}
            }},
            {"$group": {
                "_id": "$mese",
                "totale": {"$sum": {"$toDouble": {"$ifNull": ["$total_amount", 0]}}},
                "totale_iva": {"$sum": {"$toDouble": {"$ifNull": ["$iva", 0]}}}
            }}
        ]
        fatt_results = await db[Collections.INVOICES].aggregate(fatt_pipeline).to_list(12)
        for r in fatt_results:
            mese = r["_id"]
            if mese and 1 <= mese <= 12:
                trend_data[mese]["uscite"] = round(r["totale"] or 0, 2)
                trend_data[mese]["iva_credito"] = round(r["totale_iva"] or 0, 2)
    except Exception as e:
        logger.warning(f"Errore aggregazione fatture: {e}")
    
    # Converti in lista ordinata e calcola saldi
    result_data = []
    for mese in range(1, 13):
        m = trend_data[mese]
        m["saldo"] = round(m["entrate"] - m["uscite"], 2)
        m["saldo_iva"] = round(m["iva_debito"] - m["iva_credito"], 2)
        result_data.append(m)
    
    # Calcola totali annuali
    totale_entrate = sum(t["entrate"] for t in result_data)
    totale_uscite = sum(t["uscite"] for t in result_data)
    totale_iva_debito = sum(t["iva_debito"] for t in result_data)
    totale_iva_credito = sum(t["iva_credito"] for t in result_data)
    
    # Calcola media e picchi
    mesi_con_dati = [t for t in result_data if t["entrate"] > 0 or t["uscite"] > 0]
    media_entrate = totale_entrate / len(mesi_con_dati) if mesi_con_dati else 0
    media_uscite = totale_uscite / len(mesi_con_dati) if mesi_con_dati else 0
    
    mese_max_entrate = max(result_data, key=lambda x: x["entrate"])
    mese_max_uscite = max(result_data, key=lambda x: x["uscite"])
    
    return {
        "anno": anno,
        "trend_mensile": result_data,
        "totali": {
            "entrate": round(totale_entrate, 2),
            "uscite": round(totale_uscite, 2),
            "saldo": round(totale_entrate - totale_uscite, 2),
            "iva_debito": round(totale_iva_debito, 2),
            "iva_credito": round(totale_iva_credito, 2),
            "saldo_iva": round(totale_iva_debito - totale_iva_credito, 2)
        },
        "statistiche": {
            "media_entrate_mensile": round(media_entrate, 2),
            "media_uscite_mensile": round(media_uscite, 2),
            "mese_picco_entrate": mese_max_entrate["mese_nome"],
            "mese_picco_uscite": mese_max_uscite["mese_nome"],
            "mesi_con_dati": len(mesi_con_dati)
        },
        "chart_data": {
            "labels": [t["mese_nome"] for t in result_data],
            "entrate": [t["entrate"] for t in result_data],
            "uscite": [t["uscite"] for t in result_data],
            "saldo": [t["saldo"] for t in result_data]
        }
    }


@router.get(
    "/spese-per-categoria",
    summary="Spese per categoria",
    description="Distribuzione spese per categoria (per grafico a torta)"
)
async def get_spese_per_categoria(
    anno: int = Query(None, description="Anno di riferimento")
) -> Dict[str, Any]:
    """
    Ottiene la distribuzione delle spese per categoria.
    Usa i dati dell'estratto conto per categorie accurate.
    """
    db = Database.get_db()
    
    if not anno:
        anno = datetime.now().year
    
    # Query estratto conto per categorie
    pipeline = [
        {"$match": {
            "data": {"$regex": f"^{anno}"},
            "tipo": "uscita"  # Solo uscite
        }},
        {"$group": {
            "_id": "$categoria",
            "totale": {"$sum": {"$abs": "$importo"}},
            "count": {"$sum": 1}
        }},
        {"$sort": {"totale": -1}},
        {"$limit": 10}
    ]
    
    risultati = await db["estratto_conto_movimenti"].aggregate(pipeline).to_list(10)
    
    # Se non ci sono dati nell'estratto conto, prova con le fatture
    if not risultati:
        # Raggruppa per fornitore come proxy per categoria
        pipeline_fatture = [
            {"$match": {
                "$or": [
                    {"invoice_date": {"$regex": f"^{anno}"}},
                    {"data_ricezione": {"$regex": f"^{anno}"}}
                ]
            }},
            {"$group": {
                "_id": "$supplier_name",
                "totale": {"$sum": "$total_amount"},
                "count": {"$sum": 1}
            }},
            {"$sort": {"totale": -1}},
            {"$limit": 10}
        ]
        risultati = await db[Collections.INVOICES].aggregate(pipeline_fatture).to_list(10)
    
    # Formatta per il grafico
    categorie = []
    totale_spese = 0
    
    for r in risultati:
        cat_nome = r["_id"] or "Non categorizzato"
        if len(cat_nome) > 25:
            cat_nome = cat_nome[:22] + "..."
        
        categorie.append({
            "nome": cat_nome,
            "valore": round(r["totale"], 2),
            "count": r["count"]
        })
        totale_spese += r["totale"]
    
    # Calcola percentuali
    for c in categorie:
        c["percentuale"] = round((c["valore"] / totale_spese * 100) if totale_spese > 0 else 0, 1)
    
    return {
        "anno": anno,
        "categorie": categorie,
        "totale_spese": round(totale_spese, 2),
        "numero_categorie": len(categorie)
    }


@router.get(
    "/confronto-annuale",
    summary="Confronto con anno precedente",
    description="Confronta i dati dell'anno con l'anno precedente"
)
async def get_confronto_annuale(
    anno: int = Query(None, description="Anno di riferimento")
) -> Dict[str, Any]:
    """
    Confronta le metriche chiave tra anno corrente e precedente.
    """
    db = Database.get_db()
    
    if not anno:
        anno = datetime.now().year
    
    anno_prec = anno - 1
    
    async def get_totali_anno(a: int) -> Dict:
        # Entrate (corrispettivi)
        entrate_res = await db["corrispettivi"].aggregate([
            {"$match": {"data": {"$regex": f"^{a}"}}},
            {"$group": {"_id": None, "totale": {"$sum": "$totale"}}}
        ]).to_list(1)
        entrate = entrate_res[0]["totale"] if entrate_res else 0
        
        # Uscite (fatture)
        uscite_res = await db[Collections.INVOICES].aggregate([
            {"$match": {
                "$or": [
                    {"data_ricezione": {"$regex": f"^{a}"}},
                    {"invoice_date": {"$regex": f"^{a}"}}
                ]
            }},
            {"$group": {"_id": None, "totale": {"$sum": "$total_amount"}}}
        ]).to_list(1)
        uscite = uscite_res[0]["totale"] if uscite_res else 0
        
        # Numero fatture
        num_fatture = await db[Collections.INVOICES].count_documents({
            "$or": [
                {"data_ricezione": {"$regex": f"^{a}"}},
                {"invoice_date": {"$regex": f"^{a}"}}
            ]
        })
        
        return {
            "anno": a,
            "entrate": round(entrate, 2),
            "uscite": round(uscite, 2),
            "saldo": round(entrate - uscite, 2),
            "num_fatture": num_fatture
        }
    
    corrente = await get_totali_anno(anno)
    precedente = await get_totali_anno(anno_prec)
    
    # Calcola variazioni percentuali
    def calc_variazione(nuovo, vecchio):
        if vecchio == 0:
            return 100 if nuovo > 0 else 0
        return round((nuovo - vecchio) / abs(vecchio) * 100, 1)
    
    variazioni = {
        "entrate": calc_variazione(corrente["entrate"], precedente["entrate"]),
        "uscite": calc_variazione(corrente["uscite"], precedente["uscite"]),
        "saldo": calc_variazione(corrente["saldo"], precedente["saldo"]) if precedente["saldo"] != 0 else 0,
        "num_fatture": calc_variazione(corrente["num_fatture"], precedente["num_fatture"])
    }
    
    return {
        "anno_corrente": corrente,
        "anno_precedente": precedente,
        "variazioni_percentuali": variazioni
    }


@router.get(
    "/stato-riconciliazione",
    summary="Stato riconciliazione",
    description="Statistiche sullo stato della riconciliazione"
)
async def get_stato_riconciliazione(
    anno: int = Query(None, description="Anno di riferimento")
) -> Dict[str, Any]:
    """
    Ottiene statistiche dettagliate sullo stato della riconciliazione.
    """
    db = Database.get_db()
    
    if not anno:
        anno = datetime.now().year
    
    # Fatture fornitori
    fatture_totali = await db[Collections.INVOICES].count_documents({
        "$or": [
            {"data_ricezione": {"$regex": f"^{anno}"}},
            {"invoice_date": {"$regex": f"^{anno}"}}
        ]
    })
    
    fatture_pagate = await db[Collections.INVOICES].count_documents({
        "$or": [
            {"data_ricezione": {"$regex": f"^{anno}"}},
            {"invoice_date": {"$regex": f"^{anno}"}}
        ],
        "pagato": True
    })
    
    # Importi fatture
    importi_pipeline = [
        {"$match": {
            "$or": [
                {"data_ricezione": {"$regex": f"^{anno}"}},
                {"invoice_date": {"$regex": f"^{anno}"}}
            ]
        }},
        {"$group": {
            "_id": "$pagato",
            "totale": {"$sum": "$total_amount"}
        }}
    ]
    importi_res = await db[Collections.INVOICES].aggregate(importi_pipeline).to_list(10)
    
    importo_pagato = sum(r["totale"] for r in importi_res if r["_id"] == True)
    importo_da_pagare = sum(r["totale"] for r in importi_res if r["_id"] != True)
    
    # Salari
    salari_totali = await db["prima_nota_salari"].count_documents({
        "anno": anno
    })
    
    salari_riconciliati = await db["prima_nota_salari"].count_documents({
        "anno": anno,
        "riconciliato": True
    })
    
    # Percentuali
    perc_fatture = round((fatture_pagate / fatture_totali * 100) if fatture_totali > 0 else 0, 1)
    perc_salari = round((salari_riconciliati / salari_totali * 100) if salari_totali > 0 else 0, 1)
    
    return {
        "anno": anno,
        "fatture": {
            "totali": fatture_totali,
            "pagate": fatture_pagate,
            "da_pagare": fatture_totali - fatture_pagate,
            "percentuale_pagate": perc_fatture,
            "importo_pagato": round(importo_pagato, 2),
            "importo_da_pagare": round(importo_da_pagare, 2)
        },
        "salari": {
            "totali": salari_totali,
            "riconciliati": salari_riconciliati,
            "da_riconciliare": salari_totali - salari_riconciliati,
            "percentuale_riconciliati": perc_salari
        },
        "riepilogo": {
            "percentuale_globale": round((perc_fatture + perc_salari) / 2, 1) if (fatture_totali > 0 or salari_totali > 0) else 0
        }
    }


@router.get(
    "/bilancio-istantaneo",
    summary="Bilancio Istantaneo",
    description="Calcolo rapido di Ricavi, Costi, IVA e Utile Lordo dall'analisi delle fatture XML"
)
async def get_bilancio_istantaneo(
    anno: int = Query(None, description="Anno di riferimento")
) -> Dict[str, Any]:
    """
    Calcola il bilancio istantaneo basato sulle fatture caricate.
    - Ricavi: fatture emesse (invoices_emesse) o corrispettivi
    - Costi: fatture ricevute (invoices)
    - IVA a Debito: IVA sulle vendite
    - IVA a Credito: IVA sugli acquisti
    - Utile Lordo: Ricavi - Costi
    """
    db = Database.get_db()
    
    if not anno:
        anno = datetime.now().year
    
    try:
        # RICAVI: Corrispettivi + Fatture Emesse
        # I corrispettivi usano il campo "data" (es. "2026-01-03"), non "anno"
        corr_res = await db["corrispettivi"].aggregate([
            {"$match": {
                "data": {"$regex": f"^{anno}"},
                "entity_status": {"$ne": "deleted"}  # Escludi eliminati
            }},
            {"$group": {
                "_id": None, 
                "imponibile": {"$sum": {"$ifNull": ["$totale_imponibile", 0]}},
                "iva": {"$sum": {"$ifNull": ["$totale_iva", 0]}},
                "totale": {"$sum": {"$ifNull": ["$totale", 0]}}
            }}
        ]).to_list(1)
        
        ricavi_corr = corr_res[0] if corr_res else {"imponibile": 0, "iva": 0, "totale": 0}
        
        # Fatture emesse (se presenti) - cerca anche per data
        fatt_emesse_res = await db["invoices_emesse"].aggregate([
            {"$match": {
                "$or": [
                    {"anno": anno},
                    {"data": {"$regex": f"^{anno}"}},
                    {"invoice_date": {"$regex": f"^{anno}"}}
                ]
            }},
            {"$group": {
                "_id": None,
                "imponibile": {"$sum": {"$ifNull": ["$imponibile", 0]}},
                "iva": {"$sum": {"$ifNull": ["$iva", 0]}},
                "totale": {"$sum": {"$ifNull": ["$totale", {"$ifNull": ["$total_amount", 0]}]}}
            }}
        ]).to_list(1)
        
        ricavi_fatt = fatt_emesse_res[0] if fatt_emesse_res else {"imponibile": 0, "iva": 0, "totale": 0}
        
        # COSTI: Fatture ricevute
        costi_res = await db[Collections.INVOICES].aggregate([
            {"$match": {"anno": anno}},
            {"$group": {
                "_id": None,
                "imponibile": {"$sum": {"$ifNull": ["$importo_imponibile", {"$ifNull": ["$imponibile", 0]}]}},
                "iva": {"$sum": {"$ifNull": ["$importo_iva", {"$ifNull": ["$iva", 0]}]}},
                "totale": {"$sum": {"$ifNull": ["$importo_totale", {"$ifNull": ["$total_amount", 0]}]}}
            }}
        ]).to_list(1)
        
        costi = costi_res[0] if costi_res else {"imponibile": 0, "iva": 0, "totale": 0}
        
        # Calcoli
        ricavi_totali = float(ricavi_corr.get("totale", 0) or 0) + float(ricavi_fatt.get("totale", 0) or 0)
        imponibile_ricavi = float(ricavi_corr.get("imponibile", 0) or 0) + float(ricavi_fatt.get("imponibile", 0) or 0)
        iva_debito = float(ricavi_corr.get("iva", 0) or 0) + float(ricavi_fatt.get("iva", 0) or 0)
        
        costi_totali = float(costi.get("totale", 0) or 0)
        imponibile_costi = float(costi.get("imponibile", 0) or 0)
        iva_credito = float(costi.get("iva", 0) or 0)
        
        utile_lordo = ricavi_totali - costi_totali
        saldo_iva = iva_debito - iva_credito
        
        # Conta documenti
        num_fatture_ricevute = await db[Collections.INVOICES].count_documents({"anno": anno})
        num_corrispettivi = await db["corrispettivi"].count_documents({"data": {"$regex": f"^{anno}"}})
        
        return {
            "anno": anno,
            "ricavi": {
                "totale": round(ricavi_totali, 2),
                "imponibile": round(imponibile_ricavi, 2),
                "da_corrispettivi": round(float(ricavi_corr.get("totale", 0) or 0), 2),
                "da_fatture_emesse": round(float(ricavi_fatt.get("totale", 0) or 0), 2)
            },
            "costi": {
                "totale": round(costi_totali, 2),
                "imponibile": round(imponibile_costi, 2)
            },
            "iva": {
                "debito": round(iva_debito, 2),
                "credito": round(iva_credito, 2),
                "saldo": round(saldo_iva, 2),
                "da_versare": round(max(0, saldo_iva), 2),
                "a_credito": round(abs(min(0, saldo_iva)), 2)
            },
            "bilancio": {
                "utile_lordo": round(utile_lordo, 2),
                "margine_percentuale": round((utile_lordo / ricavi_totali * 100) if ricavi_totali > 0 else 0, 1)
            },
            "documenti": {
                "fatture_ricevute": num_fatture_ricevute,
                "corrispettivi": num_corrispettivi
            }
        }
        
    except Exception as e:
        logger.error(f"Errore calcolo bilancio istantaneo: {e}")
        return {
            "anno": anno,
            "ricavi": {"totale": 0, "imponibile": 0},
            "costi": {"totale": 0, "imponibile": 0},
            "iva": {"debito": 0, "credito": 0, "saldo": 0},
            "bilancio": {"utile_lordo": 0, "margine_percentuale": 0},
            "documenti": {"fatture_ricevute": 0, "corrispettivi": 0},
            "error": str(e)
        }
