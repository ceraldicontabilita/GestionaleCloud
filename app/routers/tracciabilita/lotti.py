"""
Router per la gestione dei Lotti.
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict
from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/lotti", tags=["Lotti"])

from app.routers.tracciabilita.server import db

# ==================== MODELLI ====================

class LottoCreate(BaseModel):
    prodotto: str
    ingredienti_dettaglio: List[str] = []
    data_produzione: str
    data_scadenza: str
    numero_lotto: str
    etichetta: str = ""
    quantita: float = Field(default=1, gt=0, description="Quantità deve essere > 0")
    unita_misura: str = "pz"

class Lotto(LottoCreate):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    scadenza_abbattuto: str = ""
    mesi_abbattuto: int = 0
    ingrediente_critico: str = ""
    conservazione_note: str = ""
    allergeni: List[str] = []
    allergeni_dettaglio: Dict = {}
    allergeni_testo: str = ""
    progressivo: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# ==================== ENDPOINTS ====================

@router.get("")
async def get_lotti(search: Optional[str] = Query(None)):
    """Lista lotti con ricerca opzionale — normalizza entrambi gli schemi"""
    query = {}
    if search:
        query["$or"] = [
            {"prodotto": {"$regex": search, "$options": "i"}},
            {"prodotto_nome": {"$regex": search, "$options": "i"}},
            {"numero_lotto": {"$regex": search, "$options": "i"}},
            {"lotto_id": {"$regex": search, "$options": "i"}},
        ]
    items = await db.lotti.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    # Normalizza schema: garantisce che i campi attesi dal frontend siano sempre presenti
    normalized = []
    for it in items:
        n = dict(it)
        # Mappa campi nuovo schema → vecchio schema atteso dal frontend
        if not n.get("prodotto") and n.get("prodotto_nome"):
            n["prodotto"] = n["prodotto_nome"]
        if not n.get("numero_lotto") and n.get("lotto_id"):
            n["numero_lotto"] = n["lotto_id"]
        if not n.get("id") and n.get("lotto_id"):
            n["id"] = n["lotto_id"]
        # Campi richiesti dal frontend — default se assenti nel DB
        if "stato" not in n or n["stato"] is None:
            n["stato"] = "attivo"
        if "consumato" not in n or n["consumato"] is None:
            n["consumato"] = False
        if "data_consumo" not in n:
            n["data_consumo"] = None
        normalized.append(n)
    return normalized

@router.get("/{lotto_id}")
async def get_lotto(lotto_id: str):
    """Ottiene un lotto per ID"""
    item = await db.lotti.find_one({"id": lotto_id}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Lotto non trovato")
    item = dict(item)
    if "stato" not in item or item["stato"] is None:
        item["stato"] = "attivo"
    if "consumato" not in item or item["consumato"] is None:
        item["consumato"] = False
    if "data_consumo" not in item:
        item["data_consumo"] = None
    return item

@router.post("", response_model=Lotto)
async def create_lotto(item: LottoCreate):
    """Crea un nuovo lotto"""
    data = item.model_dump()
    data["id"] = str(uuid.uuid4())
    data["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.lotti.insert_one(data)
    return data

@router.delete("/{lotto_id}")
async def delete_lotto(lotto_id: str):
    """Elimina un lotto (cerca per id o lotto_id per compatibilità schema vecchio)"""
    result = await db.lotti.delete_one({"$or": [{"id": lotto_id}, {"lotto_id": lotto_id}]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Lotto non trovato")
    return {"success": True}
