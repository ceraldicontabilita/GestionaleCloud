"""Notifiche in-app del dipendente."""
import logging
from datetime import datetime, timezone
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Query, Depends

from app.hr.database import Database
from app.hr.utils.identity import get_identity

logger = logging.getLogger(__name__)
router = APIRouter()
COLL = "notifiche"
# Tipi "broadcast" inviati a OGNI dipendente (turni/buste/conferme): per l'admin
# sono rumore (vedrebbe 1 copia per dipendente). L'admin vede solo gli avvisi che
# richiedono la sua attenzione (richieste in entrata, contestazioni, alert).
ADMIN_NASCONDI = ["turni", "turno_pubblicato", "busta_paga", "richiesta_risolta"]


def _query_per(identity: Dict[str, Any]) -> Dict[str, Any]:
    if identity.get("role") == "admin":
        return {"tipo": {"$nin": ADMIN_NASCONDI}}
    return {"dipendente_id": identity["id"]}


@router.get("", summary="Le mie notifiche (admin: solo quelle di sua competenza)")
async def le_mie(solo_non_lette: bool = Query(False),
                 identity: Dict[str, Any] = Depends(get_identity)):
    db = Database.get_db()
    q = _query_per(identity)
    if solo_non_lette:
        q["letta"] = False
    return await db[COLL].find(q, {"_id": 0}).sort("creato_il", -1).to_list(500)


@router.get("/conteggio", summary="Conteggio non lette")
async def conteggio(identity: Dict[str, Any] = Depends(get_identity)):
    db = Database.get_db()
    q = _query_per(identity)
    q["letta"] = False
    n = await db[COLL].count_documents(q)
    return {"non_lette": n}


@router.post("/{notifica_id}/letta", summary="Segna come letta")
async def segna_letta(notifica_id: str, identity: Dict[str, Any] = Depends(get_identity)):
    db = Database.get_db()
    q = {"id": notifica_id} if identity.get("role") == "admin" else {"id": notifica_id, "dipendente_id": identity["id"]}
    r = await db[COLL].update_one(
        q,
        {"$set": {"letta": True, "letta_il": datetime.now(timezone.utc).isoformat()}},
    )
    if r.matched_count == 0:
        raise HTTPException(404, "Notifica non trovata")
    return {"ok": True}
