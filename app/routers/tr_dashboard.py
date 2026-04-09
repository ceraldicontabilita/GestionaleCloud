"""
Router Dashboard Tracciabilità — Produzioni, Vendita Banco, Lotti, Chiusure, Acquaviva.
Adattato dai rispettivi router del repo tracciabilita.
Prefix: /api/tr/
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
import uuid, re

from app.database import get_database
from app.tr_utils import oggi_iso

router = APIRouter(tags=["Tracciabilità - Dashboard"])

# ══════════════════════════════════════════════════════════════════════════════
#  PRODUZIONI
# ══════════════════════════════════════════════════════════════════════════════

class ProduzioneCrea(BaseModel):
    ricetta_id: str
    ricetta_nome: str
    pezzi: int
    moltiplicatore: float = 1.0
    peso_totale_g: float = 0
    costo_totale: float = 0
    note: str = ""

@router.post("/produzioni")
async def registra_produzione(p: ProduzioneCrea, db: AsyncIOMotorDatabase = Depends(get_database)):
    doc = p.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["data"] = datetime.now(timezone.utc).isoformat()
    await db["produzioni"].insert_one(doc)
    await db["vendite_banco"].insert_one({
        "id": str(uuid.uuid4()), "prodotto_id": p.ricetta_id, "prodotto_nome": p.ricetta_nome,
        "reparto": "pasticceria", "pezzi_prodotti": p.pezzi, "pezzi_venduti": 0,
        "data": oggi_iso(), "fonte": "produzione", "costo_totale": p.costo_totale,
        "stato": "aperto", "created_at": datetime.now(timezone.utc).isoformat()})
    doc.pop("_id", None)
    return doc

@router.get("/produzioni/per-oggi")
async def produzioni_oggi(db: AsyncIOMotorDatabase = Depends(get_database)):
    oggi = oggi_iso()
    pipeline = [
        {"$addFields": {"data_str": {"$substr": ["$data", 0, 10]}}},
        {"$match": {"data_str": oggi, "reparto": {"$in": ["pasticceria", "rosticceria"]}}},
        {"$project": {"_id": 0}},
    ]
    return await db["produzioni"].aggregate(pipeline).to_list(200)

@router.get("/produzioni")
async def get_produzioni(search: Optional[str] = None, limit: int = Query(500, le=2000),
                          db: AsyncIOMotorDatabase = Depends(get_database)):
    q = {}
    if search: q["ricetta_nome"] = {"$regex": search, "$options": "i"}
    items = await db["produzioni"].find(q, {"_id": 0}).sort("data", -1).limit(limit).to_list(limit)
    for p in items:
        if "moltiplicatore" not in p or p["moltiplicatore"] is None: p["moltiplicatore"] = 1.0
    return items

@router.get("/produzioni/stats")
async def stats_produzioni(db: AsyncIOMotorDatabase = Depends(get_database)):
    pipeline = [
        {"$group": {"_id": "$ricetta_nome", "totale_pezzi": {"$sum": "$pezzi"},
                     "totale_costo": {"$sum": "$costo_totale"}, "num": {"$sum": 1},
                     "ultima": {"$max": "$data"}}},
        {"$sort": {"totale_pezzi": -1}}, {"$limit": 20}
    ]
    result = await db["produzioni"].aggregate(pipeline).to_list(20)
    for r in result: r["ricetta"] = r.pop("_id", "")
    return result

@router.delete("/produzioni/{produzione_id}")
async def elimina_produzione(produzione_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    r = await db["produzioni"].delete_one({"id": produzione_id})
    if r.deleted_count == 0: raise HTTPException(404, "Non trovata")
    return {"success": True}

# ══════════════════════════════════════════════════════════════════════════════
#  VENDITA BANCO
# ══════════════════════════════════════════════════════════════════════════════

class VenditaBancoIn(BaseModel):
    prodotto_id: str
    prodotto_nome: str
    reparto: str = "rosticceria"
    pezzi_prodotti: int
    foto_url: Optional[str] = None
    data: Optional[str] = None

class InvendutoIn(BaseModel):
    vendita_id: str
    pezzi_invenduto: int
    note: Optional[str] = ""

@router.post("/vendita-banco/registra")
async def registra_vendita(p: VenditaBancoIn, db: AsyncIOMotorDatabase = Depends(get_database)):
    doc = {"id": str(uuid.uuid4()), "prodotto_id": p.prodotto_id, "prodotto_nome": p.prodotto_nome,
           "reparto": p.reparto, "foto_url": p.foto_url, "pezzi_prodotti": p.pezzi_prodotti,
           "pezzi_invenduto": None, "pezzi_venduti": None, "data": p.data or oggi_iso(),
           "creato_at": datetime.now(timezone.utc).isoformat(), "invenduto_at": None, "stato": "aperto"}
    await db["vendite_banco"].insert_one(doc)
    doc.pop("_id", None)
    return doc

@router.put("/vendita-banco/{vendita_id}/invenduto")
async def registra_invenduto(vendita_id: str, p: InvendutoIn, db: AsyncIOMotorDatabase = Depends(get_database)):
    v = await db["vendite_banco"].find_one({"id": vendita_id}, {"_id": 0})
    if not v: raise HTTPException(404, "Non trovata")
    pv = max(0, v["pezzi_prodotti"] - p.pezzi_invenduto)
    await db["vendite_banco"].update_one({"id": vendita_id},
        {"$set": {"pezzi_invenduto": p.pezzi_invenduto, "pezzi_venduti": pv,
                  "note_invenduto": p.note, "invenduto_at": datetime.now(timezone.utc).isoformat(), "stato": "chiuso"}})
    return {"vendita_id": vendita_id, "pezzi_venduti": pv, "pezzi_invenduto": p.pezzi_invenduto}

@router.get("/vendita-banco/oggi")
async def vendite_oggi(reparto: str = "", db: AsyncIOMotorDatabase = Depends(get_database)):
    q = {"data": oggi_iso()}
    if reparto: q["reparto"] = reparto
    docs = await db["vendite_banco"].find(q, {"_id": 0}).sort("creato_at", -1).to_list(200)
    docs = [d for d in docs if d.get("prodotto_nome")]
    for doc in docs:
        if doc.get("costo_produzione") and doc.get("prezzo_vendita"): continue
        nome = (doc.get("prodotto_nome") or "").strip().lower()
        pv = await db["prodotti_vendita"].find_one({"nome_display": {"$regex": nome, "$options": "i"}},
                                                    {"_id": 0, "costo_produzione": 1, "prezzo_vendita": 1})
        if pv:
            if not doc.get("costo_produzione"): doc["costo_produzione"] = pv.get("costo_produzione", 0)
            if not doc.get("prezzo_vendita"): doc["prezzo_vendita"] = pv.get("prezzo_vendita", 0)
            continue
        ric = await db["ricette"].find_one({"nome": {"$regex": nome, "$options": "i"}},
                                            {"_id": 0, "costo_totale": 1, "pezzi_produzione": 1, "prezzo_vendita": 1})
        if ric:
            ct = ric.get("costo_totale", 0); pz = ric.get("pezzi_produzione", 1)
            if not doc.get("costo_produzione"): doc["costo_produzione"] = round(ct/pz, 4)
            if not doc.get("prezzo_vendita"): doc["prezzo_vendita"] = ric.get("prezzo_vendita", 0)
    return docs

@router.delete("/vendita-banco/{vendita_id}")
async def elimina_vendita(vendita_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    r = await db["vendite_banco"].delete_one({"id": vendita_id})
    if r.deleted_count == 0: raise HTTPException(404)
    return {"success": True}

# ══════════════════════════════════════════════════════════════════════════════
#  LOTTI
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/lotti")
async def get_lotti(search: Optional[str] = None, db: AsyncIOMotorDatabase = Depends(get_database)):
    q = {}
    if search:
        q["$or"] = [{"prodotto": {"$regex": search, "$options": "i"}},
                     {"prodotto_nome": {"$regex": search, "$options": "i"}},
                     {"numero_lotto": {"$regex": search, "$options": "i"}}]
    items = await db["lotti"].find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    for it in items:
        if not it.get("prodotto") and it.get("prodotto_nome"): it["prodotto"] = it["prodotto_nome"]
        if not it.get("numero_lotto") and it.get("lotto_id"): it["numero_lotto"] = it["lotto_id"]
        if not it.get("id") and it.get("lotto_id"): it["id"] = it["lotto_id"]
        it.setdefault("stato", "attivo"); it.setdefault("consumato", False); it.setdefault("data_consumo", None)
    return items

@router.patch("/lotti/{lotto_id}/consuma")
async def consuma_lotto(lotto_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    r = await db["lotti"].update_one(
        {"$or": [{"id": lotto_id}, {"lotto_id": lotto_id}]},
        {"$set": {"consumato": True, "stato": "consumato",
                  "data_consumo": datetime.now(timezone.utc).isoformat()}})
    if r.matched_count == 0: raise HTTPException(404, "Lotto non trovato")
    return {"success": True}

# ══════════════════════════════════════════════════════════════════════════════
#  CHIUSURE — giorno produttivo/riposo
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/chiusure/giorno-non-produttivo/oggi")
async def get_giorno_stato(db: AsyncIOMotorDatabase = Depends(get_database)):
    oggi = oggi_iso()
    doc = await db["chiusure_giornaliere"].find_one({"data": oggi}, {"_id": 0})
    if not doc:
        return {"data": oggi, "non_produttivo": False}
    return doc

@router.post("/chiusure/giorno-non-produttivo/oggi")
async def set_giorno_stato(non_produttivo: bool = True, db: AsyncIOMotorDatabase = Depends(get_database)):
    oggi = oggi_iso()
    await db["chiusure_giornaliere"].update_one(
        {"data": oggi}, {"$set": {"data": oggi, "non_produttivo": non_produttivo,
                                   "updated_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    return {"success": True, "data": oggi, "non_produttivo": non_produttivo}

# ══════════════════════════════════════════════════════════════════════════════
#  ACQUAVIVA — magazzino congelatore
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/acquaviva/magazzino-congelatore")
async def magazzino_congelatore(db: AsyncIOMotorDatabase = Depends(get_database)):
    anno = datetime.now(timezone.utc).year
    data_inizio = f"{anno}-01-01"
    # Ultime 2 fatture Vandemoortele
    tutte = await db["fatture"].find({"fornitore": {"$regex": "vandemoortele", "$options": "i"}},
                                      {"_id": 0, "prodotti": 1, "data_fattura": 1, "numero_fattura": 1}
                                      ).sort("data_fattura", -1).to_list(200)
    # Se fatture non trovate nella collection "fatture", prova "fatture_passive"
    if not tutte:
        tutte = await db["fatture_passive"].find(
            {"fornitore_denominazione": {"$regex": "vandemoortele", "$options": "i"}},
            {"_id": 0, "linee": 1, "data": 1, "numero": 1}
        ).sort("data", -1).to_list(200)
        # Adatta formato
        for f in tutte:
            f["prodotti"] = [{"descrizione": l.get("descrizione",""), "quantita": l.get("quantita",0),
                              "prezzo": l.get("prezzo_unitario",0)} for l in f.get("linee", [])]
            f["data_fattura"] = f.get("data", "")
            f["numero_fattura"] = f.get("numero", "")
    fatture = tutte[:2]
    entrate_desc = {}
    for fat in fatture:
        for p in fat.get("prodotti", []):
            desc = p.get("descrizione", "").strip()
            qty = float(p.get("quantita", 0) or 0)
            prezzo = float(p.get("prezzo", 0) or 0)
            if not desc or qty <= 0: continue
            m_peso = re.search(r"(\d+\.?\d*)\s*G\b", desc.upper())
            peso_g = float(m_peso.group(1)) if m_peso else None
            m_kg = re.findall(r"([\d]+[.,]?[\d]*)\s*KG", desc.upper())
            kg_cart = None
            for val in reversed(m_kg):
                v = float(val.replace(',', '.'))
                if 0.5 < v < 50: kg_cart = v; break
            if kg_cart is None and m_kg:
                v = float(m_kg[-1].replace(',', '.'))
                if v > 50: kg_cart = round(v / 100, 2)
            pz_cart = round(kg_cart * 1000 / peso_g) if kg_cart and peso_g and peso_g > 0 else None
            if desc not in entrate_desc:
                entrate_desc[desc] = {"cartoni": 0, "peso_g": peso_g, "kg_cartone": kg_cart,
                                      "pz_cartone": pz_cart, "prezzo_cartone": prezzo, "pz_totali": 0}
            entrate_desc[desc]["cartoni"] += qty
            if pz_cart: entrate_desc[desc]["pz_totali"] += int(qty * pz_cart)
    data_min = fatture[-1].get("data_fattura", data_inizio) if fatture else data_inizio
    uscite = await db["vendite_banco"].aggregate([
        {"$match": {"fonte": "colazione", "data": {"$gte": data_min}}},
        {"$group": {"_id": "$prodotto_nome", "pezzi_usciti": {"$sum": "$pezzi_prodotti"}}}
    ]).to_list(500)
    tot_uscite = sum(u["pezzi_usciti"] for u in uscite)
    tot_entrate = sum(e["pz_totali"] for e in entrate_desc.values())
    prodotti = [{"descrizione_fattura": d, "cartoni_acquistati": i["cartoni"], "pz_cartone": i.get("pz_cartone"),
                 "pezzi_entrati": i["pz_totali"], "saldo": max(0, i["pz_totali"])} for d, i in
                sorted(entrate_desc.items(), key=lambda x: -x[1]["pz_totali"])]
    return {"anno": anno, "totale_pezzi_entrati": tot_entrate, "totale_pezzi_usciti": tot_uscite,
            "saldo_congelatore": max(0, tot_entrate - tot_uscite), "prodotti": prodotti}


# ══════════════════════════════════════════════════════════════════════════════
#  TABLET — Lista prodotti per reparto
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/tablet/{reparto}")
async def get_tablet(reparto: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    """Lista prodotti per tablet (rosticceria/pasticceria)."""
    prodotti = []
    ricette = await db["ricette"].find(
        {"$or": [{"reparto": reparto}, {"reparto": {"$exists": False}}]},
        {"_id": 0, "id": 1, "nome": 1, "foto_url": 1, "reparto": 1, "note": 1, "pezzi_produzione": 1}
    ).to_list(200)
    for r in ricette:
        prodotti.append({
            "id": r.get("id", ""), "nome": r.get("nome", ""),
            "foto_url": r.get("foto_url", ""), "reparto": r.get("reparto", reparto),
            "note": r.get("note", ""), "pezzi_default": r.get("pezzi_produzione", 1),
        })
    if not prodotti:
        pvs = await db["prodotti_vendita"].find(
            {"reparto": {"$regex": reparto, "$options": "i"}}, {"_id": 0}
        ).to_list(200)
        for p in pvs:
            prodotti.append({
                "id": p.get("id", ""), "nome": p.get("nome_display", p.get("nome", "")),
                "foto_url": p.get("foto_url", ""), "reparto": reparto,
            })
    return prodotti
