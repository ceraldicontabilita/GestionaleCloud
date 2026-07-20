"""Router Agenti AI — segnalazioni, stato, gestione."""
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from typing import Any, Dict, Optional
from datetime import datetime, timezone

from app.database import Database
from app.utils.dependencies import get_current_admin_user

router = APIRouter(tags=["Agenti AI"])


@router.get("/segnalazioni")
async def get_segnalazioni(
    non_lette: bool = Query(False),
    tipo: Optional[str] = Query(None),
    limit: int = Query(50)
):
    """Restituisce le segnalazioni degli agenti AI."""
    db = Database.get_db()
    query = {}
    if non_lette:
        query["letta"] = False
    if tipo:
        query["tipo"] = tipo
    segnalazioni = await db["agenti_segnalazioni"].find(
        query, {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    return {"segnalazioni": segnalazioni, "totale": len(segnalazioni)}


@router.get("/segnalazioni/count")
async def get_count_non_lette():
    """Contatore badge segnalazioni non lette."""
    db = Database.get_db()
    count = await db["agenti_segnalazioni"].count_documents({"letta": False})
    return {"non_lette": count}


@router.get("/segnalazioni/summary")
async def get_segnalazioni_summary():
    """Contatori per tipo — usato dal widget dashboard."""
    db = Database.get_db()
    pipeline = [
        {"$match": {"risolta": {"$ne": True}}},
        {"$group": {"_id": "$tipo", "count": {"$sum": 1}}}
    ]
    rows = await db["agenti_segnalazioni"].aggregate(pipeline).to_list(20)
    result = {"urgente": 0, "avviso": 0, "info": 0, "suggerimento": 0, "anomalia": 0}
    for r in rows:
        tipo = r["_id"] or "info"
        if tipo in result:
            result[tipo] += r["count"]
    # Urgenti include anche anomalie
    result["urgente"] += result.pop("anomalia", 0)
    result["totale"] = sum(result.values())
    return result


@router.put("/segnalazioni/{sid}/letta")
async def segna_letta(sid: str):
    """Segna una segnalazione come letta."""
    db = Database.get_db()
    await db["agenti_segnalazioni"].update_one(
        {"id": sid},
        {"$set": {"letta": True, "letta_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"status": "ok"}


@router.put("/segnalazioni/{sid}/risolta")
async def segna_risolta(sid: str):
    """Segna una segnalazione come risolta."""
    db = Database.get_db()
    await db["agenti_segnalazioni"].update_one(
        {"id": sid},
        {"$set": {"risolta": True, "risolta_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"status": "ok"}


@router.get("/stato")
async def get_stato_agenti():
    """Stato di tutti gli agenti AI."""
    db = Database.get_db()
    stati = await db["agenti_stato"].find({}, {"_id": 0}).to_list(20)
    return {"agenti": stati}


@router.post("/run")
async def run_agenti_manuale(agente: Optional[str] = Query(None)):
    """Esegue manualmente gli agenti AI. Se 'agente' e' passato (bottone
    'Esegui ora' sulla singola card), esegue solo quell'agente — prima il
    parametro non esisteva e ogni card, qualunque fosse, lanciava sempre
    l'intero giro di TUTTI gli agenti."""
    db = Database.get_db()
    try:
        from app.agents.orchestrator import run_agenti
        await run_agenti(db, agente_specifico=agente)
        msg = f"Agente {agente} eseguito con successo" if agente else "Agenti eseguiti con successo"
        return {"status": "ok", "message": msg}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=423, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Esecuzione agenti non riuscita") from exc


@router.get("/pattern-appresi")
async def get_pattern_appresi(categoria: str = Query(None)):
    """Pattern appresi dalla LearningCervello."""
    db = Database.get_db()
    query = {"confidenza": {"$gte": 0.3}}
    if categoria:
        query["categoria"] = categoria
    pattern = await db["agenti_apprendimenti"].find(
        query, {"_id": 0}
    ).sort("occorrenze", -1).limit(100).to_list(100)
    categorie = list({p.get("categoria", "generico") for p in pattern})
    return {"pattern": pattern, "totale": len(pattern), "categorie": categorie}


@router.get("/decisioni")
async def get_decisioni(
    stato: Optional[str] = Query(None),
    agente: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """Registro strutturato delle decisioni, dalla piu' recente."""
    db = Database.get_db()
    query: Dict[str, Any] = {}
    if stato:
        query["execution_status"] = stato
    if agente:
        query["agent"] = agente
    decisioni = await db["ai_decisions"].find(
        query, {"_id": 0}
    ).sort("timestamp", -1).limit(limit).to_list(limit)
    return {"decisioni": decisioni, "totale": len(decisioni)}


@router.get("/decisioni/{decision_id}/eventi")
async def get_eventi_decisione(decision_id: str):
    """Cronologia append-only di una decisione."""
    db = Database.get_db()
    eventi = await db["ai_decision_events"].find(
        {"decision_id": decision_id}, {"_id": 0}
    ).sort("timestamp", 1).to_list(500)
    return {"eventi": eventi, "totale": len(eventi)}


def _identita_admin(admin: Dict[str, Any]) -> str:
    return str(admin.get("email") or admin.get("user_id") or "admin")


@router.post("/decisioni/{decision_id}/approva")
async def approva_decisione(
    decision_id: str,
    body: Optional[Dict[str, Any]] = Body(None),
    admin: Dict[str, Any] = Depends(get_current_admin_user),
):
    """Approva umanamente la proposta, senza eseguirla."""
    from app.agents.decision_engine import cambia_stato_decisione

    try:
        decisione = await cambia_stato_decisione(
            Database.get_db(),
            decision_id,
            True,
            _identita_admin(admin),
            str((body or {}).get("nota") or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not decisione:
        raise HTTPException(status_code=404, detail="Decisione non trovata")
    return {"status": "approved_pending_execution", "decisione": decisione}


@router.post("/decisioni/{decision_id}/rifiuta")
async def rifiuta_decisione(
    decision_id: str,
    body: Optional[Dict[str, Any]] = Body(None),
    admin: Dict[str, Any] = Depends(get_current_admin_user),
):
    """Rifiuta umanamente una proposta e ne registra il motivo."""
    from app.agents.decision_engine import cambia_stato_decisione

    try:
        decisione = await cambia_stato_decisione(
            Database.get_db(),
            decision_id,
            False,
            _identita_admin(admin),
            str((body or {}).get("nota") or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not decisione:
        raise HTTPException(status_code=404, detail="Decisione non trovata")
    return {"status": "rejected", "decisione": decisione}


@router.get("/automazioni/stato")
async def get_stato_automazioni():
    from app.agents.decision_engine import automazioni_sospese

    sospese = await automazioni_sospese(Database.get_db())
    return {"sospese": sospese, "modalita": "shadow"}


@router.post("/automazioni/ferma")
async def ferma_automazioni(admin: Dict[str, Any] = Depends(get_current_admin_user)):
    from app.agents.decision_engine import imposta_automazioni

    return await imposta_automazioni(Database.get_db(), True, _identita_admin(admin))


@router.post("/automazioni/riprendi")
async def riprendi_automazioni(admin: Dict[str, Any] = Depends(get_current_admin_user)):
    from app.agents.decision_engine import imposta_automazioni

    return await imposta_automazioni(Database.get_db(), False, _identita_admin(admin))
