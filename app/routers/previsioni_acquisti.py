"""
Sistema Previsioni Acquisti
Memorizza quantità prodotti da fatture XML e calcola statistiche per previsioni.
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import logging

from app.database import Database

logger = logging.getLogger(__name__)
router = APIRouter()

# Giorni lavorativi annuali per calcolo medie
GIORNI_LAVORATIVI_ANNO = 340
GIORNI_SETTIMANA = 7


async def registra_acquisto_da_fattura(db, fattura: Dict[str, Any]):
    """
    Estrae i prodotti dalla fattura e li registra nella collezione acquisti_prodotti.
    Chiamato ogni volta che viene processato un XML fattura.
    """
    try:
        linee = fattura.get("linee", []) or fattura.get("lines", [])
        if not linee:
            return 0
        
        fornitore = fattura.get("supplier_name", "")
        data_fattura = fattura.get("invoice_date", "")
        numero_fattura = fattura.get("invoice_number", "")
        fattura_id = fattura.get("id", "")
        
        # Estrai anno dalla data fattura
        anno = None
        if data_fattura:
            try:
                anno = int(data_fattura.split("-")[0])
            except Exception:
                anno = datetime.now().year
        else:
            anno = datetime.now().year
        
        registrati = 0
        for linea in linee:
            descrizione = linea.get("descrizione", "") or linea.get("description", "")
            quantita = linea.get("quantita", 0) or linea.get("quantity", 0) or 1
            prezzo_unitario = linea.get("prezzo_unitario", 0) or linea.get("unit_price", 0)
            totale_linea = linea.get("totale", 0) or linea.get("total", 0)
            unita_misura = linea.get("unita_misura", "") or linea.get("unit", "")
            codice = linea.get("codice", "") or linea.get("code", "")
            
            if not descrizione:
                continue
            
            # Normalizza descrizione per raggruppamento
            descrizione_normalizzata = descrizione.strip().upper()[:100]
            
            acquisto = {
                "fattura_id": fattura_id,
                "numero_fattura": numero_fattura,
                "fornitore": fornitore,
                "data_fattura": data_fattura,
                "anno": anno,
                "mese": int(data_fattura.split("-")[1]) if data_fattura and len(data_fattura.split("-")) > 1 else None,
                "descrizione": descrizione,
                "descrizione_normalizzata": descrizione_normalizzata,
                "codice_prodotto": codice,
                "quantita": float(quantita) if quantita else 1,
                "unita_misura": unita_misura or "PZ",
                "prezzo_unitario": float(prezzo_unitario) if prezzo_unitario else 0,
                "totale_linea": float(totale_linea) if totale_linea else 0,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Evita duplicati (stessa fattura + stessa linea)
            existing = await db["acquisti_prodotti"].find_one({
                "fattura_id": fattura_id,
                "descrizione_normalizzata": descrizione_normalizzata
            })
            
            if not existing:
                await db["acquisti_prodotti"].insert_one(acquisto.copy())
                registrati += 1
        
        return registrati
        
    except Exception as e:
        logger.error(f"Errore registrazione acquisto: {e}")
        return 0


@router.get("/prodotti")
async def lista_prodotti(
    anno: Optional[int] = Query(None, description="Filtra per anno"),
    fornitore: Optional[str] = Query(None, description="Filtra per fornitore"),
    search: Optional[str] = Query(None, description="Cerca prodotto"),
    limit: int = Query(100, ge=1, le=500)
) -> Dict[str, Any]:
    """
    Lista prodotti acquistati con quantità aggregate.
    """
    db = Database.get_db()
    
    match_query = {}
    if anno:
        match_query["anno"] = anno
    if fornitore:
        match_query["fornitore"] = {"$regex": fornitore, "$options": "i"}
    if search:
        match_query["descrizione"] = {"$regex": search, "$options": "i"}
    
    # Aggrega per prodotto
    pipeline = [
        {"$match": match_query},
        {"$group": {
            "_id": "$descrizione_normalizzata",
            "descrizione": {"$first": "$descrizione"},
            "unita_misura": {"$first": "$unita_misura"},
            "quantita_totale": {"$sum": "$quantita"},
            "spesa_totale": {"$sum": "$totale_linea"},
            "num_acquisti": {"$sum": 1},
            "fornitori": {"$addToSet": "$fornitore"},
            "primo_acquisto": {"$min": "$data_fattura"},
            "ultimo_acquisto": {"$max": "$data_fattura"},
            "prezzo_medio": {"$avg": "$prezzo_unitario"}
        }},
        {"$sort": {"quantita_totale": -1}},
        {"$limit": limit}
    ]
    
    prodotti = []
    async for doc in db["acquisti_prodotti"].aggregate(pipeline):
        doc["id"] = doc.pop("_id")
        doc["fornitori"] = list(doc.get("fornitori", []))[:5]  # Max 5 fornitori
        prodotti.append(doc)
    
    return {
        "prodotti": prodotti,
        "totale": len(prodotti),
        "anno_filtro": anno
    }


@router.get("/statistiche")
async def statistiche_acquisti(
    anno: int = Query(..., description="Anno di riferimento"),
    prodotto: Optional[str] = Query(None, description="Filtra per prodotto specifico")
) -> Dict[str, Any]:
    """
    Calcola statistiche dettagliate per previsioni acquisti.
    
    Per ogni prodotto calcola:
    - Media giornaliera (quantità / 340 giorni)
    - Media settimanale
    - Frequenza acquisti (ogni quanti giorni)
    - Confronto con anno precedente
    """
    db = Database.get_db()
    
    match_query = {"anno": anno}
    if prodotto:
        match_query["descrizione"] = {"$regex": prodotto, "$options": "i"}
    
    # Statistiche anno corrente
    pipeline = [
        {"$match": match_query},
        {"$group": {
            "_id": "$descrizione_normalizzata",
            "descrizione": {"$first": "$descrizione"},
            "unita_misura": {"$first": "$unita_misura"},
            "quantita_totale": {"$sum": "$quantita"},
            "spesa_totale": {"$sum": "$totale_linea"},
            "num_acquisti": {"$sum": 1},
            "date_acquisti": {"$push": "$data_fattura"},
            "primo_acquisto": {"$min": "$data_fattura"},
            "ultimo_acquisto": {"$max": "$data_fattura"}
        }},
        {"$sort": {"quantita_totale": -1}},
        {"$limit": 100}
    ]
    
    # Statistiche anno precedente per confronto
    anno_prec = anno - 1
    match_prec = {"anno": anno_prec}
    if prodotto:
        match_prec["descrizione"] = {"$regex": prodotto, "$options": "i"}
    
    pipeline_prec = [
        {"$match": match_prec},
        {"$group": {
            "_id": "$descrizione_normalizzata",
            "quantita_totale_prec": {"$sum": "$quantita"},
            "spesa_totale_prec": {"$sum": "$totale_linea"},
            "num_acquisti_prec": {"$sum": 1}
        }}
    ]
    
    # Esegui query
    stats_corrente = {}
    async for doc in db["acquisti_prodotti"].aggregate(pipeline):
        prod_id = doc["_id"]
        
        # Calcola giorni effettivi nel periodo
        if doc.get("primo_acquisto") and doc.get("ultimo_acquisto"):
            try:
                primo = datetime.strptime(doc["primo_acquisto"], "%Y-%m-%d")
                ultimo = datetime.strptime(doc["ultimo_acquisto"], "%Y-%m-%d")
                giorni_periodo = max((ultimo - primo).days, 1)
            except Exception:
                giorni_periodo = GIORNI_LAVORATIVI_ANNO
        else:
            giorni_periodo = GIORNI_LAVORATIVI_ANNO
        
        quantita = doc["quantita_totale"]
        num_acquisti = doc["num_acquisti"]
        
        # Calcola medie
        media_giornaliera = quantita / GIORNI_LAVORATIVI_ANNO
        media_settimanale = media_giornaliera * GIORNI_SETTIMANA
        
        # Frequenza acquisti (ogni quanti giorni acquistiamo)
        frequenza_giorni = giorni_periodo / max(num_acquisti, 1)
        
        stats_corrente[prod_id] = {
            "descrizione": doc["descrizione"],
            "unita_misura": doc["unita_misura"],
            "quantita_totale": quantita,
            "spesa_totale": doc["spesa_totale"],
            "num_acquisti": num_acquisti,
            "media_giornaliera": round(media_giornaliera, 2),
            "media_settimanale": round(media_settimanale, 2),
            "frequenza_giorni": round(frequenza_giorni, 1),
            "primo_acquisto": doc["primo_acquisto"],
            "ultimo_acquisto": doc["ultimo_acquisto"]
        }
    
    # Aggiungi confronto anno precedente
    stats_prec = {}
    async for doc in db["acquisti_prodotti"].aggregate(pipeline_prec):
        stats_prec[doc["_id"]] = doc
    
    # Combina risultati
    risultati = []
    for prod_id, stats in stats_corrente.items():
        prec = stats_prec.get(prod_id, {})
        
        # Calcola variazione percentuale
        q_prec = prec.get("quantita_totale_prec", 0)
        q_corr = stats["quantita_totale"]
        
        if q_prec > 0:
            variazione_pct = ((q_corr - q_prec) / q_prec) * 100
        else:
            variazione_pct = 100 if q_corr > 0 else 0
        
        risultato = {
            **stats,
            "id": prod_id,
            "anno": anno,
            "quantita_anno_prec": q_prec,
            "variazione_pct": round(variazione_pct, 1),
            "trend": "↑" if variazione_pct > 5 else ("↓" if variazione_pct < -5 else "→")
        }
        risultati.append(risultato)
    
    return {
        "statistiche": risultati,
        "anno": anno,
        "anno_confronto": anno_prec,
        "totale_prodotti": len(risultati)
    }


@router.get("/previsioni")
async def previsioni_acquisti(
    anno_riferimento: int = Query(..., description="Anno da usare come riferimento (es: 2025)"),
    settimane_previsione: int = Query(4, ge=1, le=52, description="Settimane da prevedere")
) -> Dict[str, Any]:
    """
    Genera previsioni acquisti basate sullo storico.
    
    Usa i dati dell'anno di riferimento per proporre gli acquisti da fare
    nelle prossime N settimane.
    """
    db = Database.get_db()
    
    # Ottieni statistiche anno riferimento
    pipeline = [
        {"$match": {"anno": anno_riferimento}},
        {"$group": {
            "_id": "$descrizione_normalizzata",
            "descrizione": {"$first": "$descrizione"},
            "unita_misura": {"$first": "$unita_misura"},
            "quantita_totale": {"$sum": "$quantita"},
            "num_acquisti": {"$sum": 1},
            "fornitori": {"$addToSet": "$fornitore"},
            "prezzo_medio": {"$avg": "$prezzo_unitario"}
        }},
        {"$match": {"quantita_totale": {"$gt": 0}}},
        {"$sort": {"quantita_totale": -1}},
        {"$limit": 200}
    ]
    
    previsioni = []
    async for doc in db["acquisti_prodotti"].aggregate(pipeline):
        quantita = doc["quantita_totale"]
        
        # Calcola medie
        media_settimanale = (quantita / GIORNI_LAVORATIVI_ANNO) * GIORNI_SETTIMANA
        
        # Quantità prevista per le prossime N settimane
        quantita_prevista = media_settimanale * settimane_previsione
        
        # Frequenza ordini (ogni quante settimane ordinare)
        num_acquisti = doc["num_acquisti"]
        if num_acquisti > 0:
            settimane_anno = GIORNI_LAVORATIVI_ANNO / GIORNI_SETTIMANA
            frequenza_ordine_settimane = settimane_anno / num_acquisti
        else:
            frequenza_ordine_settimane = 52
        
        # Costo stimato
        prezzo_medio = doc.get("prezzo_medio", 0) or 0
        costo_stimato = quantita_prevista * prezzo_medio
        
        previsione = {
            "id": doc["_id"],
            "prodotto": doc["descrizione"],
            "unita_misura": doc["unita_misura"],
            "quantita_anno_rif": round(quantita, 2),
            "media_settimanale": round(media_settimanale, 2),
            "quantita_prevista": round(quantita_prevista, 2),
            "frequenza_ordine_settimane": round(frequenza_ordine_settimane, 1),
            "prossimo_ordine_tra_giorni": round(frequenza_ordine_settimane * 7, 0),
            "fornitori_abituali": list(doc.get("fornitori", []))[:3],
            "prezzo_medio": round(prezzo_medio, 2),
            "costo_stimato": round(costo_stimato, 2)
        }
        previsioni.append(previsione)
    
    # Totale costo stimato
    costo_totale = sum(p["costo_stimato"] for p in previsioni)
    
    return {
        "previsioni": previsioni,
        "anno_riferimento": anno_riferimento,
        "settimane_previsione": settimane_previsione,
        "totale_prodotti": len(previsioni),
        "costo_totale_stimato": round(costo_totale, 2)
    }


@router.post("/popola-storico")
async def popola_storico_da_fatture() -> Dict[str, Any]:
    """
    Popola la collezione acquisti_prodotti da tutte le fatture esistenti.
    Da eseguire una volta per inizializzare lo storico.
    """
    db = Database.get_db()
    
    # Conta fatture
    totale_fatture = await db["invoices"].count_documents({})
    
    processate = 0
    prodotti_registrati = 0
    errori = 0
    
    cursor = db["invoices"].find({}, {"_id": 0})
    async for fattura in cursor:
        try:
            registrati = await registra_acquisto_da_fattura(db, fattura)
            prodotti_registrati += registrati
            processate += 1
        except Exception as e:
            logger.error(f"Errore fattura: {e}")
            errori += 1
    
    return {
        "success": True,
        "fatture_processate": processate,
        "prodotti_registrati": prodotti_registrati,
        "errori": errori,
        "totale_fatture": totale_fatture
    }


@router.get("/confronto-ordine")
async def confronto_ordine(
    anno_riferimento: int = Query(..., description="Anno di riferimento"),
    prodotto: str = Query(..., description="Nome prodotto"),
    quantita_ordinata: float = Query(..., description="Quantità che vuoi ordinare")
) -> Dict[str, Any]:
    """
    Confronta una quantità da ordinare con la media storica.
    Dice se sei sopra o sotto la media.
    """
    db = Database.get_db()
    
    # Trova statistiche prodotto
    pipeline = [
        {"$match": {
            "anno": anno_riferimento,
            "descrizione": {"$regex": prodotto, "$options": "i"}
        }},
        {"$group": {
            "_id": "$descrizione_normalizzata",
            "descrizione": {"$first": "$descrizione"},
            "unita_misura": {"$first": "$unita_misura"},
            "quantita_totale": {"$sum": "$quantita"},
            "num_acquisti": {"$sum": 1}
        }}
    ]
    
    risultato = None
    async for doc in db["acquisti_prodotti"].aggregate(pipeline):
        risultato = doc
        break
    
    if not risultato:
        raise HTTPException(status_code=404, detail=f"Prodotto '{prodotto}' non trovato nello storico {anno_riferimento}")
    
    quantita_storico = risultato["quantita_totale"]
    num_acquisti = risultato["num_acquisti"]
    
    # Calcola media per singolo ordine
    media_per_ordine = quantita_storico / max(num_acquisti, 1)
    
    # Confronta
    differenza = quantita_ordinata - media_per_ordine
    differenza_pct = (differenza / media_per_ordine) * 100 if media_per_ordine > 0 else 0
    
    if differenza_pct > 20:
        giudizio = "SOPRA MEDIA (+{:.0f}%)".format(differenza_pct)
        emoji = "📈"
        consiglio = "Stai ordinando più del solito. Verifica se necessario."
    elif differenza_pct < -20:
        giudizio = "SOTTO MEDIA ({:.0f}%)".format(differenza_pct)
        emoji = "📉"
        consiglio = "Stai ordinando meno del solito. Potrebbe bastare?"
    else:
        giudizio = "IN LINEA"
        emoji = "✅"
        consiglio = "Quantità in linea con lo storico."
    
    return {
        "prodotto": risultato["descrizione"],
        "unita_misura": risultato["unita_misura"],
        "quantita_ordinata": quantita_ordinata,
        "media_per_ordine": round(media_per_ordine, 2),
        "differenza": round(differenza, 2),
        "differenza_pct": round(differenza_pct, 1),
        "giudizio": giudizio,
        "emoji": emoji,
        "consiglio": consiglio,
        "storico": {
            "anno": anno_riferimento,
            "quantita_totale": quantita_storico,
            "num_ordini": num_acquisti
        }
    }
