"""Shifts router - Gestione tipi turno + pianificazione settimanale.

Espone:
  - /api/shifts/tipi                GET/POST              lista e creazione tipi turno
  - /api/shifts/tipi/{turno_id}     PUT/DELETE            modifica ed eliminazione tipo turno
  - /api/shifts/assegnazioni        GET                   lista assegnazioni dipendente-giorno
  - /api/shifts/assegnazioni        POST                  upsert assegnazione (turno_id None -> rimozione)
  - /api/shifts/assegnazioni/{ass_id} DELETE              elimina singola assegnazione

Schema dati (Mongo):
  shifts_tipi:       { id, nome, orario_inizio, orario_fine, colore, created_at }
  shifts_assegnazioni: { id, dipendente_id, giorno, turno_id, created_at }
                      giorno in {"Lun","Mar","Mer","Gio","Ven","Sab","Dom"}

Compatibilità: manteniamo anche i vecchi endpoint /schedule (GET/POST) che scrivevano
su collezione "shifts" e che non venivano usati dal frontend.
"""
from fastapi import APIRouter, Body, Depends, HTTPException, status
from typing import Dict, Any, List
from datetime import datetime, timezone
from uuid import uuid4
import logging

from app.hr.database import Database
from app.hr.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


# Giorni validi per assegnazione settimanale
GIORNI_VALIDI = {"Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# =========================================================================
# TIPI TURNO
# =========================================================================

@router.get("/tipi", summary="Elenco tipi turno")
async def list_tipi_turno(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """Restituisce tutti i tipi turno definiti (mattina, pomeriggio, ecc.)."""
    db = Database.get_db()
    items = await db["shifts_tipi"].find({}, {"_id": 0}).sort("nome", 1).to_list(200)
    return items


@router.post(
    "/tipi",
    status_code=status.HTTP_201_CREATED,
    summary="Crea un nuovo tipo turno",
)
async def create_tipo_turno(
    data: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    nome = (data.get("nome") or "").strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Il nome del turno è obbligatorio")

    db = Database.get_db()
    doc = {
        "id": str(uuid4()),
        "nome": nome,
        "orario_inizio": data.get("orario_inizio") or "08:00",
        "orario_fine": data.get("orario_fine") or "16:00",
        "colore": data.get("colore") or "#0f2744",
        "created_at": _now(),
    }
    await db["shifts_tipi"].insert_one(doc.copy())
    logger.info("Turno creato: %s", doc["nome"])
    return {k: v for k, v in doc.items() if k != "_id"}


@router.put("/tipi/{turno_id}", summary="Aggiorna un tipo turno")
async def update_tipo_turno(
    turno_id: str,
    data: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, str]:
    db = Database.get_db()
    update = {
        k: v
        for k, v in {
            "nome": (data.get("nome") or "").strip() or None,
            "orario_inizio": data.get("orario_inizio"),
            "orario_fine": data.get("orario_fine"),
            "colore": data.get("colore"),
        }.items()
        if v is not None
    }
    if not update:
        raise HTTPException(status_code=400, detail="Nessun campo da aggiornare")
    res = await db["shifts_tipi"].update_one({"id": turno_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Turno non trovato")
    return {"message": "Turno aggiornato"}


@router.delete("/tipi/{turno_id}", summary="Elimina un tipo turno")
async def delete_tipo_turno(
    turno_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, str]:
    db = Database.get_db()
    res = await db["shifts_tipi"].delete_one({"id": turno_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Turno non trovato")
    # Rimuovi cascata le assegnazioni
    await db["shifts_assegnazioni"].delete_many({"turno_id": turno_id})
    return {"message": "Turno eliminato"}


# =========================================================================
# ASSEGNAZIONI SETTIMANALI
# =========================================================================

@router.get("/assegnazioni", summary="Elenco assegnazioni settimanali")
async def list_assegnazioni(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    db = Database.get_db()
    items = await db["shifts_assegnazioni"].find({}, {"_id": 0}).to_list(5000)
    return items


@router.post("/assegnazioni", summary="Upsert assegnazione dipendente-giorno")
async def upsert_assegnazione(
    data: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, str]:
    """Assegna (o rimuove, se turno_id=None) un turno a un dipendente per un giorno."""
    dipendente_id = data.get("dipendente_id")
    giorno = data.get("giorno")
    turno_id = data.get("turno_id") or None

    if not dipendente_id or not giorno:
        raise HTTPException(
            status_code=400,
            detail="dipendente_id e giorno sono obbligatori",
        )
    if giorno not in GIORNI_VALIDI:
        raise HTTPException(
            status_code=400,
            detail=f"giorno non valido, attesi: {sorted(GIORNI_VALIDI)}",
        )

    db = Database.get_db()
    existing = await db["shifts_assegnazioni"].find_one(
        {"dipendente_id": dipendente_id, "giorno": giorno}
    )

    if turno_id:
        if existing:
            await db["shifts_assegnazioni"].update_one(
                {"id": existing["id"]}, {"$set": {"turno_id": turno_id}}
            )
        else:
            await db["shifts_assegnazioni"].insert_one(
                {
                    "id": str(uuid4()),
                    "dipendente_id": dipendente_id,
                    "giorno": giorno,
                    "turno_id": turno_id,
                    "created_at": _now(),
                }
            )
        return {"message": "Assegnazione salvata"}

    # rimozione
    if existing:
        await db["shifts_assegnazioni"].delete_one({"id": existing["id"]})
    return {"message": "Assegnazione rimossa"}


@router.delete(
    "/assegnazioni/{assegnazione_id}", summary="Elimina una singola assegnazione"
)
async def delete_assegnazione(
    assegnazione_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, str]:
    db = Database.get_db()
    res = await db["shifts_assegnazioni"].delete_one({"id": assegnazione_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Assegnazione non trovata")
    return {"message": "Assegnazione eliminata"}


# =========================================================================
# LEGACY (mantenuti per compatibilità — non usati dal frontend attuale)
# =========================================================================

@router.get("/schedule", summary="[legacy] Get shift schedule")
async def get_schedule(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    db = Database.get_db()
    shifts = await db["shifts"].find({}, {"_id": 0}).sort("date", -1).to_list(500)
    return shifts


@router.post(
    "/schedule",
    status_code=status.HTTP_201_CREATED,
    summary="[legacy] Create shift schedule",
)
async def create_schedule(
    data: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, str]:
    db = Database.get_db()
    data["id"] = str(uuid4())
    data["created_at"] = datetime.now(timezone.utc)
    await db["shifts"].insert_one(data.copy())
    return {"message": "Schedule created", "id": data["id"]}
