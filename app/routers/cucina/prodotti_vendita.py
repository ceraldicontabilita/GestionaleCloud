"""
Router Cucina — Prodotti Vendita
Adattato da /tmp/ceraldi_zip/unificazione_v2/backend/prodotti_vendita.py
prefix: /cucina/prodotti-vendita
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone
import uuid

from app.database import Database

router = APIRouter(prefix="/prodotti-vendita", tags=["Cucina Prodotti Vendita"])


class ProdottoVendita(BaseModel):
    nome: str
    categoria: str = ""
    descrizione: str = ""
    ricetta_id: Optional[str] = None
    fonte: str = "interno"
    fornitore: str = ""
    pezzi_cartone: Optional[int] = None
    pezzi_per_ricetta: Optional[int] = None
    pezzi_singolo: Optional[int] = None
    peso_pezzo_g: Optional[float] = None
    codice_prodotto: str = ""
    prezzo_vendita: float = 0
    costo_produzione: float = 0
    costo_produzione_cartone: float = 0
    margine_percentuale: float = 0
    margine_euro: float = 0
    iva: float = 10
    iva_compresa_aliquota: float = 10
    prezzo_ivato: float = 0
    prezzo_netto: float = 0
    attivo: bool = True
    visibile_tablet: bool = True
    visibile_ricette: bool = True
    stagionale: bool = False
    stagione_note: str = ""
    allergeni: List[str] = []
    ingredienti: str = ""
    istruzioni_cottura: str = ""
    acquaviva_id: str = ""
    vegano: bool = False
    immagine_url: Optional[str] = None


@router.get("/lista")
async def get_prodotti_vendita(solo_attivi: bool = False, categoria: Optional[str] = None, limit: int = 100):
    db = Database.get_db()
    query = {}
    if categoria:
        query["categoria"] = categoria
    cursor = db["prodotti_vendita"].find(query, {"_id": 0, "nome": 1, "categoria": 1, "prezzo_vendita": 1, "costo_produzione": 1, "iva": 1, "attivo": 1, "unita_misura": 1}).limit(limit)
    prodotti = await cursor.to_list(limit)
    for p in prodotti:
        pv = float(p.get("prezzo_vendita", 0) or 0)
        cp = float(p.get("costo_produzione", 0) or 0)
        iva = float(p.get("iva", 10) or 10)
        if pv > 0 and cp > 0:
            margine = pv - cp
            p["margine_euro"] = round(margine, 2)
            p["margine_percentuale"] = round((margine / pv) * 100, 1)
            p["prezzo_ivato"] = round(pv * (1 + iva / 100), 2)
        elif pv > 0:
            p["prezzo_ivato"] = round(pv * (1 + iva / 100), 2)
    return prodotti


@router.get("/categorie")
async def get_categorie():
    db = Database.get_db()
    categorie = await db["prodotti_vendita"].distinct("categoria")
    return [c for c in categorie if c]


@router.get("/anteprima-prezzi-margine")
async def anteprima_prezzi_margine(margine_percentuale: float = 30.0):
    db = Database.get_db()
    query = {
        "costo_produzione": {"$gt": 0},
        "$or": [
            {"prezzo_vendita": {"$exists": False}},
            {"prezzo_vendita": 0},
            {"prezzo_vendita": None}
        ]
    }
    prodotti = await db["prodotti_vendita"].find(query, {"_id": 0}).to_list(1000)
    preview = []
    for p in prodotti:
        costo = float(p.get("costo_produzione") or 0)
        if costo <= 0:
            continue
        prezzo = round(costo / (1 - margine_percentuale / 100), 2)
        iva = float(p.get("iva", 10) or 10)
        preview.append({
            "id": p["id"], "nome": p["nome"], "costo": costo,
            "prezzo_suggerito": prezzo,
            "prezzo_ivato": round(prezzo * (1 + iva / 100), 2),
            "categoria": p.get("categoria", ""), "fonte": p.get("fonte", "")
        })
    return sorted(preview, key=lambda x: x["nome"])


@router.get("/{prodotto_id}")
async def get_prodotto(prodotto_id: str):
    db = Database.get_db()
    prodotto = await db["prodotti_vendita"].find_one({"id": prodotto_id}, {"_id": 0})
    if not prodotto:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")
    return prodotto


@router.post("/")
async def create_prodotto(prodotto: ProdottoVendita):
    db = Database.get_db()
    if prodotto.prezzo_vendita > 0 and prodotto.costo_produzione > 0:
        prodotto.margine_euro = round(prodotto.prezzo_vendita - prodotto.costo_produzione, 2)
        prodotto.margine_percentuale = round((prodotto.margine_euro / prodotto.prezzo_vendita) * 100, 1)
    prodotto.prezzo_ivato = round(prodotto.prezzo_vendita * (1 + prodotto.iva / 100), 2)
    doc = prodotto.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    await db["prodotti_vendita"].insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/{prodotto_id}")
async def aggiorna_prodotto(prodotto_id: str, prodotto: ProdottoVendita):
    db = Database.get_db()
    existing = await db["prodotti_vendita"].find_one({"id": prodotto_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")
    pv = float(prodotto.prezzo_vendita or 0)
    cp = float(prodotto.costo_produzione or 0)
    iva = float(prodotto.iva or 10)
    update_data = prodotto.model_dump()
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    update_data["prezzo_ivato"] = round(pv * (1 + iva / 100), 2)
    if pv > 0 and cp > 0:
        margine = pv - cp
        update_data["margine_euro"] = round(margine, 2)
        update_data["margine_percentuale"] = round((margine / pv) * 100, 1)
    else:
        update_data["margine_euro"] = 0
        update_data["margine_percentuale"] = 0
    await db["prodotti_vendita"].update_one({"id": prodotto_id}, {"$set": update_data})
    return await db["prodotti_vendita"].find_one({"id": prodotto_id}, {"_id": 0})


@router.put("/{prodotto_id}/prezzo")
async def aggiorna_prezzo_prodotto(prodotto_id: str, prezzo_vendita: float, iva: float = 10):
    db = Database.get_db()
    prodotto = await db["prodotti_vendita"].find_one({"id": prodotto_id}, {"_id": 0})
    if not prodotto:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")
    costo = float(prodotto.get("costo_produzione", 0) or 0)
    iva_rate = float(prodotto.get("iva", iva) or iva)
    update = {
        "prezzo_vendita": prezzo_vendita,
        "prezzo_ivato": round(prezzo_vendita * (1 + iva_rate / 100), 2),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    if prezzo_vendita > 0 and costo > 0:
        margine = prezzo_vendita - costo
        update["margine_euro"] = round(margine, 2)
        update["margine_percentuale"] = round((margine / prezzo_vendita) * 100, 1)
    else:
        update["margine_euro"] = 0
        update["margine_percentuale"] = 0
    await db["prodotti_vendita"].update_one({"id": prodotto_id}, {"$set": update})
    return await db["prodotti_vendita"].find_one({"id": prodotto_id}, {"_id": 0})


@router.delete("/{prodotto_id}")
async def delete_prodotto(prodotto_id: str):
    db = Database.get_db()
    result = await db["prodotti_vendita"].delete_one({"id": prodotto_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")
    return {"success": True}


@router.post("/imposta-prezzi-da-margine")
async def imposta_prezzi_da_margine(margine_percentuale: float = 30.0):
    db = Database.get_db()
    prodotti = await db["prodotti_vendita"].find(
        {"costo_produzione": {"$gt": 0}, "$or": [{"prezzo_vendita": {"$lte": 0}}, {"prezzo_vendita": None}]},
        {"_id": 0}
    ).to_list(1000)
    aggiornati = 0
    for p in prodotti:
        costo = float(p.get("costo_produzione") or 0)
        if costo <= 0:
            continue
        prezzo = round(costo / (1 - margine_percentuale / 100), 2)
        iva = float(p.get("iva", 10) or 10)
        await db["prodotti_vendita"].update_one(
            {"id": p["id"]},
            {"$set": {
                "prezzo_vendita": prezzo,
                "prezzo_ivato": round(prezzo * (1 + iva / 100), 2),
                "margine_percentuale": margine_percentuale,
                "margine_euro": round(prezzo - costo, 2),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        aggiornati += 1
    return {"success": True, "aggiornati": aggiornati}
