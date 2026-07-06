"""
Utility condivise per lo scadenziario fornitori (usate da scadenzario_fornitori.py).
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional

logger = logging.getLogger(__name__)

COL_SCADENZIARIO = "scadenziario_fornitori"
COL_BANK_TRANSACTIONS = "bank_transactions"
COL_RICONCILIAZIONI   = "riconciliazioni"
COL_FATTURE      = "invoices"

# Fuzzy matching opzionale
try:
    from rapidfuzz import fuzz
    FUZZY_AVAILABLE = True
except ImportError:
    FUZZY_AVAILABLE = False

METODI_PAGAMENTO = {
    "MP01": {"desc": "Contanti",  "tipo": "contanti",  "giorni_default": 0},
    "MP02": {"desc": "Assegno",   "tipo": "assegno",   "giorni_default": 0},
    "MP03": {"desc": "Assegno circolare", "tipo": "assegno", "giorni_default": 0},
    "MP05": {"desc": "Bonifico",  "tipo": "bonifico",  "giorni_default": 30},
    "MP09": {"desc": "RID",       "tipo": "rid",       "giorni_default": 30},
    "MP12": {"desc": "RIBA",      "tipo": "riba",      "giorni_default": 60},
}


async def cerca_match_bancario(
    db, scadenza: Dict, tolleranza_giorni: int = 30,
    tolleranza_importo: float = 0.50, include_suggerimenti: bool = False
) -> Optional[Dict]:
    """Cerca match tra scadenza e movimenti bancari."""
    importo = abs(float(scadenza.get("importo_totale", 0)))
    data_scadenza = scadenza.get("data_scadenza")
    fornitore_nome = (scadenza.get("fornitore_nome") or "").strip()
    fornitore_nome_lower = fornitore_nome.lower()
    numero_fattura = scadenza.get("numero_fattura", "")

    if not data_scadenza or not importo:
        return None

    try:
        data_scad = datetime.strptime(data_scadenza[:10], "%Y-%m-%d")
        data_min = (data_scad - timedelta(days=120)).strftime("%Y-%m-%d")
        data_max = (data_scad + timedelta(days=tolleranza_giorni)).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None

    parole_comuni = {"srl", "spa", "snc", "sas", "di", "e", "del", "della", "gruppo", "italia"}
    parole_fornitore = [p.lower() for p in fornitore_nome.split() if len(p) >= 4 and p.lower() not in parole_comuni]
    prima_parola = parole_fornitore[0] if parole_fornitore else ""

    query_esatto = {
        "tipo": {"$in": ["uscita", "addebito"]},
        "$or": [
            {"importo": {"$gte": importo - 1.0, "$lte": importo + 1.0}},
            {"importo": {"$gte": -importo - 1.0, "$lte": -importo + 1.0}}
        ],
        "data": {"$gte": data_min, "$lte": data_max},
        "fattura_id": {"$exists": False}
    }
    movimenti_esatti = await db["estratto_conto_movimenti"].find(query_esatto, {"_id": 0}).to_list(50)

    for mov in movimenti_esatti:
        testo = f"{(mov.get('fornitore') or '')} {(mov.get('descrizione_originale') or '')}".lower()
        nome_match = prima_parola and prima_parola in testo
        if not nome_match and FUZZY_AVAILABLE and mov.get("fornitore"):
            nome_match = fuzz.partial_ratio(fornitore_nome_lower, mov["fornitore"].lower()) >= 75
        if nome_match:
            mov.update({"source_collection": "estratto_conto_movimenti", "match_type": "alta_confidenza", "match_score": 95, "confidence": "HIGH"})
            return mov

    if movimenti_esatti and importo >= 100:
        mov = movimenti_esatti[0]
        if abs(abs(float(mov.get("importo", 0))) - importo) <= 1.0:
            mov.update({"source_collection": "estratto_conto_movimenti", "match_type": "media_confidenza", "match_score": 75, "confidence": "MEDIUM"})
            return mov

    if include_suggerimenti:
        tolleranza_sugg = max(importo * 0.10, 20.0)
        query_sugg = {
            "tipo": {"$in": ["uscita", "addebito"]},
            "$or": [
                {"importo": {"$gte": importo - tolleranza_sugg, "$lte": importo + tolleranza_sugg}},
                {"importo": {"$gte": -importo - tolleranza_sugg, "$lte": -importo + tolleranza_sugg}}
            ],
            "data": {"$gte": data_min, "$lte": data_max},
            "fattura_id": {"$exists": False}
        }
        movimenti_sugg = await db["estratto_conto_movimenti"].find(query_sugg, {"_id": 0}).to_list(20)
        if movimenti_sugg:
            best = min(movimenti_sugg, key=lambda m: abs(abs(float(m.get("importo", 0))) - importo))
            best.update({"source_collection": "estratto_conto_movimenti", "match_type": "suggerimento", "match_score": 50, "confidence": "LOW"})
            return best
    return None


async def esegui_riconciliazione(
    db, scadenza_id: str, transazione_id: str,
    source_collection: str = "estratto_conto_movimenti"
) -> Dict:
    """Esegue riconciliazione tra scadenza e movimento bancario."""
    now = datetime.now(timezone.utc).isoformat()
    await db[COL_SCADENZIARIO].update_one(
        {"id": scadenza_id},
        {"$set": {"stato": "saldato", "pagato": True, "riconciliato": True,
                  "transazione_bancaria_id": transazione_id, "data_pagamento": now, "updated_at": now}}
    )
    if source_collection == "estratto_conto_movimenti":
        await db["estratto_conto_movimenti"].update_one(
            {"id": transazione_id},
            {"$set": {"fattura_id": scadenza_id, "riconciliato": True, "updated_at": now}}
        )
    else:
        await db[COL_BANK_TRANSACTIONS].update_one(
            {"id": transazione_id},
            {"$set": {"riconciliato": True, "scadenza_id": scadenza_id, "updated_at": now}}
        )
    riconciliazione = {
        "id": str(uuid.uuid4()), "scadenza_id": scadenza_id, "transazione_id": transazione_id,
        "source_collection": source_collection, "tipo": "automatica",
        "data_riconciliazione": now, "created_at": now
    }
    await db[COL_RICONCILIAZIONI].insert_one(riconciliazione.copy())
    return {"success": True, "riconciliazione_id": riconciliazione["id"]}
