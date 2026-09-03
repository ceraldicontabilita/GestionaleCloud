"""
Riconciliazione Engine v2 — Gestionale Ceraldi Group
=====================================================
Motore di scoring per il match tra movimenti reali e partite aperte.
Sostituisce la riconciliazione base (importo ±0.05 + fuzzy nome) con
un sistema a 4 livelli di confidenza.

Utilizzo:
    from app.hr.services.riconciliazione_engine import cerca_match, conferma_match
    
    candidati = await cerca_match(movimento, db)
    # candidati = [{"partita": {...}, "score": 0.95, "livello": "esatto", ...}]
    
    await conferma_match(match_id, db)
"""
import logging
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

COLL_MATCH = "riconciliazioni_match"

# Soglie di confidenza
SOGLIA_AUTO = 0.90      # Sopra: riconciliazione automatica
SOGLIA_PROPOSTA = 0.60  # Sopra: proposta all'utente
SOGLIA_MINIMA = 0.30    # Sotto: scartato

# Tolleranze importo
TOLLERANZA_ESATTA = 0.05
TOLLERANZA_COMMISSIONE = 10.00  # per commissioni POS/bancarie


# ============================================================
# STRUTTURA CANDIDATO MATCH
# ============================================================
def _candidato(partita: Dict, score: float, livello: str,
               motivo: str, differenza: float = 0.0) -> Dict:
    return {
        "partita": partita,
        "score": round(score, 3),
        "livello": livello,  # "esatto" | "pattern" | "approssimato" | "debole"
        "motivo": motivo,
        "differenza_importo": round(differenza, 2)
    }


# ============================================================
# CERCA MATCH — Funzione principale
# ============================================================
async def cerca_match(
    movimento: Dict[str, Any],
    db,
    soglia_minima: float = SOGLIA_MINIMA
) -> List[Dict]:
    """
    Cerca candidati di riconciliazione per un movimento bancario/cassa.
    
    Args:
        movimento: dict con almeno {importo, data, descrizione, segno}
        db: database Motor
        soglia_minima: score minimo per includere un candidato
    
    Returns:
        Lista di candidati ordinati per score decrescente.
    """
    importo = abs(movimento.get("importo", 0))
    data = movimento.get("data", "")
    descrizione = (movimento.get("descrizione", "") or "").upper()
    segno = movimento.get("segno", movimento.get("tipo", ""))
    
    if importo < 0.01:
        return []
    
    candidati = []
    
    # ---- LIVELLO 1: Match esatto ----
    candidati_l1 = await _match_esatto(importo, data, descrizione, segno, db)
    candidati.extend(candidati_l1)
    
    # ---- LIVELLO 2: Match per pattern noto ----
    candidati_l2 = await _match_pattern(importo, data, descrizione, segno, db)
    # Aggiungi solo se non già trovati al livello 1
    ids_l1 = {c["partita"]["id"] for c in candidati_l1}
    candidati.extend([c for c in candidati_l2 if c["partita"]["id"] not in ids_l1])
    
    # ---- LIVELLO 3: Match approssimato ----
    ids_esistenti = {c["partita"]["id"] for c in candidati}
    candidati_l3 = await _match_approssimato(importo, data, descrizione, segno, db)
    candidati.extend([c for c in candidati_l3 if c["partita"]["id"] not in ids_esistenti])
    
    # Filtra per soglia e ordina per score
    candidati = [c for c in candidati if c["score"] >= soglia_minima]
    candidati.sort(key=lambda x: x["score"], reverse=True)
    
    return candidati[:10]  # max 10 candidati


# ============================================================
# LIVELLO 1: Match esatto
# ============================================================
async def _match_esatto(
    importo: float, data: str, descrizione: str, segno: str, db
) -> List[Dict]:
    """
    Importo identico + controparte univoca + finestra temporale stretta.
    Score: 0.90-1.00
    """
    from app.hr.services.partite_aperte_engine import COLL_PARTITE
    
    candidati = []
    
    # Cerca partite con importo quasi identico
    partite = await db[COLL_PARTITE].find(
        {
            "stato": {"$in": ["aperta", "parziale"]},
            "residuo": {"$gte": importo - TOLLERANZA_ESATTA,
                       "$lte": importo + TOLLERANZA_ESATTA}
        },
        {"_id": 0}
    ).limit(20).to_list(20)
    
    for p in partite:
        score = 0.70  # base per importo match
        motivo_parts = ["Importo identico"]
        
        # Bonus controparte trovata nella descrizione
        controparte_nome = (p.get("controparte_nome", "") or "").upper()
        if controparte_nome and len(controparte_nome) >= 3:
            # Prova match parziale del nome nella descrizione banca
            parole_nome = controparte_nome.split()
            parole_trovate = sum(1 for parola in parole_nome
                               if len(parola) >= 3 and parola in descrizione)
            if parole_trovate >= 2 or (len(parole_nome) == 1 and parole_trovate == 1):
                score += 0.20
                motivo_parts.append("nome controparte in descrizione")
        
        # Bonus data vicina alla scadenza
        if data and p.get("data_scadenza"):
            try:
                diff_gg = abs((datetime.fromisoformat(data) -
                              datetime.fromisoformat(p["data_scadenza"])).days)
                if diff_gg <= 3:
                    score += 0.10
                    motivo_parts.append("data vicina a scadenza")
                elif diff_gg <= 7:
                    score += 0.05
            except (ValueError, TypeError):
                pass
        
        # Se è l'unica partita con quell'importo → ancora più forte
        if len(partite) == 1:
            score += 0.05
            motivo_parts.append("unica partita compatibile")
        
        diff = abs(importo - p.get("residuo", 0))
        candidati.append(_candidato(p, min(score, 1.0), "esatto",
                                   " + ".join(motivo_parts), diff))
    
    return candidati


# ============================================================
# LIVELLO 2: Match per pattern noto
# ============================================================
async def _match_pattern(
    importo: float, data: str, descrizione: str, segno: str, db
) -> List[Dict]:
    """
    Pattern riconosciuti: F24, POS, stipendi, commissioni.
    Score: 0.70-0.90
    """
    from app.hr.services.partite_aperte_engine import COLL_PARTITE
    
    candidati = []
    
    # Pattern F24: causale contiene "F24", "ERARIO", "TRIBUT"
    if any(kw in descrizione for kw in ["F24", "ERARIO", "TRIBUT", "AGENZIA ENTRATE"]):
        partite = await db[COLL_PARTITE].find(
            {
                "tipo": "f24",
                "stato": {"$in": ["aperta", "parziale"]},
                "residuo": {"$gte": importo - 1.0, "$lte": importo + 1.0}
            },
            {"_id": 0}
        ).limit(5).to_list(5)
        
        for p in partite:
            diff = abs(importo - p.get("residuo", 0))
            score = 0.85 if diff < TOLLERANZA_ESATTA else 0.75
            candidati.append(_candidato(p, score, "pattern",
                                       "Pattern F24 in descrizione", diff))
    
    # Pattern stipendi: causale contiene "STIP", "BONIF", "EMOLUMENT"
    if any(kw in descrizione for kw in ["STIP", "EMOLUMENT", "SALARI", "PAGA"]):
        partite = await db[COLL_PARTITE].find(
            {
                "tipo": "stipendio",
                "stato": {"$in": ["aperta", "parziale"]},
                "residuo": {"$gte": importo - 5.0, "$lte": importo + 5.0}
            },
            {"_id": 0}
        ).limit(10).to_list(10)
        
        for p in partite:
            diff = abs(importo - p.get("residuo", 0))
            score = 0.80 if diff < 1.0 else 0.70
            candidati.append(_candidato(p, score, "pattern",
                                       "Pattern stipendio in descrizione", diff))
    
    # Pattern POS: causale contiene "POS", "NEXI", "SIA", "ACCREDITO CARTE"
    if any(kw in descrizione for kw in ["POS", "NEXI", "SIA ", "CARTE", "ACCREDITO"]):
        partite = await db[COLL_PARTITE].find(
            {
                "tipo": "pos_atteso",
                "stato": {"$in": ["aperta", "parziale"]},
                "residuo": {"$gte": importo - TOLLERANZA_COMMISSIONE,
                           "$lte": importo + TOLLERANZA_COMMISSIONE}
            },
            {"_id": 0}
        ).limit(10).to_list(10)
        
        for p in partite:
            diff = abs(importo - p.get("residuo", 0))
            score = 0.85 if diff < 1.0 else (0.75 if diff < 5.0 else 0.65)
            motivo = "Pattern POS"
            if diff > TOLLERANZA_ESATTA:
                motivo += f" (prob. commissione €{diff:.2f})"
            candidati.append(_candidato(p, score, "pattern", motivo, diff))
    
    return candidati


# ============================================================
# LIVELLO 3: Match approssimato
# ============================================================
async def _match_approssimato(
    importo: float, data: str, descrizione: str, segno: str, db
) -> List[Dict]:
    """
    Importo vicino, controparte probabile.
    Score: 0.30-0.65
    """
    from app.hr.services.partite_aperte_engine import COLL_PARTITE
    
    candidati = []
    
    # Cerca partite con importo vicino (±5%)
    margine = importo * 0.05
    partite = await db[COLL_PARTITE].find(
        {
            "stato": {"$in": ["aperta", "parziale"]},
            "residuo": {"$gte": importo - max(margine, 5.0),
                       "$lte": importo + max(margine, 5.0)}
        },
        {"_id": 0}
    ).limit(15).to_list(15)
    
    for p in partite:
        score = 0.40
        diff = abs(importo - p.get("residuo", 0))
        motivo_parts = [f"Importo vicino (diff €{diff:.2f})"]
        
        # Bonus nome controparte
        controparte_nome = (p.get("controparte_nome", "") or "").upper()
        if controparte_nome and len(controparte_nome) >= 4:
            parole = [pa for pa in controparte_nome.split() if len(pa) >= 4]
            trovate = sum(1 for pa in parole if pa in descrizione)
            if trovate >= 1:
                score += 0.15
                motivo_parts.append("nome parziale in descrizione")
        
        # Bonus data vicina
        if data and p.get("data_scadenza"):
            try:
                diff_gg = abs((datetime.fromisoformat(data) -
                              datetime.fromisoformat(p["data_scadenza"])).days)
                if diff_gg <= 10:
                    score += 0.05
            except (ValueError, TypeError):
                pass
        
        candidati.append(_candidato(p, score, "approssimato",
                                   " + ".join(motivo_parts), diff))
    
    return candidati


# ============================================================
# CREA RECORD MATCH
# ============================================================
async def crea_match(
    movimento_id: str,
    movimento_collection: str,
    partita_id: str,
    tipo_match: str,
    importo_riconciliato: float,
    confidenza: float,
    db,
    origine: str = "auto"
) -> Dict:
    """Crea un record di match in riconciliazioni_match."""
    
    # Leggi residuo attuale
    from app.hr.services.partite_aperte_engine import COLL_PARTITE
    partita = await db[COLL_PARTITE].find_one(
        {"id": partita_id}, {"_id": 0, "residuo": 1}
    )
    residuo_pre = partita.get("residuo", 0) if partita else 0
    residuo_post = round(residuo_pre - importo_riconciliato, 2)
    
    stato = "confermato" if confidenza >= SOGLIA_AUTO and origine == "auto" else "candidato"
    
    match_doc = {
        "id": f"rm_{uuid.uuid4().hex[:12]}",
        "movimento_id": movimento_id,
        "movimento_collection": movimento_collection,
        "partita_id": partita_id,
        "partita_collection": COLL_PARTITE,
        "tipo_match": tipo_match,
        "importo_riconciliato": round(importo_riconciliato, 2),
        "residuo_pre": round(residuo_pre, 2),
        "residuo_post": max(residuo_post, 0),
        "confidenza": round(confidenza, 3),
        "origine": origine,
        "stato": stato,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "confirmed_at": datetime.now(timezone.utc).isoformat() if stato == "confermato" else None,
        "confirmed_by": "sistema" if stato == "confermato" else None
    }
    
    await db[COLL_MATCH].insert_one(match_doc)
    logger.info(
        f"Match creato: {match_doc['id']} ({stato}) "
        f"mov={movimento_id} ↔ par={partita_id} "
        f"€{importo_riconciliato} conf={confidenza}"
    )
    
    return match_doc


# ============================================================
# CONFERMA / RESPINGI MATCH
# ============================================================
async def conferma_match(match_id: str, db, confirmed_by: str = "utente") -> Dict:
    """
    Conferma un match candidato. Aggiorna la partita e il movimento collegati.
    """
    match_doc = await db[COLL_MATCH].find_one({"id": match_id}, {"_id": 0})
    if not match_doc:
        return {"success": False, "error": "Match non trovato"}
    
    if match_doc["stato"] == "confermato":
        return {"success": True, "info": "Già confermato"}
    
    # Aggiorna stato match
    await db[COLL_MATCH].update_one(
        {"id": match_id},
        {"$set": {
            "stato": "confermato",
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
            "confirmed_by": confirmed_by
        }}
    )
    
    # Chiudi/aggiorna partita
    from app.hr.services.partite_aperte_engine import chiudi_partita
    result_partita = await chiudi_partita(
        match_doc["partita_id"],
        match_id,
        match_doc["importo_riconciliato"],
        db
    )
    
    # Aggiorna movimento come riconciliato
    mov_coll = match_doc.get("movimento_collection", "estratto_conto_movimenti")
    await db[mov_coll].update_one(
        {"id": match_doc["movimento_id"]},
        {"$set": {
            "stato_riconciliazione": "riconciliato",
            "match_id": match_id,
            "riconciliato_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    logger.info(f"Match {match_id} confermato da {confirmed_by}")

    # --- EVENT BUS: propaga evento match confermato ---
    # Attiva gli handler che aggiornano fattura/F24/cedolino/POS collegati
    try:
        from app.hr.services.event_bus import propagate_event, EventTypes
        await propagate_event(EventTypes.MATCH_CONFERMATO, {
            "match_id": match_id,
            "partita_id": match_doc.get("partita_id"),
            "movimento_id": match_doc.get("movimento_id"),
            "importo_riconciliato": match_doc.get("importo_riconciliato"),
        }, db, source_module="riconciliazione_engine", user=confirmed_by)
    except Exception:
        logger.exception("Errore propagazione evento match.confermato")

    return {
        "success": True,
        "match_id": match_id,
        "partita": result_partita
    }


async def respingi_match(match_id: str, db, rejected_by: str = "utente") -> bool:
    """Respinge un match candidato. Lo logga per apprendimento futuro."""
    result = await db[COLL_MATCH].update_one(
        {"id": match_id},
        {"$set": {
            "stato": "respinto",
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
            "confirmed_by": rejected_by
        }}
    )
    
    if result.modified_count > 0:
        logger.info(f"Match {match_id} respinto da {rejected_by}")
    
    return result.modified_count > 0


# ============================================================
# STATISTICHE
# ============================================================
async def stats_riconciliazione(db) -> Dict:
    """Statistiche generali sulla riconciliazione."""
    pipeline = [
        {"$group": {
            "_id": "$stato",
            "count": {"$sum": 1},
            "totale": {"$sum": "$importo_riconciliato"}
        }}
    ]
    
    result = {}
    async for doc in db[COLL_MATCH].aggregate(pipeline):
        result[doc["_id"]] = {
            "count": doc["count"],
            "totale": round(doc["totale"], 2)
        }
    
    return result
