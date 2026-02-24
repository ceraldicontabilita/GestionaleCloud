"""
To-Do Router - Gestione Task e Promemoria
==========================================

Funzionalità:
- CRUD task
- Priorità (alta, media, bassa)
- Scadenze con promemoria
- Collegamento a documenti (fatture, verbali, fornitori)
- Filtri per stato, priorità, assegnatario
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel
import uuid

from app.database import Database
from app.utils.error_handler import handle_errors

router = APIRouter()

COLLECTION = "todo_tasks"


# =============================================================================
# MODELLI PYDANTIC
# =============================================================================

class TaskCreate(BaseModel):
    titolo: str
    descrizione: Optional[str] = ""
    priorita: str = "media"  # alta, media, bassa
    scadenza: Optional[str] = None  # YYYY-MM-DD
    categoria: Optional[str] = "generale"
    assegnato_a: Optional[str] = None
    # Collegamento documenti
    fattura_id: Optional[str] = None
    verbale_id: Optional[str] = None
    fornitore_id: Optional[str] = None
    documento_tipo: Optional[str] = None  # fattura, verbale, fornitore, f24, altro
    documento_riferimento: Optional[str] = None


class TaskUpdate(BaseModel):
    titolo: Optional[str] = None
    descrizione: Optional[str] = None
    priorita: Optional[str] = None
    scadenza: Optional[str] = None
    categoria: Optional[str] = None
    assegnato_a: Optional[str] = None
    completato: Optional[bool] = None
    fattura_id: Optional[str] = None
    verbale_id: Optional[str] = None
    fornitore_id: Optional[str] = None
    documento_tipo: Optional[str] = None
    documento_riferimento: Optional[str] = None


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/lista")
@handle_errors
async def get_tasks(
    stato: Optional[str] = Query(None, description="da_fare, completato, tutti"),
    priorita: Optional[str] = Query(None, description="alta, media, bassa"),
    categoria: Optional[str] = Query(None),
    scadenza_entro: Optional[int] = Query(None, description="Giorni dalla scadenza"),
    cerca: Optional[str] = Query(None, description="Ricerca nel titolo/descrizione"),
    limit: int = Query(100, le=500)
) -> Dict[str, Any]:
    """Lista task con filtri."""
    db = Database.get_db()
    
    query = {}
    
    # Filtro stato
    if stato == "da_fare":
        query["completato"] = {"$ne": True}
    elif stato == "completato":
        query["completato"] = True
    
    # Filtro priorità
    if priorita:
        query["priorita"] = priorita
    
    # Filtro categoria
    if categoria:
        query["categoria"] = categoria
    
    # Filtro scadenza
    if scadenza_entro is not None:
        data_limite = (datetime.now() + timedelta(days=scadenza_entro)).strftime("%Y-%m-%d")
        query["scadenza"] = {"$lte": data_limite, "$ne": None}
    
    # Ricerca testo
    if cerca:
        query["$or"] = [
            {"titolo": {"$regex": cerca, "$options": "i"}},
            {"descrizione": {"$regex": cerca, "$options": "i"}}
        ]
    
    # Ordina per: priorità (alta prima), poi scadenza (prima le più vicine)
    tasks = await db[COLLECTION].find(query, {"_id": 0}).sort([
        ("completato", 1),  # Non completati prima
        ("priorita_ordine", 1),  # Alta (1), Media (2), Bassa (3)
        ("scadenza", 1)  # Scadenze più vicine prima
    ]).limit(limit).to_list(limit)
    
    # Calcola statistiche
    totale = await db[COLLECTION].count_documents({})
    da_fare = await db[COLLECTION].count_documents({"completato": {"$ne": True}})
    completati = await db[COLLECTION].count_documents({"completato": True})
    
    # Scadenze imminenti (prossimi 3 giorni)
    oggi = datetime.now().strftime("%Y-%m-%d")
    tra_3_giorni = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
    urgenti = await db[COLLECTION].count_documents({
        "completato": {"$ne": True},
        "scadenza": {"$lte": tra_3_giorni, "$gte": oggi}
    })
    
    # Scaduti
    scaduti = await db[COLLECTION].count_documents({
        "completato": {"$ne": True},
        "scadenza": {"$lt": oggi}
    })
    
    return {
        "success": True,
        "tasks": tasks,
        "stats": {
            "totale": totale,
            "da_fare": da_fare,
            "completati": completati,
            "urgenti": urgenti,
            "scaduti": scaduti
        }
    }


@router.post("/crea")
@handle_errors
async def crea_task(task: TaskCreate) -> Dict[str, Any]:
    """Crea un nuovo task."""
    db = Database.get_db()
    
    # Mappa priorità a numero per ordinamento
    priorita_ordine = {"alta": 1, "media": 2, "bassa": 3}.get(task.priorita, 2)
    
    nuovo_task = {
        "id": str(uuid.uuid4()),
        "titolo": task.titolo,
        "descrizione": task.descrizione or "",
        "priorita": task.priorita,
        "priorita_ordine": priorita_ordine,
        "scadenza": task.scadenza,
        "categoria": task.categoria or "generale",
        "assegnato_a": task.assegnato_a,
        "completato": False,
        "completato_at": None,
        # Documenti collegati
        "fattura_id": task.fattura_id,
        "verbale_id": task.verbale_id,
        "fornitore_id": task.fornitore_id,
        "documento_tipo": task.documento_tipo,
        "documento_riferimento": task.documento_riferimento,
        # Audit
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db[COLLECTION].insert_one(nuovo_task)
    
    return {
        "success": True,
        "message": "Task creato con successo",
        "task": {k: v for k, v in nuovo_task.items() if k != "_id"}
    }


@router.put("/{task_id}")
@handle_errors
async def aggiorna_task(task_id: str, task: TaskUpdate) -> Dict[str, Any]:
    """Aggiorna un task esistente."""
    db = Database.get_db()
    
    # Trova task esistente
    esistente = await db[COLLECTION].find_one({"id": task_id})
    if not esistente:
        raise HTTPException(status_code=404, detail="Task non trovato")
    
    # Prepara aggiornamento
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    
    if task.titolo is not None:
        update_data["titolo"] = task.titolo
    if task.descrizione is not None:
        update_data["descrizione"] = task.descrizione
    if task.priorita is not None:
        update_data["priorita"] = task.priorita
        update_data["priorita_ordine"] = {"alta": 1, "media": 2, "bassa": 3}.get(task.priorita, 2)
    if task.scadenza is not None:
        update_data["scadenza"] = task.scadenza
    if task.categoria is not None:
        update_data["categoria"] = task.categoria
    if task.assegnato_a is not None:
        update_data["assegnato_a"] = task.assegnato_a
    if task.completato is not None:
        update_data["completato"] = task.completato
        if task.completato:
            update_data["completato_at"] = datetime.now(timezone.utc).isoformat()
        else:
            update_data["completato_at"] = None
    
    # Documenti collegati
    if task.fattura_id is not None:
        update_data["fattura_id"] = task.fattura_id
    if task.verbale_id is not None:
        update_data["verbale_id"] = task.verbale_id
    if task.fornitore_id is not None:
        update_data["fornitore_id"] = task.fornitore_id
    if task.documento_tipo is not None:
        update_data["documento_tipo"] = task.documento_tipo
    if task.documento_riferimento is not None:
        update_data["documento_riferimento"] = task.documento_riferimento
    
    await db[COLLECTION].update_one({"id": task_id}, {"$set": update_data})
    
    # Recupera task aggiornato
    aggiornato = await db[COLLECTION].find_one({"id": task_id}, {"_id": 0})
    
    return {
        "success": True,
        "message": "Task aggiornato",
        "task": aggiornato
    }


@router.put("/{task_id}/completa")
@handle_errors
async def completa_task(task_id: str) -> Dict[str, Any]:
    """Marca un task come completato."""
    db = Database.get_db()
    
    result = await db[COLLECTION].update_one(
        {"id": task_id},
        {"$set": {
            "completato": True,
            "completato_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Task non trovato")
    
    return {"success": True, "message": "Task completato"}


@router.put("/{task_id}/riapri")
@handle_errors
async def riapri_task(task_id: str) -> Dict[str, Any]:
    """Riapre un task completato."""
    db = Database.get_db()
    
    result = await db[COLLECTION].update_one(
        {"id": task_id},
        {"$set": {
            "completato": False,
            "completato_at": None,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Task non trovato")
    
    return {"success": True, "message": "Task riaperto"}


@router.delete("/{task_id}")
@handle_errors
async def elimina_task(task_id: str) -> Dict[str, Any]:
    """Elimina un task."""
    db = Database.get_db()
    
    result = await db[COLLECTION].delete_one({"id": task_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Task non trovato")
    
    return {"success": True, "message": "Task eliminato"}


@router.get("/categorie")
@handle_errors
async def get_categorie() -> Dict[str, Any]:
    """Restituisce le categorie disponibili."""
    db = Database.get_db()
    
    # Categorie predefinite
    predefinite = [
        "generale",
        "fatture",
        "verbali",
        "fornitori",
        "f24",
        "scadenze",
        "dipendenti",
        "noleggio",
        "haccp",
        "altro"
    ]
    
    # Categorie usate
    pipeline = [
        {"$group": {"_id": "$categoria"}},
        {"$match": {"_id": {"$ne": None}}}
    ]
    usate = await db[COLLECTION].aggregate(pipeline).to_list(100)
    categorie_usate = [c["_id"] for c in usate]
    
    # Unisci predefinite + usate
    tutte = list(set(predefinite + categorie_usate))
    tutte.sort()
    
    return {
        "success": True,
        "categorie": tutte
    }


@router.get("/scadenze-oggi")
@handle_errors
async def get_scadenze_oggi() -> Dict[str, Any]:
    """Restituisce i task in scadenza oggi."""
    db = Database.get_db()
    
    oggi = datetime.now().strftime("%Y-%m-%d")
    
    tasks = await db[COLLECTION].find({
        "completato": {"$ne": True},
        "scadenza": oggi
    }, {"_id": 0}).to_list(100)
    
    return {
        "success": True,
        "data": oggi,
        "tasks": tasks,
        "totale": len(tasks)
    }


@router.get("/scadenze-settimana")
@handle_errors
async def get_scadenze_settimana() -> Dict[str, Any]:
    """Restituisce i task in scadenza questa settimana."""
    db = Database.get_db()
    
    oggi = datetime.now().strftime("%Y-%m-%d")
    tra_7_giorni = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    
    tasks = await db[COLLECTION].find({
        "completato": {"$ne": True},
        "scadenza": {"$gte": oggi, "$lte": tra_7_giorni}
    }, {"_id": 0}).sort("scadenza", 1).to_list(100)
    
    return {
        "success": True,
        "da": oggi,
        "a": tra_7_giorni,
        "tasks": tasks,
        "totale": len(tasks)
    }


@router.get("/statistiche")
@handle_errors
async def get_statistiche() -> Dict[str, Any]:
    """Statistiche complete dei task."""
    db = Database.get_db()
    
    oggi = datetime.now().strftime("%Y-%m-%d")
    
    # Totali
    totale = await db[COLLECTION].count_documents({})
    da_fare = await db[COLLECTION].count_documents({"completato": {"$ne": True}})
    completati = await db[COLLECTION].count_documents({"completato": True})
    
    # Per priorità
    alta = await db[COLLECTION].count_documents({"priorita": "alta", "completato": {"$ne": True}})
    media = await db[COLLECTION].count_documents({"priorita": "media", "completato": {"$ne": True}})
    bassa = await db[COLLECTION].count_documents({"priorita": "bassa", "completato": {"$ne": True}})
    
    # Scaduti
    scaduti = await db[COLLECTION].count_documents({
        "completato": {"$ne": True},
        "scadenza": {"$lt": oggi, "$ne": None}
    })
    
    # In scadenza oggi
    oggi_count = await db[COLLECTION].count_documents({
        "completato": {"$ne": True},
        "scadenza": oggi
    })
    
    # Per categoria
    pipeline = [
        {"$match": {"completato": {"$ne": True}}},
        {"$group": {"_id": "$categoria", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    per_categoria = await db[COLLECTION].aggregate(pipeline).to_list(20)
    
    return {
        "success": True,
        "statistiche": {
            "totale": totale,
            "da_fare": da_fare,
            "completati": completati,
            "percentuale_completamento": round((completati / totale * 100) if totale > 0 else 0, 1),
            "per_priorita": {
                "alta": alta,
                "media": media,
                "bassa": bassa
            },
            "scaduti": scaduti,
            "in_scadenza_oggi": oggi_count,
            "per_categoria": {c["_id"] or "senza_categoria": c["count"] for c in per_categoria}
        }
    }
