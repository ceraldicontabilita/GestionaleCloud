"""Finanziaria router - Financial costs management."""
from fastapi import APIRouter, Body, Query, status
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, date
from uuid import uuid4
import logging

from app.database import Database
from app.routers.prima_nota_module.common import (
    aggrega_saldo_prima_nota,
    appartenenza_conto_bpm,
    filtro_saldo_prima_nota,
    saldi_banca_per_conto,
)
from app.services import conti_pos
from app.services.conto_economico_gestionale import FILTRO_CORRISPETTIVI_VALIDI
from app.services.fatture_report_ae import FILTRO_FATTURE_ATTIVE
from app.utils.error_handler import handle_errors
from app.services.stato_pagamento_fattura import FILTRO_NON_PAGATE

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
    
    # Esclude movimenti storno-soft-delete (status deleted/archived) e i
    # duplicati POS già identificati come tali (categoria POS_DUPLICATO) —
    # stesso filtro usato da tutte le altre query di riepilogo prima nota
    # (prima_nota_module/cassa.py, banca.py, sync.py, manutenzione.py).
    # Senza questo filtro i movimenti "eliminati" dall'utente o dal job di
    # dedup restavano comunque sommati qui, gonfiando i totali.
    prima_nota_match_cassa = filtro_saldo_prima_nota("prima_nota_cassa")
    prima_nota_match_banca = filtro_saldo_prima_nota("prima_nota_banca")
    esclusione_trasferimenti = {"$nor": [
        {"categoria": {"$regex": "versament|prelevament|trasferiment", "$options": "i"}},
        {"source": "trasferimento_interno"},
    ]}
    flusso_economico_match_cassa = {"$and": [prima_nota_match_cassa, esclusione_trasferimenti]}
    flusso_economico_match_banca = {"$and": [prima_nota_match_banca, esclusione_trasferimenti]}

    try:
        # Get Prima Nota Cassa totals
        cassa_pipeline = [
            {"$match": {"$and": [flusso_economico_match_cassa, {"data": date_range}]}},
            {"$group": {
                "_id": "$tipo",
                "total": {"$sum": "$importo"}
            }}
        ]
        cassa_result = await db["prima_nota_cassa"].aggregate(cassa_pipeline).to_list(100)
        cassa_entrate = sum(r["total"] for r in cassa_result if r["_id"] == "entrata")
        cassa_uscite = sum(r["total"] for r in cassa_result if r["_id"] == "uscita")

        # Prima Nota Banca: BPM 19.01.01 (con le righe storiche senza conto)
        # e Mastercard SumUp 19.01.05 sono conti diversi e non si fondono in
        # un solo «Banca» (stessa separazione di get_prima_nota_stats).
        async def _flussi_banca(appartenenza):
            risultato = await db["prima_nota_banca"].aggregate([
                {"$match": {"$and": [
                    flusso_economico_match_banca, {"data": date_range}, appartenenza,
                ]}},
                {"$group": {
                    "_id": "$tipo",
                    "total": {"$sum": "$importo"}
                }}
            ]).to_list(100)
            entrate = sum(r["total"] for r in risultato if r["_id"] == "entrata")
            uscite = sum(r["total"] for r in risultato if r["_id"] == "uscita")
            return entrate, uscite

        banca_entrate, banca_uscite = await _flussi_banca(appartenenza_conto_bpm())
        sumup_entrate, sumup_uscite = await _flussi_banca(
            {"conto_contabile": conti_pos.CONTO_SUMUP_MASTERCARD})
        altri_entrate, altri_uscite = await _flussi_banca(
            {"conto_contabile": {"$nin": [
                conti_pos.CONTO_BPM, conti_pos.CONTO_SUMUP_MASTERCARD, None, "",
            ]}})

        # Riporto iniziale (impostato a mano dall'utente o cumulato anni
        # precedenti): senza, i saldi qui differivano dalla Prima Nota
        # appena l'utente impostava il riporto al 01/01.
        saldo_query_cassa = filtro_saldo_prima_nota("prima_nota_cassa", data=date_range)
        saldi_cassa = await aggrega_saldo_prima_nota(
            db, "prima_nota_cassa", saldo_query_cassa, anno,
        )
        saldi_conti_banca = await saldi_banca_per_conto(db, date_range, anno)
        saldi_banca = saldi_conti_banca["bpm"]
        saldi_sumup = saldi_conti_banca["sumup"]
        saldi_altri = saldi_conti_banca["altri"]
        riporto_cassa = saldi_cassa["saldo_precedente"]
        riporto_banca = saldi_banca["saldo_precedente"]
        
        # ============ IVA DAI CORRISPETTIVI (DEBITO) ============
        corr_pipeline = [
            {"$match": {
                **FILTRO_CORRISPETTIVI_VALIDI,
                "data": date_range,
            }},
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
                "tipo_documento": {"$nin": NOTE_CREDITO_TYPES},
                **FILTRO_FATTURE_ATTIVE,
            }},
            {"$group": {
                "_id": None,
                "total_iva": {"$sum": {"$ifNull": ["$iva_detraibile", 0]}},
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
                "tipo_documento": {"$in": NOTE_CREDITO_TYPES},
                **FILTRO_FATTURE_ATTIVE,
            }},
            {"$group": {
                "_id": None,
                "total_iva": {"$sum": {"$ifNull": ["$iva_detraibile", 0]}},
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

        # ``iva_detraibile`` assente vuol dire «non deciso», non zero: con
        # anche una sola fattura attiva del periodo non classificata l'IVA a
        # credito e il saldo non si conoscono.
        iva_da_classificare = await db["invoices"].count_documents({
            **FILTRO_FATTURE_ATTIVE,
            "iva_detraibile": None,
            "$or": [
                {"data_ricezione": date_range},
                {"$and": [{"data_ricezione": {"$exists": False}}, {"invoice_date": date_range}]}
            ],
        })
        
        # ============ FATTURE DA PAGARE (non pagate) ============
        fatture_da_pagare = await db["invoices"].aggregate([
            {"$match": {
                "invoice_date": date_range,
                "status": {"$nin": ["deleted", "archived"]},
                "entity_status": {"$ne": "deleted"},
                **FILTRO_NON_PAGATE,
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
        
        total_income = cassa_entrate + banca_entrate + sumup_entrate + altri_entrate
        # NON sommare salari perché sono già in banca_uscite
        total_expenses = cassa_uscite + banca_uscite + sumup_uscite + altri_uscite
        saldo_iva = None if iva_da_classificare else iva_debito - iva_credito
        if iva_da_classificare:
            vat_status = f"Da classificare ({iva_da_classificare} fatture senza IVA detraibile)"
        else:
            vat_status = "Da versare" if saldo_iva > 0 else "A credito"
        variazione_finanziaria = round(total_income - total_expenses, 2)
        saldo_totale = round(saldi_cassa["saldo"] + saldi_conti_banca["totale"], 2)
        riporto_totale = round(riporto_cassa + riporto_banca, 2)
        
        return {
            "anno": anno,
            "total_income": round(total_income, 2),
            "total_expenses": round(total_expenses, 2),
            # `balance` resta per retrocompatibilita', ma rappresenta la sola
            # variazione dei flussi dell'anno, non la disponibilita contabile.
            "balance": variazione_finanziaria,
            "flow_balance": variazione_finanziaria,
            "available_balance": saldo_totale,
            "opening_balance": riporto_totale,
            "financial_basis": "prima_nota_cassa_banca",
            "financial_note": (
                "Entrate e uscite escludono i trasferimenti interni. La disponibilita "
                "contabile include i riporti iniziali e i movimenti interni di Cassa/Banca."
            ),
            "cassa": {
                "entrate": round(cassa_entrate, 2),
                "uscite": round(cassa_uscite, 2),
                "riporto": round(riporto_cassa, 2),
                "saldo": saldi_cassa["saldo"],
                "nota_flussi": "Entrate/uscite escludono i trasferimenti interni; il saldo li include.",
            },
            # Solo Banca BPM (19.01.01 e righe storiche senza conto): saldo di
            # Prima Nota, non saldo certificato dall'estratto conto.
            "banca": {
                "entrate": round(banca_entrate, 2),
                "uscite": round(banca_uscite, 2),  # Include già salari e F24
                "riporto": round(riporto_banca, 2),
                "saldo": saldi_banca["saldo"],
                "conto": conti_pos.CONTO_BPM,
                "fonte": "prima_nota_banca",
                "saldo_certificato": False,
                "nota_flussi": "Entrate/uscite escludono i trasferimenti interni; il saldo li include.",
            },
            "sumup": {
                "entrate": round(sumup_entrate, 2),
                "uscite": round(sumup_uscite, 2),
                "riporto": 0.0,
                "saldo": saldi_sumup["saldo"],
                "conto": conti_pos.CONTO_SUMUP_MASTERCARD,
                "fonte": "prima_nota_banca",
                "saldo_certificato": False,
            },
            "altri_conti_banca": {
                "entrate": round(altri_entrate, 2),
                "uscite": round(altri_uscite, 2),
                "saldo": saldi_altri["saldo"],
            },
            "salari": {
                "totale": None,
                "disponibile": False,
                "nota": (
                    "Il dettaglio salari ha una grana propria (cedolino, acconto e saldo) "
                    "e non viene risommato qui; i pagamenti verificati sono gia inclusi "
                    "nelle uscite Banca."
                ),
            },
            # IVA Section
            "vat_debit": round(iva_debito, 2),
            "vat_credit": None if iva_da_classificare else round(iva_credito, 2),
            "vat_balance": None if saldo_iva is None else round(saldo_iva, 2),
            "vat_status": vat_status,
            "vat_da_classificare": iva_da_classificare,
            "vat_basis": "stima_classificata",
            "vat_note": (
                "Stima da documenti classificati; non sostituisce la liquidazione IVA "
                "mensile verificata con F24 e addebito bancario."
            ),
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
                "iva": None if iva_da_classificare else round(iva_credito, 2),
                "iva_da_classificare": iva_da_classificare,
            },
            # Campi H1 richiesti dalla specifica (con riporto iniziale)
            "saldo_cassa": saldi_cassa["saldo"],
            "saldo_banca": saldi_banca["saldo"],
            "saldo_sumup": saldi_sumup["saldo"],
            "saldo_totale": saldo_totale,
            # Payables/Receivables
            "payables": round(payables, 2),
            # Zero sarebbe un dato inventato: non esiste ancora una fonte
            # canonica delle fatture attive e quindi dei crediti clienti.
            "receivables": None,
            "receivables_available": False,
            "receivables_note": "Fatture attive non gestite da una fonte canonica.",
        }
    except Exception:
        logger.exception("Errore financial summary")
        # Non trasformare un errore reale in un riepilogo a zero, che puo'
        # essere scambiato per un dato contabile valido dal frontend.
        raise


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
    data: Dict[str, Any] = Body(...)
) -> Dict[str, str]:
    """Create a financial cost entry."""
    db = Database.get_db()
    data["id"] = str(uuid4())
    data["created_at"] = datetime.now(timezone.utc)
    
    await db["costi_finanziari"].insert_one(data.copy())
    
    return {"message": "Cost created", "id": data["id"]}
