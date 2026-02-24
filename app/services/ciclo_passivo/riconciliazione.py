"""
Modulo Riconciliazione per il Ciclo Passivo.
Abbina movimenti bancari a scadenze fornitori.
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional

from .constants import (
    SCADENZIARIO_COLLECTION,
    RICONCILIAZIONI_COLLECTION
)

logger = logging.getLogger(__name__)


async def cerca_match_bancario(
    db,
    scadenza: Dict,
    tolleranza_giorni: int = 30,
    tolleranza_importo: float = 0.50,
    include_suggerimenti: bool = False
) -> Optional[Dict]:
    """
    Cerca un movimento bancario che corrisponde alla scadenza.
    
    Criteri di match:
    1. Importo esatto o con tolleranza
    2. Data entro tolleranza_giorni dalla scadenza
    3. Descrizione contenente riferimenti al fornitore
    
    Returns:
        Match trovato con score, o None
    """
    importo_scadenza = abs(float(scadenza.get("importo", 0)))
    if importo_scadenza <= 0:
        return None
    
    data_scadenza_str = scadenza.get("data_scadenza", "")
    fornitore_nome = scadenza.get("fornitore_nome", "").lower()
    fornitore_piva = scadenza.get("fornitore_piva", "")
    
    # Parse data scadenza
    try:
        data_scadenza = datetime.strptime(data_scadenza_str[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        data_scadenza = datetime.now()
    
    data_min = (data_scadenza - timedelta(days=tolleranza_giorni)).strftime("%Y-%m-%d")
    data_max = (data_scadenza + timedelta(days=tolleranza_giorni)).strftime("%Y-%m-%d")
    
    # Query movimenti bancari in uscita (negativi) non riconciliati
    query = {
        "importo": {"$lt": 0},  # Uscite
        "data": {"$gte": data_min, "$lte": data_max},
        "riconciliato": {"$ne": True}
    }
    
    movimenti = await db["estratto_conto_movimenti"].find(
        query,
        {"_id": 0, "id": 1, "data": 1, "importo": 1, "descrizione": 1, "causale": 1}
    ).limit(100).to_list(100)
    
    matches = []
    
    for mov in movimenti:
        importo_mov = abs(float(mov.get("importo", 0)))
        differenza_importo = abs(importo_mov - importo_scadenza)
        
        # Score basato su differenza importo
        if differenza_importo <= 0.01:
            score_importo = 100
        elif differenza_importo <= tolleranza_importo:
            score_importo = 80
        elif differenza_importo <= importo_scadenza * 0.05:
            score_importo = 60
        else:
            continue  # Skip se troppo diverso
        
        # Score basato su descrizione
        descrizione = (mov.get("descrizione", "") + " " + mov.get("causale", "")).lower()
        score_descrizione = 0
        
        # Cerca riferimenti al fornitore
        if fornitore_piva and fornitore_piva.lower() in descrizione:
            score_descrizione = 50
        elif fornitore_nome:
            # Cerca parole del nome fornitore
            parole_fornitore = [p for p in fornitore_nome.split() if len(p) > 3]
            matches_parole = sum(1 for p in parole_fornitore if p in descrizione)
            if matches_parole > 0:
                score_descrizione = min(40, matches_parole * 15)
        
        # Cerca numero fattura
        num_doc = scadenza.get("numero_documento", "")
        if num_doc and num_doc.lower() in descrizione:
            score_descrizione += 30
        
        score_totale = (score_importo * 0.6) + (score_descrizione * 0.4)
        
        if score_totale >= 40:  # Soglia minima
            matches.append({
                "movimento_id": mov.get("id"),
                "data": mov.get("data"),
                "importo": importo_mov,
                "descrizione": mov.get("descrizione", "")[:100],
                "score": round(score_totale, 1),
                "differenza_importo": round(differenza_importo, 2)
            })
    
    # Ordina per score e restituisci il migliore
    matches.sort(key=lambda x: x["score"], reverse=True)
    
    if matches:
        best = matches[0]
        if include_suggerimenti:
            best["altri_suggerimenti"] = matches[1:5]
        return best
    
    return None


async def esegui_riconciliazione(
    db,
    scadenza_id: str,
    transazione_id: str,
    source_collection: str = "estratto_conto_movimenti"
) -> Dict:
    """
    Esegue la riconciliazione tra una scadenza e un movimento bancario.
    
    Aggiorna:
    - Scadenza: stato=pagato, transazione_id
    - Movimento bancario: riconciliato=True
    - Crea record in riconciliazioni
    
    Returns:
        Risultato operazione
    """
    # Carica scadenza
    scadenza = await db[SCADENZIARIO_COLLECTION].find_one({"id": scadenza_id})
    if not scadenza:
        return {"success": False, "error": "Scadenza non trovata"}
    
    # Carica movimento
    movimento = await db[source_collection].find_one({"id": transazione_id})
    if not movimento:
        return {"success": False, "error": "Movimento bancario non trovato"}
    
    now = datetime.now(timezone.utc)
    
    # Aggiorna scadenza
    await db[SCADENZIARIO_COLLECTION].update_one(
        {"id": scadenza_id},
        {"$set": {
            "stato": "pagato",
            "pagato": True,
            "data_pagamento": movimento.get("data"),
            "transazione_id": transazione_id,
            "source_collection": source_collection,
            "importo_residuo": 0,
            "updated_at": now.isoformat()
        }}
    )
    
    # Aggiorna movimento
    await db[source_collection].update_one(
        {"id": transazione_id},
        {"$set": {
            "riconciliato": True,
            "scadenza_id": scadenza_id,
            "fattura_id": scadenza.get("fattura_id"),
            "updated_at": now.isoformat()
        }}
    )
    
    # Crea record riconciliazione
    riconciliazione = {
        "id": str(uuid.uuid4()),
        "scadenza_id": scadenza_id,
        "transazione_id": transazione_id,
        "source_collection": source_collection,
        "fattura_id": scadenza.get("fattura_id"),
        "fornitore_id": scadenza.get("fornitore_id"),
        "fornitore_nome": scadenza.get("fornitore_nome"),
        "importo_scadenza": scadenza.get("importo"),
        "importo_movimento": abs(float(movimento.get("importo", 0))),
        "data_movimento": movimento.get("data"),
        "data_riconciliazione": now.isoformat(),
        "metodo": "manuale",
        "created_at": now.isoformat()
    }
    
    await db[RICONCILIAZIONI_COLLECTION].insert_one(riconciliazione.copy())
    
    logger.info(f"Riconciliazione completata: scadenza {scadenza_id} <-> movimento {transazione_id}")
    
    return {
        "success": True,
        "riconciliazione_id": riconciliazione["id"],
        "scadenza_id": scadenza_id,
        "transazione_id": transazione_id,
        "importo": scadenza.get("importo")
    }
