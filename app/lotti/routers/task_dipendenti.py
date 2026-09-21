"""
task_dipendenti.py
------------------
Task/checklist giornalieri per i dipendenti tablet.
I task vengono generati automaticamente ogni mattina alle 07:00 dallo scheduler
in base a: sanificazioni da fare, lotti in scadenza, produzioni pianificate.
I dipendenti li vedono dal tablet al login e li spuntano durante il turno.

Collection: task_dipendenti
"""

import uuid
import logging
from datetime import datetime, timezone, date, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel

from app.lotti.db import database as db
from app.lotti.auth import require_admin
from app.lotti.servizi.lotto_arricchimento_service import calcola_stato_scadenza

router = APIRouter(prefix="/task-dipendenti", tags=["task_dipendenti"])
logger = logging.getLogger(__name__)


class TaskIn(BaseModel):
    titolo: str
    descrizione: Optional[str] = ""
    reparto: str = "tutti"  # pasticceria | rosticceria | cucina | tutti
    priorita: str = "normale"  # urgente | normale | bassa
    assegnato_a: Optional[str] = None  # nome dipendente o None = tutti
    data: Optional[str] = None  # yyyy-mm-dd, default oggi


async def crea_task_scadenza_lotto(lotto: dict, fonte: str) -> tuple[dict, bool]:
    """Un task al giorno per il lotto reale, condiviso fra tablet e scheduler."""
    giorni = calcola_stato_scadenza(lotto.get("data_scadenza"))["giorni_alla_scadenza"]
    if giorni is None or giorni < 0:
        raise HTTPException(409, "Lotto scaduto o con scadenza da verificare: non usare")
    if (lotto.get("quantita") or 0) <= 0 or lotto.get("consumato") or lotto.get("esaurito") or lotto.get("stato") in {"smaltito", "esaurito", "bloccato_richiamo"}:
        raise HTTPException(409, "Lotto non disponibile per l'uso")
    lotto_id = lotto.get("id") or lotto.get("lotto_id")
    if not lotto_id:
        raise HTTPException(409, "Identità del lotto non disponibile")

    oggi = date.today().isoformat()
    task_id = f"scadenza:{oggi}:{lotto_id}"
    doc = {
        "_id": task_id, "id": task_id,
        "titolo": f"🕐 Usa prima: {lotto.get('prodotto') or lotto.get('prodotto_nome') or '?'}",
        "descrizione": f"Lotto {lotto.get('numero_lotto') or lotto.get('lotto_id') or lotto_id} scade il {lotto.get('data_scadenza')}.",
        "reparto": "tutti", "tipo": "scadenza", "priorita": "urgente",
        "assegnato_a": None, "data": oggi,
        "completato": False, "completato_da": None, "completato_il": None,
        "fonte": fonte, "lotto_id": lotto_id,
        "numero_lotto": lotto.get("numero_lotto") or lotto.get("lotto_id"),
        "creato_il": datetime.now(timezone.utc).isoformat(),
    }
    risultato = await db.task_dipendenti.update_one(
        {"_id": task_id}, {"$setOnInsert": doc}, upsert=True,
    )
    salvato = await db.task_dipendenti.find_one({"_id": task_id}, {"_id": 0})
    return salvato, risultato.upserted_id is not None


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/oggi")
async def get_task_oggi(reparto: Optional[str] = None):
    """Task del giorno — filtrabili per reparto."""
    oggi = date.today().isoformat()
    query = {"data": oggi, "annullato": {"$ne": True}}
    if reparto and reparto != "tutti":
        query["$or"] = [{"reparto": reparto}, {"reparto": "tutti"}]

    tasks = await db.task_dipendenti.find(query, {"_id": 0}).sort("priorita", 1).to_list(100)

    aperti = [t for t in tasks if not t.get("completato")]
    completati = [t for t in tasks if t.get("completato")]

    return {
        "data": oggi,
        "totale": len(tasks),
        "aperti": len(aperti),
        "completati": len(completati),
        "tasks": tasks,
    }


@router.post("")
async def crea_task(payload: TaskIn):
    """Crea un task manuale per i dipendenti."""
    oggi = date.today().isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "titolo": payload.titolo,
        "descrizione": payload.descrizione or "",
        "reparto": payload.reparto,
        "tipo": "manuale",
        "priorita": payload.priorita,
        "assegnato_a": payload.assegnato_a,
        "data": payload.data or oggi,
        "completato": False,
        "completato_da": None,
        "completato_il": None,
        "fonte": "manuale",
        "creato_il": datetime.now(timezone.utc).isoformat(),
    }
    await db.task_dipendenti.insert_one(doc)
    doc.pop("_id", None)
    return {"ok": True, "task": doc}


@router.post("/lotti/{lotto_id}/usa-oggi")
async def usa_oggi_lotto(lotto_id: str):
    lotto = await db.lotti.find_one({"$or": [{"id": lotto_id}, {"lotto_id": lotto_id}]}, {"_id": 0})
    if not lotto:
        raise HTTPException(404, "Lotto non trovato")
    task, creato = await crea_task_scadenza_lotto(lotto, "manuale")
    return {"ok": True, "creato": creato, "task": task}


@router.patch("/{task_id}/completa")
async def completa_task(task_id: str, operatore_nome: Optional[str] = None):
    """Segna un task come completato — chiamato dal tablet quando il dipendente lo spunta."""
    ora = datetime.now(timezone.utc)
    r = await db.task_dipendenti.update_one(
        {"id": task_id, "annullato": {"$ne": True}},
        {
            "$set": {
                "completato": True,
                "completato_da": operatore_nome or "operatore",
                "completato_il": ora.isoformat(),
            }
        },
    )
    if r.matched_count == 0:
        raise HTTPException(404, "Task non trovato")
    return {"ok": True, "completato_il": ora.isoformat()}


@router.patch("/{task_id}/annulla")
async def annulla_task(task_id: str, motivo: str = Query(...), _admin=Depends(require_admin)):
    """Ritira un task errato conservandone la storia."""
    r = await db.task_dipendenti.update_one(
        {"id": task_id, "annullato": {"$ne": True}},
        {"$set": {"annullato": True, "motivo_annullamento": motivo,
                  "annullato_il": datetime.now(timezone.utc).isoformat()}},
    )
    if r.matched_count == 0:
        raise HTTPException(404, "Task non trovato o già annullato")
    return {"ok": True, "task_id": task_id}


@router.post("/genera-oggi")
async def genera_task_giornalieri():
    """
    Genera automaticamente i task del giorno.
    Chiamata dallo scheduler alle 07:00.
    Non sovrascrive task già esistenti per oggi.
    """
    oggi = date.today().isoformat()
    ieri = (date.today() - timedelta(days=1)).isoformat()
    ora = datetime.now(timezone.utc)

    # Conta task già presenti oggi
    esistenti = await db.task_dipendenti.count_documents(
        {"data": oggi, "fonte": {"$ne": "manuale"}}
    )
    if esistenti > 0:
        return {"ok": True, "messaggio": "Task già generati per oggi", "generati": 0}

    tasks_da_creare = []

    # 1. Lotti in scadenza entro 2 giorni → task "Da usare prima".
    # data_scadenza è in formati misti (dd/mm/yyyy e yyyy-mm-dd): il confronto
    # va fatto in Python, un $lte come stringa matchava sempre le date italiane.
    candidati = await db.lotti.find(
        {
            "consumato": {"$ne": True},
            "esaurito": {"$ne": True},
            "stato": {"$nin": ["smaltito", "esaurito", "bloccato_richiamo"]},
            "quantita": {"$gt": 0},
            "data_scadenza": {"$nin": [None, ""]},
        },
        {"_id": 0, "id": 1, "lotto_id": 1, "prodotto": 1,
         "data_scadenza": 1, "numero_lotto": 1, "quantita": 1, "stato": 1,
         "consumato": 1, "esaurito": 1},
    ).to_list(2000)
    lotti_urgenti = []
    for l in candidati:
        giorni = calcola_stato_scadenza(l.get("data_scadenza"))["giorni_alla_scadenza"]
        if (l.get("id") or l.get("lotto_id")) and giorni is not None and 0 <= giorni <= 2:
            lotti_urgenti.append(l)
            if len(lotti_urgenti) >= 20:
                break

    task_scadenza_creati = []
    for lotto in lotti_urgenti:
        task, creato = await crea_task_scadenza_lotto(lotto, "auto_scadenza")
        if creato:
            task_scadenza_creati.append(task)

    # 2. Controllo temperature mattina
    tasks_da_creare.append(
        {
            "id": str(uuid.uuid4()),
            "titolo": "🌡 Controlla temperature frigo e congelatori",
            "descrizione": "Registra le temperature di tutti i frigoriferi e congelatori. Segnala qualsiasi anomalia.",
            "reparto": "tutti",
            "tipo": "temperatura",
            "priorita": "urgente",
            "assegnato_a": None,
            "data": oggi,
            "completato": False,
            "completato_da": None,
            "completato_il": None,
            "fonte": "auto_temperatura",
            "creato_il": ora.isoformat(),
        }
    )

    # 3. Task produzione da ordini ricevuti
    cutoff_3gg = (ora - timedelta(days=3)).isoformat()
    ordini_con_ricette = await db.ordini_fornitori.find(
        {
            "stato": {"$in": ["ricevuto", "inviato_fornitori"]},
            "ricette_da_produrre": {"$exists": True, "$ne": []},
            "updated_at": {"$gte": cutoff_3gg},
        },
        {"_id": 0, "ricette_da_produrre": 1},
    ).to_list(10)

    for ordine in ordini_con_ricette:
        for ricetta in ordine.get("ricette_da_produrre", []):
            if ricetta.get("prodotta"):
                continue
            nome = ricetta.get("nome") or ricetta.get("ricetta_nome", "")
            pezzi = ricetta.get("pezzi", 0)
            reparto = ricetta.get("reparto", "tutti")
            tasks_da_creare.append(
                {
                    "id": str(uuid.uuid4()),
                    "titolo": f"👨‍🍳 Da produrre: {nome}",
                    "descrizione": f"Produrre {pezzi} pezzi di {nome} come pianificato nell'ordine.",
                    "reparto": reparto or "tutti",
                    "tipo": "produzione",
                    "priorita": "normale",
                    "assegnato_a": None,
                    "data": oggi,
                    "completato": False,
                    "completato_da": None,
                    "completato_il": None,
                    "fonte": "auto_produzione",
                    "ricetta_nome": nome,
                    "creato_il": ora.isoformat(),
                }
            )

    if tasks_da_creare:
        await db.task_dipendenti.insert_many(tasks_da_creare)
        for t in tasks_da_creare:
            t.pop("_id", None)

    generati = [*task_scadenza_creati, *tasks_da_creare]
    logger.info(f"[Task] Generati {len(generati)} task per {oggi}")
    return {"ok": True, "generati": len(generati), "tasks": generati}
