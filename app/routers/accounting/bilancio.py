"""
Bilancio Router - Stato Patrimoniale e Conto Economico

================================================================================
LOGICA CONTABILE ITALIANA - REGOLE FONDAMENTALI
================================================================================

STRUTTURA DATABASE (Sistema NON multi-utente):
---------------------------------------------
1. CORRISPETTIVI: Vendite al pubblico (scontrini/ricevute fiscali)
   - Rappresentano l'UNICA fonte di RICAVI
   - Contengono: totale, totale_imponibile, totale_iva
   - P.IVA azienda: 04523831214

2. INVOICES: TUTTE fatture RICEVUTE da fornitori (ciclo passivo)
   - Rappresentano i COSTI (acquisti)
   - Tipi documento: TD01 (ordinaria), TD24 (differita), TD04/TD08 (note credito)
   - Hanno sempre 'supplier_name' (fornitore) e 'supplier_vat'

3. FATTURE EMESSE A CLIENTI (quando caricate):
   - NON sono ricavi aggiuntivi!
   - Sono fatture che SOSTITUISCONO uno scontrino già emesso
   - L'importo è GIÀ CONTEGGIATO nei corrispettivi
   - Servono solo per il cliente che vuole detrarre l'IVA
   - NON calcolare l'IVA sulle fatture emesse (già nei corrispettivi!)

CONTO ECONOMICO (per competenza):
---------------------------------
RICAVI = Solo Corrispettivi (totale_imponibile)
         - Le fatture emesse NON sono ricavi aggiuntivi
         
COSTI = Fatture Ricevute (imponibile) - Note Credito (TD04, TD08)

UTILE/PERDITA = RICAVI - COSTI

LIQUIDAZIONE IVA:
-----------------
IVA DEBITO = IVA da corrispettivi (totale_iva)
             - NON include IVA da fatture emesse (sarebbe doppio!)
             
IVA CREDITO = IVA da fatture ricevute (iva)
              - Meno IVA da note di credito

IVA DA VERSARE = IVA DEBITO - IVA CREDITO
                 (se negativo = credito da riportare)

================================================================================
"""
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse
from typing import Dict, Any
from datetime import datetime
from app.database import Database, Collections
from io import BytesIO
import logging

from app.models.stati import STATI_PAGATI
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()

COLLECTION_PRIMA_NOTA_CASSA = "prima_nota_cassa"
COLLECTION_PRIMA_NOTA_BANCA = "prima_nota_banca"

# P.IVA dell'azienda (per identificare fatture emesse vs ricevute)
PIVA_AZIENDA = "04523831214"


@router.get("/stato-patrimoniale")
@handle_errors
async def get_stato_patrimoniale(
    anno: int = Query(None, description="Anno di riferimento"),
    data_a: str = Query(None, description="Data fine (YYYY-MM-DD)")
) -> Dict[str, Any]:
    """
    Genera lo Stato Patrimoniale.
    
    ATTIVO:
    - Cassa (saldo prima nota cassa)
    - Banca (saldo prima nota banca)
    - Crediti vs clienti (fatture emesse non pagate)
    
    PASSIVO:
    - Debiti vs fornitori (fatture ricevute non pagate)
    - Capitale e riserve
    """
    db = Database.get_db()
    
    if not anno:
        anno = datetime.now().year
    
    data_fine = data_a or f"{anno}-12-31"
    data_inizio = f"{anno}-01-01"
    
    # === ATTIVO ===
    
    # Cassa
    pipeline_cassa = [
        {"$match": {"data": {"$lte": data_fine}}},
        {"$group": {
            "_id": None,
            "entrate": {"$sum": {"$cond": [{"$eq": ["$tipo", "entrata"]}, "$importo", 0]}},
            "uscite": {"$sum": {"$cond": [{"$eq": ["$tipo", "uscita"]}, "$importo", 0]}}
        }}
    ]
    cassa_result = await db[COLLECTION_PRIMA_NOTA_CASSA].aggregate(pipeline_cassa).to_list(1)
    saldo_cassa = 0
    if cassa_result:
        saldo_cassa = cassa_result[0].get("entrate", 0) - cassa_result[0].get("uscite", 0)
    
    # Banca
    pipeline_banca = [
        {"$match": {"data": {"$lte": data_fine}}},
        {"$group": {
            "_id": None,
            "entrate": {"$sum": {"$cond": [{"$eq": ["$tipo", "entrata"]}, "$importo", 0]}},
            "uscite": {"$sum": {"$cond": [{"$eq": ["$tipo", "uscita"]}, "$importo", 0]}}
        }}
    ]
    banca_result = await db[COLLECTION_PRIMA_NOTA_BANCA].aggregate(pipeline_banca).to_list(1)
    saldo_banca = 0
    if banca_result:
        saldo_banca = banca_result[0].get("entrate", 0) - banca_result[0].get("uscite", 0)
    
    # Crediti (fatture emesse non pagate - dalla collection fatture_emesse)
    # NOTA: La collection 'invoices' contiene solo fatture RICEVUTE (da fornitori = DEBITI)
    # I crediti vs clienti derivano da fatture EMESSE (vendite a credito)
    try:
        crediti = await db["fatture_emesse"].aggregate([
            {"$match": {
                "status": {"$nin": STATI_PAGATI},
                "pagato": {"$ne": True},
                "$or": [
                    {"data_emissione": {"$lte": data_fine}},
                    {"invoice_date": {"$lte": data_fine}}
                ]
            }},
            {"$group": {"_id": None, "totale": {"$sum": {"$ifNull": ["$total_amount", {"$ifNull": ["$importo_totale", 0]}]}}}}
        ]).to_list(1)
        totale_crediti = crediti[0]["totale"] if crediti else 0
    except Exception:
        totale_crediti = 0
    
    # === PASSIVO ===
    
    # Debiti (fatture ricevute non pagate)
    # NOTA: Tutte le fatture in 'invoices' sono RICEVUTE (da fornitori)
    # Il filtro esclude solo le note di credito (TD04, TD08)
    debiti = await db[Collections.INVOICES].aggregate([
        {"$match": {
            "tipo_documento": {"$nin": ["TD04", "TD08"]},  # Escludi solo Note Credito
            "status": {"$nin": STATI_PAGATI},
            "pagato": {"$ne": True},
            "$or": [
                {"invoice_date": {"$lte": data_fine}},
                {"data_ricezione": {"$lte": data_fine}}
            ]
        }},
        {"$group": {"_id": None, "totale": {"$sum": "$total_amount"}}}
    ]).to_list(1)
    totale_debiti = debiti[0]["totale"] if debiti else 0
    
    # Calcoli
    totale_attivo = saldo_cassa + saldo_banca + totale_crediti
    totale_passivo = totale_debiti
    patrimonio_netto = totale_attivo - totale_passivo
    
    return {
        "anno": anno,
        "data_riferimento": data_fine,
        "attivo": {
            "disponibilita_liquide": {
                "cassa": round(saldo_cassa, 2),
                "banca": round(saldo_banca, 2),
                "totale": round(saldo_cassa + saldo_banca, 2)
            },
            "crediti": {
                "crediti_vs_clienti": round(totale_crediti, 2),
                "totale": round(totale_crediti, 2)
            },
            "totale_attivo": round(totale_attivo, 2)
        },
        "passivo": {
            "debiti": {
                "debiti_vs_fornitori": round(totale_debiti, 2),
                "totale": round(totale_debiti, 2)
            },
            "patrimonio_netto": round(patrimonio_netto, 2),
            "totale_passivo": round(totale_debiti + patrimonio_netto, 2)
        }
    }


@router.get("/conto-economico")
@handle_errors
async def get_conto_economico(
    anno: int = Query(None, description="Anno di riferimento"),
    mese: int = Query(None, description="Mese (1-12)")
) -> Dict[str, Any]:
    """
    Genera il Conto Economico secondo principi contabili italiani.
    
    STRUTTURA DATABASE:
    - 'corrispettivi': Vendite al pubblico (scontrini/ricevute) = RICAVI
    - 'invoices': TUTTE fatture RICEVUTE da fornitori = COSTI
      - TD01, TD24, TD02, TD06, TD27, null = Fatture acquisto
      - TD04, TD08 = Note di Credito (riducono i costi)
    
    RICAVI (per competenza):
    - Corrispettivi: dalla collezione 'corrispettivi' (totale_imponibile)
    - (Non esistono fatture emesse a clienti in questo sistema)
    
    COSTI (per competenza):
    - Acquisti: TUTTE le fatture ricevute (escluse NC)
    - Note di Credito: TD04, TD08 sottratte dai costi
    """
    db = Database.get_db()
    
    if not anno:
        anno = datetime.now().year
    
    # Periodo
    if mese:
        data_inizio = f"{anno}-{mese:02d}-01"
        if mese == 12:
            data_fine = f"{anno}-12-31"
        else:
            import calendar
            ultimo_giorno = calendar.monthrange(anno, mese)[1]
            data_fine = f"{anno}-{mese:02d}-{ultimo_giorno}"
    else:
        data_inizio = f"{anno}-01-01"
        data_fine = f"{anno}-12-31"
    
    # === RICAVI ===
    # I ricavi derivano ESCLUSIVAMENTE dai corrispettivi (vendite al pubblico)
    # Non esistono "fatture emesse" a clienti in questo sistema
    
    corrispettivi_result = await db["corrispettivi"].aggregate([
        {"$match": {
            "data": {"$gte": data_inizio, "$lte": data_fine}
        }},
        {"$group": {
            "_id": None,
            "totale_imponibile": {"$sum": {"$ifNull": ["$totale_imponibile", 0]}},
            "totale_iva": {"$sum": {"$ifNull": ["$totale_iva", 0]}},
            "totale_lordo": {"$sum": {"$ifNull": ["$totale", 0]}},
            "count": {"$sum": 1}
        }}
    ]).to_list(1)
    
    totale_corrispettivi = corrispettivi_result[0]["totale_imponibile"] if corrispettivi_result else 0
    iva_vendite = corrispettivi_result[0]["totale_iva"] if corrispettivi_result else 0
    num_corrispettivi = corrispettivi_result[0]["count"] if corrispettivi_result else 0
    totale_lordo_corrispettivi = corrispettivi_result[0]["totale_lordo"] if corrispettivi_result else 0
    
    # === COSTI ===
    
    # 1. TUTTE le Fatture Ricevute (acquisti) - ESCLUSE solo le Note Credito (TD04, TD08)
    # La collezione 'invoices' contiene SOLO fatture RICEVUTE da fornitori
    fatture_ricevute = await db[Collections.INVOICES].aggregate([
        {"$match": {
            "tipo_documento": {"$nin": ["TD04", "TD08"]},  # Escludi solo Note Credito
            "$or": [
                {"invoice_date": {"$gte": data_inizio, "$lte": data_fine}},
                {"data_ricezione": {"$gte": data_inizio, "$lte": data_fine}}
            ]
        }},
        {"$group": {
            "_id": None,
            "totale_imponibile": {"$sum": {"$ifNull": ["$imponibile", {"$subtract": ["$total_amount", {"$ifNull": ["$iva", 0]}]}]}},
            "totale_iva": {"$sum": {"$ifNull": ["$iva", 0]}},
            "totale_lordo": {"$sum": "$total_amount"},
            "count": {"$sum": 1}
        }}
    ]).to_list(1)
    
    totale_acquisti = fatture_ricevute[0]["totale_imponibile"] if fatture_ricevute else 0
    iva_acquisti = fatture_ricevute[0]["totale_iva"] if fatture_ricevute else 0
    num_fatture = fatture_ricevute[0]["count"] if fatture_ricevute else 0
    
    # 2. Note di Credito RICEVUTE (riducono i costi) - TD04, TD08
    note_credito = await db[Collections.INVOICES].aggregate([
        {"$match": {
            "tipo_documento": {"$in": ["TD04", "TD08"]},
            "$or": [
                {"invoice_date": {"$gte": data_inizio, "$lte": data_fine}},
                {"data_ricezione": {"$gte": data_inizio, "$lte": data_fine}}
            ]
        }},
        {"$group": {
            "_id": None,
            "totale_imponibile": {"$sum": {"$ifNull": ["$imponibile", {"$subtract": ["$total_amount", {"$ifNull": ["$iva", 0]}]}]}},
            "totale_iva": {"$sum": {"$ifNull": ["$iva", 0]}},
            "count": {"$sum": 1}
        }}
    ]).to_list(1)
    
    totale_note_credito = note_credito[0]["totale_imponibile"] if note_credito else 0
    iva_note_credito = note_credito[0]["totale_iva"] if note_credito else 0
    num_note_credito = note_credito[0]["count"] if note_credito else 0
    
    # === CALCOLI FINALI ===
    # REGOLA CONTABILE ITALIANA:
    # - Ricavi = SOLO Corrispettivi (vendite al pubblico)
    # - Le fatture emesse a clienti NON sono ricavi aggiuntivi (già nei corrispettivi)
    # - Costi = Fatture Ricevute da fornitori - Note Credito
    
    # Ricavi = Solo Corrispettivi (imponibile)
    totale_ricavi = totale_corrispettivi
    
    # Costi = Acquisti - Note Credito
    costi_netti = totale_acquisti - totale_note_credito
    totale_costi = costi_netti
    
    # Risultato
    utile_perdita = totale_ricavi - totale_costi
    
    # Margine percentuale
    margine_pct = round((utile_perdita / totale_ricavi * 100), 1) if totale_ricavi > 0 else 0
    
    return {
        "anno": anno,
        "mese": mese,
        "periodo": {
            "da": data_inizio,
            "a": data_fine
        },
        "ricavi": {
            "corrispettivi": round(totale_corrispettivi, 2),
            "corrispettivi_lordi": round(totale_lordo_corrispettivi, 2),
            "totale_ricavi": round(totale_ricavi, 2),
            # NOTA: Le fatture emesse NON compaiono qui perché l'importo è già nei corrispettivi
        },
        "costi": {
            "acquisti": round(totale_acquisti, 2),
            "note_credito": round(totale_note_credito, 2),
            "costi_netti": round(costi_netti, 2),
            "totale_costi": round(totale_costi, 2)
        },
        "risultato": {
            "utile_perdita": round(utile_perdita, 2),
            "margine_percentuale": margine_pct,
            "tipo": "utile" if utile_perdita >= 0 else "perdita"
        },
        "dettaglio_iva": {
            "iva_vendite": round(iva_vendite, 2),  # Solo da corrispettivi (NON da fatture emesse)
            "iva_acquisti": round(iva_acquisti - iva_note_credito, 2),
            "iva_netta": round(iva_vendite - (iva_acquisti - iva_note_credito), 2)
        },
        "statistiche": {
            "num_corrispettivi": num_corrispettivi,
            "num_fatture_ricevute": num_fatture,
            "num_note_credito": num_note_credito
        },
        "note": "Ricavi = Corrispettivi (vendite al pubblico). Costi = Fatture ricevute - Note credito."
    }


@router.get("/riepilogo")
@handle_errors
async def get_riepilogo_bilancio(anno: int = Query(None)) -> Dict[str, Any]:
    """Riepilogo completo bilancio: stato patrimoniale + conto economico."""
    if not anno:
        anno = datetime.now().year
    
    # Use helper functions to avoid Query parameter issues
    stato_patrimoniale = await _get_stato_patrimoniale_data(anno)
    conto_economico = await _get_conto_economico_data(anno)
    
    return {
        "anno": anno,
        "stato_patrimoniale": stato_patrimoniale,
        "conto_economico": conto_economico
    }


@router.get("/conto-economico-dettagliato")
@handle_errors
async def get_conto_economico_dettagliato(
    anno: int = Query(None, description="Anno di riferimento"),
    mese: int = Query(None, description="Mese (1-12)")
) -> Dict[str, Any]:
    """
    Conto Economico DETTAGLIATO secondo schema civilistico art. 2425 c.c.
    
    Classifica automaticamente i costi per natura con regole di:
    - Deducibilità ai fini IRES/IRPEF
    - Detraibilità IVA
    
    VOCI PRINCIPALI:
    - B6: Acquisti materie prime e merci
    - B7: Costi per servizi (energia, telefonia, consulenze, manutenzioni, ecc.)
    - B8: Godimento beni terzi (affitti, noleggio auto con limite €3.615,20)
    - B9: Costi del personale (stipendi, contributi, TFR)
    - C17: Interessi passivi (mutui, commissioni bancarie)
    """
    from app.services.classificazione_costi import classifica_fornitore
    
    db = Database.get_db()
    
    if not anno:
        anno = datetime.now().year
    
    # Periodo
    if mese:
        data_inizio = f"{anno}-{mese:02d}-01"
        import calendar
        ultimo_giorno = calendar.monthrange(anno, mese)[1]
        data_fine = f"{anno}-{mese:02d}-{ultimo_giorno}"
    else:
        data_inizio = f"{anno}-01-01"
        data_fine = f"{anno}-12-31"
    
    # === A) RICAVI ===
    # A1: Ricavi delle vendite (Corrispettivi)
    corrispettivi = await db["corrispettivi"].aggregate([
        {"$match": {"data": {"$gte": data_inizio, "$lte": data_fine}}},
        {"$group": {
            "_id": None,
            "totale_imponibile": {"$sum": {"$ifNull": ["$totale_imponibile", 0]}},
            "totale_iva": {"$sum": {"$ifNull": ["$totale_iva", 0]}},
            "totale_lordo": {"$sum": {"$ifNull": ["$totale", 0]}},
            "count": {"$sum": 1}
        }}
    ]).to_list(1)
    
    ricavi_vendite = corrispettivi[0]["totale_imponibile"] if corrispettivi else 0
    iva_vendite = corrispettivi[0]["totale_iva"] if corrispettivi else 0
    
    # === B) COSTI DELLA PRODUZIONE ===
    # Recupera tutte le fatture e classifica per categoria
    fatture = await db[Collections.INVOICES].find({
        "tipo_documento": {"$nin": ["TD04", "TD08"]},
        "$or": [
            {"invoice_date": {"$gte": data_inizio, "$lte": data_fine}},
            {"data_ricezione": {"$gte": data_inizio, "$lte": data_fine}}
        ]
    }).to_list(5000)
    
    # Classifica ogni fattura
    costi_per_categoria = {}
    for fatt in fatture:
        supplier = fatt.get("supplier_name", "")
        descrizione = fatt.get("descrizione", "")
        categoria = classifica_fornitore(supplier, descrizione)
        
        imponibile = fatt.get("imponibile") or (fatt.get("total_amount", 0) - fatt.get("iva", 0))
        iva = fatt.get("iva", 0)
        
        if categoria not in costi_per_categoria:
            costi_per_categoria[categoria] = {
                "imponibile": 0,
                "iva": 0,
                "count": 0
            }
        
        costi_per_categoria[categoria]["imponibile"] += imponibile
        costi_per_categoria[categoria]["iva"] += iva
        costi_per_categoria[categoria]["count"] += 1
    
    # Note di credito
    note_credito = await db[Collections.INVOICES].aggregate([
        {"$match": {
            "tipo_documento": {"$in": ["TD04", "TD08"]},
            "$or": [
                {"invoice_date": {"$gte": data_inizio, "$lte": data_fine}},
                {"data_ricezione": {"$gte": data_inizio, "$lte": data_fine}}
            ]
        }},
        {"$group": {
            "_id": None,
            "totale": {"$sum": {"$ifNull": ["$imponibile", {"$subtract": ["$total_amount", {"$ifNull": ["$iva", 0]}]}]}},
            "iva": {"$sum": {"$ifNull": ["$iva", 0]}}
        }}
    ]).to_list(1)
    
    totale_nc = note_credito[0]["totale"] if note_credito else 0
    
    # === B9) COSTI DEL PERSONALE ===
    # Recupera dai cedolini (anno può essere int o stringa)
    cedolini = await db["cedolini"].aggregate([
        {"$match": {
            "$or": [{"anno": anno}, {"anno": str(anno)}]
        }},
        {"$group": {
            "_id": None,
            "totale_lordo": {"$sum": {"$ifNull": ["$lordo", 0]}},
            "totale_netto": {"$sum": {"$ifNull": ["$netto", 0]}},
            "totale_inps_dip": {"$sum": {"$ifNull": ["$inps_dipendente", 0]}},
            "totale_inps_az": {"$sum": {"$ifNull": ["$inps_azienda", 0]}},
            "totale_inail": {"$sum": {"$ifNull": ["$inail", 0]}},
            "totale_tfr": {"$sum": {"$ifNull": ["$tfr", 0]}},
            "totale_costo_azienda": {"$sum": {"$ifNull": ["$costo_azienda", 0]}},
            "totale_irpef": {"$sum": {"$ifNull": ["$irpef", 0]}},
            "count": {"$sum": 1}
        }}
    ]).to_list(1)
    
    if cedolini and cedolini[0]["count"] > 0:
        ced = cedolini[0]
        lordo = ced["totale_lordo"]
        
        # Se abbiamo costo_azienda diretto, usalo
        if ced["totale_costo_azienda"] > 0:
            costo_personale = {
                "B9a_salari_stipendi": round(lordo, 2),
                "B9b_oneri_sociali": round(ced["totale_inps_az"] + ced["totale_inail"], 2),
                "B9c_tfr": round(ced["totale_tfr"], 2),
                "totale": round(ced["totale_costo_azienda"], 2),
                "num_cedolini": ced["count"]
            }
        else:
            # Stima oneri se non disponibili
            # INPS azienda circa 30% del lordo, TFR 6.91% del lordo
            inps_azienda = ced["totale_inps_az"] if ced["totale_inps_az"] > 0 else (lordo * 0.30)
            tfr = ced["totale_tfr"] if ced["totale_tfr"] > 0 else (lordo * 0.0691)
            costo_personale = {
                "B9a_salari_stipendi": round(lordo, 2),
                "B9b_oneri_sociali": round(inps_azienda, 2),
                "B9c_tfr": round(tfr, 2),
                "totale": round(lordo + inps_azienda + tfr, 2),
                "num_cedolini": ced["count"],
                "note": "Oneri stimati (dati parziali)" if ced["totale_inps_az"] == 0 else None
            }
    else:
        costo_personale = {"B9a_salari_stipendi": 0, "B9b_oneri_sociali": 0, "B9c_tfr": 0, "totale": 0, "num_cedolini": 0}
    
    # === Costruisci il Conto Economico dettagliato ===
    # Organizza per macrocategoria
    B6_merci = costi_per_categoria.get("B6_MATERIE_PRIME", {"imponibile": 0, "iva": 0, "count": 0})
    
    B7_servizi = {
        "energia": costi_per_categoria.get("B7_UTENZE_ENERGIA", {"imponibile": 0, "iva": 0, "count": 0}),
        "acqua": costi_per_categoria.get("B7_UTENZE_ACQUA", {"imponibile": 0, "iva": 0, "count": 0}),
        "telefonia": costi_per_categoria.get("B7_TELEFONIA", {"imponibile": 0, "iva": 0, "count": 0}),
        "consulenze": costi_per_categoria.get("B7_CONSULENZE", {"imponibile": 0, "iva": 0, "count": 0}),
        "manutenzioni": costi_per_categoria.get("B7_MANUTENZIONI", {"imponibile": 0, "iva": 0, "count": 0}),
        "assicurazioni": costi_per_categoria.get("B7_ASSICURAZIONI", {"imponibile": 0, "iva": 0, "count": 0}),
        "trasporti": costi_per_categoria.get("B7_TRASPORTI", {"imponibile": 0, "iva": 0, "count": 0}),
        "pubblicita": costi_per_categoria.get("B7_PUBBLICITA", {"imponibile": 0, "iva": 0, "count": 0}),
        "altri_servizi": costi_per_categoria.get("B7_SERVIZI", {"imponibile": 0, "iva": 0, "count": 0}),
    }
    totale_B7 = sum(v["imponibile"] for v in B7_servizi.values())
    
    B8_godimento = {
        "affitti": costi_per_categoria.get("B8_GODIMENTO_AFFITTI", {"imponibile": 0, "iva": 0, "count": 0}),
        "noleggio_auto": costi_per_categoria.get("B8_NOLEGGIO_AUTO", {"imponibile": 0, "iva": 0, "count": 0}),
        "leasing": costi_per_categoria.get("B8_LEASING", {"imponibile": 0, "iva": 0, "count": 0}),
    }
    totale_B8 = sum(v["imponibile"] for v in B8_godimento.values())
    
    # Costi auto (carburante, manutenzione auto)
    costi_auto = {
        "carburante": costi_per_categoria.get("AUTO_CARBURANTE", {"imponibile": 0, "iva": 0, "count": 0}),
        "manutenzione_auto": costi_per_categoria.get("AUTO_MANUTENZIONE", {"imponibile": 0, "iva": 0, "count": 0}),
    }
    totale_costi_auto = sum(v["imponibile"] for v in costi_auto.values())
    
    # Oneri finanziari
    C17_finanziari = {
        "commissioni_bancarie": costi_per_categoria.get("C17_COMMISSIONI_BANCARIE", {"imponibile": 0, "iva": 0, "count": 0}),
    }
    totale_C17 = sum(v["imponibile"] for v in C17_finanziari.values())
    
    # Altri costi (B14)
    B14_altri = costi_per_categoria.get("B14_ONERI_DIVERSI", {"imponibile": 0, "iva": 0, "count": 0})
    
    # === CALCOLI DEDUCIBILITÀ ===
    # Telefonia: deducibile 80%
    tel_deducibile = B7_servizi["telefonia"]["imponibile"] * 0.80
    tel_indeducibile = B7_servizi["telefonia"]["imponibile"] * 0.20
    
    # Noleggio auto: deducibile 20%, max €3.615,20/anno
    noleggio_imponibile = B8_godimento["noleggio_auto"]["imponibile"]
    noleggio_limitato = min(noleggio_imponibile, 3615.20)
    noleggio_deducibile = noleggio_limitato * 0.20
    noleggio_indeducibile = noleggio_imponibile - noleggio_deducibile
    
    # Carburante auto: 20%
    carburante_deducibile = costi_auto["carburante"]["imponibile"] * 0.20
    carburante_indeducibile = costi_auto["carburante"]["imponibile"] * 0.80
    
    # TOTALI
    totale_costi_produzione = (
        B6_merci["imponibile"] +
        totale_B7 +
        totale_B8 +
        costo_personale["totale"] +
        totale_costi_auto +
        B14_altri["imponibile"] -
        totale_nc
    )
    
    totale_costi = totale_costi_produzione + totale_C17
    
    # RISULTATO
    risultato_operativo = ricavi_vendite - totale_costi_produzione
    risultato_ante_imposte = risultato_operativo - totale_C17
    
    # Calcolo costi indeducibili totali
    totale_indeducibile = tel_indeducibile + noleggio_indeducibile + carburante_indeducibile
    
    return {
        "anno": anno,
        "mese": mese,
        "periodo": {"da": data_inizio, "a": data_fine},
        
        "A_RICAVI": {
            "A1_vendite": {
                "corrispettivi": round(ricavi_vendite, 2),
                "corrispettivi_lordi": round(corrispettivi[0]["totale_lordo"] if corrispettivi else 0, 2),
                "iva_vendite": round(iva_vendite, 2),
                "note": "UNICA fonte ricavi - Le fatture emesse sono già incluse"
            },
            "totale_ricavi": round(ricavi_vendite, 2)
        },
        
        "B_COSTI_PRODUZIONE": {
            "B6_materie_prime_merci": {
                "imponibile": round(B6_merci["imponibile"], 2),
                "iva": round(B6_merci["iva"], 2),
                "num_fatture": B6_merci["count"],
                "deducibilita": "100%",
                "detraibilita_iva": "100%"
            },
            "B7_servizi": {
                "dettaglio": {
                    "energia_elettrica_gas": {
                        "imponibile": round(B7_servizi["energia"]["imponibile"], 2),
                        "deducibilita": "100%",
                        "detraibilita_iva": "100%"
                    },
                    "acqua": {
                        "imponibile": round(B7_servizi["acqua"]["imponibile"], 2),
                        "deducibilita": "100%",
                        "detraibilita_iva": "100%"
                    },
                    "telefonia": {
                        "imponibile": round(B7_servizi["telefonia"]["imponibile"], 2),
                        "deducibile": round(tel_deducibile, 2),
                        "indeducibile": round(tel_indeducibile, 2),
                        "deducibilita": "80%",
                        "detraibilita_iva": "50%",
                        "note": "Art. 102 TUIR"
                    },
                    "consulenze": {
                        "imponibile": round(B7_servizi["consulenze"]["imponibile"], 2),
                        "deducibilita": "100%"
                    },
                    "manutenzioni": {
                        "imponibile": round(B7_servizi["manutenzioni"]["imponibile"], 2),
                        "deducibilita": "100%",
                        "note": "Limite 5% beni ammortizzabili"
                    },
                    "assicurazioni": {
                        "imponibile": round(B7_servizi["assicurazioni"]["imponibile"], 2),
                        "deducibilita": "100%",
                        "detraibilita_iva": "Esente art. 10"
                    },
                    "trasporti": {
                        "imponibile": round(B7_servizi["trasporti"]["imponibile"], 2),
                        "deducibilita": "100%"
                    },
                    "pubblicita": {
                        "imponibile": round(B7_servizi["pubblicita"]["imponibile"], 2),
                        "deducibilita": "100%"
                    },
                    "altri_servizi": {
                        "imponibile": round(B7_servizi["altri_servizi"]["imponibile"], 2)
                    }
                },
                "totale": round(totale_B7, 2)
            },
            "B7_auto_aziendali": {
                "carburante": {
                    "imponibile": round(costi_auto["carburante"]["imponibile"], 2),
                    "deducibile": round(carburante_deducibile, 2),
                    "indeducibile": round(carburante_indeducibile, 2),
                    "deducibilita": "20% (70% se assegnata)",
                    "detraibilita_iva": "40%",
                    "note": "Art. 164 TUIR"
                },
                "manutenzione": {
                    "imponibile": round(costi_auto["manutenzione_auto"]["imponibile"], 2),
                    "deducibilita": "20%",
                    "detraibilita_iva": "40%"
                },
                "totale": round(totale_costi_auto, 2)
            },
            "B8_godimento_beni_terzi": {
                "affitti_locazioni": {
                    "imponibile": round(B8_godimento["affitti"]["imponibile"], 2),
                    "deducibilita": "100%",
                    "detraibilita_iva": "Spesso esente immobili"
                },
                "noleggio_auto": {
                    "imponibile": round(noleggio_imponibile, 2),
                    "importo_limitato": round(noleggio_limitato, 2),
                    "deducibile": round(noleggio_deducibile, 2),
                    "indeducibile": round(noleggio_indeducibile, 2),
                    "deducibilita": "20% su max €3.615,20/anno",
                    "detraibilita_iva": "40%",
                    "note": "Art. 164 TUIR - 70% se assegnata a dipendente"
                },
                "leasing": {
                    "imponibile": round(B8_godimento["leasing"]["imponibile"], 2)
                },
                "totale": round(totale_B8, 2)
            },
            "B9_costo_personale": {
                "B9a_salari_stipendi": round(costo_personale["B9a_salari_stipendi"], 2),
                "B9b_oneri_sociali": round(costo_personale["B9b_oneri_sociali"], 2),
                "B9c_tfr": round(costo_personale["B9c_tfr"], 2),
                "totale": round(costo_personale["totale"], 2),
                "num_cedolini": costo_personale["num_cedolini"],
                "deducibilita": "100%",
                "note": "Fuori campo IVA"
            },
            "B14_oneri_diversi": {
                "imponibile": round(B14_altri["imponibile"], 2),
                "num_fatture": B14_altri["count"]
            },
            "note_credito_ricevute": {
                "totale": round(totale_nc, 2),
                "note": "Riducono i costi"
            },
            "totale_costi_produzione": round(totale_costi_produzione, 2)
        },
        
        "C_PROVENTI_ONERI_FINANZIARI": {
            "C17_interessi_oneri": {
                "commissioni_bancarie": {
                    "imponibile": round(C17_finanziari["commissioni_bancarie"]["imponibile"], 2),
                    "deducibilita": "100%",
                    "detraibilita_iva": "Esente art. 10"
                },
                "interessi_passivi_mutui": {
                    "imponibile": 0,  # Da implementare con collezione mutui
                    "deducibilita": "Limite ROL 30%",
                    "note": "Art. 96 TUIR"
                }
            },
            "totale_oneri_finanziari": round(totale_C17, 2)
        },
        
        "RISULTATO": {
            "risultato_operativo": round(risultato_operativo, 2),
            "risultato_ante_imposte": round(risultato_ante_imposte, 2),
            "tipo": "utile" if risultato_ante_imposte >= 0 else "perdita",
            "margine_percentuale": round((risultato_ante_imposte / ricavi_vendite * 100), 1) if ricavi_vendite > 0 else 0
        },
        
        "FISCALE": {
            "totale_costi_indeducibili": round(totale_indeducibile, 2),
            "dettaglio_indeducibili": {
                "telefonia_20%": round(tel_indeducibile, 2),
                "noleggio_auto_80%": round(noleggio_indeducibile, 2),
                "carburante_80%": round(carburante_indeducibile, 2)
            },
            "reddito_fiscale_stimato": round(risultato_ante_imposte + totale_indeducibile, 2),
            "note": "Il reddito fiscale va calcolato con variazioni in aumento/diminuzione"
        },
        
        "STATISTICHE": {
            "totale_fatture_classificate": len(fatture),
            "categorie_riconosciute": len(costi_per_categoria)
        }
    }


@router.get("/export-pdf")
@handle_errors
async def export_bilancio_pdf(anno: int = Query(None)):
    """Esporta Bilancio in PDF."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.units import cm
    except ImportError:
        raise HTTPException(status_code=500, detail="reportlab non installato")
    
    if not anno:
        anno = datetime.now().year
    
    # Carica dati usando le funzioni helper (non le endpoint functions)
    stato_patrimoniale = await _get_stato_patrimoniale_data(anno)
    conto_economico = await _get_conto_economico_data(anno)
    
    # Crea PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, alignment=1, spaceAfter=20)
    section_style = ParagraphStyle('Section', parent=styles['Heading2'], fontSize=14, spaceAfter=10, spaceBefore=15)
    
    elements = []
    
    # Titolo
    elements.append(Paragraph(f"BILANCIO {anno}", title_style))
    elements.append(Paragraph(f"Generato il {datetime.now().strftime('%d/%m/%Y')}", styles['Normal']))
    elements.append(Spacer(1, 20))
    
    # === STATO PATRIMONIALE ===
    elements.append(Paragraph("STATO PATRIMONIALE", section_style))
    
    sp = stato_patrimoniale
    # Calcola totale passivo per il PDF
    totale_passivo = sp['passivo']['debiti']['totale'] + sp['passivo']['patrimonio_netto']
    sp_data = [
        ['ATTIVO', '', 'PASSIVO', ''],
        ['Cassa', f"€ {sp['attivo']['disponibilita_liquide']['cassa']:,.2f}", 
         'Debiti vs Fornitori', f"€ {sp['passivo']['debiti']['totale']:,.2f}"],
        ['Banca', f"€ {sp['attivo']['disponibilita_liquide']['banca']:,.2f}", '', ''],
        ['Crediti vs Clienti', f"€ {sp['attivo']['crediti']['totale']:,.2f}", 
         'Patrimonio Netto', f"€ {sp['passivo']['patrimonio_netto']:,.2f}"],
        ['', '', '', ''],
        ['TOTALE ATTIVO', f"€ {sp['attivo']['totale_attivo']:,.2f}", 
         'TOTALE PASSIVO', f"€ {totale_passivo:,.2f}"]
    ]
    
    sp_table = Table(sp_data, colWidths=[5*cm, 4*cm, 5*cm, 4*cm])
    sp_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#dcfce7')),
        ('BACKGROUND', (2, 0), (3, 0), colors.HexColor('#fee2e2')),
        ('BACKGROUND', (0, -1), (1, -1), colors.HexColor('#22c55e')),
        ('BACKGROUND', (2, -1), (3, -1), colors.HexColor('#ef4444')),
        ('TEXTCOLOR', (0, -1), (-1, -1), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.gray),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(sp_table)
    elements.append(Spacer(1, 30))
    
    # === CONTO ECONOMICO ===
    elements.append(Paragraph("CONTO ECONOMICO", section_style))
    
    ce = conto_economico
    # NOTA: I ricavi derivano SOLO dai corrispettivi (vendite al pubblico)
    # I costi derivano dalle fatture ricevute - note credito
    # Helper function returns 'totale' instead of 'totale_ricavi'/'totale_costi' and 'utile_lordo' instead of 'utile_perdita'
    utile_perdita = ce['risultato']['utile_lordo']
    ce_data = [
        ['RICAVI', ''],
        ['Corrispettivi (Vendite al Pubblico)', f"€ {ce['ricavi']['corrispettivi']:,.2f}"],
        ['TOTALE RICAVI', f"€ {ce['ricavi']['totale']:,.2f}"],
        ['', ''],
        ['COSTI', ''],
        ['Acquisti (Fatture Ricevute)', f"€ {ce['costi']['acquisti']:,.2f}"],
        ['Note di Credito Ricevute', f"-€ {ce['costi']['note_credito']:,.2f}"],
        ['TOTALE COSTI (Netto)', f"€ {ce['costi']['totale']:,.2f}"],
        ['', ''],
        ['RISULTATO', f"€ {utile_perdita:,.2f}"]
    ]
    
    ce_table = Table(ce_data, colWidths=[10*cm, 6*cm])
    # Table rows: 0=RICAVI header, 1=Corrispettivi, 2=TOTALE RICAVI, 3=empty, 
    #             4=COSTI header, 5=Acquisti, 6=Note Credito, 7=TOTALE COSTI, 8=empty, 9=RISULTATO
    ce_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dcfce7')),  # RICAVI header
        ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#22c55e')),  # TOTALE RICAVI
        ('BACKGROUND', (0, 4), (-1, 4), colors.HexColor('#fee2e2')),  # COSTI header
        ('BACKGROUND', (0, 7), (-1, 7), colors.HexColor('#ef4444')),  # TOTALE COSTI
        ('BACKGROUND', (0, 9), (-1, 9), colors.HexColor('#1e293b') if utile_perdita >= 0 else colors.HexColor('#dc2626')),  # RISULTATO
        ('TEXTCOLOR', (0, 2), (-1, 2), colors.white),
        ('TEXTCOLOR', (0, 7), (-1, 7), colors.white),
        ('TEXTCOLOR', (0, 9), (-1, 9), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 2), (-1, 2), 'Helvetica-Bold'),
        ('FONTNAME', (0, 4), (-1, 4), 'Helvetica-Bold'),
        ('FONTNAME', (0, 7), (-1, 7), 'Helvetica-Bold'),
        ('FONTNAME', (0, 9), (-1, 9), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.gray),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(ce_table)
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=bilancio_{anno}.pdf"}
    )



@router.get("/confronto-annuale")
@handle_errors
async def get_confronto_annuale(
    anno_corrente: int = Query(..., description="Anno corrente"),
    anno_precedente: int = Query(None, description="Anno precedente (default: anno_corrente - 1)")
) -> Dict[str, Any]:
    """
    Confronto anno su anno del Conto Economico.
    Mostra variazioni assolute e percentuali tra due anni.
    """
    if not anno_precedente:
        anno_precedente = anno_corrente - 1
    
    # Ottieni dati per entrambi gli anni usando le funzioni helper
    ce_corrente = await _get_conto_economico_data(anno_corrente)
    ce_precedente = await _get_conto_economico_data(anno_precedente)
    
    sp_corrente = await _get_stato_patrimoniale_data(anno_corrente)
    sp_precedente = await _get_stato_patrimoniale_data(anno_precedente)
    
    def calc_variazione(attuale: float, precedente: float) -> Dict[str, Any]:
        """Calcola variazione assoluta e percentuale."""
        variazione_abs = attuale - precedente
        variazione_pct = ((attuale - precedente) / precedente * 100) if precedente != 0 else 0
        return {
            "attuale": round(attuale, 2),
            "precedente": round(precedente, 2),
            "variazione": round(variazione_abs, 2),
            "variazione_pct": round(variazione_pct, 1),
            "trend": "up" if variazione_abs > 0 else ("down" if variazione_abs < 0 else "stable")
        }
    
    # Confronto Conto Economico
    # NOTA: I ricavi derivano SOLO dai corrispettivi (vendite al pubblico)
    # I costi derivano dalle fatture ricevute - note credito
    confronto_ce = {
        "ricavi": {
            "corrispettivi": calc_variazione(
                ce_corrente["ricavi"]["corrispettivi"],
                ce_precedente["ricavi"]["corrispettivi"]
            ),
            "totale_ricavi": calc_variazione(
                ce_corrente["ricavi"]["totale"],
                ce_precedente["ricavi"]["totale"]
            )
        },
        "costi": {
            "acquisti": calc_variazione(
                ce_corrente["costi"]["acquisti"],
                ce_precedente["costi"]["acquisti"]
            ),
            "note_credito": calc_variazione(
                ce_corrente["costi"]["note_credito"],
                ce_precedente["costi"]["note_credito"]
            ),
            "totale_costi": calc_variazione(
                ce_corrente["costi"]["totale"],
                ce_precedente["costi"]["totale"]
            )
        },
        "risultato": {
            "risultato_operativo": calc_variazione(
                ce_corrente["risultato"]["risultato_operativo"],
                ce_precedente["risultato"]["risultato_operativo"]
            ),
            "utile_lordo": calc_variazione(
                ce_corrente["risultato"]["utile_lordo"],
                ce_precedente["risultato"]["utile_lordo"]
            ),
            "utile_netto": calc_variazione(
                ce_corrente["risultato"]["utile_netto"],
                ce_precedente["risultato"]["utile_netto"]
            )
        }
    }
    
    # Confronto Stato Patrimoniale
    confronto_sp = {
        "attivo": {
            "cassa": calc_variazione(
                sp_corrente["attivo"]["disponibilita_liquide"]["cassa"],
                sp_precedente["attivo"]["disponibilita_liquide"]["cassa"]
            ),
            "banca": calc_variazione(
                sp_corrente["attivo"]["disponibilita_liquide"]["banca"],
                sp_precedente["attivo"]["disponibilita_liquide"]["banca"]
            ),
            "crediti": calc_variazione(
                sp_corrente["attivo"]["crediti"]["totale"],
                sp_precedente["attivo"]["crediti"]["totale"]
            ),
            "totale_attivo": calc_variazione(
                sp_corrente["attivo"]["totale_attivo"],
                sp_precedente["attivo"]["totale_attivo"]
            )
        },
        "passivo": {
            "debiti": calc_variazione(
                sp_corrente["passivo"]["debiti"]["totale"],
                sp_precedente["passivo"]["debiti"]["totale"]
            ),
            "patrimonio_netto": calc_variazione(
                sp_corrente["passivo"]["patrimonio_netto"],
                sp_precedente["passivo"]["patrimonio_netto"]
            )
        }
    }
    
    # KPI di performance
    margine_lordo_corrente = (ce_corrente["risultato"]["utile_lordo"] / ce_corrente["ricavi"]["totale"] * 100) if ce_corrente["ricavi"]["totale"] > 0 else 0
    margine_lordo_precedente = (ce_precedente["risultato"]["utile_lordo"] / ce_precedente["ricavi"]["totale"] * 100) if ce_precedente["ricavi"]["totale"] > 0 else 0
    
    roi_corrente = (ce_corrente["risultato"]["utile_netto"] / sp_corrente["attivo"]["totale_attivo"] * 100) if sp_corrente["attivo"]["totale_attivo"] > 0 else 0
    roi_precedente = (ce_precedente["risultato"]["utile_netto"] / sp_precedente["attivo"]["totale_attivo"] * 100) if sp_precedente["attivo"]["totale_attivo"] > 0 else 0
    
    kpi = {
        "margine_lordo_pct": calc_variazione(margine_lordo_corrente, margine_lordo_precedente),
        "roi_pct": calc_variazione(roi_corrente, roi_precedente),
        "crescita_ricavi_pct": round(confronto_ce["ricavi"]["totale_ricavi"]["variazione_pct"], 1),
        "crescita_costi_pct": round(confronto_ce["costi"]["totale_costi"]["variazione_pct"], 1)
    }
    
    return {
        "anno_corrente": anno_corrente,
        "anno_precedente": anno_precedente,
        "conto_economico": confronto_ce,
        "stato_patrimoniale": confronto_sp,
        "kpi": kpi,
        "sintesi": {
            "ricavi_trend": "📈 In crescita" if confronto_ce["ricavi"]["totale_ricavi"]["trend"] == "up" else ("📉 In calo" if confronto_ce["ricavi"]["totale_ricavi"]["trend"] == "down" else "➡️ Stabile"),
            "utile_trend": "📈 In crescita" if confronto_ce["risultato"]["utile_netto"]["trend"] == "up" else ("📉 In calo" if confronto_ce["risultato"]["utile_netto"]["trend"] == "down" else "➡️ Stabile"),
            "liquidita_trend": "📈 In crescita" if confronto_sp["attivo"]["totale_attivo"]["trend"] == "up" else ("📉 In calo" if confronto_sp["attivo"]["totale_attivo"]["trend"] == "down" else "➡️ Stabile")
        }
    }


# Helper functions per evitare problemi con Query params
async def _get_stato_patrimoniale_data(anno: int) -> Dict[str, Any]:
    """Helper interno per ottenere stato patrimoniale."""
    db = Database.get_db()
    
    data_fine = f"{anno}-12-31"
    
    # Cassa
    pipeline_cassa = [
        {"$match": {"data": {"$lte": data_fine}}},
        {"$group": {
            "_id": None,
            "entrate": {"$sum": {"$cond": [{"$eq": ["$tipo", "entrata"]}, "$importo", 0]}},
            "uscite": {"$sum": {"$cond": [{"$eq": ["$tipo", "uscita"]}, "$importo", 0]}}
        }}
    ]
    cassa_result = await db[COLLECTION_PRIMA_NOTA_CASSA].aggregate(pipeline_cassa).to_list(1)
    saldo_cassa = 0
    if cassa_result:
        saldo_cassa = cassa_result[0].get("entrate", 0) - cassa_result[0].get("uscite", 0)
    
    # Banca
    pipeline_banca = [
        {"$match": {"data": {"$lte": data_fine}}},
        {"$group": {
            "_id": None,
            "entrate": {"$sum": {"$cond": [{"$eq": ["$tipo", "entrata"]}, "$importo", 0]}},
            "uscite": {"$sum": {"$cond": [{"$eq": ["$tipo", "uscita"]}, "$importo", 0]}}
        }}
    ]
    banca_result = await db[COLLECTION_PRIMA_NOTA_BANCA].aggregate(pipeline_banca).to_list(1)
    saldo_banca = 0
    if banca_result:
        saldo_banca = banca_result[0].get("entrate", 0) - banca_result[0].get("uscite", 0)
    
    # Crediti
    crediti = await db[Collections.INVOICES].aggregate([
        {"$match": {
            "tipo_documento": {"$in": ["TD01", "TD24", "TD26"]},
            "status": {"$ne": "paid"},
            "invoice_date": {"$lte": data_fine}
        }},
        {"$group": {"_id": None, "totale": {"$sum": "$total_amount"}}}
    ]).to_list(1)
    totale_crediti = crediti[0]["totale"] if crediti else 0
    
    # Debiti
    debiti = await db[Collections.INVOICES].aggregate([
        {"$match": {
            "tipo_documento": {"$nin": ["TD01", "TD24", "TD26"]},
            "status": {"$ne": "paid"},
            "pagato": {"$ne": True},
            "invoice_date": {"$lte": data_fine}
        }},
        {"$group": {"_id": None, "totale": {"$sum": "$total_amount"}}}
    ]).to_list(1)
    totale_debiti = debiti[0]["totale"] if debiti else 0
    
    totale_attivo = saldo_cassa + saldo_banca + totale_crediti
    totale_passivo = totale_debiti
    patrimonio_netto = totale_attivo - totale_passivo
    
    return {
        "anno": anno,
        "attivo": {
            "disponibilita_liquide": {
                "cassa": round(saldo_cassa, 2),
                "banca": round(saldo_banca, 2),
                "totale": round(saldo_cassa + saldo_banca, 2)
            },
            "crediti": {
                "totale": round(totale_crediti, 2)
            },
            "totale_attivo": round(totale_attivo, 2)
        },
        "passivo": {
            "debiti": {
                "totale": round(totale_debiti, 2)
            },
            "patrimonio_netto": round(patrimonio_netto, 2)
        }
    }


async def _get_conto_economico_data(anno: int) -> Dict[str, Any]:
    """
    Helper interno per ottenere conto economico.
    
    LOGICA CONTABILE CORRETTA:
    - Ricavi = SOLO Corrispettivi (vendite al pubblico)
    - Costi = Fatture Ricevute (da fornitori) - Note Credito
    
    NOTA: Tutte le fatture nella collezione 'invoices' sono RICEVUTE (acquisti).
    Non esistono fatture emesse a clienti in questo sistema.
    """
    db = Database.get_db()
    
    data_inizio = f"{anno}-01-01"
    data_fine = f"{anno}-12-31"
    
    # === RICAVI ===
    # Solo corrispettivi (vendite al pubblico)
    corrispettivi_result = await db["corrispettivi"].aggregate([
        {"$match": {
            "data": {"$gte": data_inizio, "$lte": data_fine}
        }},
        {"$group": {
            "_id": None,
            "totale_imponibile": {"$sum": {"$ifNull": ["$totale_imponibile", 0]}}
        }}
    ]).to_list(1)
    totale_corrispettivi = corrispettivi_result[0]["totale_imponibile"] if corrispettivi_result else 0
    
    # === COSTI ===
    # TUTTE le fatture ricevute (escluse solo le note credito)
    fatture_ricevute = await db[Collections.INVOICES].aggregate([
        {"$match": {
            "tipo_documento": {"$nin": ["TD04", "TD08"]},  # Escludi solo Note Credito
            "$or": [
                {"invoice_date": {"$gte": data_inizio, "$lte": data_fine}},
                {"data_ricezione": {"$gte": data_inizio, "$lte": data_fine}}
            ]
        }},
        {"$group": {
            "_id": None,
            "totale": {"$sum": {"$ifNull": ["$imponibile", {"$subtract": ["$total_amount", {"$ifNull": ["$iva", 0]}]}]}}
        }}
    ]).to_list(1)
    totale_acquisti = fatture_ricevute[0]["totale"] if fatture_ricevute else 0
    
    # Note Credito (riducono i costi)
    note_credito = await db[Collections.INVOICES].aggregate([
        {"$match": {
            "tipo_documento": {"$in": ["TD04", "TD08"]},
            "$or": [
                {"invoice_date": {"$gte": data_inizio, "$lte": data_fine}},
                {"data_ricezione": {"$gte": data_inizio, "$lte": data_fine}}
            ]
        }},
        {"$group": {
            "_id": None,
            "totale": {"$sum": {"$ifNull": ["$imponibile", {"$subtract": ["$total_amount", {"$ifNull": ["$iva", 0]}]}]}}
        }}
    ]).to_list(1)
    totale_note_credito = note_credito[0]["totale"] if note_credito else 0
    
    # Calcoli finali
    totale_ricavi = totale_corrispettivi
    costi_netti = totale_acquisti - totale_note_credito
    risultato_operativo = totale_ricavi - costi_netti
    
    # Stima imposte (IRES 24% + IRAP 3.9% = ~28%)
    aliquota_imposte = 0.28
    utile_netto = risultato_operativo * (1 - aliquota_imposte) if risultato_operativo > 0 else risultato_operativo
    
    return {
        "anno": anno,
        "ricavi": {
            "corrispettivi": round(totale_corrispettivi, 2),
            "totale": round(totale_ricavi, 2)
        },
        "costi": {
            "acquisti": round(totale_acquisti, 2),
            "note_credito": round(totale_note_credito, 2),
            "costi_netti": round(costi_netti, 2),
            "totale": round(costi_netti, 2)
        },
        "risultato": {
            "risultato_operativo": round(risultato_operativo, 2),
            "utile_lordo": round(risultato_operativo, 2),
            "utile_netto": round(utile_netto, 2)
        }
    }



@router.get("/export/pdf/confronto")
@handle_errors
async def export_confronto_pdf(
    anno_corrente: int = Query(...),
    anno_precedente: int = Query(None)
) -> StreamingResponse:
    """
    Esporta il bilancio comparativo anno su anno in PDF.
    """
    if not anno_precedente:
        anno_precedente = anno_corrente - 1
    
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
        from reportlab.lib.units import cm
    except ImportError:
        raise HTTPException(status_code=500, detail="reportlab non installato")
    
    # Ottieni dati confronto
    confronto = await get_confronto_annuale(anno_corrente=anno_corrente, anno_precedente=anno_precedente)
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm, leftMargin=1.5*cm, rightMargin=1.5*cm)
    elements = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=20, textColor=colors.HexColor('#1e40af'), spaceAfter=20)
    subtitle_style = ParagraphStyle('Subtitle', parent=styles['Heading2'], fontSize=14, textColor=colors.HexColor('#374151'), spaceAfter=10)
    
    # Titolo
    elements.append(Paragraph("📊 Bilancio Comparativo", title_style))
    elements.append(Paragraph(f"<b>{anno_precedente}</b> vs <b>{anno_corrente}</b>", subtitle_style))
    elements.append(Spacer(1, 20))
    
    # Helper per formattare
    def fmt_eur(val):
        return f"€ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    
    def fmt_pct(val):
        return f"{val:+.1f}%"
    
    def get_trend_symbol(trend):
        if trend == "up": return "▲"
        if trend == "down": return "▼"
        return "="
    
    # CONTO ECONOMICO
    elements.append(Paragraph("📈 CONTO ECONOMICO", subtitle_style))
    
    ce = confronto["conto_economico"]
    # NOTA: I ricavi derivano SOLO dai corrispettivi (vendite al pubblico)
    ce_data = [
        ["Voce", f"{anno_precedente}", f"{anno_corrente}", "Variazione", "%"],
        ["RICAVI", "", "", "", ""],
        ["  Corrispettivi", fmt_eur(ce["ricavi"]["corrispettivi"]["precedente"]), fmt_eur(ce["ricavi"]["corrispettivi"]["attuale"]), fmt_eur(ce["ricavi"]["corrispettivi"]["variazione"]), fmt_pct(ce["ricavi"]["corrispettivi"]["variazione_pct"])],
        ["  TOTALE RICAVI", fmt_eur(ce["ricavi"]["totale_ricavi"]["precedente"]), fmt_eur(ce["ricavi"]["totale_ricavi"]["attuale"]), fmt_eur(ce["ricavi"]["totale_ricavi"]["variazione"]), fmt_pct(ce["ricavi"]["totale_ricavi"]["variazione_pct"])],
        ["COSTI", "", "", "", ""],
        ["  Acquisti", fmt_eur(ce["costi"]["acquisti"]["precedente"]), fmt_eur(ce["costi"]["acquisti"]["attuale"]), fmt_eur(ce["costi"]["acquisti"]["variazione"]), fmt_pct(ce["costi"]["acquisti"]["variazione_pct"])],
        ["  Note Credito", fmt_eur(ce["costi"]["note_credito"]["precedente"]), fmt_eur(ce["costi"]["note_credito"]["attuale"]), fmt_eur(ce["costi"]["note_credito"]["variazione"]), fmt_pct(ce["costi"]["note_credito"]["variazione_pct"])],
        ["  TOTALE COSTI", fmt_eur(ce["costi"]["totale_costi"]["precedente"]), fmt_eur(ce["costi"]["totale_costi"]["attuale"]), fmt_eur(ce["costi"]["totale_costi"]["variazione"]), fmt_pct(ce["costi"]["totale_costi"]["variazione_pct"])],
        ["RISULTATO", "", "", "", ""],
        ["  Utile lordo", fmt_eur(ce["risultato"]["utile_lordo"]["precedente"]), fmt_eur(ce["risultato"]["utile_lordo"]["attuale"]), fmt_eur(ce["risultato"]["utile_lordo"]["variazione"]), fmt_pct(ce["risultato"]["utile_lordo"]["variazione_pct"])],
        ["  Utile netto", fmt_eur(ce["risultato"]["utile_netto"]["precedente"]), fmt_eur(ce["risultato"]["utile_netto"]["attuale"]), fmt_eur(ce["risultato"]["utile_netto"]["variazione"]), fmt_pct(ce["risultato"]["utile_netto"]["variazione_pct"])],
    ]
    
    ce_table = Table(ce_data, colWidths=[5*cm, 3.5*cm, 3.5*cm, 3*cm, 2*cm])
    ce_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#f0f9ff')),
        ('BACKGROUND', (0, 4), (-1, 4), colors.HexColor('#fef2f2')),
        ('BACKGROUND', (0, 8), (-1, 8), colors.HexColor('#f0fdf4')),
        ('FONTNAME', (0, 3), (-1, 3), 'Helvetica-Bold'),
        ('FONTNAME', (0, 7), (-1, 7), 'Helvetica-Bold'),
        ('FONTNAME', (0, 10), (-1, 10), 'Helvetica-Bold'),
    ]))
    elements.append(ce_table)
    elements.append(Spacer(1, 30))
    
    # STATO PATRIMONIALE
    elements.append(Paragraph("🏦 STATO PATRIMONIALE", subtitle_style))
    
    sp = confronto["stato_patrimoniale"]
    sp_data = [
        ["Voce", f"{anno_precedente}", f"{anno_corrente}", "Variazione", "%"],
        ["ATTIVO", "", "", "", ""],
        ["  Cassa", fmt_eur(sp["attivo"]["cassa"]["precedente"]), fmt_eur(sp["attivo"]["cassa"]["attuale"]), fmt_eur(sp["attivo"]["cassa"]["variazione"]), fmt_pct(sp["attivo"]["cassa"]["variazione_pct"])],
        ["  Banca", fmt_eur(sp["attivo"]["banca"]["precedente"]), fmt_eur(sp["attivo"]["banca"]["attuale"]), fmt_eur(sp["attivo"]["banca"]["variazione"]), fmt_pct(sp["attivo"]["banca"]["variazione_pct"])],
        ["  Crediti", fmt_eur(sp["attivo"]["crediti"]["precedente"]), fmt_eur(sp["attivo"]["crediti"]["attuale"]), fmt_eur(sp["attivo"]["crediti"]["variazione"]), fmt_pct(sp["attivo"]["crediti"]["variazione_pct"])],
        ["  TOTALE ATTIVO", fmt_eur(sp["attivo"]["totale_attivo"]["precedente"]), fmt_eur(sp["attivo"]["totale_attivo"]["attuale"]), fmt_eur(sp["attivo"]["totale_attivo"]["variazione"]), fmt_pct(sp["attivo"]["totale_attivo"]["variazione_pct"])],
        ["PASSIVO", "", "", "", ""],
        ["  Debiti", fmt_eur(sp["passivo"]["debiti"]["precedente"]), fmt_eur(sp["passivo"]["debiti"]["attuale"]), fmt_eur(sp["passivo"]["debiti"]["variazione"]), fmt_pct(sp["passivo"]["debiti"]["variazione_pct"])],
        ["  Patrimonio netto", fmt_eur(sp["passivo"]["patrimonio_netto"]["precedente"]), fmt_eur(sp["passivo"]["patrimonio_netto"]["attuale"]), fmt_eur(sp["passivo"]["patrimonio_netto"]["variazione"]), fmt_pct(sp["passivo"]["patrimonio_netto"]["variazione_pct"])],
    ]
    
    sp_table = Table(sp_data, colWidths=[5*cm, 3.5*cm, 3.5*cm, 3*cm, 2*cm])
    sp_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#059669')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#f0fdf4')),
        ('BACKGROUND', (0, 6), (-1, 6), colors.HexColor('#fef2f2')),
        ('FONTNAME', (0, 5), (-1, 5), 'Helvetica-Bold'),
        ('FONTNAME', (0, 8), (-1, 8), 'Helvetica-Bold'),
    ]))
    elements.append(sp_table)
    elements.append(Spacer(1, 30))
    
    # KPI
    elements.append(Paragraph("📊 INDICATORI DI PERFORMANCE", subtitle_style))
    
    kpi = confronto["kpi"]
    sintesi = confronto["sintesi"]
    
    kpi_text = f"""
    <b>Margine Lordo:</b> {kpi['margine_lordo_pct']['attuale']:.1f}% ({fmt_pct(kpi['margine_lordo_pct']['variazione_pct'])} vs anno prec.)<br/>
    <b>ROI:</b> {kpi['roi_pct']['attuale']:.1f}% ({fmt_pct(kpi['roi_pct']['variazione_pct'])} vs anno prec.)<br/>
    <b>Crescita Ricavi:</b> {fmt_pct(kpi['crescita_ricavi_pct'])}<br/>
    <b>Crescita Costi:</b> {fmt_pct(kpi['crescita_costi_pct'])}<br/><br/>
    <b>Sintesi:</b><br/>
    • Ricavi: {sintesi['ricavi_trend']}<br/>
    • Utile: {sintesi['utile_trend']}<br/>
    • Liquidità: {sintesi['liquidita_trend']}
    """
    
    elements.append(Paragraph(kpi_text, styles['Normal']))
    
    # Footer
    elements.append(Spacer(1, 40))
    footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=9, textColor=colors.gray)
    elements.append(Paragraph(f"Documento generato il {datetime.now().strftime('%d/%m/%Y %H:%M')} - Azienda Semplice ERP", footer_style))
    
    doc.build(elements)
    buffer.seek(0)
    
    filename = f"Bilancio_Comparativo_{anno_precedente}_vs_{anno_corrente}.pdf"
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
