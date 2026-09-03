"""
Gestione accessi dipendenti (solo admin): PIN personale e ruolo applicativo.
"""
import logging
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, Body, Depends

from app.hr.database import Database, Collections
from app.hr.utils.identity import require_roles
from app.hr.services import auth_dipendenti as auth_dip

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", summary="Elenco accessi dipendenti (admin)")
async def lista_accessi(_: Dict[str, Any] = Depends(require_roles("admin"))) -> List[Dict[str, Any]]:
    db = Database.get_db()
    docs = await db[Collections.EMPLOYEES].find(
        {"merged_into": {"$exists": False}},
        {"_id": 0, "id": 1, "nome_completo": 1, "nome": 1, "cognome": 1,
         "mansione": 1, "ruolo": 1, "ruolo_app": 1, "pin_hash": 1, "attivo": 1},
    ).to_list(500)
    out = []
    for d in docs:
        if not d.get("id"):
            continue
        nome = (d.get("nome_completo") or f"{d.get('nome','')} {d.get('cognome','')}").strip()
        if not nome:
            continue
        out.append({
            "id": d.get("id"),
            "nome_completo": nome,
            "mansione": d.get("mansione", "") or d.get("ruolo", ""),
            "ruolo_app": d.get("ruolo_app", "dipendente"),
            "pin_impostato": bool(d.get("pin_hash")),
            "attivo": d.get("attivo", True),
        })
    out.sort(key=lambda x: x["nome_completo"].lower())
    return out


@router.post("/{dipendente_id}/pin", summary="Imposta/azzera PIN dipendente (admin)")
async def set_pin(
    dipendente_id: str,
    payload: Dict[str, Any] = Body(..., example={"pin": "1234"}),
    _: Dict[str, Any] = Depends(require_roles("admin")),
):
    pin = str(payload.get("pin", "")).strip()
    try:
        ok = await auth_dip.imposta_pin(dipendente_id, pin)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not ok:
        raise HTTPException(404, "Dipendente non trovato")
    return {"ok": True, "dipendente_id": dipendente_id, "pin_impostato": True}


@router.delete("/{dipendente_id}/pin", summary="Rimuove PIN dipendente (admin)")
async def del_pin(dipendente_id: str, _: Dict[str, Any] = Depends(require_roles("admin"))):
    ok = await auth_dip.rimuovi_pin(dipendente_id)
    if not ok:
        raise HTTPException(404, "Dipendente non trovato")
    return {"ok": True, "dipendente_id": dipendente_id, "pin_impostato": False}


@router.post("/{dipendente_id}/ruolo", summary="Imposta ruolo applicativo (admin)")
async def set_ruolo(
    dipendente_id: str,
    payload: Dict[str, Any] = Body(..., example={"ruolo_app": "responsabile_turni"}),
    _: Dict[str, Any] = Depends(require_roles("admin")),
):
    ruolo = str(payload.get("ruolo_app", "")).strip()
    try:
        ok = await auth_dip.imposta_ruolo(dipendente_id, ruolo)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not ok:
        raise HTTPException(404, "Dipendente non trovato")
    return {"ok": True, "dipendente_id": dipendente_id, "ruolo_app": ruolo}
