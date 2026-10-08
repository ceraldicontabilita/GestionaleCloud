"""
Partite Aperte Engine — Gestionale Ceraldi Group
==================================================
Gestisce la creazione, chiusura e ricerca delle partite aperte.
Le partite aperte sono lo scadenziario materializzato: ogni debito/credito
atteso è un record reale che vive fino alla chiusura.

Utilizzo:
    from app.services.partite_aperte_engine import crea_partita, chiudi_partita
    
    # Quando arriva una fattura fornitore:
    await crea_partita(
        tipo="fattura_fornitore",
        documento_id=fattura["id"],
        documento_collection="invoices",
        controparte_id=fornitore_id,
        controparte_nome="Mario Rossi SRL",
        importo=1500.00,
        data_scadenza="2026-05-15",
        data_documento="2026-04-01",
        db=db
    )
"""
import logging
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

COLL_PARTITE = "partite_aperte"


# ============================================================
# TIPI DI PARTITA
# ============================================================
class TipoPartita:
    FATTURA_FORNITORE = "fattura_fornitore"
    NOTA_CREDITO = "nota_credito"
    F24 = "f24"
    STIPENDIO = "stipendio"
    POS_ATTESO = "pos_atteso"
    TRASFERIMENTO = "trasferimento"
    ALTRO = "altro"


class StatoPartita:
    APERTA = "aperta"
    PARZIALE = "parziale"
    CHIUSA = "chiusa"
    COMPENSATA = "compensata"
    DA_VERIFICARE = "da_verificare"


# ============================================================
# CREAZIONE PARTITA
# ============================================================
async def crea_partita(
    tipo: str,
    documento_id: str,
    documento_collection: str,
    controparte_id: str,
    controparte_nome: str,
    importo: float,
    db,
    data_scadenza: Optional[str] = None,
    data_documento: Optional[str] = None,
    priorita: int = 1,
    extra: Optional[Dict] = None
) -> Optional[Dict]:
    """
    Crea una nuova partita aperta. Idempotente: non duplica se esiste già
    per lo stesso documento_id + tipo.
    
    Returns: la partita creata, o None se già esistente.
    """
    # Idempotenza
    existing = await db[COLL_PARTITE].find_one({
        "documento_id": documento_id,
        "tipo": tipo,
        "stato": {"$in": [StatoPartita.APERTA, StatoPartita.PARZIALE]}
    })
    
    if existing:
        logger.debug(f"Partita già esistente per {tipo}/{documento_id}, skip")
        return None
    
    partita = {
        "id": f"pa_{uuid.uuid4().hex[:12]}",
        "tipo": tipo,
        "controparte_id": controparte_id,
        "controparte_nome": controparte_nome,
        "documento_id": documento_id,
        "documento_collection": documento_collection,
        "importo_originale": round(importo, 2),
        "residuo": round(importo, 2),
        "data_scadenza": data_scadenza,
        "data_documento": data_documento,
        "stato": StatoPartita.APERTA,
        "priorita": priorita,
        "match_ids": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    
    if extra:
        partita["extra"] = extra
    
    await db[COLL_PARTITE].insert_one(partita)
    logger.info(f"Partita creata: {tipo} {controparte_nome} €{importo} (id: {partita['id']})")
    return partita


# ============================================================
# CHIUSURA PARTITA (totale o parziale)
# ============================================================
async def chiudi_partita(
    partita_id: str,
    match_id: str,
    importo_pagato: float,
    db
) -> Dict[str, Any]:
    """
    Chiude (totalmente o parzialmente) una partita.
    Aggiorna residuo e stato. Aggiunge il match_id alla lista match.
    
    Returns: stato aggiornato della partita.
    """
    partita = await db[COLL_PARTITE].find_one(
        {"id": partita_id},
        {"_id": 0}
    )
    
    if not partita:
        return {"success": False, "error": "Partita non trovata"}
    
    vecchio_residuo = partita.get("residuo", 0)
    nuovo_residuo = round(vecchio_residuo - importo_pagato, 2)
    
    if nuovo_residuo <= 0.01:  # tolleranza centesimo
        nuovo_stato = StatoPartita.CHIUSA
        nuovo_residuo = 0.0
    else:
        nuovo_stato = StatoPartita.PARZIALE
    
    await db[COLL_PARTITE].update_one(
        {"id": partita_id},
        {
            "$set": {
                "residuo": nuovo_residuo,
                "stato": nuovo_stato,
                "updated_at": datetime.now(timezone.utc).isoformat()
            },
            "$addToSet": {"match_ids": match_id}
        }
    )
    
    logger.info(
        f"Partita {partita_id} aggiornata: "
        f"€{vecchio_residuo} → €{nuovo_residuo} ({nuovo_stato})"
    )
    
    return {
        "success": True,
        "partita_id": partita_id,
        "vecchio_residuo": vecchio_residuo,
        "nuovo_residuo": nuovo_residuo,
        "stato": nuovo_stato
    }


# ============================================================
# RICERCA PARTITE COMPATIBILI (per il motore di riconciliazione)
# ============================================================
async def cerca_partite_compatibili(
    importo: float,
    db,
    controparte_id: Optional[str] = None,
    controparte_nome: Optional[str] = None,
    tipo: Optional[str] = None,
    data_riferimento: Optional[str] = None,
    finestra_gg: int = 30,
    tolleranza_importo: float = 0.50,
    limit: int = 10
) -> List[Dict]:
    """
    Cerca partite aperte compatibili con un movimento.
    Usata dal motore di riconciliazione.
    
    Returns: lista di candidati ordinati per probabilità di match.
    """
    query: Dict[str, Any] = {
        "stato": {"$in": [StatoPartita.APERTA, StatoPartita.PARZIALE]}
    }
    
    if controparte_id:
        query["controparte_id"] = controparte_id
    
    if tipo:
        query["tipo"] = tipo
    
    # Cerca per residuo vicino all'importo
    importo_abs = abs(importo)
    query["residuo"] = {
        "$gte": importo_abs - tolleranza_importo,
        "$lte": importo_abs + tolleranza_importo
    }
    
    # Finestra temporale sulla data scadenza
    if data_riferimento:
        try:
            data_ref = datetime.fromisoformat(data_riferimento.replace("Z", "+00:00"))
            data_da = (data_ref - timedelta(days=finestra_gg)).strftime("%Y-%m-%d")
            data_a = (data_ref + timedelta(days=finestra_gg)).strftime("%Y-%m-%d")
            query["$or"] = [
                {"data_scadenza": {"$gte": data_da, "$lte": data_a}},
                {"data_scadenza": None},  # partite senza scadenza
                {"data_scadenza": ""}
            ]
        except (ValueError, TypeError):
            pass
    
    candidates = await db[COLL_PARTITE].find(
        query, {"_id": 0}
    ).sort("data_scadenza", 1).limit(limit).to_list(limit)
    
    # Se nessun risultato con controparte, allarga la ricerca
    if not candidates and controparte_id:
        query_allargata = dict(query)
        del query_allargata["controparte_id"]
        candidates = await db[COLL_PARTITE].find(
            query_allargata, {"_id": 0}
        ).sort("data_scadenza", 1).limit(limit).to_list(limit)
    
    return candidates


async def cerca_partite_per_controparte(
    controparte_id: str,
    db,
    solo_aperte: bool = True,
    limit: int = 50
) -> List[Dict]:
    """Ritorna tutte le partite di una controparte."""
    query: Dict[str, Any] = {"controparte_id": controparte_id}
    if solo_aperte:
        query["stato"] = {"$in": [StatoPartita.APERTA, StatoPartita.PARZIALE]}
    
    return await db[COLL_PARTITE].find(
        query, {"_id": 0}
    ).sort("data_scadenza", 1).limit(limit).to_list(limit)


# ============================================================
# RICALCOLO RESIDUI
# ============================================================
async def ricalcola_residui(controparte_id: str, db) -> Dict[str, Any]:
    """
    Ricalcola i residui di tutte le partite di una controparte
    basandosi sui match confermati in riconciliazioni_match.
    """
    partite = await db[COLL_PARTITE].find(
        {
            "controparte_id": controparte_id,
            "stato": {"$in": [StatoPartita.APERTA, StatoPartita.PARZIALE]}
        },
        {"_id": 0}
    ).to_list(100)
    
    aggiornate = 0
    for partita in partite:
        # Somma tutti i match confermati per questa partita
        match_confermati = await db["riconciliazioni_match"].find(
            {
                "partita_id": partita["id"],
                "stato": "confermato"
            },
            {"_id": 0, "importo_riconciliato": 1}
        ).to_list(100)
        
        totale_pagato = sum(m.get("importo_riconciliato", 0) for m in match_confermati)
        nuovo_residuo = round(partita["importo_originale"] - totale_pagato, 2)
        
        if nuovo_residuo <= 0.01:
            nuovo_stato = StatoPartita.CHIUSA
            nuovo_residuo = 0.0
        elif totale_pagato > 0:
            nuovo_stato = StatoPartita.PARZIALE
        else:
            nuovo_stato = StatoPartita.APERTA
        
        await db[COLL_PARTITE].update_one(
            {"id": partita["id"]},
            {"$set": {
                "residuo": nuovo_residuo,
                "stato": nuovo_stato,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        aggiornate += 1
    
    return {"controparte_id": controparte_id, "partite_ricalcolate": aggiornate}


# ============================================================
# STATISTICHE PARTITE
# ============================================================
async def totale_partite_aperte(db) -> Dict[str, Any]:
    """Ritorna totali partite aperte raggruppati per tipo."""
    pipeline = [
        {"$match": {"stato": {"$in": ["aperta", "parziale"]}}},
        {"$group": {
            "_id": "$tipo",
            "count": {"$sum": 1},
            "totale_residuo": {"$sum": "$residuo"}
        }},
        {"$sort": {"totale_residuo": -1}}
    ]
    
    result = {}
    async for doc in db[COLL_PARTITE].aggregate(pipeline):
        result[doc["_id"]] = {
            "count": doc["count"],
            "totale_residuo": round(doc["totale_residuo"], 2)
        }
    
    return result
