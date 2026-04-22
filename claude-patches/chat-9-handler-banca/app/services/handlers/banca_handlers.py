"""
Handler Eventi Banca — Gestionale Ceraldi Group
=================================================
Handler che si attivano quando un movimento bancario viene importato.
Cerca automaticamente match con partite aperte usando il motore di
riconciliazione a 4 livelli.

Flusso:
1. Arriva movimento da estratto conto (import CSV/PDF)
2. propagate_event("movimento_banca.importato", {...})
3. Handler cerca partite compatibili con scoring
4. Se score ≥ 0.90 → crea match confermato automaticamente
5. Se score 0.60-0.90 → crea match candidato (proposta utente)
6. Se score < 0.30 → genera alert "non riconciliato"
7. Ogni match confermato aggiorna fattura/F24/stipendio collegato
"""
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# Soglie (da riconciliazione_engine)
SOGLIA_AUTO = 0.90
SOGLIA_PROPOSTA = 0.60


# ============================================================
# HANDLER PRINCIPALE: movimento banca → cerca match
# ============================================================
async def on_movimento_banca_cerca_match(event: Dict[str, Any], db) -> Optional[Dict]:
    """
    Quando arriva un movimento bancario, cerca partite aperte compatibili.
    Crea match automatici o proposte in base allo score.
    """
    from app.services.riconciliazione_engine import cerca_match, crea_match

    movimento_id = event.get("movimento_id")
    importo = event.get("importo", 0)
    descrizione = event.get("descrizione", "")
    data = event.get("data", "")
    tipo = event.get("tipo", "")  # entrata/uscita

    if not movimento_id or abs(importo) < 0.01:
        return None

    # Ignora commissioni bancarie piccole
    if _is_commissione_bancaria(descrizione, importo):
        return {"action": "skip", "reason": "commissione bancaria"}

    # Cerca candidati
    movimento = {
        "importo": importo,
        "data": data,
        "descrizione": descrizione,
        "tipo": tipo,
        "segno": tipo
    }

    candidati = await cerca_match(movimento, db)

    if not candidati:
        # Genera alert "non riconciliato"
        from app.services.alert_engine import genera_alert
        await genera_alert(
            "RIC_NON_RICONCILIATO",
            movimento_id,
            "estratto_conto_movimenti",
            f"Movimento €{importo:.2f} del {data} senza match: {descrizione[:60]}",
            db,
            extra={"importo": importo, "data": data, "descrizione": descrizione[:100]}
        )
        return {"action": "nessun_match", "alert": "RIC_NON_RICONCILIATO"}

    risultati = []
    best = candidati[0]

    if best["score"] >= SOGLIA_AUTO:
        # Match automatico confermato
        match_doc = await crea_match(
            movimento_id=movimento_id,
            movimento_collection="estratto_conto_movimenti",
            partita_id=best["partita"]["id"],
            tipo_match=best["partita"].get("tipo", "altro"),
            importo_riconciliato=abs(importo),
            confidenza=best["score"],
            db=db,
            origine="auto"
        )

        # Propaga effetti: aggiorna entità collegata
        await _propaga_effetti_match(match_doc, best["partita"], db)

        risultati.append({
            "match_id": match_doc["id"],
            "stato": "confermato",
            "score": best["score"],
            "livello": best["livello"],
            "partita_id": best["partita"]["id"]
        })

    elif best["score"] >= SOGLIA_PROPOSTA:
        # Proposta — crea candidati per conferma utente
        for cand in candidati[:3]:  # max 3 proposte
            if cand["score"] >= SOGLIA_PROPOSTA:
                match_doc = await crea_match(
                    movimento_id=movimento_id,
                    movimento_collection="estratto_conto_movimenti",
                    partita_id=cand["partita"]["id"],
                    tipo_match=cand["partita"].get("tipo", "altro"),
                    importo_riconciliato=abs(importo),
                    confidenza=cand["score"],
                    db=db,
                    origine="proposta"
                )
                risultati.append({
                    "match_id": match_doc["id"],
                    "stato": "candidato",
                    "score": cand["score"],
                    "livello": cand["livello"]
                })

        # Alert match ambiguo se più candidati
        if len(risultati) > 1:
            from app.services.alert_engine import genera_alert
            await genera_alert(
                "RIC_MATCH_AMBIGUO",
                movimento_id,
                "estratto_conto_movimenti",
                f"Movimento €{importo:.2f} ha {len(risultati)} match possibili — conferma manuale",
                db
            )

    else:
        # Score troppo basso — alert
        from app.services.alert_engine import genera_alert
        await genera_alert(
            "RIC_NON_RICONCILIATO",
            movimento_id,
            "estratto_conto_movimenti",
            f"Movimento €{importo:.2f} del {data}: match debole (score {best['score']:.2f})",
            db
        )
        return {"action": "match_debole", "best_score": best["score"]}

    # Audit
    from app.services.audit_logger import log_evento
    await log_evento(
        modulo="riconciliazione",
        azione="match_cercato",
        entita_id=movimento_id,
        entita_collection="estratto_conto_movimenti",
        db=db,
        nuovo_stato={"candidati": len(candidati), "confermati_auto": sum(1 for r in risultati if r["stato"] == "confermato")},
        fonte="event_handler",
        dettaglio=f"€{importo:.2f} — {len(candidati)} candidati, best score {best['score']:.3f} ({best['livello']})"
    )

    return {"action": "match_trovati", "risultati": risultati}


# ============================================================
# HANDLER: conferma match → propaga effetti
# ============================================================
async def on_match_confermato_propaga(event: Dict[str, Any], db) -> Optional[Dict]:
    """
    Quando un match viene confermato (manualmente o automaticamente),
    propaga gli effetti: aggiorna fattura/F24/stipendio/POS.
    """
    match_id = event.get("match_id")
    if not match_id:
        return None

    match_doc = await db["riconciliazioni_match"].find_one(
        {"id": match_id}, {"_id": 0}
    )
    if not match_doc:
        return None

    partita = await db["partite_aperte"].find_one(
        {"id": match_doc.get("partita_id")}, {"_id": 0}
    )
    if not partita:
        return None

    await _propaga_effetti_match(match_doc, partita, db)

    # Risolvi alert
    from app.services.alert_engine import risolvi_alert
    await risolvi_alert("RIC_NON_RICONCILIATO", match_doc["movimento_id"], db)
    await risolvi_alert("RIC_MATCH_AMBIGUO", match_doc["movimento_id"], db)

    return {"action": "effetti_propagati", "tipo": partita.get("tipo")}


# ============================================================
# HANDLER: audit log movimento banca
# ============================================================
async def on_movimento_banca_audit(event: Dict[str, Any], db) -> Optional[Dict]:
    """Registra l'import di un movimento bancario nell'audit log."""
    from app.services.audit_logger import log_evento

    await log_evento(
        modulo="banca",
        azione="movimento_importato",
        entita_id=event.get("movimento_id", ""),
        entita_collection="estratto_conto_movimenti",
        db=db,
        nuovo_stato={
            "importo": event.get("importo"),
            "tipo": event.get("tipo"),
            "descrizione": (event.get("descrizione", "") or "")[:80],
        },
        fonte=event.get("source_module", "bank_import"),
        dettaglio=f"€{event.get('importo', 0):.2f} {event.get('data', '')}"
    )
    return {"action": "audit_log"}


# ============================================================
# FUNZIONI INTERNE
# ============================================================
async def _propaga_effetti_match(match_doc: Dict, partita: Dict, db):
    """
    Propaga gli effetti di un match confermato all'entità business collegata.
    Aggiorna fattura, F24, cedolino o corrispettivo in base al tipo di partita.
    """
    tipo = partita.get("tipo", "")
    documento_id = partita.get("documento_id", "")
    documento_coll = partita.get("documento_collection", "")
    importo_ric = match_doc.get("importo_riconciliato", 0)

    if not documento_id or not documento_coll:
        return

    from app.services.alert_engine import risolvi_alert

    if tipo == "fattura_fornitore":
        # Aggiorna la fattura come pagata/parzialmente pagata
        fattura = await db[documento_coll].find_one({"id": documento_id}, {"_id": 0, "importo_totale": 1, "importo_pagato": 1})
        if fattura:
            importo_totale = fattura.get("importo_totale", 0)
            importo_gia_pagato = fattura.get("importo_pagato", 0) or 0
            nuovo_pagato = round(importo_gia_pagato + importo_ric, 2)

            update_fields = {
                "importo_pagato": nuovo_pagato,
                "riconciliato": True,
                "stato_riconciliazione": "riconciliato",
                "match_id": match_doc["id"],
                "riconciliato_at": match_doc.get("confirmed_at"),
            }
            if nuovo_pagato >= importo_totale - 0.05:
                update_fields["pagato"] = True
                update_fields["stato"] = "pagata"
                update_fields["stato_pagamento"] = "pagata"
            else:
                update_fields["stato_pagamento"] = "parzialmente_pagata"

            await db[documento_coll].update_one(
                {"id": documento_id},
                {"$set": update_fields}
            )

            # Risolvi alert fattura
            await risolvi_alert("FAT_DA_PAGARE_SCADUTA", documento_id, db)
            await risolvi_alert("BNK_FAT_SENZA_RISCONTRO", documento_id, db)

    elif tipo == "f24":
        # Aggiorna F24 come pagato
        await db[documento_coll].update_one(
            {"id": documento_id},
            {"$set": {
                "stato_pagamento": "pagato",
                "pagato": True,
                "riconciliato": True,
                "match_id": match_doc["id"],
            }}
        )
        await risolvi_alert("F24_NON_PAGATO", documento_id, db)
        await risolvi_alert("F24_SCADUTO", documento_id, db)
        await risolvi_alert("F24_NON_RICONCILIATO", documento_id, db)
        await risolvi_alert("BNK_F24_NON_RICONCILIATO", documento_id, db)

    elif tipo == "stipendio":
        # Aggiorna cedolino come pagato
        await db[documento_coll].update_one(
            {"id": documento_id},
            {"$set": {
                "stato_pagamento": "pagato",
                "pagato": True,
                "riconciliato": True,
                "match_id": match_doc["id"],
            }}
        )
        await risolvi_alert("CED_NON_PAGATO", documento_id, db)
        await risolvi_alert("CED_MATCH_BANCA_AMBIGUO", documento_id, db)

    elif tipo == "pos_atteso":
        # Aggiorna corrispettivo POS come riconciliato
        await db[documento_coll].update_one(
            {"id": documento_id},
            {"$set": {
                "pos_riconciliato": True,
                "match_id": match_doc["id"],
            }}
        )
        await risolvi_alert("BNK_POS_NON_RICONCILIATO", documento_id, db)
        await risolvi_alert("RIC_POS_NON_QUADRATO", documento_id, db)

    logger.info(f"Effetti match propagati: tipo={tipo}, doc={documento_id}")


def _is_commissione_bancaria(descrizione: str, importo: float) -> bool:
    """Verifica se il movimento è una commissione bancaria da ignorare."""
    desc = (descrizione or "").upper()
    imp = abs(importo)

    keywords = ["COMMISSIONI", "COMM.", "SPESE TENUTA", "CANONE", "BOLLO", "IMPOSTA BOLLO"]
    if any(kw in desc for kw in keywords) and imp <= 50.0:
        return True

    # Importi tipici commissioni
    if imp <= 3.00 and any(kw in desc for kw in ["COMM", "SPESE"]):
        return True

    return False
