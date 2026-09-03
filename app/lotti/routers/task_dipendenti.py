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
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.lotti.db import database as db

router = APIRouter(prefix="/task-dipendenti", tags=["task_dipendenti"])
logger = logging.getLogger(__name__)


class TaskIn(BaseModel):
    titolo: str
    descrizione: Optional[str] = ""
    reparto: str = "tutti"  # pasticceria | rosticceria | cucina | tutti
    tipo: str = "manuale"  # sanificazione | produzione | temperatura | scadenza | manuale
    priorita: str = "normale"  # urgente | normale | bassa
    assegnato_a: Optional[str] = None  # nome dipendente o None = tutti
    data: Optional[str] = None  # yyyy-mm-dd, default oggi


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/oggi")
async def get_task_oggi(reparto: Optional[str] = None):
    """Task del giorno — filtrabili per reparto."""
    oggi = date.today().isoformat()
    query = {"data": oggi}
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
        "tipo": payload.tipo,
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


@router.patch("/{task_id}/completa")
async def completa_task(task_id: str, operatore_nome: Optional[str] = None):
    """Segna un task come completato — chiamato dal tablet quando il dipendente lo spunta."""
    ora = datetime.now(timezone.utc)
    r = await db.task_dipendenti.update_one(
        {"id": task_id},
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


@router.delete("/{task_id}")
async def elimina_task(task_id: str):
    await db.task_dipendenti.delete_one({"id": task_id})
    return {"ok": True}


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
    from app.lotti.routers.utils import parse_data_flessibile
    fra_2gg = date.today() + timedelta(days=2)
    candidati = await db.lotti.find(
        {
            "consumato": {"$ne": True},
            "esaurito": {"$ne": True},
            "stato": {"$nin": ["smaltito", "esaurito"]},
            "data_scadenza": {"$nin": [None, ""]},
        },
        {"_id": 0, "prodotto": 1, "data_scadenza": 1, "frigo_numero": 1, "numero_lotto": 1},
    ).to_list(2000)
    lotti_urgenti = []
    for l in candidati:
        d = parse_data_flessibile(l.get("data_scadenza"))
        if d and d <= fra_2gg:
            lotti_urgenti.append(l)
            if len(lotti_urgenti) >= 20:
                break

    for lotto in lotti_urgenti:
        tasks_da_creare.append(
            {
                "id": str(uuid.uuid4()),
                "titolo": f"🕐 Usa prima: {lotto.get('prodotto','?')}",
                "descrizione": f"Lotto {lotto.get('numero_lotto','')} scade il {lotto.get('data_scadenza','')}. Usare questo prodotto in priorità oggi.",
                "reparto": "tutti",
                "tipo": "scadenza",
                "priorita": "urgente",
                "assegnato_a": None,
                "data": oggi,
                "completato": False,
                "completato_da": None,
                "completato_il": None,
                "fonte": "auto_scadenza",
                "lotto_id": lotto.get("numero_lotto"),
                "creato_il": ora.isoformat(),
            }
        )

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

    logger.info(f"[Task] Generati {len(tasks_da_creare)} task per {oggi}")
    return {"ok": True, "generati": len(tasks_da_creare), "tasks": tasks_da_creare}
