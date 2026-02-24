"""
Liquidazione IVA Router - Calcolo preciso IVA mensile per confronto con commercialista.

================================================================================
LOGICA LIQUIDAZIONE IVA - CONTABILITÀ ITALIANA
================================================================================

IVA A DEBITO (da versare all'Erario):
-------------------------------------
- Fonte: SOLO corrispettivi (collezione 'corrispettivi')
- Campo: totale_iva
- IMPORTANTE: Le fatture emesse a clienti NON generano IVA debito aggiuntiva!
             L'IVA è già inclusa nei corrispettivi (lo scontrino originale)

IVA A CREDITO (detraibile):
---------------------------
- Fonte: Fatture ricevute da fornitori (collezione 'invoices')
- Campo: iva
- Tipi documento: TD01, TD24, TD02, TD06, TD27
- Note Credito (TD04, TD08): riducono l'IVA credito

DEROGHE TEMPORALI:
------------------
1. Regola 15 giorni: fattura mese precedente registrata entro il 15 del mese corrente
2. Regola 12 giorni: fattura registrata entro 12 giorni dalla data operazione

FORMULA:
--------
IVA DA VERSARE = IVA DEBITO (corrispettivi) - IVA CREDITO (fatture - NC)
Se negativo = credito da riportare al mese successivo

================================================================================
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import Dict, Any
from datetime import date
import logging
import io

from app.database import Database
from app.utils.error_handler import handle_errors
from app.services.liquidazione_iva import (
    compute_vat_liquidation_from_db,
    export_liquidazione_iva_pdf,
    month_bounds,
    MESI_ITALIANI
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/liquidazione-iva", tags=["Liquidazione IVA"])


@router.get("/calcola/{anno}/{mese}")
@handle_errors
async def calcola_liquidazione_iva(
    anno: int,
    mese: int,
    credito_precedente: float = Query(0, description="Credito IVA da riportare dal mese precedente")
) -> Dict[str, Any]:
    """
    Calcola la liquidazione IVA per un mese specifico.
    
    Logica:
    - IVA a DEBITO: somma IVA da corrispettivi del periodo
    - IVA a CREDITO: somma IVA da fatture acquisto ricevute nel periodo
    - Deroghe temporali: regola 15 giorni e 12 giorni per fatture mese precedente
    - Note Credito (TD04, TD08): sottratte dal totale IVA credito
    
    Args:
        anno: Anno (es. 2025)
        mese: Mese (1-12)
        credito_precedente: Credito IVA da riportare (default 0)
    
    Returns:
        Dettaglio completo della liquidazione IVA
    """
    if mese < 1 or mese > 12:
        raise HTTPException(status_code=400, detail="Mese deve essere compreso tra 1 e 12")
    
    if anno < 2020 or anno > 2030:
        raise HTTPException(status_code=400, detail="Anno non valido")
    
    db = Database.get_db()
    
    try:
        period_start, period_end = month_bounds(anno, mese)
        month_prefix = f"{anno}-{mese:02d}"
        
        # Recupera fatture del periodo (usa data_ricezione con fallback a invoice_date)
        # Include anche fatture del mese precedente per deroghe temporali
        prev_month = mese - 1 if mese > 1 else 12
        prev_year = anno if mese > 1 else anno - 1
        prev_prefix = f"{prev_year}-{prev_month:02d}"
        
        fatture_query = {
            "$or": [
                # Fatture con data_ricezione nel periodo
                {"data_ricezione": {"$regex": f"^{month_prefix}"}},
                # Fatture senza data_ricezione ma con invoice_date nel periodo
                {
                    "$and": [
                        {"data_ricezione": {"$exists": False}},
                        {"invoice_date": {"$regex": f"^{month_prefix}"}}
                    ]
                },
                # Fatture mese precedente (per deroghe temporali)
                {"invoice_date": {"$regex": f"^{prev_prefix}"}},
            ]
        }
        
        fatture = await db["invoices"].find(fatture_query, {"_id": 0}).to_list(5000)
        logger.info(f"Fatture trovate per liquidazione {mese}/{anno}: {len(fatture)}")
        
        # Recupera corrispettivi del periodo
        corrispettivi = await db["corrispettivi"].find(
            {"data": {"$regex": f"^{month_prefix}"}},
            {"_id": 0}
        ).to_list(5000)
        logger.info(f"Corrispettivi trovati per liquidazione {mese}/{anno}: {len(corrispettivi)}")
        
        # Calcola liquidazione
        result = compute_vat_liquidation_from_db(
            year=anno,
            month=mese,
            fatture=fatture,
            corrispettivi=corrispettivi,
            prev_credit_carry=credito_precedente
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Errore calcolo liquidazione IVA: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/confronto/{anno}/{mese}")
@handle_errors
async def confronto_iva_commercialista(
    anno: int,
    mese: int,
    iva_debito_commercialista: float = Query(..., description="IVA a debito calcolata dal commercialista"),
    iva_credito_commercialista: float = Query(..., description="IVA a credito calcolata dal commercialista")
) -> Dict[str, Any]:
    """
    Confronta la liquidazione IVA calcolata con quella del commercialista.
    
    Utile per identificare discrepanze e verificare la correttezza dei dati.
    
    Args:
        anno: Anno
        mese: Mese (1-12)
        iva_debito_commercialista: IVA a debito da confrontare
        iva_credito_commercialista: IVA a credito da confrontare
    
    Returns:
        Confronto dettagliato con evidenza delle differenze
    """
    # Calcola liquidazione interna
    result = await calcola_liquidazione_iva(anno, mese)
    
    # Calcola differenze
    diff_debito = result["iva_debito"] - iva_debito_commercialista
    diff_credito = result["iva_credito"] - iva_credito_commercialista
    diff_saldo = (result["iva_debito"] - result["iva_credito"]) - (iva_debito_commercialista - iva_credito_commercialista)
    
    # Soglia di tolleranza (1 euro)
    tolleranza = 1.0
    
    return {
        "periodo": f"{MESI_ITALIANI[mese]} {anno}",
        "calcolo_interno": {
            "iva_debito": result["iva_debito"],
            "iva_credito": result["iva_credito"],
            "saldo": round(result["iva_debito"] - result["iva_credito"], 2)
        },
        "calcolo_commercialista": {
            "iva_debito": iva_debito_commercialista,
            "iva_credito": iva_credito_commercialista,
            "saldo": round(iva_debito_commercialista - iva_credito_commercialista, 2)
        },
        "differenze": {
            "iva_debito": round(diff_debito, 2),
            "iva_credito": round(diff_credito, 2),
            "saldo": round(diff_saldo, 2)
        },
        "esito": {
            "coincide": abs(diff_debito) <= tolleranza and abs(diff_credito) <= tolleranza,
            "tolleranza_euro": tolleranza,
            "note": "✅ I calcoli coincidono" if abs(diff_debito) <= tolleranza and abs(diff_credito) <= tolleranza 
                    else "⚠️ Ci sono differenze significative da verificare"
        },
        "dettaglio_interno": result
    }


@router.get("/export/pdf/{anno}/{mese}")
@handle_errors
async def export_liquidazione_pdf(
    anno: int,
    mese: int,
    credito_precedente: float = Query(0, description="Credito IVA da riportare")
) -> StreamingResponse:
    """
    Esporta la liquidazione IVA in formato PDF.
    
    Args:
        anno: Anno
        mese: Mese (1-12)
        credito_precedente: Credito IVA da mese precedente
    
    Returns:
        PDF con dettaglio liquidazione IVA
    """
    # Calcola liquidazione
    result = await calcola_liquidazione_iva(anno, mese, credito_precedente)
    
    try:
        # Genera PDF
        pdf_bytes = export_liquidazione_iva_pdf(
            result=result,
            azienda_nome="Ceraldi Group S.R.L."
        )
        
        filename = f"Liquidazione_IVA_{MESI_ITALIANI[mese]}_{anno}.pdf"
        
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except ImportError:
        raise HTTPException(
            status_code=500, 
            detail="reportlab non installato. Esegui: pip install reportlab"
        )


@router.get("/riepilogo-annuale/{anno}")
@handle_errors
async def riepilogo_annuale(anno: int) -> Dict[str, Any]:
    """
    Riepilogo della liquidazione IVA per tutto l'anno.
    
    Calcola la liquidazione per ogni mese e mostra il progressivo.
    
    Args:
        anno: Anno di riferimento
    
    Returns:
        Riepilogo annuale con dettaglio mensile
    """
    risultati_mensili = []
    credito_progressivo = 0
    
    for mese in range(1, 13):
        try:
            result = await calcola_liquidazione_iva(anno, mese, credito_progressivo)
            
            risultati_mensili.append({
                "mese": mese,
                "mese_nome": MESI_ITALIANI[mese],
                "iva_debito": result["iva_debito"],
                "iva_credito": result["iva_credito"],
                "credito_precedente": result["credito_precedente"],
                "iva_da_versare": result["iva_da_versare"],
                "credito_da_riportare": result["credito_da_riportare"],
                "stato": result["stato"],
                "fatture_count": result["statistiche"]["fatture_incluse"],
                "corrispettivi_count": result["statistiche"]["corrispettivi_count"]
            })
            
            # Aggiorna credito progressivo per il mese successivo
            credito_progressivo = result["credito_da_riportare"]
            
        except Exception as e:
            logger.warning(f"Errore calcolo mese {mese}: {e}")
            risultati_mensili.append({
                "mese": mese,
                "mese_nome": MESI_ITALIANI[mese],
                "errore": str(e)
            })
    
    # Totali annuali
    tot_debito = sum(r.get("iva_debito", 0) for r in risultati_mensili if "iva_debito" in r)
    tot_credito = sum(r.get("iva_credito", 0) for r in risultati_mensili if "iva_credito" in r)
    tot_versato = sum(r.get("iva_da_versare", 0) for r in risultati_mensili if "iva_da_versare" in r)
    
    return {
        "anno": anno,
        "mensile": risultati_mensili,
        "totali": {
            "iva_debito_totale": round(tot_debito, 2),
            "iva_credito_totale": round(tot_credito, 2),
            "iva_versata_totale": round(tot_versato, 2),
            "credito_finale": round(credito_progressivo, 2),
            "saldo_annuale": round(tot_debito - tot_credito, 2)
        }
    }


@router.get("/dettaglio-fatture/{anno}/{mese}")
@handle_errors
async def dettaglio_fatture_liquidazione(
    anno: int,
    mese: int,
    tipo: str = Query("tutte", description="tutte, incluse, escluse")
) -> Dict[str, Any]:
    """
    Mostra il dettaglio delle fatture incluse/escluse dalla liquidazione IVA.
    
    Utile per debug e verifica con il commercialista.
    
    Args:
        anno: Anno
        mese: Mese (1-12)
        tipo: Filtro (tutte, incluse, escluse)
    
    Returns:
        Lista fatture con motivo inclusione/esclusione
    """
    from app.services.liquidazione_iva import month_bounds, prev_month, within_12_days_rule, parse_date, NOTE_CREDITO_TYPES
    
    db = Database.get_db()
    
    period_start, period_end = month_bounds(anno, mese)
    prev_y, prev_m = prev_month(anno, mese)
    prev_start, prev_end = month_bounds(prev_y, prev_m)
    fifteenth = date(anno, mese, 15)
    
    month_prefix = f"{anno}-{mese:02d}"
    prev_prefix = f"{prev_y}-{prev_m:02d}"
    
    # Query ampliata per includere anche mese precedente
    fatture = await db["invoices"].find({
        "$or": [
            {"data_ricezione": {"$regex": f"^{month_prefix}"}},
            {"$and": [{"data_ricezione": {"$exists": False}}, {"invoice_date": {"$regex": f"^{month_prefix}"}}]},
            {"invoice_date": {"$regex": f"^{prev_prefix}"}},
        ]
    }, {"_id": 0}).to_list(5000)
    
    risultato = {"incluse": [], "escluse": []}
    
    for inv in fatture:
        op_date = parse_date(inv.get("invoice_date", ""))
        reg_date = parse_date(inv.get("data_ricezione", "") or inv.get("invoice_date", ""))
        
        dettaglio = {
            "invoice_number": inv.get("invoice_number"),
            "supplier_name": inv.get("supplier_name"),
            "invoice_date": inv.get("invoice_date"),
            "data_ricezione": inv.get("data_ricezione"),
            "total_amount": inv.get("total_amount"),
            "iva": inv.get("iva"),
            "tipo_documento": inv.get("tipo_documento"),
            "is_nota_credito": inv.get("tipo_documento") in NOTE_CREDITO_TYPES
        }
        
        if not op_date or not reg_date:
            dettaglio["motivo_esclusione"] = "Date mancanti"
            risultato["escluse"].append(dettaglio)
            continue
        
        # Verifica criteri
        same_month = period_start <= op_date <= period_end and reg_date <= period_end
        deroga_15 = prev_start <= op_date <= prev_end and reg_date <= fifteenth and prev_y == anno and mese != 1
        deroga_12 = within_12_days_rule(op_date, reg_date, anno, mese)
        
        if same_month or deroga_15 or deroga_12:
            dettaglio["criterio_inclusione"] = (
                "Stesso mese" if same_month else
                "Deroga 15 giorni" if deroga_15 else
                "Deroga 12 giorni"
            )
            risultato["incluse"].append(dettaglio)
        else:
            dettaglio["motivo_esclusione"] = "Fuori periodo (nessuna deroga applicabile)"
            risultato["escluse"].append(dettaglio)
    
    # Filtra in base al tipo richiesto
    if tipo == "incluse":
        return {"fatture": risultato["incluse"], "count": len(risultato["incluse"])}
    elif tipo == "escluse":
        return {"fatture": risultato["escluse"], "count": len(risultato["escluse"])}
    else:
        return {
            "incluse": {"fatture": risultato["incluse"], "count": len(risultato["incluse"])},
            "escluse": {"fatture": risultato["escluse"], "count": len(risultato["escluse"])},
            "totale": len(fatture)
        }
