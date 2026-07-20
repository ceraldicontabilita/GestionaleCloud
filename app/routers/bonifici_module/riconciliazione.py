"""
Bonifici Module - Riconciliazione con estratto conto.
"""
from fastapi import HTTPException, Depends
from app.utils.dependencies import get_current_admin_user
from typing import Dict, Any
from datetime import datetime, timezone
import uuid
import asyncio
import logging

from app.database import Database

logger = logging.getLogger(__name__)

# Cache per task di riconciliazione
_riconciliazione_task: Dict[str, Dict[str, Any]] = {}


def _nome_beneficiario(bonifico: Dict[str, Any]) -> str:
    return (
        bonifico.get("dipendente_nome")
        or (bonifico.get("beneficiario") or {}).get("nome")
        or ""
    ).strip()


def _parse_data(value: Any):
    testo = str(value or "")
    try:
        if "T" in testo:
            return datetime.fromisoformat(
                testo.replace("+00:00", "").replace("Z", "")
            )
        return datetime.strptime(testo[:10], "%Y-%m-%d")
    except (TypeError, ValueError):
        return None


def trova_movimento_bancario_univoco(
    bonifico: Dict[str, Any], movimenti: list, movimenti_usati: set
):
    """Nome completo in causale + importo esatto + data vicina, un solo match."""
    from app.services.bonifici_pdf_ingest import nome_presente_nel_testo
    nome = _nome_beneficiario(bonifico)
    data_bonifico = _parse_data(bonifico.get("data"))
    try:
        importo_bonifico = round(abs(float(bonifico.get("importo") or 0)), 2)
    except (TypeError, ValueError):
        return None
    if not nome or not data_bonifico or importo_bonifico <= 0:
        return None

    candidati = []
    for indice, movimento in enumerate(movimenti):
        if indice in movimenti_usati or movimento.get("riconciliato") is True:
            continue
        try:
            importo_raw = float(movimento.get("importo") or 0)
        except (TypeError, ValueError):
            continue
        if round(abs(importo_raw), 2) != importo_bonifico:
            continue
        if not (movimento.get("tipo") == "uscita" or importo_raw < 0):
            continue
        data_movimento = _parse_data(movimento.get("data"))
        if not data_movimento or abs((data_bonifico - data_movimento).days) > 3:
            continue
        descrizione = (
            movimento.get("descrizione_originale")
            or movimento.get("descrizione")
            or ""
        )
        if not nome_presente_nel_testo(nome, descrizione):
            continue
        candidati.append((indice, movimento))
    return candidati[0] if len(candidati) == 1 else None


async def _registra_match_bancario(db, bonifico: Dict[str, Any], movimento: Dict[str, Any]):
    """Certifica il PDF e, se collegato, la relativa riga stipendio."""
    now = datetime.now(timezone.utc).isoformat()
    salario_id = bonifico.get("operazione_salario_id")
    descrizione = (
        movimento.get("descrizione_originale")
        or movimento.get("descrizione")
        or ""
    )
    await db.bonifici_transfers.update_one(
        {"id": bonifico.get("id")},
        {"$set": {
            "riconciliato": True,
            "stato_riconciliazione": "riconciliato_estratto_conto",
            "data_riconciliazione": now,
            "movimento_estratto_conto_id": movimento.get("id"),
            "movimento_data": movimento.get("data"),
            "movimento_descrizione": descrizione[:100],
            "riconciliazione_evidenze": [
                "nome_completo_in_causale", "importo_esatto", "data_compatibile"
            ],
        }},
    )
    await db.estratto_conto_movimenti.update_one(
        {"id": movimento.get("id")},
        {"$set": {
            "riconciliato": True,
            "tipo_riconciliazione": "bonifico_pdf_nome_importo",
            "bonifico_transfer_id": bonifico.get("id"),
            "stipendio_id": salario_id,
            "data_riconciliazione": now,
        }},
    )
    if salario_id:
        importo = round(abs(float(movimento.get("importo") or 0)), 2)
        await db.prima_nota_salari.update_one(
            {"id": salario_id},
            {"$set": {
                "importo_bonifico": importo,
                "saldo": 0.0,
                "riconciliato": True,
                "data_pagamento": str(movimento.get("data") or "")[:10],
                "movimento_bancario_id": movimento.get("id"),
                "updated_at": now,
            }},
        )


async def riconcilia_bonifici_con_estratto(background: bool = False) -> Dict[str, Any]:
    """
    Riconcilia i bonifici con i movimenti dell'estratto conto.
    Match basato su: importo esatto e data (±1 giorno).
    """
    if background:
        task_id = str(uuid.uuid4())
        _riconciliazione_task[task_id] = {
            "task_id": task_id,
            "status": "pending",
            "message": "Avvio riconciliazione...",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "processed": 0,
            "total": 0,
            "riconciliati": 0
        }
        
        asyncio.create_task(_execute_riconciliazione_batch(task_id))
        
        return {
            "background": True,
            "task_id": task_id,
            "message": "Riconciliazione avviata in background. Usa /riconcilia/task/{task_id} per lo stato."
        }
    
    # Modalità sincrona
    db = Database.get_db()
    
    bonifici = await db.bonifici_transfers.find(
        {"riconciliato": {"$ne": True}},
        {"_id": 0}
    ).to_list(10000)
    
    movimenti = await db.estratto_conto_movimenti.find({}, {"_id": 0}).to_list(50000)
    if len(movimenti) >= 50000:
        logger.warning("riconcilia_bonifici_con_estratto: raggiunto il tetto di 50000 documenti, possibile troncamento")

    if not bonifici:
        return {"success": True, "message": "Nessun bonifico da riconciliare", "riconciliati": 0}
    
    if not movimenti:
        return {"success": False, "message": "Nessun movimento estratto conto caricato", "riconciliati": 0}
    
    riconciliati = 0
    movimenti_usati = set()
    
    for bonifico in bonifici:
        match = trova_movimento_bancario_univoco(
            bonifico, movimenti, movimenti_usati
        )
        if not match:
            continue
        indice, movimento = match
        await _registra_match_bancario(db, bonifico, movimento)
        movimenti_usati.add(indice)
        riconciliati += 1
    
    return {
        "success": True,
        "message": f"Riconciliazione completata: {riconciliati} bonifici riconciliati",
        "riconciliati": riconciliati,
        "totale_bonifici": len(bonifici),
        "non_riconciliati": len(bonifici) - riconciliati
    }


async def _execute_riconciliazione_batch(task_id: str):
    """Esegue riconciliazione in background."""
    try:
        db = Database.get_db()
        
        bonifici = await db.bonifici_transfers.find(
            {"riconciliato": {"$ne": True}},
            {"_id": 0}
        ).to_list(10000)
        
        movimenti = await db.estratto_conto_movimenti.find({}, {"_id": 0}).to_list(50000)
        if len(movimenti) >= 50000:
            logger.warning("_execute_riconciliazione_batch: raggiunto il tetto di 50000 documenti, possibile troncamento")

        _riconciliazione_task[task_id]["total"] = len(bonifici)
        _riconciliazione_task[task_id]["status"] = "processing"
        
        if not bonifici or not movimenti:
            _riconciliazione_task[task_id]["status"] = "completed"
            _riconciliazione_task[task_id]["message"] = "Nessun dato da riconciliare"
            return
        
        riconciliati = 0
        movimenti_usati = set()
        
        for i, bonifico in enumerate(bonifici):
            match = trova_movimento_bancario_univoco(
                bonifico, movimenti, movimenti_usati
            )
            if match:
                indice, movimento = match
                await _registra_match_bancario(db, bonifico, movimento)
                movimenti_usati.add(indice)
                riconciliati += 1
            
            if i % 50 == 0:
                _riconciliazione_task[task_id]["processed"] = i + 1
                _riconciliazione_task[task_id]["riconciliati"] = riconciliati
        
        _riconciliazione_task[task_id]["status"] = "completed"
        _riconciliazione_task[task_id]["processed"] = len(bonifici)
        _riconciliazione_task[task_id]["riconciliati"] = riconciliati
        _riconciliazione_task[task_id]["message"] = f"Completato: {riconciliati} riconciliati"
        _riconciliazione_task[task_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
        
    except Exception as e:
        _riconciliazione_task[task_id]["status"] = "error"
        _riconciliazione_task[task_id]["message"] = str(e)


async def get_riconciliazione_task(task_id: str) -> Dict[str, Any]:
    """Stato di un task di riconciliazione in background."""
    if task_id not in _riconciliazione_task:
        raise HTTPException(status_code=404, detail="Task non trovato")
    return _riconciliazione_task[task_id]


async def stato_riconciliazione_bonifici() -> Dict[str, Any]:
    """Stato della riconciliazione bonifici."""
    db = Database.get_db()
    
    totale = await db.bonifici_transfers.count_documents({})
    riconciliati = await db.bonifici_transfers.count_documents({"riconciliato": True})
    non_riconciliati = totale - riconciliati
    
    pipeline = [
        {"$group": {
            "_id": "$riconciliato",
            "totale": {"$sum": "$importo"},
            "count": {"$sum": 1}
        }}
    ]
    stats = {doc["_id"]: {"totale": doc["totale"], "count": doc["count"]} 
             async for doc in db.bonifici_transfers.aggregate(pipeline)}
    
    return {
        "totale": totale,
        "riconciliati": riconciliati,
        "non_riconciliati": non_riconciliati,
        "percentuale": round(riconciliati / max(totale, 1) * 100, 1),
        "importo_riconciliato": round(stats.get(True, {}).get("totale", 0), 2),
        "importo_non_riconciliato": round(stats.get(False, {}).get("totale", 0) + stats.get(None, {}).get("totale", 0), 2)
    }


async def dashboard_bonifici() -> Dict[str, Any]:
    """Dashboard completa bonifici con statistiche."""
    db = Database.get_db()
    
    totale = await db.bonifici_transfers.count_documents({})
    riconciliati = await db.bonifici_transfers.count_documents({"riconciliato": True})
    
    pipeline = [
        {"$group": {
            "_id": None,
            "totale_importi": {"$sum": "$importo"},
            "importo_riconciliato": {"$sum": {"$cond": [{"$eq": ["$riconciliato", True]}, "$importo", 0]}}
        }}
    ]
    totali = await db.bonifici_transfers.aggregate(pipeline).to_list(1)
    totali = totali[0] if totali else {"totale_importi": 0, "importo_riconciliato": 0}
    
    # Jobs recenti
    jobs = await db.bonifici_jobs.find({}, {"_id": 0}).sort("created_at", -1).limit(5).to_list(5)
    
    # Per anno
    per_anno = await db.bonifici_transfers.aggregate([
        {"$addFields": {"year": {"$substr": ["$data", 0, 4]}}},
        {"$group": {
            "_id": "$year",
            "count": {"$sum": 1},
            "totale": {"$sum": "$importo"}
        }},
        {"$sort": {"_id": -1}}
    ]).to_list(10)
    
    return {
        "totale_bonifici": totale,
        "bonifici_riconciliati": riconciliati,
        "bonifici_non_riconciliati": totale - riconciliati,
        "percentuale_riconciliazione": round(riconciliati / max(totale, 1) * 100, 1),
        "totale_importi": round(totali.get("totale_importi", 0), 2),
        "importo_riconciliato": round(totali.get("importo_riconciliato", 0), 2),
        "jobs_recenti": jobs,
        "per_anno": {a["_id"]: {"count": a["count"], "totale": round(a["totale"] or 0, 2)} for a in per_anno if a["_id"]}
    }


async def reset_riconciliazione(_admin: Dict[str, Any] = Depends(get_current_admin_user)) -> Dict[str, Any]:
    """Reset riconciliazione per tutti i bonifici."""
    db = Database.get_db()
    
    result = await db.bonifici_transfers.update_many(
        {},
        {"$set": {"riconciliato": False}, "$unset": {"movimento_estratto_conto_id": "", "data_riconciliazione": ""}}
    )
    
    return {"success": True, "reset": result.modified_count}


async def associa_bonifici_dipendenti(dry_run: bool = True) -> Dict[str, Any]:
    """Associa bonifici ai dipendenti tramite nome beneficiario."""
    from app.services.bonifici_pdf_ingest import identita_coincide
    db = Database.get_db()
    
    bonifici = await db.bonifici_transfers.find(
        {"salario_associato": {"$ne": True}},
        {"_id": 0}
    ).to_list(10000)
    
    dipendenti = await db.employees.find({}, {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "iban": 1}).to_list(1000)
    
    associazioni = []
    for bonifico in bonifici:
        beneficiario = ((bonifico.get("beneficiario") or {}).get("nome") or "").strip()
        beneficiario_iban = ((bonifico.get("beneficiario") or {}).get("iban") or "").upper()
        
        if not beneficiario and not beneficiario_iban:
            continue
        
        candidati = []
        for dip in dipendenti:
            nome_completo = f"{dip.get('nome', '')} {dip.get('cognome', '')}".strip()
            dip_iban = (dip.get("iban") or "").upper()
            
            match = False
            if beneficiario_iban and dip_iban and beneficiario_iban == dip_iban:
                match = True
            elif beneficiario and nome_completo:
                match = identita_coincide(beneficiario, nome_completo)
            
            if match:
                candidati.append((dip, nome_completo))
        if len(candidati) == 1:
            dip, nome_completo = candidati[0]
            associazioni.append({
                "bonifico_id": bonifico.get("id"),
                "dipendente_id": dip.get("id"),
                "dipendente_nome": nome_completo,
                "importo": bonifico.get("importo"),
                "data": bonifico.get("data")
            })
    
    if not dry_run:
        for ass in associazioni:
            await db.bonifici_transfers.update_one(
                {"id": ass["bonifico_id"]},
                {"$set": {
                    "salario_associato": True,
                    "dipendente_id": ass["dipendente_id"],
                    "dipendente_nome": ass["dipendente_nome"],
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
    
    return {
        "dry_run": dry_run,
        "potenziali_associazioni": len(associazioni),
        "associazioni": associazioni[:50] if dry_run else [],
        "eseguite": 0 if dry_run else len(associazioni)
    }
