"""
Router Controllo di Gestione e Budget
Analisi costi/ricavi, centri di costo, budget e confronti
"""
from fastapi import APIRouter
from typing import Dict, Any
import logging

from app.database import Database
from app.middleware.performance import istantanea
from app.services.conto_economico_gestionale import costo_personale, ricavi_corrispettivi
from app.services.fatture_report_ae import FILTRO_FATTURE_ATTIVE
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
@istantanea(ttl=120, max_eta=1800, persistente=True)
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
    # Corrispettivi validi (filtro e imponibile unici:
    # services/conto_economico_gestionale.py). Filtrare il solo
    # ``entity_status`` contava due volte le 30 righe di luglio con
    # ``status: deleted``.
    ricavi_rt = await ricavi_corrispettivi(db, {"$gte": data_inizio, "$lt": data_fine})
    totale_corrispettivi = ricavi_rt["imponibile"]
    copertura_corrispettivi = {
        "dal": ricavi_rt["dal"],
        "al": ricavi_rt["al"],
        "documenti": ricavi_rt["documenti"],
    }
    if ricavi_rt["senza_imponibile"]:
        copertura_corrispettivi["senza_imponibile"] = ricavi_rt["senza_imponibile"]

    # Ricavi = SOLO corrispettivi: `invoices` contiene solo fatture RICEVUTE,
    # le TD01/TD24/TD26 non sono fatture emesse — contarle nei ricavi
    # gonfiava i ricavi coi costi (bug #10 audit memoria/endpoints/README.md).
    ricavi_totali = totale_corrispettivi

    # === COSTI ===
    # Costo del personale = lordo delle buste del periodo. ``costo_azienda``
    # non esiste su nessuna busta ne' riga salari: sommarlo dava 0 e la
    # Dashboard mostrava un utile falso. I contributi datoriali non ci sono
    # sui dati: None col motivo, mai 0. Senza nessun lordo il costo e' None.
    personale = await costo_personale(db, anno, mese)
    totale_personale = personale["lordo"]

    # Acquisti: TUTTE le fatture ricevute attive (prima le TD01/TD24/TD26 —
    # la quasi totalita' — erano escluse), con le note di credito dedotte.
    # «Attiva» con lo stesso criterio del giornale: fuori le copie archiviate
    # (``archived`` e ``archiviata``), le cancellate e le collisioni aperte.
    acquisti = await db["invoices"].aggregate([
        {"$match": {
            **FILTRO_FATTURE_ATTIVE,
            "invoice_date": {"$gte": data_inizio, "$lt": data_fine},
            "tipo_documento": {"$nin": ["TD04", "TD08"]},
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
            **FILTRO_FATTURE_ATTIVE,
            "invoice_date": {"$gte": data_inizio, "$lt": data_fine},
            "tipo_documento": {"$in": ["TD04", "TD08"]},
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
    # Un costo che non si conosce non e' zero: senza il personale anche il
    # totale dei costi e il margine sono «Dato non disponibile».
    costi_totali = (
        None if totale_personale is None
        else totale_personale + totale_acquisti + totale_altre_uscite
    )

    # Margine
    margine = None if costi_totali is None else ricavi_totali - costi_totali
    margine_percentuale = (
        round(margine / ricavi_totali * 100, 1)
        if margine is not None and ricavi_totali > 0 else None
    )

    return {
        "periodo": periodo,
        "anno": anno,
        "mese": mese,
        "ricavi": {
            "corrispettivi": round(totale_corrispettivi, 2),
            "totale": round(ricavi_totali, 2)
        },
        "costi": {
            "personale": _arrotonda(totale_personale),
            # Quota datoriale assente sui dati: dichiarata, mai stimata.
            "personale_contributi": None,
            "personale_contributi_motivo": personale["contributi_motivo"],
            "personale_incompleto": personale["incompleto"],
            "personale_motivo": personale["motivo"],
            "personale_buste": personale["buste"],
            "acquisti_merce": round(totale_acquisti, 2),
            "altre_uscite": round(totale_altre_uscite, 2),
            "totale": _arrotonda(costi_totali),
        },
        "margine": {
            "importo": _arrotonda(margine),
            "percentuale": margine_percentuale,
            "tipo": None if margine is None else ("utile" if margine > 0 else "perdita"),
            # Senza contributi datoriali il margine e' sovrastimato.
            "incompleto": personale["incompleto"],
        },
        "criterio": "competenza_imponibile_senza_doppio_conteggio_pagamenti",
        "fonti": ["corrispettivi", "invoices", "cedolini.lordo"],
        "copertura_corrispettivi": copertura_corrispettivi,
    }


def _arrotonda(valore):
    return None if valore is None else round(valore, 2)


@router.get("/trend-mensile")
@handle_errors
async def get_trend_mensile(anno: int) -> Dict[str, Any]:
    """
    Trend mensile di ricavi, costi e margine.
    """
    risultati = []
    nomi = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu",
            "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]

    for mese in range(1, 13):
        try:
            analisi = await get_analisi_costi_ricavi(anno=anno, mese=mese)
            risultati.append({
                "mese": mese,
                "mese_nome": nomi[mese - 1],
                "ricavi": analisi["ricavi"]["totale"],
                "costi": analisi["costi"]["totale"],
                "margine": analisi["margine"]["importo"]
            })
        except Exception as exc:
            # Un mese che non si riesce a leggere non vale zero.
            logger.warning(
                "[ControlloGestione] trend %s/%s non calcolato: %s: %s",
                mese, anno, type(exc).__name__, exc,
            )
            risultati.append({
                "mese": mese,
                "mese_nome": nomi[mese - 1],
                "ricavi": None,
                "costi": None,
                "margine": None
            })

    def _somma(campo):
        valori = [r[campo] for r in risultati]
        return None if any(v is None for v in valori) else round(sum(valori), 2)

    return {
        "anno": anno,
        "trend": risultati,
        "totale_anno": {
            "ricavi": _somma("ricavi"),
            "costi": _somma("costi"),
            "margine": _somma("margine"),
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
    
    # Dati annuali
    analisi = await get_analisi_costi_ricavi(anno=anno)
    
    # Calcola KPI
    ricavi = analisi["ricavi"]["totale"]
    costi = analisi["costi"]["totale"]
    lordo_personale = analisi["costi"]["personale"]
    costo_merce = analisi["costi"]["acquisti_merce"]

    # Senza il costo del personale margine e costi non si conoscono: None,
    # mai uno zero che sembrerebbe un dato.
    return {
        "anno": anno,
        "kpi": {
            "margine_operativo": {
                "valore": analisi["margine"]["importo"],
                "percentuale": analisi["margine"]["percentuale"],
                "descrizione": "Margine sui ricavi"
            },
            "incidenza_personale": {
                "valore": (
                    round(lordo_personale / ricavi * 100, 1)
                    if lordo_personale is not None and ricavi > 0 else None
                ),
                "descrizione": "% costo personale su ricavi",
                "benchmark": "< 35%"
            },
            "incidenza_merce": {
                "valore": round(costo_merce / ricavi * 100, 1) if ricavi > 0 else None,
                "descrizione": "% costo materie prime su ricavi",
                "benchmark": "25-35%"
            },
            "costo_medio_giornaliero": {
                "valore": None if costi is None else round(costi / 365, 2),
                "descrizione": "Costo operativo medio giornaliero"
            },
            "ricavo_medio_giornaliero": {
                "valore": round(ricavi / 365, 2),
                "descrizione": "Ricavo medio giornaliero"
            }
        },
        "dettaglio": analisi
    }
