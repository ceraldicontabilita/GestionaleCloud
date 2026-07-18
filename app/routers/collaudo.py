"""
COLLAUDO AUTOMATICO — endpoint (richiesta utente 18/07/2026).

POST /api/collaudo/esegui  → esegue tutti i check invarianti (sola lettura,
                             genera/risolve gli alert) e ritorna il report
GET  /api/collaudo/ultimo  → ultimo report salvato
GET  /api/collaudo/storico → elenco sintetico degli ultimi report
"""
from typing import Any, Dict

from fastapi import APIRouter, Depends, Query

from app.database import Database
from app.utils.dependencies import get_current_admin_user
from app.utils.error_handler import handle_errors

router = APIRouter()


@router.post("/esegui")
@handle_errors
async def esegui_collaudo_endpoint(
    alerts: bool = Query(True, description="Genera/risolvi gli alert"),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    from app.services.collaudo_invarianti import esegui_collaudo
    return await esegui_collaudo(Database.get_db(), genera_alerts=alerts)


@router.get("/ultimo")
@handle_errors
async def ultimo_report() -> Dict[str, Any]:
    db = Database.get_db()
    report = await db["collaudo_report"].find_one({}, {"_id": 0}, sort=[("eseguito_at", -1)])
    return report or {"message": "Nessun collaudo ancora eseguito"}


@router.get("/storico")
@handle_errors
async def storico_report(limit: int = Query(20, le=100)) -> Dict[str, Any]:
    db = Database.get_db()
    reports = await db["collaudo_report"].find(
        {}, {"_id": 0, "checks": 0}
    ).sort("eseguito_at", -1).limit(limit).to_list(limit)
    return {"reports": reports}
