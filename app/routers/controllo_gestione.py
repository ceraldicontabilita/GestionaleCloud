"""
Router Controllo di Gestione e Budget
Analisi costi/ricavi, centri di costo, budget e confronti
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from uuid import uuid4
import logging

from app.database import Database
from app.utils.error_handler import handle_errors

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================
# MODELLI
# ============================================

# NB: i modelli/endpoint Budget sono stati rimossi da questo router (audit mappa
# lug 2026): il budget canonico è in accounting/contabilita_gestionale.py
# (/api/contabilita-gestionale/budget*), usato dal frontend BudgetPrevisionale.jsx.


# ============================================
# ENDPOINT CONTROLLO GESTIONE
# ============================================

@router.get("/costi-ricavi")
@handle_errors
async def get_analisi_costi_ricavi(
    anno: int,
    mese: int = None
) -> Dict[str, Any]:
    """
    Analisi dettagliata costi e ricavi.
    Aggrega dati da prima nota, cedolini, fatture.
    """
    db = Database.get_db()
    
    if mese:
        data_inizio = f"{anno}-{mese:02d}-01"
        if mese == 12:
            data_fine = f"{anno + 1}-01-01"
        else:
            data_fine = f"{anno}-{mese+1:02d}-01"
        periodo = f"{mese:02d}/{anno}"
    else:
        data_inizio = f"{anno}-01-01"
        data_fine = f"{anno + 1}-01-01"
        periodo = str(anno)
    
    # === RICAVI ===
    # Corrispettivi
    corrispettivi = await db["corrispettivi"].aggregate([
        {"$match": {
            "data": {"$gte": data_inizio, "$lt": data_fine},
            "entity_status": {"$ne": "deleted"},
        }},
        {"$group": {"_id": None, "totale": {
            "$sum": {"$ifNull": ["$totale_imponibile", 0]}
        }}}
    ]).to_list(1)
    totale_corrispettivi = corrispettivi[0]["totale"] if corrispettivi else 0
    
    # Ricavi = SOLO corrispettivi: `invoices` contiene solo fatture RICEVUTE,
    # le TD01/TD24/TD26 non sono fatture emesse — contarle nei ricavi
    # gonfiava i ricavi coi costi (bug #10 audit memoria/endpoints/README.md).
    ricavi_totali = totale_corrispettivi
    
    # === COSTI ===
    # Costo personale (cedolini)
    costo_personale = await db["cedolini"].aggregate([
        {"$match": {"anno": anno, **({"mese": mese} if mese else {})}},
        {"$group": {"_id": None, "totale": {"$sum": "$costo_azienda"}}}
    ]).to_list(1)
    totale_personale = costo_personale[0]["totale"] if costo_personale else 0
    
    # Se non ci sono cedolini, usa prima_nota_salari
    if totale_personale == 0:
        salari = await db["prima_nota_salari"].aggregate([
            {"$match": {"anno": anno, **({"mese": mese} if mese else {})}},
            {"$group": {"_id": None, "totale": {"$sum": "$costo_azienda"}}}
        ]).to_list(1)
        totale_personale = salari[0]["totale"] if salari else 0
    
    # Acquisti: TUTTE le fatture ricevute (prima le TD01/TD24/TD26 — la quasi
    # totalità — erano escluse), con le note di credito dedotte
    acquisti = await db["invoices"].aggregate([
        {"$match": {
            "invoice_date": {"$gte": data_inizio, "$lt": data_fine},
            "tipo_documento": {"$nin": ["TD04", "TD08"]},
            "status": {"$nin": ["deleted", "archived"]},
        }},
        {"$group": {"_id": None, "totale": {"$sum": {
            "$ifNull": ["$imponibile", {
                "$subtract": ["$total_amount", {"$ifNull": ["$iva", 0]}]
            }]
        }}}}
    ]).to_list(1)
    totale_acquisti = acquisti[0]["totale"] if acquisti else 0

    note_credito = await db["invoices"].aggregate([
        {"$match": {
            "invoice_date": {"$gte": data_inizio, "$lt": data_fine},
            "tipo_documento": {"$in": ["TD04", "TD08"]},
            "status": {"$nin": ["deleted", "archived"]},
        }},
        {"$group": {"_id": None, "totale": {"$sum": {
            "$ifNull": ["$imponibile", {
                "$subtract": ["$total_amount", {"$ifNull": ["$iva", 0]}]
            }]
        }}}}
    ]).to_list(1)
    totale_acquisti -= note_credito[0]["totale"] if note_credito else 0
    
    # I pagamenti in Prima Nota non sono nuovi costi: sommarli alle fatture
    # contabilizzava due volte la stessa spesa e includeva anche trasferimenti
    # Cassa/Banca/POS. Le altre uscite restano zero finche' non esiste un
    # documento di costo classificato nel registro contabile canonico.
    totale_altre_uscite = 0
    costi_totali = totale_personale + totale_acquisti
    
    # Margine
    margine = ricavi_totali - costi_totali
    margine_percentuale = (margine / ricavi_totali * 100) if ricavi_totali > 0 else 0
    
    return {
        "periodo": periodo,
        "anno": anno,
        "mese": mese,
        "ricavi": {
            "corrispettivi": round(totale_corrispettivi, 2),
            "totale": round(ricavi_totali, 2)
        },
        "costi": {
            "personale": round(totale_personale, 2),
            "acquisti_merce": round(totale_acquisti, 2),
            "altre_uscite": round(totale_altre_uscite, 2),
            "totale": round(costi_totali, 2)
        },
        "margine": {
            "importo": round(margine, 2),
            "percentuale": round(margine_percentuale, 1),
            "tipo": "utile" if margine > 0 else "perdita"
        },
        "criterio": "competenza_imponibile_senza_doppio_conteggio_pagamenti",
        "fonti": ["corrispettivi", "invoices", "cedolini/prima_nota_salari"],
    }


@router.get("/trend-mensile")
@handle_errors
async def get_trend_mensile(anno: int) -> Dict[str, Any]:
    """
    Trend mensile di ricavi, costi e margine.
    """
    risultati = []
    
    for mese in range(1, 13):
        try:
            analisi = await get_analisi_costi_ricavi(anno=anno, mese=mese)
            risultati.append({
                "mese": mese,
                "mese_nome": ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", 
                             "Lug", "Ago", "Set", "Ott", "Nov", "Dic"][mese-1],
                "ricavi": analisi["ricavi"]["totale"],
                "costi": analisi["costi"]["totale"],
                "margine": analisi["margine"]["importo"]
            })
        except Exception:
            risultati.append({
                "mese": mese,
                "mese_nome": ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", 
                             "Lug", "Ago", "Set", "Ott", "Nov", "Dic"][mese-1],
                "ricavi": 0,
                "costi": 0,
                "margine": 0
            })
    
    return {
        "anno": anno,
        "trend": risultati,
        "totale_anno": {
            "ricavi": round(sum(r["ricavi"] for r in risultati), 2),
            "costi": round(sum(r["costi"] for r in risultati), 2),
            "margine": round(sum(r["margine"] for r in risultati), 2)
        }
    }


@router.get("/costi-per-categoria")
@handle_errors
async def get_costi_per_categoria(
    anno: int,
    mese: int = None
) -> Dict[str, Any]:
    """
    Breakdown dei costi per categoria.
    """
    db = Database.get_db()
    
    if mese:
        data_inizio = f"{anno}-{mese:02d}-01"
        if mese == 12:
            data_fine = f"{anno}-12-31"
        else:
            data_fine = f"{anno}-{mese+1:02d}-01"
    else:
        data_inizio = f"{anno}-01-01"
        data_fine = f"{anno}-12-31"
    
    # Acquisti per fornitore/categoria
    acquisti_per_fornitore = await db["invoices"].aggregate([
        {"$match": {
            "invoice_date": {"$gte": data_inizio, "$lt": data_fine},
            "tipo_documento": {"$nin": ["TD01", "TD04", "TD24", "TD26"]}
        }},
        {"$group": {
            "_id": "$supplier_name",
            "totale": {"$sum": "$total_amount"},
            "num_fatture": {"$sum": 1}
        }},
        {"$sort": {"totale": -1}},
        {"$limit": 20}
    ]).to_list(20)
    
    # Prima nota cassa per categoria
    uscite_per_categoria = await db["prima_nota_cassa"].aggregate([
        {"$match": {
            "data": {"$gte": data_inizio, "$lt": data_fine},
            "tipo": "uscita"
        }},
        {"$group": {
            "_id": "$categoria",
            "totale": {"$sum": "$importo"},
            "num_movimenti": {"$sum": 1}
        }},
        {"$sort": {"totale": -1}}
    ]).to_list(50)
    
    return {
        "anno": anno,
        "mese": mese,
        "acquisti_per_fornitore": [
            {
                "fornitore": a["_id"] or "Sconosciuto",
                "totale": round(a["totale"], 2),
                "num_fatture": a["num_fatture"]
            }
            for a in acquisti_per_fornitore
        ],
        "uscite_per_categoria": [
            {
                "categoria": u["_id"] or "Non categorizzato",
                "totale": round(u["totale"], 2),
                "num_movimenti": u["num_movimenti"]
            }
            for u in uscite_per_categoria
        ]
    }


# ============================================
# ENDPOINT BUDGET — RIMOSSI (audit mappa lug 2026)
# Il budget canonico vive in accounting/contabilita_gestionale.py, prefisso
# /api/contabilita-gestionale/budget*, usato dal frontend (BudgetPrevisionale.jsx).
# Questi endpoint duplicati (/api/controllo-gestione/budget*) non erano usati dal
# frontend e sono stati eliminati per evitare due scritture sulla stessa coll `budget`.
# ============================================


@router.get("/kpi/{anno}")
@handle_errors
async def get_kpi_gestionali(anno: int) -> Dict[str, Any]:
    """
    KPI gestionali principali.
    """
    db = Database.get_db()
    
    # Dati annuali
    analisi = await get_analisi_costi_ricavi(anno=anno)
    
    # Calcola KPI
    ricavi = analisi["ricavi"]["totale"]
    costi = analisi["costi"]["totale"]
    costo_personale = analisi["costi"]["personale"]
    costo_merce = analisi["costi"]["acquisti_merce"]
    
    return {
        "anno": anno,
        "kpi": {
            "margine_operativo": {
                "valore": round(analisi["margine"]["importo"], 2),
                "percentuale": round(analisi["margine"]["percentuale"], 1),
                "descrizione": "Margine sui ricavi"
            },
            "incidenza_personale": {
                "valore": round(costo_personale / ricavi * 100, 1) if ricavi > 0 else 0,
                "descrizione": "% costo personale su ricavi",
                "benchmark": "< 35%"
            },
            "incidenza_merce": {
                "valore": round(costo_merce / ricavi * 100, 1) if ricavi > 0 else 0,
                "descrizione": "% costo materie prime su ricavi",
                "benchmark": "25-35%"
            },
            "costo_medio_giornaliero": {
                "valore": round(costi / 365, 2),
                "descrizione": "Costo operativo medio giornaliero"
            },
            "ricavo_medio_giornaliero": {
                "valore": round(ricavi / 365, 2),
                "descrizione": "Ricavo medio giornaliero"
            }
        },
        "dettaglio": analisi
    }
