"""
Router Indici di Bilancio - Versione Semplificata
ROI, ROE, Liquidità e altri indici principali
"""
from fastapi import APIRouter, Query
from typing import Dict, Any
import logging

from app.database import Database
from app.utils.error_handler import handle_errors

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/calcola/{anno}")
@handle_errors
async def calcola_indici_bilancio(anno: int) -> Dict[str, Any]:
    """
    Calcola gli indici di bilancio principali.
    Versione semplificata basata sui dati disponibili.
    """
    db = Database.get_db()
    
    data_inizio = f"{anno}-01-01"
    data_fine = f"{anno}-12-31"
    
    # === DATI PATRIMONIALI ===
    
    # Cassa
    saldo_cassa = await db["saldi_giornalieri"].find_one(
        {"data": {"$lte": data_fine}},
        {"_id": 0, "saldo_finale": 1},
        sort=[("data", -1)]
    )
    disponibilita_liquide_cassa = saldo_cassa.get("saldo_finale", 0) if saldo_cassa else 0
    
    # Banca (estratto conto)
    saldo_banca = await db["estratto_conto_movimenti"].aggregate([
        {"$match": {"data": {"$lte": data_fine}}},
        {"$sort": {"data": -1}},
        {"$limit": 1}
    ]).to_list(1)
    disponibilita_liquide_banca = saldo_banca[0].get("saldo", 0) if saldo_banca else 0
    
    disponibilita_liquide = disponibilita_liquide_cassa + disponibilita_liquide_banca
    
    # Crediti vs clienti (fatture emesse non incassate)
    crediti = await db["invoices"].aggregate([
        {"$match": {
            "tipo_documento": {"$in": ["TD01", "TD24", "TD26"]},
            "pagato": {"$ne": True}
        }},
        {"$group": {"_id": None, "totale": {"$sum": "$total_amount"}}}
    ]).to_list(1)
    crediti_clienti = crediti[0]["totale"] if crediti else 0
    
    # Debiti vs fornitori (fatture ricevute non pagate)
    debiti = await db["invoices"].aggregate([
        {"$match": {
            "tipo_documento": {"$nin": ["TD01", "TD04", "TD24", "TD26"]},
            "pagato": {"$ne": True}
        }},
        {"$group": {"_id": None, "totale": {"$sum": "$total_amount"}}}
    ]).to_list(1)
    debiti_fornitori = debiti[0]["totale"] if debiti else 0
    
    # Fondo TFR
    tfr = await db["employees"].aggregate([
        {"$match": {"status": {"$in": ["attivo", "active"]}}},
        {"$group": {"_id": None, "totale": {"$sum": "$tfr_accantonato"}}}
    ]).to_list(1)
    fondo_tfr = tfr[0]["totale"] if tfr else 0
    
    # Cespiti (valore netto)
    cespiti = await db["cespiti"].aggregate([
        {"$match": {"stato": "attivo"}},
        {"$group": {"_id": None, "totale": {"$sum": "$valore_residuo"}}}
    ]).to_list(1)
    immobilizzazioni = cespiti[0]["totale"] if cespiti else 0
    
    # === DATI ECONOMICI ===
    
    # Ricavi (corrispettivi + fatture emesse)
    corrispettivi = await db["corrispettivi"].aggregate([
        {"$match": {"data": {"$gte": data_inizio, "$lte": data_fine}}},
        {"$group": {"_id": None, "totale": {"$sum": "$totale"}}}
    ]).to_list(1)
    totale_corrispettivi = corrispettivi[0]["totale"] if corrispettivi else 0
    
    fatture_emesse = await db["invoices"].aggregate([
        {"$match": {
            "invoice_date": {"$gte": data_inizio, "$lte": data_fine},
            "tipo_documento": {"$in": ["TD01", "TD24", "TD26"]}
        }},
        {"$group": {"_id": None, "totale": {"$sum": "$total_amount"}}}
    ]).to_list(1)
    totale_fatture_emesse = fatture_emesse[0]["totale"] if fatture_emesse else 0
    
    ricavi_totali = totale_corrispettivi + totale_fatture_emesse
    
    # Costi operativi
    acquisti = await db["invoices"].aggregate([
        {"$match": {
            "invoice_date": {"$gte": data_inizio, "$lte": data_fine},
            "tipo_documento": {"$nin": ["TD01", "TD04", "TD24", "TD26"]}
        }},
        {"$group": {"_id": None, "totale": {"$sum": "$total_amount"}}}
    ]).to_list(1)
    costi_acquisti = acquisti[0]["totale"] if acquisti else 0
    
    # Costo personale
    personale = await db["prima_nota_salari"].aggregate([
        {"$match": {"anno": anno}},
        {"$group": {"_id": None, "totale": {"$sum": "$costo_azienda"}}}
    ]).to_list(1)
    costo_personale = personale[0]["totale"] if personale else 0
    
    costi_totali = costi_acquisti + costo_personale
    
    # Utile operativo (EBIT approssimato)
    utile_operativo = ricavi_totali - costi_totali
    
    # === CALCOLO INDICI ===
    
    # Attivo circolante
    attivo_circolante = disponibilita_liquide + crediti_clienti
    
    # Totale attivo
    totale_attivo = attivo_circolante + immobilizzazioni
    
    # Passività correnti (debiti + altri debiti a breve)
    passivita_correnti = debiti_fornitori
    
    # Patrimonio netto (approssimato come attivo - passivo - tfr)
    patrimonio_netto = totale_attivo - passivita_correnti - fondo_tfr
    
    # Capitale investito
    capitale_investito = totale_attivo
    
    # --- INDICI ---
    
    # ROI (Return on Investment) = Utile operativo / Capitale investito
    roi = (utile_operativo / capitale_investito * 100) if capitale_investito > 0 else 0
    
    # ROE (Return on Equity) = Utile netto / Patrimonio netto
    # Utile netto approssimato = Utile operativo (senza imposte per semplicità)
    roe = (utile_operativo / patrimonio_netto * 100) if patrimonio_netto > 0 else 0
    
    # ROS (Return on Sales) = Utile operativo / Ricavi
    ros = (utile_operativo / ricavi_totali * 100) if ricavi_totali > 0 else 0
    
    # Current Ratio = Attivo corrente / Passivo corrente
    current_ratio = (attivo_circolante / passivita_correnti) if passivita_correnti > 0 else float('inf')
    
    # Quick Ratio = (Disp. liquide + Crediti) / Passivo corrente (= current ratio in questo caso)
    quick_ratio = current_ratio
    
    # Indice di indebitamento = Passivo totale / Patrimonio netto
    passivo_totale = passivita_correnti + fondo_tfr
    indice_indebitamento = (passivo_totale / patrimonio_netto) if patrimonio_netto > 0 else float('inf')
    
    # Rotazione capitale = Ricavi / Capitale investito
    rotazione_capitale = (ricavi_totali / capitale_investito) if capitale_investito > 0 else 0
    
    return {
        "anno": anno,
        "dati_patrimoniali": {
            "attivo": {
                "disponibilita_liquide": round(disponibilita_liquide, 2),
                "crediti_clienti": round(crediti_clienti, 2),
                "immobilizzazioni": round(immobilizzazioni, 2),
                "totale_attivo": round(totale_attivo, 2)
            },
            "passivo": {
                "debiti_fornitori": round(debiti_fornitori, 2),
                "fondo_tfr": round(fondo_tfr, 2),
                "totale_passivo": round(passivo_totale, 2)
            },
            "patrimonio_netto": round(patrimonio_netto, 2)
        },
        "dati_economici": {
            "ricavi": round(ricavi_totali, 2),
            "costi": round(costi_totali, 2),
            "utile_operativo": round(utile_operativo, 2)
        },
        "indici": {
            "redditivita": {
                "ROI": {
                    "valore": round(roi, 2),
                    "unita": "%",
                    "descrizione": "Rendimento del capitale investito",
                    "interpretazione": "buono" if roi > 10 else ("sufficiente" if roi > 5 else "insufficiente")
                },
                "ROE": {
                    "valore": round(roe, 2),
                    "unita": "%",
                    "descrizione": "Rendimento del capitale proprio",
                    "interpretazione": "buono" if roe > 15 else ("sufficiente" if roe > 8 else "insufficiente")
                },
                "ROS": {
                    "valore": round(ros, 2),
                    "unita": "%",
                    "descrizione": "Redditività delle vendite",
                    "interpretazione": "buono" if ros > 10 else ("sufficiente" if ros > 5 else "insufficiente")
                }
            },
            "liquidita": {
                "current_ratio": {
                    "valore": round(current_ratio, 2) if current_ratio != float('inf') else "N/A",
                    "descrizione": "Capacità di coprire debiti a breve",
                    "interpretazione": "buono" if current_ratio > 1.5 else ("sufficiente" if current_ratio > 1 else "critico")
                },
                "quick_ratio": {
                    "valore": round(quick_ratio, 2) if quick_ratio != float('inf') else "N/A",
                    "descrizione": "Liquidità immediata",
                    "interpretazione": "buono" if quick_ratio > 1 else "da monitorare"
                }
            },
            "solidita": {
                "indice_indebitamento": {
                    "valore": round(indice_indebitamento, 2) if indice_indebitamento != float('inf') else "N/A",
                    "descrizione": "Rapporto debiti/patrimonio",
                    "interpretazione": "buono" if indice_indebitamento < 1 else ("accettabile" if indice_indebitamento < 2 else "elevato")
                }
            },
            "efficienza": {
                "rotazione_capitale": {
                    "valore": round(rotazione_capitale, 2),
                    "descrizione": "Efficienza utilizzo capitale",
                    "interpretazione": "buono" if rotazione_capitale > 1 else "da migliorare"
                }
            }
        }
    }


@router.get("/confronto-anni")
@handle_errors
async def confronta_indici_anni(
    anno_corrente: int = Query(...),
    anno_precedente: int = Query(None)
) -> Dict[str, Any]:
    """
    Confronta indici tra due anni.
    """
    if not anno_precedente:
        anno_precedente = anno_corrente - 1
    
    indici_corrente = await calcola_indici_bilancio(anno_corrente)
    indici_precedente = await calcola_indici_bilancio(anno_precedente)
    
    def calcola_variazione(corrente, precedente):
        if precedente == 0 or precedente == "N/A" or corrente == "N/A":
            return "N/A"
        return round((corrente - precedente) / abs(precedente) * 100, 1)
    
    confronto = {
        "ROI": {
            "corrente": indici_corrente["indici"]["redditivita"]["ROI"]["valore"],
            "precedente": indici_precedente["indici"]["redditivita"]["ROI"]["valore"],
            "variazione_pct": calcola_variazione(
                indici_corrente["indici"]["redditivita"]["ROI"]["valore"],
                indici_precedente["indici"]["redditivita"]["ROI"]["valore"]
            )
        },
        "ROE": {
            "corrente": indici_corrente["indici"]["redditivita"]["ROE"]["valore"],
            "precedente": indici_precedente["indici"]["redditivita"]["ROE"]["valore"],
            "variazione_pct": calcola_variazione(
                indici_corrente["indici"]["redditivita"]["ROE"]["valore"],
                indici_precedente["indici"]["redditivita"]["ROE"]["valore"]
            )
        },
        "ROS": {
            "corrente": indici_corrente["indici"]["redditivita"]["ROS"]["valore"],
            "precedente": indici_precedente["indici"]["redditivita"]["ROS"]["valore"],
            "variazione_pct": calcola_variazione(
                indici_corrente["indici"]["redditivita"]["ROS"]["valore"],
                indici_precedente["indici"]["redditivita"]["ROS"]["valore"]
            )
        }
    }
    
    return {
        "anno_corrente": anno_corrente,
        "anno_precedente": anno_precedente,
        "confronto": confronto,
        "dettaglio_corrente": indici_corrente,
        "dettaglio_precedente": indici_precedente
    }
