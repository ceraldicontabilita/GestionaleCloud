"""HR Documenti router — Gestione documenti personali dipendenti.

Espone:
  - /api/hr-documenti                  GET (lista) / POST (crea)
  - /api/hr-documenti/{id}             GET / PUT / DELETE
  - /api/hr-documenti/in-scadenza      GET documenti in scadenza (days param)

Schema Mongo — collezione "hr_documenti":
  { id, dipendente_id, titolo, tipo, scadenza, file_url, note, data_caricamento }

Tipi supportati (a titolo indicativo — campo free):
  "Codice Fiscale", "Carta Identità", "Patente", "Permesso Soggiorno",
  "Unilav", "Contratto", "CUD", "Certificato Medico", "Altro"
"""
from fastapi import APIRouter, Body, Depends, HTTPException, status
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import logging

from app.database import Database
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in doc.items() if k != "_id"}


# =========================================================================
# Lista / Filtri
# =========================================================================

@router.get("", summary="Elenco documenti HR")
async def list_documenti(
    dipendente_id: Optional[str] = None,
    tipo: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    db = Database.get_db()
    q: Dict[str, Any] = {}
    if dipendente_id:
        q["dipendente_id"] = dipendente_id
    if tipo:
        q["tipo"] = tipo
    items = await db["hr_documenti"].find(q, {"_id": 0}).sort("data_caricamento", -1).to_list(2000)
    return items


@router.get("/in-scadenza", summary="Documenti in scadenza nei prossimi N giorni")
async def in_scadenza(
    days: int = 30,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    db = Database.get_db()
    today = datetime.now(timezone.utc).date()
    limit = (today + timedelta(days=days)).isoformat()
    items = await db["hr_documenti"].find(
        {
            "scadenza": {"$ne": None, "$lte": limit, "$gte": today.isoformat()},
        },
        {"_id": 0},
    ).sort("scadenza", 1).to_list(500)
    return items


# =========================================================================
# CRUD
# =========================================================================

@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Crea documento HR",
)
async def create_documento(
    data: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    required = ["dipendente_id", "titolo", "tipo"]
    missing = [k for k in required if not data.get(k)]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Campi obbligatori mancanti: {', '.join(missing)}",
        )

    doc = {
        "id": str(uuid4()),
        "dipendente_id": data["dipendente_id"],
        "titolo": data["titolo"].strip(),
        "tipo": data["tipo"].strip(),
        "scadenza": data.get("scadenza") or None,
        "file_url": data.get("file_url") or None,
        "note": (data.get("note") or "").strip() or None,
        "data_caricamento": _now(),
    }

    db = Database.get_db()
    await db["hr_documenti"].insert_one(doc.copy())
    logger.info("Documento HR creato: %s (%s)", doc["id"], doc["tipo"])
    return _clean(doc)


@router.get("/{doc_id}", summary="Dettaglio documento")
async def get_documento(
    doc_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    db = Database.get_db()
    item = await db["hr_documenti"].find_one({"id": doc_id}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    return item


@router.put("/{doc_id}", summary="Aggiorna documento")
async def update_documento(
    doc_id: str,
    data: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, str]:
    db = Database.get_db()
    update: Dict[str, Any] = {}
    for key in ("titolo", "tipo", "scadenza", "file_url", "note"):
        if key in data:
            update[key] = data[key] if data[key] != "" else None
    if not update:
        raise HTTPException(status_code=400, detail="Nessun campo da aggiornare")

    res = await db["hr_documenti"].update_one({"id": doc_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    return {"message": "Documento aggiornato"}


@router.delete("/{doc_id}", summary="Elimina documento")
async def delete_documento(
    doc_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, str]:
    db = Database.get_db()
    res = await db["hr_documenti"].delete_one({"id": doc_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    return {"message": "Documento eliminato"}
