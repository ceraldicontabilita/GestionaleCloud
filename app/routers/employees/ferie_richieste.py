"""Ferie Richieste router — Workflow di richiesta ferie/permessi con approvazione.

È distinto dal router `giustificativi.py` che gestisce i codici standard italiani
(FE/RL/MA) in fase di registrazione presenze. Qui gestiamo il FLUSSO di richiesta
da parte del dipendente:

  dipendente richiede → in_attesa → approvata | rifiutata

Espone:
  - /api/ferie-richieste                    GET / POST
  - /api/ferie-richieste/{id}               GET / PUT / DELETE
  - /api/ferie-richieste/{id}/approva       POST
  - /api/ferie-richieste/{id}/rifiuta       POST

Schema Mongo — collezione "ferie_richieste":
  { id, dipendente_id, tipo, data_inizio, data_fine, giorni, motivazione,
    stato, note_approvazione, approvata_da, approvata_at, created_at }

Tipi: Ferie | Permesso | Malattia | ROL | L.104 | Congedo | Altro
"""
from fastapi import APIRouter, Body, Depends, HTTPException, status
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, date
from uuid import uuid4
import logging

from app.database import Database
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

TIPI_VALIDI = {"Ferie", "Permesso", "Malattia", "ROL", "L.104", "Congedo", "Altro"}
STATI_VALIDI = {"in_attesa", "approvata", "rifiutata"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in doc.items() if k != "_id"}


def _calcola_giorni(data_inizio: str, data_fine: str) -> int:
    """Calcola giorni inclusivi tra due date ISO."""
    try:
        di = date.fromisoformat(data_inizio.split("T")[0])
        df = date.fromisoformat(data_fine.split("T")[0])
        if df < di:
            return 0
        return (df - di).days + 1
    except Exception:
        return 0


# =========================================================================
# CRUD
# =========================================================================

@router.get("", summary="Elenco richieste ferie/permessi")
async def list_richieste(
    dipendente_id: Optional[str] = None,
    stato: Optional[str] = None,
    tipo: Optional[str] = None,
    anno: Optional[int] = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    db = Database.get_db()
    q: Dict[str, Any] = {}
    if dipendente_id:
        q["dipendente_id"] = dipendente_id
    if stato:
        q["stato"] = stato
    if tipo:
        q["tipo"] = tipo
    if anno:
        q["data_inizio"] = {"$regex": f"^{anno}"}
    items = (
        await db["ferie_richieste"]
        .find(q, {"_id": 0})
        .sort("created_at", -1)
        .to_list(1000)
    )
    return items


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Crea nuova richiesta ferie/permesso",
)
async def create_richiesta(
    data: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    required = ["dipendente_id", "tipo", "data_inizio", "data_fine"]
    missing = [k for k in required if not data.get(k)]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Campi obbligatori mancanti: {', '.join(missing)}",
        )
    if data["tipo"] not in TIPI_VALIDI:
        raise HTTPException(
            status_code=400, detail=f"Tipo non valido: {data['tipo']}"
        )

    giorni = _calcola_giorni(data["data_inizio"], data["data_fine"])
    if giorni <= 0:
        raise HTTPException(
            status_code=400, detail="data_fine deve essere >= data_inizio"
        )

    doc = {
        "id": str(uuid4()),
        "dipendente_id": data["dipendente_id"],
        "tipo": data["tipo"],
        "data_inizio": data["data_inizio"],
        "data_fine": data["data_fine"],
        "giorni": giorni,
        "motivazione": (data.get("motivazione") or "").strip() or None,
        "stato": "in_attesa",
        "note_approvazione": None,
        "approvata_da": None,
        "approvata_at": None,
        "created_at": _now(),
    }

    db = Database.get_db()
    await db["ferie_richieste"].insert_one(doc.copy())
    logger.info(
        "Richiesta %s creata: %s giorni per dip %s",
        doc["tipo"],
        giorni,
        doc["dipendente_id"],
    )
    return _clean(doc)


@router.get("/{richiesta_id}", summary="Dettaglio richiesta")
async def get_richiesta(
    richiesta_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    db = Database.get_db()
    item = await db["ferie_richieste"].find_one({"id": richiesta_id}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Richiesta non trovata")
    return item


@router.put("/{richiesta_id}", summary="Modifica richiesta (solo se in attesa)")
async def update_richiesta(
    richiesta_id: str,
    data: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, str]:
    db = Database.get_db()
    existing = await db["ferie_richieste"].find_one({"id": richiesta_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Richiesta non trovata")
    if existing.get("stato") != "in_attesa":
        raise HTTPException(
            status_code=400,
            detail="Solo le richieste in attesa possono essere modificate",
        )

    update: Dict[str, Any] = {}
    for key in ("tipo", "data_inizio", "data_fine", "motivazione"):
        if key in data:
            update[key] = data[key]
    if update.get("tipo") and update["tipo"] not in TIPI_VALIDI:
        raise HTTPException(status_code=400, detail="Tipo non valido")
    if "data_inizio" in update or "data_fine" in update:
        di = update.get("data_inizio", existing["data_inizio"])
        df = update.get("data_fine", existing["data_fine"])
        update["giorni"] = _calcola_giorni(di, df)
        if update["giorni"] <= 0:
            raise HTTPException(
                status_code=400, detail="data_fine deve essere >= data_inizio"
            )

    if not update:
        raise HTTPException(status_code=400, detail="Nessun campo da aggiornare")

    await db["ferie_richieste"].update_one({"id": richiesta_id}, {"$set": update})
    return {"message": "Richiesta aggiornata"}


@router.delete("/{richiesta_id}", summary="Elimina richiesta")
async def delete_richiesta(
    richiesta_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, str]:
    db = Database.get_db()
    res = await db["ferie_richieste"].delete_one({"id": richiesta_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Richiesta non trovata")
    return {"message": "Richiesta eliminata"}


# =========================================================================
# WORKFLOW
# =========================================================================

@router.post("/{richiesta_id}/approva", summary="Approva richiesta")
async def approva(
    richiesta_id: str,
    data: Dict[str, Any] = Body(default={}),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, str]:
    db = Database.get_db()
    res = await db["ferie_richieste"].update_one(
        {"id": richiesta_id, "stato": "in_attesa"},
        {
            "$set": {
                "stato": "approvata",
                "note_approvazione": data.get("note", ""),
                "approvata_da": current_user.get("email") or current_user.get("id"),
                "approvata_at": _now(),
            }
        },
    )
    if res.matched_count == 0:
        raise HTTPException(
            status_code=404,
            detail="Richiesta non trovata o non in attesa",
        )
    return {"message": "Richiesta approvata"}


@router.post("/{richiesta_id}/rifiuta", summary="Rifiuta richiesta")
async def rifiuta(
    richiesta_id: str,
    data: Dict[str, Any] = Body(default={}),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, str]:
    db = Database.get_db()
    res = await db["ferie_richieste"].update_one(
        {"id": richiesta_id, "stato": "in_attesa"},
        {
            "$set": {
                "stato": "rifiutata",
                "note_approvazione": data.get("note", ""),
                "approvata_da": current_user.get("email") or current_user.get("id"),
                "approvata_at": _now(),
            }
        },
    )
    if res.matched_count == 0:
        raise HTTPException(
            status_code=404,
            detail="Richiesta non trovata o non in attesa",
        )
    return {"message": "Richiesta rifiutata"}
