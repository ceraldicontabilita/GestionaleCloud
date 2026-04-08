"""
Router Learning Machine — Ceraldi ERP
PREFIX: /api/learning

Sistema di controllo intelligente che impara dai dati del gestionale.
Usa Claude API per analizzare pattern, anomalie e aggiornare regole automaticamente.

Collections MongoDB:
  learning_events   → eventi strutturati da ogni azione
  learning_regole   → regole aggiornabili senza deploy
  learning_pattern  → pattern statistici (medie, soglie, frequenze)
  learning_feedback → conferme/correzioni utente
  learning_anomalie → anomalie con score confidence

Endpoints:
  POST /api/learning/evento           → registra evento
  GET  /api/learning/dashboard        → overview ML
  GET  /api/learning/regole           → regole attive
  PUT  /api/learning/regole/{id}      → modifica regola
  GET  /api/learning/anomalie         → anomalie rilevate
  POST /api/learning/anomalie/{id}/feedback → pollice su/giù
  POST /api/learning/analizza         → trigger analisi Claude API
  GET  /api/learning/pattern          → pattern appresi
  GET  /api/learning/assegni          → assegni/bonifici da riconciliare
  GET  /api/learning/documenti        → documenti non classificati
"""

from fastapi import APIRouter, Depends, BackgroundTasks
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from datetime import datetime, timedelta
import httpx, os, json

from app.database import get_database

router = APIRouter(prefix="/api/learning", tags=["Learning Machine"])

AZIENDA_ID = "b0295759-35ce-4b34-a6b4-f01b883234ad"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ── Tipi di evento riconosciuti ──────────────────────────────
TIPI_EVENTO = {
    "f24_importato", "f24_scartato", "f24_riconciliato",
    "quietanza_importata", "quietanza_riconciliata",
    "alert_confermato", "alert_ignorato", "alert_override",
    "codice_tributo_corretto", "importo_anomalo",
    "documento_non_classificato", "documento_classificato",
    "assegno_emesso", "assegno_riconciliato",
    "dipendente_aggiunto", "cedolino_importato",
    "scadenza_rispettata", "scadenza_mancata",
    "custom",
}


def _oid(doc):
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


# ════════════════════════════════════════════════════════
# REGISTRAZIONE EVENTI
# ════════════════════════════════════════════════════════
@router.post("/evento")
async def registra_evento(
    body: dict,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Registra un evento strutturato dal gestionale.
    Ogni modulo chiama questo endpoint quando accade qualcosa di rilevante.
    """
    tipo = body.get("tipo", "custom")
    if tipo not in TIPI_EVENTO:
        tipo = "custom"

    evento = {
        "tipo": tipo,
        "modulo": body.get("modulo", "sconosciuto"),
        "payload": body.get("payload", {}),
        "utente": body.get("utente", "system"),
        "azienda_id": AZIENDA_ID,
        "timestamp": datetime.utcnow(),
        "elaborato": False,
        "anomalia_score": None,
    }

    # Analisi rapida anomalia sull'importo
    if "importo" in body.get("payload", {}):
        importo = float(body["payload"]["importo"])
        evento["importo"] = importo
        # Calcola z-score rispetto alla media storica
        stats = await db["learning_pattern"].find_one({
            "tipo": tipo,
            "modulo": body.get("modulo"),
        })
        if stats and stats.get("media") and stats.get("std") and stats["std"] > 0:
            z = abs(importo - stats["media"]) / stats["std"]
            evento["anomalia_score"] = round(z, 2)
            if z > 3.0:
                evento["anomalia_flag"] = True
                # Salva anche in anomalie
                await db["learning_anomalie"].insert_one({
                    "tipo_evento": tipo,
                    "modulo": body.get("modulo"),
                    "importo": importo,
                    "z_score": z,
                    "media_storica": stats["media"],
                    "stato": "da_verificare",
                    "confidence": min(round(z / 5, 2), 1.0),
                    "timestamp": datetime.utcnow(),
                    "payload": body.get("payload", {}),
                })

    res = await db["learning_events"].insert_one(evento)

    # Aggiorna statistiche pattern (rolling update)
    await _aggiorna_pattern(db, tipo, body.get("modulo"), body.get("payload", {}))

    return {"ok": True, "evento_id": str(res.inserted_id), "tipo": tipo}


async def _aggiorna_pattern(db, tipo: str, modulo: str, payload: dict):
    """Aggiorna le statistiche rolling per tipo+modulo."""
    if "importo" not in payload:
        return
    importo = float(payload["importo"])
    key = {"tipo": tipo, "modulo": modulo}
    existing = await db["learning_pattern"].find_one(key)
    if existing:
        n = existing.get("n", 0) + 1
        old_media = existing.get("media", importo)
        new_media = old_media + (importo - old_media) / n
        # Welford variance
        old_m2 = existing.get("m2", 0)
        new_m2 = old_m2 + (importo - old_media) * (importo - new_media)
        std = (new_m2 / n) ** 0.5 if n > 1 else 0
        await db["learning_pattern"].update_one(key, {"$set": {
            "n": n, "media": round(new_media, 2), "std": round(std, 2),
            "m2": new_m2, "ultimo_importo": importo,
            "updated_at": datetime.utcnow(),
        }})
    else:
        await db["learning_pattern"].insert_one({
            **key, "n": 1, "media": importo, "std": 0,
            "m2": 0, "ultimo_importo": importo,
            "created_at": datetime.utcnow(),
        })


# ════════════════════════════════════════════════════════
# DASHBOARD
# ════════════════════════════════════════════════════════
@router.get("/dashboard")
async def dashboard_learning(db: AsyncIOMotorDatabase = Depends(get_database)):
    """Overview completa del sistema di apprendimento."""
    oggi = datetime.utcnow()
    ieri = oggi - timedelta(days=1)
    settimana = oggi - timedelta(days=7)

    n_eventi_oggi = await db["learning_events"].count_documents({
        "timestamp": {"$gte": ieri}
    })
    n_eventi_totali = await db["learning_events"].count_documents({})
    n_regole_attive = await db["learning_regole"].count_documents({"attiva": True})
    n_anomalie_aperte = await db["learning_anomalie"].count_documents({"stato": "da_verificare"})
    n_pattern = await db["learning_pattern"].count_documents({})

    # Ultime 5 anomalie
    anomalie = []
    cursor = db["learning_anomalie"].find({"stato": "da_verificare"}).sort("timestamp", -1).limit(5)
    async for a in cursor:
        anomalie.append(_oid(a))

    # Ultime regole aggiornate
    regole = []
    cursor = db["learning_regole"].find({"attiva": True}).sort("aggiornata_il", -1).limit(5)
    async for r in cursor:
        regole.append(_oid(r))

    # Distribuzione eventi per tipo
    pipeline = [
        {"$match": {"timestamp": {"$gte": settimana}}},
        {"$group": {"_id": "$tipo", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    dist = []
    async for d in db["learning_events"].aggregate(pipeline):
        dist.append({"tipo": d["_id"], "count": d["count"]})

    return {
        "n_eventi_oggi": n_eventi_oggi,
        "n_eventi_totali": n_eventi_totali,
        "n_regole_attive": n_regole_attive,
        "n_anomalie_aperte": n_anomalie_aperte,
        "n_pattern": n_pattern,
        "anomalie_recenti": anomalie,
        "regole_recenti": regole,
        "distribuzione_eventi_7gg": dist,
        "generato_il": oggi.isoformat(),
    }


# ════════════════════════════════════════════════════════
# REGOLE
# ════════════════════════════════════════════════════════
@router.get("/regole")
async def lista_regole(db: AsyncIOMotorDatabase = Depends(get_database)):
    cursor = db["learning_regole"].find().sort("priorita", -1)
    return [_oid(r) async for r in cursor]


@router.put("/regole/{rid}")
async def aggiorna_regola(rid: str, body: dict, db: AsyncIOMotorDatabase = Depends(get_database)):
    """Modifica una regola — può farlo l'utente o Claude dopo analisi."""
    update = {k: v for k, v in body.items() if k not in ("_id",)}
    update["aggiornata_il"] = datetime.utcnow()
    update["aggiornata_da"] = body.get("aggiornata_da", "utente")
    await db["learning_regole"].update_one(
        {"_id": ObjectId(rid)}, {"$set": update}
    )
    doc = await db["learning_regole"].find_one({"_id": ObjectId(rid)})
    return _oid(doc)


@router.post("/regole")
async def crea_regola(body: dict, db: AsyncIOMotorDatabase = Depends(get_database)):
    """Crea una nuova regola (manualmente o proposta da Claude)."""
    regola = {
        "nome": body.get("nome", "Regola senza nome"),
        "descrizione": body.get("descrizione", ""),
        "tipo": body.get("tipo", "custom"),
        "condizione": body.get("condizione", {}),
        "azione": body.get("azione", {}),
        "priorita": body.get("priorita", 5),
        "attiva": True,
        "confidence": body.get("confidence", 1.0),
        "origine": body.get("origine", "manuale"),
        "creata_il": datetime.utcnow(),
        "aggiornata_il": datetime.utcnow(),
        "aggiornata_da": body.get("aggiornata_da", "utente"),
        "hit_count": 0,
        "azienda_id": AZIENDA_ID,
    }
    res = await db["learning_regole"].insert_one(regola)
    return {"ok": True, "id": str(res.inserted_id)}


# ════════════════════════════════════════════════════════
# ANOMALIE + FEEDBACK
# ════════════════════════════════════════════════════════
@router.get("/anomalie")
async def lista_anomalie(
    stato: str = "da_verificare",
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    query = {}
    if stato != "tutte":
        query["stato"] = stato
    cursor = db["learning_anomalie"].find(query).sort("timestamp", -1).limit(50)
    return [_oid(a) async for a in cursor]


@router.post("/anomalie/{aid}/feedback")
async def feedback_anomalia(
    aid: str,
    body: dict,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Pollice su/giù su un'anomalia.
    Rafforza o indebolisce la regola che l'ha generata.
    """
    voto = body.get("voto")  # "confermata" | "falso_positivo" | "ignorata"
    nota = body.get("nota", "")

    feedback = {
        "anomalia_id": aid,
        "voto": voto,
        "nota": nota,
        "timestamp": datetime.utcnow(),
        "azienda_id": AZIENDA_ID,
    }
    await db["learning_feedback"].insert_one(feedback)

    # Aggiorna stato anomalia
    await db["learning_anomalie"].update_one(
        {"_id": ObjectId(aid)},
        {"$set": {"stato": voto, "nota_feedback": nota, "feedback_il": datetime.utcnow()}}
    )

    # Aggiorna confidence delle regole collegate
    if voto == "falso_positivo":
        # Riduci sensibilità soglia per questo tipo
        anomalia = await db["learning_anomalie"].find_one({"_id": ObjectId(aid)})
        if anomalia:
            await db["learning_pattern"].update_one(
                {"tipo": anomalia.get("tipo_evento"), "modulo": anomalia.get("modulo")},
                {"$inc": {"falsi_positivi": 1}},
                upsert=True,
            )

    return {"ok": True, "voto": voto}


# ════════════════════════════════════════════════════════
# ANALISI CLAUDE API (trigger manuale o batch)
# ════════════════════════════════════════════════════════
@router.post("/analizza")
async def trigger_analisi(
    body: dict,
    background_tasks: BackgroundTasks,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Triggera un'analisi Claude API sugli eventi recenti.
    Claude analizza i pattern e propone: nuove regole, soglie aggiornate, anomalie.
    """
    n_eventi = body.get("n_eventi", 50)
    background_tasks.add_task(_run_analisi_claude, db, n_eventi)
    return {"ok": True, "messaggio": f"Analisi avviata su ultimi {n_eventi} eventi"}


async def _run_analisi_claude(db, n_eventi: int):
    """Chiama Claude API per analizzare gli eventi e proporre aggiornamenti."""
    if not ANTHROPIC_API_KEY:
        return

    # Raccoglie eventi recenti
    eventi = []
    cursor = db["learning_events"].find({"elaborato": False}).sort("timestamp", -1).limit(n_eventi)
    async for e in cursor:
        e["_id"] = str(e["_id"])
        e["timestamp"] = e["timestamp"].isoformat() if hasattr(e.get("timestamp"), "isoformat") else str(e.get("timestamp"))
        eventi.append(e)

    if not eventi:
        return

    # Raccoglie regole attuali
    regole = []
    async for r in db["learning_regole"].find({"attiva": True}):
        r["_id"] = str(r["_id"])
        regole.append(r)

    # Prompt per Claude
    prompt = f"""Sei il sistema di Learning Machine del Ceraldi ERP.
Analizza questi {len(eventi)} eventi recenti e le {len(regole)} regole attuali.

EVENTI RECENTI:
{json.dumps(eventi[:20], ensure_ascii=False, indent=2)}

REGOLE ATTUALI:
{json.dumps(regole[:10], ensure_ascii=False, indent=2)}

Rispondi SOLO con JSON (nessun testo extra) con questa struttura:
{{
  "nuove_regole": [
    {{
      "nome": "...",
      "descrizione": "...",
      "tipo": "...",
      "condizione": {{}},
      "azione": {{}},
      "priorita": 5,
      "confidence": 0.9
    }}
  ],
  "regole_da_aggiornare": [
    {{
      "id": "...",
      "campo": "...",
      "nuovo_valore": "...",
      "motivo": "..."
    }}
  ],
  "pattern_rilevati": [
    {{
      "descrizione": "...",
      "frequenza": "...",
      "impatto": "alto|medio|basso"
    }}
  ],
  "anomalie_proposte": [
    {{
      "tipo_evento": "...",
      "descrizione": "...",
      "confidence": 0.8
    }}
  ],
  "sommario": "..."
}}"""

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 2000,
                    "messages": [{"role": "user", "content": prompt}],
                }
            )
            data = resp.json()
            text = data.get("content", [{}])[0].get("text", "{}")

            # Pulisce eventuali backtick
            text = text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            result = json.loads(text)

            # Salva le proposte di Claude
            analisi_doc = {
                "timestamp": datetime.utcnow(),
                "n_eventi_analizzati": len(eventi),
                "nuove_regole_proposte": result.get("nuove_regole", []),
                "regole_aggiornamenti": result.get("regole_da_aggiornare", []),
                "pattern_rilevati": result.get("pattern_rilevati", []),
                "anomalie_proposte": result.get("anomalie_proposte", []),
                "sommario": result.get("sommario", ""),
                "stato": "da_approvare",
                "azienda_id": AZIENDA_ID,
            }
            await db["learning_analisi"].insert_one(analisi_doc)

            # Applica automaticamente le regole ad alta confidence
            for regola in result.get("nuove_regole", []):
                if float(regola.get("confidence", 0)) >= 0.85:
                    regola["origine"] = "claude_auto"
                    regola["attiva"] = True
                    regola["creata_il"] = datetime.utcnow()
                    regola["aggiornata_il"] = datetime.utcnow()
                    regola["aggiornata_da"] = "claude"
                    regola["hit_count"] = 0
                    regola["azienda_id"] = AZIENDA_ID
                    await db["learning_regole"].insert_one(regola)

            # Segna eventi come elaborati
            event_ids = [e["_id"] for e in eventi]
            await db["learning_events"].update_many(
                {"_id": {"$in": [ObjectId(eid) for eid in event_ids]}},
                {"$set": {"elaborato": True}}
            )

    except Exception as exc:
        await db["learning_analisi"].insert_one({
            "timestamp": datetime.utcnow(),
            "errore": str(exc),
            "stato": "errore",
        })


# ════════════════════════════════════════════════════════
# PATTERN
# ════════════════════════════════════════════════════════
@router.get("/pattern")
async def lista_pattern(db: AsyncIOMotorDatabase = Depends(get_database)):
    cursor = db["learning_pattern"].find().sort("n", -1).limit(30)
    return [_oid(p) async for p in cursor]


# ════════════════════════════════════════════════════════
# ASSEGNI — documenti da riconciliare
# ════════════════════════════════════════════════════════
@router.get("/assegni")
async def assegni_da_riconciliare(db: AsyncIOMotorDatabase = Depends(get_database)):
    """Movimenti bancari (assegni/bonifici) non ancora riconciliati."""
    cursor = db["estratto_conto_movimenti"].find({
        "azienda_id": AZIENDA_ID,
        "riconciliato": {"$ne": True},
        "tipo": {"$in": ["assegno", "bonifico_uscita", "bonifico_entrata"]},
    }).sort("data", -1).limit(50)
    docs = [_oid(d) async for d in cursor]

    # Suggerisci match automatici con fatture
    for doc in docs:
        importo = doc.get("importo", 0)
        # Cerca fattura con importo simile
        match = await db["fatture_passive"].find_one({
            "azienda_id": AZIENDA_ID,
            "importo_totale": {"$gte": importo - 0.50, "$lte": importo + 0.50},
            "pagata": {"$ne": True},
        })
        if match:
            doc["suggerimento_match"] = {
                "tipo": "fattura_passiva",
                "id": str(match["_id"]),
                "fornitore": match.get("fornitore", {}).get("denominazione", "?"),
                "importo": match.get("importo_totale"),
                "confidence": 0.90,
            }

    return docs


# ════════════════════════════════════════════════════════
# DOCUMENTI — non classificati
# ════════════════════════════════════════════════════════
@router.get("/documenti")
async def documenti_non_classificati(db: AsyncIOMotorDatabase = Depends(get_database)):
    """Documenti importati ma non ancora classificati o riconciliati."""
    risultati = []

    # F24 senza quietanza
    cursor = db["f24"].find({
        "azienda_id": AZIENDA_ID,
        "stato": {"$nin": ["scartato", "riconciliato"]},
        "riconciliazione_quietanza": {"$exists": False},
    }).sort("scadenza", -1).limit(20)
    async for doc in cursor:
        risultati.append({
            "tipo": "f24_senza_quietanza",
            "id": str(doc["_id"]),
            "descrizione": f"F24 {doc.get('scadenza', '?')} — {doc.get('saldo_finale', 0):.2f}€",
            "priorita": "media",
        })

    # Quietanze senza F24
    cursor = db["quietanze"].find({
        "azienda_id": AZIENDA_ID,
        "f24_id": {"$exists": False},
    }).sort("data_versamento", -1).limit(20)
    async for doc in cursor:
        risultati.append({
            "tipo": "quietanza_senza_f24",
            "id": str(doc["_id"]),
            "descrizione": f"Quietanza {doc.get('data_versamento', '?')} — {doc.get('saldo_finale', 0):.2f}€",
            "priorita": "bassa",
        })

    # Avvisi bonari non abbinati a documenti
    cursor = db["quietanze"].find({
        "note_avviso_bonario": True,
        "documento_correlato_id": {"$exists": False},
    }).limit(10)
    async for doc in cursor:
        risultati.append({
            "tipo": "avviso_bonario_non_abbinato",
            "id": str(doc["_id"]),
            "codice_atto": doc.get("codice_atto"),
            "descrizione": f"Avviso bonario cod. {doc.get('codice_atto', '?')} — {doc.get('saldo_finale', 0):.2f}€",
            "priorita": "alta",
        })

    return risultati
