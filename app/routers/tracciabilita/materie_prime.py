"""
Router Materie Prime — estratto da server.py
GET  /api/materie-prime              — lista con filtri
GET  /api/materie-prime/storico      — storico completo
POST /api/materie-prime              — crea manualmente
PUT  /api/materie-prime/{id}/allergeni — aggiorna allergeni
POST /api/materie-prime/auto-rileva-allergeni — auto EU14
DELETE /api/materie-prime/{id}       — elimina
"""
from fastapi import APIRouter, HTTPException, Query
from app.routers.tracciabilita.server import db
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from datetime import datetime, timezone, timedelta
from pathlib import Path
import os, re, uuid


router = APIRouter(prefix="/materie-prime", tags=["Materie Prime"])

class MateriaPrima(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    azienda: str
    data_fattura: str
    numero_fattura: str
    materia_prima: str
    allergeni: str = "non contiene allergeni"
    descrizione_completa: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class MateriaPrimaCreate(BaseModel):
    azienda: str
    data_fattura: str
    numero_fattura: str
    materia_prima: str
    allergeni: str = "non contiene allergeni"

_ALLERGENI_KW = {
    "Latte e derivati": ["latte","lattosio","caseina","panna","burro","formaggio","mozzarella","ricotta","yogurt","siero di latte","whey"],
    "Cereali/glutine": ["farina","semola","grano","frumento","orzo","segale","avena","farro","kamut","glutine","pasta ","pizza","brioche","croissant","pangrattato","biscotto","torta"],
    "Uova": ["uova","tuorlo","albume","ovoprodotti","maionese"],
    "Soia": ["soia","soy","lecitina di soia"],
    "Frutta a guscio": ["noci ","nocciola","nocciole","mandorle","pistacchio","pinoli","anacardi","pecan","macadamia"],
    "Arachidi": ["arachidi","arachide"],
    "Sedano": ["sedano"],
    "Senape": ["senape","mostarda"],
    "Sesamo": ["sesamo","tahini"],
    "Pesce": ["acciughe","alici","tonno","salmone","baccalà"],
    "Crostacei": ["gamberi","aragoste","granchi","scampi"],
    "Molluschi": ["cozze","vongole","polpo","calamari","seppie"],
    "Lupino": ["lupino","lupini"],
    "Solfiti": ["solfiti","anidride solforosa"],
}

def _rileva(nome: str) -> str:
    nl = (nome or "").lower()
    trovati = []
    for allergene, kws in _ALLERGENI_KW.items():
        if any(kw in nl for kw in kws):
            trovati.append(allergene)
    return ("Contiene: " + ", ".join(trovati)) if trovati else "non contiene allergeni"


@router.get("/da-fatture")
async def get_materie_prime_da_fatture(mesi: int = 12):
    """
    Raggruppa i prodotti delle fatture per fornitore negli ultimi N mesi.
    Esclude i fornitori segnati come 'esclusi'.
    Usato da MateriePrimeList per mostrare i gruppi.
    """
    # Fornitori esclusi
    esclusi_docs = await db.fornitori.find({"escluso": True}, {"nome": 1, "_id": 0}).to_list(500)
    esclusi = {f["nome"].strip().lower() for f in esclusi_docs}
    
    # Calcola data limite
    data_limite = (datetime.now() - timedelta(days=mesi * 30)).strftime("%Y-%m-%d")
    
    # Carica lotti fornitori recenti (da fatture importate via PEC)
    items = await db.lotti_fornitori.find(
        {"data_fattura": {"$gte": data_limite}},
        {"_id": 0}
    ).sort([("fornitore", 1), ("data_fattura", -1)]).to_list(5000)
    
    # Raggruppa per fornitore
    gruppi = {}
    for item in items:
        az = (item.get("fornitore") or "Sconosciuto").strip()
        if az.lower() in esclusi:
            continue
        if az not in gruppi:
            gruppi[az] = {"fornitore": az, "totale_prodotti": 0, "prodotti": []}
        gruppi[az]["totale_prodotti"] += 1
        gruppi[az]["prodotti"].append({
            "descrizione": item.get("prodotto_nome", ""),
            "data_fattura": item.get("data_fattura", ""),
            "numero_fattura": item.get("fattura_ref", ""),
            "allergeni": "",
            "quantita": item.get("quantita_disponibile", ""),
            "unita": item.get("unita_misura", ""),
        })
    
    return sorted(gruppi.values(), key=lambda g: g["fornitore"])


@router.get("/storico")
async def get_storico(search: Optional[str] = None, escludi_fornitori: bool = False):
    q = {}
    if search:
        q["materia_prima"] = {"$regex": search, "$options": "i"}
    if escludi_fornitori:
        docs = await db.fornitori.find({"escluso": True}, {"nome": 1}).to_list(500)
        esclusi = [f["nome"] for f in docs]
        if esclusi:
            q["azienda"] = {"$nin": esclusi}
    return await db.materie_prime.find(q, {"_id": 0}).sort([("data_fattura", -1), ("azienda", 1)]).to_list(5000)


@router.get("/")
async def get_materie_prime(
    search: Optional[str] = Query(None),
    solo_ultimo_mese: bool = Query(True),
    escludi_fornitori: bool = Query(True)
):
    q = {}
    if search:
        q["materia_prima"] = {"$regex": search, "$options": "i"}
    if escludi_fornitori:
        docs = await db.fornitori.find({"escluso": True}, {"nome": 1}).to_list(500)
        esclusi = [f["nome"] for f in docs]
        if esclusi:
            q["azienda"] = {"$nin": esclusi}
    items = await db.materie_prime.find(q, {"_id": 0}).sort([("azienda", 1), ("data_fattura", -1)]).to_list(2000)
    if solo_ultimo_mese:
        limite = datetime.now() - timedelta(days=30)
        def _ok(item):
            try:
                d = item.get("data_fattura", "")
                fmt = "%d/%m/%Y" if "/" in d else "%Y-%m-%d"
                return datetime.strptime(d, fmt) >= limite
            except (ValueError, TypeError):
                return True
        items = [i for i in items if _ok(i)]
    return items


@router.post("/")
async def create_materia_prima(item: MateriaPrimaCreate):
    obj = MateriaPrima(**item.model_dump())
    if obj.allergeni == "non contiene allergeni" or not obj.allergeni:
        custom = await db.allergeni_custom.find_one(
            {"materia_prima": {"$regex": f"^{re.escape(obj.materia_prima)}$", "$options": "i"}}, {"_id": 0}
        )
        obj.allergeni = custom.get("allergeni", _rileva(obj.materia_prima)) if custom else _rileva(obj.materia_prima)
    obj.descrizione_completa = f"{obj.materia_prima}  {obj.allergeni} - {obj.azienda} n° fatt {obj.numero_fattura} - {obj.data_fattura}"
    doc = obj.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.materie_prime.insert_one(doc)
    return obj


@router.put("/{item_id}/allergeni")
async def update_allergeni(item_id: str, allergeni: str = Query(...)):
    materia = await db.materie_prime.find_one({"id": item_id}, {"_id": 0})
    if not materia:
        raise HTTPException(404, "Materia prima non trovata")
    new_desc = f"{materia['materia_prima']}  {allergeni} - {materia['azienda']} n° fatt {materia['numero_fattura']} - {materia['data_fattura']}"
    await db.materie_prime.update_one({"id": item_id}, {"$set": {"allergeni": allergeni, "descrizione_completa": new_desc}})
    await db.allergeni_custom.update_one(
        {"materia_prima": {"$regex": f"^{re.escape(materia['materia_prima'])}$", "$options": "i"}},
        {"$set": {"materia_prima": materia['materia_prima'], "allergeni": allergeni, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True
    )
    await db.materie_prime.update_many(
        {"materia_prima": {"$regex": f"^{re.escape(materia['materia_prima'])}$", "$options": "i"}},
        {"$set": {"allergeni": allergeni}}
    )
    return {"message": "Allergeni aggiornati", "materia_prima": materia['materia_prima'], "allergeni": allergeni}


@router.post("/auto-rileva-allergeni")
async def auto_rileva_allergeni(solo_2026: bool = True):
    tutti = await db.materie_prime.find({}, {"_id": 0, "id": 1, "materia_prima": 1, "data_fattura": 1}).to_list(10000)
    def is_2026_plus(d):
        try:
            fmt = "%d/%m/%Y" if '/' in str(d) else "%Y-%m-%d"
            return datetime.strptime(str(d), fmt).year >= 2026
        except (ValueError, TypeError):
            return False
    materie = [m for m in tutti if (not solo_2026 or is_2026_plus(m.get("data_fattura", "")))]
    aggiornati = 0
    dettagli = []
    for m in materie:
        allerg_str = _rileva(m.get("materia_prima", ""))
        trovati_lista = [a for a in _ALLERGENI_KW if any(kw in (m.get("materia_prima","") or "").lower() for kw in _ALLERGENI_KW[a])]
        await db.materie_prime.update_one(
            {"id": m["id"]},
            {"$set": {"allergeni": allerg_str, "allergeni_lista": trovati_lista, "allergeni_aggiornati_auto": True}}
        )
        aggiornati += 1
        if trovati_lista:
            dettagli.append({"nome": m["materia_prima"], "allergeni": trovati_lista})
    return {"success": True, "aggiornati": aggiornati, "con_allergeni": len(dettagli), "dettaglio": dettagli[:50]}


@router.delete("/{item_id}")
async def delete_materia_prima(item_id: str):
    r = await db.materie_prime.delete_one({"id": item_id})
    if r.deleted_count == 0:
        raise HTTPException(404, "Materia prima non trovata")
    return {"message": "Eliminata con successo"}
