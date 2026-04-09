"""
Router Ordini Fornitori (tracciabilità) — Catalogo prodotti suggeriti + CRUD ordini.
Adattato da tracciabilita/backend/routers/ordini_fornitori.py
Prefix: /api/tr/ordini-fornitori
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase
import uuid

from app.database import get_database

router = APIRouter(prefix="/ordini-fornitori", tags=["Tracciabilità - Ordini Fornitori"])

class ProdottoOrdine(BaseModel):
    prodotto_id: str; nome: str; fornitore: str = ""; quantita: float = 1.0
    unita: str = "kg"; prezzo_ultimo: float = 0.0; note: str = ""

class RicettaDaProdurre(BaseModel):
    ricetta_id: str; nome: str; reparto: str = ""; quantita: float = 1.0; note: str = ""

class OrdineCreate(BaseModel):
    reparto: str = ""; operatore: str = ""
    prodotti: List[ProdottoOrdine]
    ricette_da_produrre: List[RicettaDaProdurre] = []
    note_operatore: str = ""

@router.get("/prodotti-suggeriti")
async def prodotti_suggeriti(fornitore: Optional[str] = None, limit: int = Query(500),
                              db: AsyncIOMotorDatabase = Depends(get_database)):
    filtro = {"prezzo_kg": {"$gt": 0}}
    if fornitore: filtro["fornitore"] = fornitore
    prods = await db["dizionario_prodotti"].find(filtro, {"_id": 0}).sort(
        [("conteggio_acquisti", -1), ("ultima_fattura_data", -1)]).limit(limit).to_list(limit)
    result = []
    for p in prods:
        disp = float(p.get("quantita_disponibile_kg") or 0)
        sm = float(p.get("scorta_minima") or 0)
        ss = disp < 1.0 if sm == 0 else disp < sm
        result.append({"id": p.get("id"), "nome": p.get("nome_canonico") or p.get("nome_normalizzato","").title(),
                        "fornitore": p.get("fornitore",""), "categoria": p.get("categoria_canonica") or "Altro",
                        "prezzo_kg": float(p.get("prezzo_kg") or 0),
                        "unita_confezione": p.get("unita_confezione","kg"),
                        "quantita_disponibile_kg": disp, "sotto_scorta": ss,
                        "conteggio_acquisti": int(p.get("conteggio_acquisti") or 0)})
    result.sort(key=lambda x: (not x["sotto_scorta"], -x["conteggio_acquisti"]))
    return result

@router.post("")
async def crea_ordine(payload: OrdineCreate, db: AsyncIOMotorDatabase = Depends(get_database)):
    if not payload.prodotti: raise HTTPException(400, "Nessun prodotto")
    now = datetime.now(timezone.utc).isoformat()
    ordine = {"id": str(uuid.uuid4()), "data_ordine": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
              "stato": "inviato", "source": "tracciabilita", "reparto": payload.reparto,
              "operatore": payload.operatore, "prodotti": [p.model_dump() for p in payload.prodotti],
              "ricette_da_produrre": [r.model_dump() for r in payload.ricette_da_produrre],
              "note_operatore": payload.note_operatore, "created_at": now, "updated_at": now}
    await db["ordini_fornitori"].insert_one(ordine)
    ordine.pop("_id", None)
    return {"success": True, "ordine_id": ordine["id"], "ordine": ordine}

@router.get("")
async def lista_ordini(stato: Optional[str] = None, source: Optional[str] = None,
                        limit: int = Query(50), db: AsyncIOMotorDatabase = Depends(get_database)):
    f = {}
    if stato: f["stato"] = stato
    if source: f["source"] = source
    return await db["ordini_fornitori"].find(f, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)

@router.get("/{ordine_id}")
async def get_ordine(ordine_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    o = await db["ordini_fornitori"].find_one({"id": ordine_id}, {"_id": 0})
    if not o: raise HTTPException(404)
    return o
