"""
Router per Verifica Coerenza Dati
API per controllare la consistenza dei dati tra le varie sezioni del gestionale.
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from app.database import Database
from app.services.verifica_coerenza import (
    VerificaCoerenza, 
    esegui_verifica_completa,
    esegui_verifica_iva
)
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

MESI_NOMI = ['', 'Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno',
             'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre']


@router.get("/completa/{anno}")
async def verifica_completa(anno: int) -> Dict[str, Any]:
    """
    Esegue una verifica completa di coerenza dati per l'anno specificato.
    Controlla: IVA, Versamenti, Saldi, F24
    """
    try:
        risultato = await esegui_verifica_completa(anno)
        return risultato
    except Exception as e:
        logger.error(f"Errore verifica completa: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/iva/{anno}/{mese}")
async def verifica_iva_mese(anno: int, mese: int) -> Dict[str, Any]:
    """
    Verifica coerenza IVA per un mese specifico.
    Confronta i valori tra Fatture, Corrispettivi e Liquidazione.
    """
    if mese < 1 or mese > 12:
        raise HTTPException(status_code=400, detail="Mese deve essere tra 1 e 12")
    
    try:
        risultato = await esegui_verifica_iva(anno, mese)
        return risultato
    except Exception as e:
        logger.error(f"Errore verifica IVA: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/discrepanze/{anno}")
async def get_discrepanze(
    anno: int,
    severita: Optional[str] = Query(None, description="Filtra per severità: critical, warning, info")
) -> Dict[str, Any]:
    """
    Ottiene solo le discrepanze trovate per un anno.
    """
    try:
        risultato = await esegui_verifica_completa(anno)
        discrepanze = risultato.get("discrepanze", [])
        
        if severita:
            discrepanze = [d for d in discrepanze if d["severita"] == severita]
        
        return {
            "anno": anno,
            "discrepanze": discrepanze,
            "totale": len(discrepanze),
            "riepilogo": risultato.get("riepilogo", {})
        }
    except Exception as e:
        logger.error(f"Errore recupero discrepanze: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/widget")
async def widget_discrepanze(
    anno: Optional[int] = Query(None, description="Anno da verificare")
) -> Dict[str, Any]:
    """
    Widget veloce per mostrare alert di discrepanze.
    Usato in tutte le pagine del gestionale.
    """
    if not anno:
        anno = datetime.now().year
    
    try:
        db = Database.get_db()
        verificatore = VerificaCoerenza(db)
        
        # Verifica veloce solo per il mese corrente
        mese_corrente = datetime.now().month
        
        # IVA del mese
        iva = await verificatore.verifica_coerenza_iva_tra_pagine(anno, mese_corrente)
        
        # F24 IVA ricevuto dalla commercialista (non un movimento bancario IVA)
        f24_iva = await verificatore.trova_f24_iva_mensile(anno, mese_corrente)
        
        # Raccogli discrepanze
        discrepanze = verificatore.discrepanze
        
        return {
            "anno": anno,
            "mese": mese_corrente,
            "mese_nome": MESI_NOMI[mese_corrente],
            "has_discrepanze": len(discrepanze) > 0,
            "discrepanze": discrepanze[:5],  # Max 5 per il widget
            "totale_discrepanze": len(discrepanze),
            "critical_count": len([d for d in discrepanze if d["severita"] == "critical"]),
            "iva_credito": iva["iva_credito"]["da_fatture"],
            "iva_debito": iva["iva_debito"]["da_corrispettivi"],
            "f24_iva_stato": f24_iva.get("stato"),
            "f24_iva_importo": f24_iva.get("importo_f24"),
        }
    except Exception as e:
        logger.error(f"Errore widget discrepanze: {e}")
        return {
            "anno": anno,
            "has_discrepanze": False,
            "discrepanze": [],
            "error": str(e)
        }


@router.get("/confronto-iva-completo/{anno}")
async def confronto_iva_completo(anno: int) -> Dict[str, Any]:
    """
    Confronto completo IVA per tutto l'anno.
    Mostra mese per mese i valori da ogni fonte.
    """
    try:
        db = Database.get_db()
        verificatore = VerificaCoerenza(db)
        
        confronto_mensile = []
        from app.services.iva_liquidation_query import euros

        totale_credito_fatture_cents = 0
        totale_debito_corrispettivi_cents = 0
        periodi_calcolati = 0
        
        for mese in range(1, 13):
            iva = await verificatore.verifica_coerenza_iva_tra_pagine(anno, mese)
            
            credito = iva["iva_credito"]["da_fatture"]
            debito = iva["iva_debito"]["da_corrispettivi"]
            credito_cents = iva["iva_credito"].get("da_fatture_cents")
            debito_cents = iva["iva_debito"].get("da_corrispettivi_cents")
            f24_iva = iva.get("f24_commercialista") or {}
            periodo_calcolato = credito_cents is not None and debito_cents is not None
            if periodo_calcolato:
                totale_credito_fatture_cents += int(credito_cents)
                totale_debito_corrispettivi_cents += int(debito_cents)
                periodi_calcolati += 1
            saldo_cents = (
                int(debito_cents) - int(credito_cents) if periodo_calcolato else None
            )
            
            confronto_mensile.append({
                "mese": mese,
                "mese_nome": MESI_NOMI[mese],
                "iva_credito_fatture": credito,
                "iva_credito_fatture_cents": credito_cents,
                "iva_debito_corrispettivi": debito,
                "iva_debito_corrispettivi_cents": debito_cents,
                "num_fatture": iva["iva_credito"]["num_fatture"],
                "fatture_con_iva_competenza": (
                    iva["iva_credito"].get("conteggi", {})
                    .get("fatture_incluse_competenza", 0)
                ),
                "fatture_gia_liquidate": (
                    iva["iva_credito"].get("conteggi", {})
                    .get("fatture_gia_utilizzate", 0)
                ),
                "fatture_da_classificare": (
                    iva["iva_credito"].get("conteggi", {})
                    .get("detraibilita_da_verificare", 0)
                ),
                "iva_credito_ancora_disponibile": (
                    iva["iva_credito"].get("ancora_disponibile")
                ),
                "num_corrispettivi": iva["iva_debito"]["num_corrispettivi"],
                "saldo": euros(saldo_cents) if saldo_cents is not None else None,
                "saldo_cents": saldo_cents,
                "da_versare": euros(max(saldo_cents, 0)) if saldo_cents is not None else None,
                "a_credito": euros(max(-saldo_cents, 0)) if saldo_cents is not None else None,
                "periodo_calcolato": periodo_calcolato,
                "stato_calcolo": iva.get("stato_calcolo", "CALCOLATO" if periodo_calcolato else "NON_CALCOLATO"),
                "fonte_calcolo": iva.get("fonte_calcolo"),
                "scadenza_nominale": iva.get("scadenza_nominale"),
                "scadenza_legale": iva.get("scadenza_legale"),
                "codice_tributo_iva": f24_iva.get("codice_tributo"),
                "importo_f24_commercialista": f24_iva.get("importo_f24"),
                "stato_f24": f24_iva.get("stato"),
                "scostamento_f24": f24_iva.get("scostamento_gestionale"),
                "coerente_f24": f24_iva.get("coerente"),
                "f24_multi_tributo": f24_iva.get("f24_multi_tributo", False),
                "altri_codici_tributo": f24_iva.get("altri_codici_tributo", []),
            })
        
        return {
            "anno": anno,
            "mensile": confronto_mensile,
            "totali": {
                "iva_credito_totale": euros(totale_credito_fatture_cents),
                "iva_credito_totale_cents": totale_credito_fatture_cents,
                "iva_debito_totale": euros(totale_debito_corrispettivi_cents),
                "iva_debito_totale_cents": totale_debito_corrispettivi_cents,
                "saldo_annuale": euros(
                    totale_debito_corrispettivi_cents - totale_credito_fatture_cents
                ),
                "saldo_annuale_cents": (
                    totale_debito_corrispettivi_cents - totale_credito_fatture_cents
                ),
                "periodi_calcolati": periodi_calcolati,
                "periodi_non_calcolati": 12 - periodi_calcolati,
            },
            "discrepanze": verificatore.discrepanze
        }
    except Exception as e:
        logger.error(f"Errore confronto IVA completo: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/verifica-bonifici-vs-banca/{anno}")
async def verifica_bonifici_vs_banca(anno: int) -> Dict[str, Any]:
    """
    Verifica che i bonifici registrati corrispondano ai movimenti bancari.
    """
    try:
        db = Database.get_db()
        prefix = f"{anno}"
        
        # Bonifici registrati
        pipeline_bonifici = [
            {"$match": {"data": {"$regex": f"^{prefix}"}}},
            {"$group": {
                "_id": None,
                "totale": {"$sum": "$importo"},
                "count": {"$sum": 1},
                "riconciliati": {"$sum": {"$cond": [{"$eq": ["$riconciliato", True]}, 1, 0]}},
                "totale_riconciliato": {"$sum": {"$cond": [{"$eq": ["$riconciliato", True]}, "$importo", 0]}}
            }}
        ]
        res_bonifici = await db["bonifici_transfers"].aggregate(pipeline_bonifici).to_list(1)
        
        bonifici = res_bonifici[0] if res_bonifici else {
            "totale": 0, "count": 0, "riconciliati": 0, "totale_riconciliato": 0
        }
        
        # Movimenti bancari (bonifici in uscita)
        pipeline_banca = [
            {"$match": {
                "data": {"$regex": f"^{prefix}"},
                "$or": [
                    {"descrizione_originale": {"$regex": "BONIFICO", "$options": "i"}},
                    {"descrizione_originale": {"$regex": "SEPA", "$options": "i"}}
                ],
                "importo": {"$lt": 0}
            }},
            {"$group": {"_id": None, "totale": {"$sum": {"$abs": "$importo"}}, "count": {"$sum": 1}}}
        ]
        res_banca = await db["estratto_conto_movimenti"].aggregate(pipeline_banca).to_list(1)
        
        banca = res_banca[0] if res_banca else {"totale": 0, "count": 0}
        
        differenza = bonifici["totale"] - banca["totale"]
        
        return {
            "anno": anno,
            "bonifici_registrati": {
                "totale": round(bonifici["totale"], 2),
                "count": bonifici["count"],
                "riconciliati": bonifici["riconciliati"],
                "totale_riconciliato": round(bonifici["totale_riconciliato"], 2),
                "non_riconciliati": bonifici["count"] - bonifici["riconciliati"]
            },
            "bonifici_banca": {
                "totale": round(banca["totale"], 2),
                "count": banca["count"]
            },
            "differenza": round(differenza, 2),
            "coerente": abs(differenza) < 1,
            "alert": None if abs(differenza) < 1 else {
                "tipo": "warning" if abs(differenza) < 100 else "critical",
                "messaggio": f"Differenza di {round(differenza, 2)}€ tra bonifici registrati e movimenti bancari"
            }
        }
    except Exception as e:
        logger.error(f"Errore verifica bonifici: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/riepilogo-giornaliero")
async def riepilogo_verifiche_giornaliero() -> Dict[str, Any]:
    """
    Riepilogo giornaliero di tutte le verifiche.
    Da usare come dashboard principale.
    """
    try:
        anno = datetime.now().year
        mese = datetime.now().month
        
        db = Database.get_db()
        verificatore = VerificaCoerenza(db)
        
        # Esegui tutte le verifiche
        verifica = await verificatore.verifica_completa(anno)
        
        # Aggiungi info extra
        verifica["data_verifica"] = datetime.now(timezone.utc).isoformat()
        verifica["mese_corrente"] = MESI_NOMI[mese]
        
        # Stato generale
        if verifica["riepilogo"]["critical"] > 0:
            verifica["stato_generale"] = "CRITICO"
            verifica["stato_colore"] = "red"
        elif verifica["riepilogo"]["warning"] > 0:
            verifica["stato_generale"] = "ATTENZIONE"
            verifica["stato_colore"] = "orange"
        else:
            verifica["stato_generale"] = "OK"
            verifica["stato_colore"] = "green"
        
        return verifica
    except Exception as e:
        logger.error(f"Errore riepilogo giornaliero: {e}")
        raise HTTPException(status_code=500, detail=str(e))
