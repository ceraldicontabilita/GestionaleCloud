"""
Router per Verifica Coerenza Dati
API per controllare la consistenza dei dati tra le varie sezioni del gestionale.
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Dict, Any, Optional
from datetime import datetime
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
        
        # Versamenti
        versamenti = await verificatore.verifica_versamenti_vs_banca(anno, mese_corrente)
        
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
            "versamenti_ok": abs(versamenti.get("differenza", 0)) < 1
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
        totale_credito_fatture = 0
        totale_debito_corrispettivi = 0
        
        for mese in range(1, 13):
            iva = await verificatore.verifica_coerenza_iva_tra_pagine(anno, mese)
            
            credito = iva["iva_credito"]["da_fatture"]
            debito = iva["iva_debito"]["da_corrispettivi"]
            
            totale_credito_fatture += credito
            totale_debito_corrispettivi += debito
            
            confronto_mensile.append({
                "mese": mese,
                "mese_nome": MESI_NOMI[mese],
                "iva_credito_fatture": credito,
                "iva_debito_corrispettivi": debito,
                "num_fatture": iva["iva_credito"]["num_fatture"],
                "num_corrispettivi": iva["iva_debito"]["num_corrispettivi"],
                "saldo": round(debito - credito, 2),
                "da_versare": max(debito - credito, 0),
                "a_credito": max(credito - debito, 0)
            })
        
        return {
            "anno": anno,
            "mensile": confronto_mensile,
            "totali": {
                "iva_credito_totale": round(totale_credito_fatture, 2),
                "iva_debito_totale": round(totale_debito_corrispettivi, 2),
                "saldo_annuale": round(totale_debito_corrispettivi - totale_credito_fatture, 2)
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
        verifica["data_verifica"] = datetime.now().isoformat()
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
