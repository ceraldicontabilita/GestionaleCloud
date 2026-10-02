"""Router Agenti AI — segnalazioni, stato, gestione, cruscotto per settore e proposte AI.

Ogni route e' solo admin: il cruscotto legge code e giri di tutta la contabilita'.
"""
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from typing import Any, Dict, Optional
from datetime import datetime, timezone

from app.database import Database
from app.utils.dependencies import get_current_admin_mfa_user, get_current_admin_user

router = APIRouter(tags=["Agenti AI"])


@router.get("/cash-flow-13-settimane")
async def get_cash_flow_13_settimane(
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
):
    """Previsione aggregata e di sola lettura; solo admin, come tutto il cruscotto."""
    from app.services.cash_flow_13w_service import calcola_cash_flow_13_settimane

    return await calcola_cash_flow_13_settimane(Database.get_db())


@router.get("/segnalazioni")
async def get_segnalazioni(
    non_lette: bool = Query(False),
    tipo: Optional[str] = Query(None),
    limit: int = Query(50),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
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
async def get_count_non_lette(_admin: Dict[str, Any] = Depends(get_current_admin_user)):
    """Contatore badge segnalazioni non lette."""
    db = Database.get_db()
    count = await db["agenti_segnalazioni"].count_documents({"letta": False})
    return {"non_lette": count}


@router.get("/segnalazioni/summary")
async def get_segnalazioni_summary(_admin: Dict[str, Any] = Depends(get_current_admin_user)):
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
async def segna_letta(sid: str, _admin: Dict[str, Any] = Depends(get_current_admin_user)):
    """Segna una segnalazione come letta."""
    db = Database.get_db()
    await db["agenti_segnalazioni"].update_one(
        {"id": sid},
        {"$set": {"letta": True, "letta_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"status": "ok"}


@router.put("/segnalazioni/{sid}/risolta")
async def segna_risolta(sid: str, _admin: Dict[str, Any] = Depends(get_current_admin_user)):
    """Segna una segnalazione come risolta."""
    db = Database.get_db()
    await db["agenti_segnalazioni"].update_one(
        {"id": sid},
        {"$set": {"risolta": True, "risolta_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"status": "ok"}


@router.get("/stato")
async def get_stato_agenti(_admin: Dict[str, Any] = Depends(get_current_admin_user)):
    """Stato di tutti gli agenti AI."""
    db = Database.get_db()
    stati = await db["agenti_stato"].find({}, {"_id": 0}).to_list(20)
    return {"agenti": stati}


@router.post("/run")
async def run_agenti_manuale(agente: Optional[str] = Query(None),
                             _admin: Dict[str, Any] = Depends(get_current_admin_user)):
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
async def get_pattern_appresi(categoria: str = Query(None),
                              _admin: Dict[str, Any] = Depends(get_current_admin_user)):
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
    includi_storico: bool = Query(False),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
):
    """Registro decisioni: una riga corrente per problema, storico opzionale."""
    from app.agents.decision_engine import decisioni_correnti

    db = Database.get_db()
    query: Dict[str, Any] = {}
    if stato:
        query["execution_status"] = stato
    if agente:
        query["agent"] = agente
    limite_lettura = limit if includi_storico else 500
    decisioni = await db["ai_decisions"].find(
        query, {"_id": 0}
    ).sort("timestamp", -1).limit(limite_lettura).to_list(limite_lettura)
    if not includi_storico:
        decisioni = decisioni_correnti(decisioni)[:limit]
    return {"decisioni": decisioni, "totale": len(decisioni)}


@router.get("/decisioni/{decision_id}/eventi")
async def get_eventi_decisione(decision_id: str, _admin: Dict[str, Any] = Depends(get_current_admin_user)):
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
    admin: Dict[str, Any] = Depends(get_current_admin_mfa_user),
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
    admin: Dict[str, Any] = Depends(get_current_admin_mfa_user),
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
async def get_stato_automazioni(_admin: Dict[str, Any] = Depends(get_current_admin_user)):
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


# ---------------------------------------------------------------------------
# Cruscotto per settore e proposte AI (decisione del titolare, 02/10/2026)
# ---------------------------------------------------------------------------
from app.middleware.performance import istantanea  # noqa: E402
from app.services import agenti_proposte  # noqa: E402


@istantanea(ttl=60, max_eta=900, persistente=True)
async def _settori_istantanea() -> Dict[str, Any]:
    from app.services.agenti_settori import stato_settori

    return await stato_settori(Database.get_db())


@router.get("/settori")
async def get_settori(_admin: Dict[str, Any] = Depends(get_current_admin_user)):
    """Per settore: ultimi giri, code ferme e proposte AI in attesa. Istantanea: pronta, si ricalcola in sottofondo."""
    return await _settori_istantanea()


@router.get("/proposte")
async def get_proposte(
    settore: Optional[str] = Query(None),
    stato: Optional[str] = Query(agenti_proposte.STATO_PROPOSTA),
    limit: int = Query(200, ge=1, le=1000),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
):
    """Le proposte dell'agente AI (``stato`` vuoto = tutte)."""
    righe = await agenti_proposte.elenco(Database.get_db(), settore=settore, stato_filtro=stato or None, limite=limit)
    return {"proposte": righe, "totale": len(righe), "motivi_rifiuto": list(agenti_proposte.MOTIVI_RIFIUTO)}


@router.post("/proposte/giro")
async def giro_proposte(_admin: Dict[str, Any] = Depends(get_current_admin_user)):
    """Un lotto subito (lo stesso giro dello scheduler): legge, propone, mai applica."""
    return await agenti_proposte.giro(Database.get_db())


@router.post("/proposte/conferma-sicure")
async def conferma_proposte_sicure(
    settore: Optional[str] = Query(None),
    admin: Dict[str, Any] = Depends(get_current_admin_user),
):
    """Conferma tutte le proposte a confidenza alta, ognuna col motore del suo tipo."""
    return await agenti_proposte.conferma_sicure(Database.get_db(), _identita_admin(admin), settore=settore)


@router.post("/proposte/{proposta_id}/conferma")
async def conferma_proposta(proposta_id: str, admin: Dict[str, Any] = Depends(get_current_admin_user)):
    """Applica la proposta col motore deterministico del tipo; una gia' decisa non si riapplica."""
    try:
        esito = await agenti_proposte.conferma(Database.get_db(), proposta_id, _identita_admin(admin))
    except agenti_proposte.PropostaNonTrovata:
        raise HTTPException(status_code=404, detail="Proposta non trovata")
    except agenti_proposte.PropostaNonApplicabile as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not esito.get("gia_decisa") and not (esito.get("esito") or {}).get("success"):
        raise HTTPException(status_code=409, detail={
            "code": "PROPOSTA_NON_APPLICATA",
            "message": str((esito.get("esito") or {}).get("message") or (esito.get("esito") or {}).get("motivo")
                           or "il motore del tipo proposto non ha registrato il documento"),
            "esito": esito.get("esito"),
        })
    return esito


@router.post("/proposte/{proposta_id}/rifiuta")
async def rifiuta_proposta(
    proposta_id: str,
    body: Optional[Dict[str, Any]] = Body(None),
    admin: Dict[str, Any] = Depends(get_current_admin_user),
):
    """Rifiuta con un motivo a chip (``motivo``), nota solo per «altro»."""
    dati = body or {}
    try:
        return await agenti_proposte.rifiuta(Database.get_db(), proposta_id, _identita_admin(admin),
                                             str(dati.get("motivo") or ""), str(dati.get("nota") or ""))
    except agenti_proposte.PropostaNonTrovata:
        raise HTTPException(status_code=404, detail="Proposta non trovata")
    except agenti_proposte.PropostaNonApplicabile as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
