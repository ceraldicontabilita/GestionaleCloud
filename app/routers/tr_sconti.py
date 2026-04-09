"""
Router Sconti Merce — Prodotti ricevuti come sconto dai fornitori.
Adattato da tracciabilita/backend/routers/sconti_merce.py
Prefix: /api/tr/sconti-merce
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase
import uuid, re

from app.database import get_database

router = APIRouter(prefix="/sconti-merce", tags=["Tracciabilità - Sconti Merce"])

class ScontoMerce(BaseModel):
    data: str; fornitore: str; prodotto: str
    cartoni: float = 0; pezzi_per_cartone: float = 0; pezzi_totali: float = 0
    valore_unitario: float = 0; valore_totale: float = 0
    fattura_riferimento: str = ""; note: str = ""

def _calc_pezzi_da_nome(nome):
    m = re.search(r'(\d+(?:[,\.]\d+)?)\s*G\s+(\d+(?:[,\.]\d+)?)\s*KG', nome.upper())
    if m:
        try:
            pg = float(m.group(1).replace(',','.')); pk = float(m.group(2).replace(',','.'))
            if pg > 0: return round((pk*1000)/pg)
        except: pass
    return None

def _parse_data(doc):
    try:
        if "/" in doc["data"]:
            p = doc["data"].split("/"); doc["giorno"]=int(p[0]); doc["mese"]=int(p[1]); doc["anno"]=int(p[2])
        else:
            dt=datetime.fromisoformat(doc["data"]); doc["mese"]=dt.month; doc["anno"]=dt.year
    except:
        now=datetime.now(timezone.utc); doc["mese"]=now.month; doc["anno"]=now.year

@router.get("/")
async def get_sconti(fornitore: Optional[str]=None, mese: Optional[int]=None,
                      anno: Optional[int]=None, limit: int=Query(200, le=1000),
                      db: AsyncIOMotorDatabase = Depends(get_database)):
    q = {}
    if fornitore: q["fornitore"] = {"$regex": fornitore, "$options": "i"}
    if mese: q["mese"] = mese
    if anno: q["anno"] = anno
    return await db["sconti_merce"].find(q, {"_id": 0}).sort("data", -1).limit(limit).to_list(limit)

@router.post("/")
async def crea_sconto(s: ScontoMerce, db: AsyncIOMotorDatabase = Depends(get_database)):
    doc = s.model_dump(); doc["id"] = str(uuid.uuid4())
    if doc["pezzi_totali"]==0 and doc["cartoni"]>0 and doc["pezzi_per_cartone"]>0:
        doc["pezzi_totali"] = round(doc["cartoni"]*doc["pezzi_per_cartone"], 2)
    if doc["valore_totale"]==0 and doc["valore_unitario"]>0:
        u = doc["cartoni"] if doc["cartoni"]>0 else doc["pezzi_totali"]
        doc["valore_totale"] = round(doc["valore_unitario"]*u, 2)
    _parse_data(doc)
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    await db["sconti_merce"].insert_one(doc)
    doc.pop("_id", None)
    return doc

@router.delete("/{sconto_id}")
async def elimina(sconto_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    r = await db["sconti_merce"].delete_one({"id": sconto_id})
    if r.deleted_count == 0: raise HTTPException(404)
    return {"success": True}

@router.post("/importa-da-fatture")
async def importa(db: AsyncIOMotorDatabase = Depends(get_database)):
    """Importa sconti merce dalle fatture (prodotti prezzo=0 / tipo SC).
    Cerca nelle collection fatture e fatture_passive."""
    # Prova fatture (tracciabilita), poi fatture_passive (gestionale2)
    fatture = await db["fatture"].find({}, {"_id": 0}).to_list(10000)
    if not fatture:
        fatture_p = await db["fatture_passive"].find({}, {"_id": 0}).to_list(10000)
        fatture = []
        for fp in fatture_p:
            fatture.append({
                "fornitore": fp.get("fornitore_denominazione",""),
                "numero_fattura": fp.get("numero",""),
                "data_fattura": fp.get("data",""),
                "prodotti": [{"descrizione": l.get("descrizione",""), "quantita": l.get("quantita",0),
                              "prezzo": l.get("prezzo_unitario",0), "unita_misura": l.get("unita_misura","")}
                             for l in fp.get("linee", [])]
            })
    imp = salt = val = 0
    for fat in fatture:
        forn = fat.get("fornitore","").strip()
        if not forn: continue
        nf = fat.get("numero_fattura",""); df = fat.get("data_fattura","")
        prods = fat.get("prodotti", [])
        prezzi = {}
        for p in prods:
            pr = float(p.get("prezzo",0) or 0)
            if pr > 0:
                nm = (p.get("descrizione","") or "").strip().upper()
                if nm: prezzi[nm] = pr
        for p in prods:
            pr = float(p.get("prezzo",0) or 0)
            if pr > 0: continue
            nm = (p.get("descrizione","") or "").strip()
            if not nm: continue
            if await db["sconti_merce"].find_one({"fornitore": forn, "prodotto": nm, "fattura_riferimento": nf}):
                salt += 1; continue
            qt = float(p.get("quantita",0) or 0)
            mese, anno, giorno = 1, datetime.now(timezone.utc).year, 1
            try:
                if "-" in df: pp=df.split("-"); anno=int(pp[0]); mese=int(pp[1]); giorno=int(pp[2][:2])
                elif "/" in df: pp=df.split("/"); giorno=int(pp[0]); mese=int(pp[1]); anno=int(pp[2])
            except: pass
            vu = prezzi.get(nm.upper(), 0); vt = round(vu*qt, 2) if vu and qt else 0
            if vu: val += 1
            um = (p.get("unita_misura","") or "").strip()
            cart = qt if um.upper() not in ("CF","PZ","NR","N") else 0
            pzt = qt if um.upper() in ("CF","PZ","NR","N") else 0
            ppc = _calc_pezzi_da_nome(nm)
            if ppc and cart: pzt = cart * ppc
            doc = {"id": str(uuid.uuid4()), "data": df, "giorno": giorno, "fornitore": forn,
                   "prodotto": nm, "cartoni": cart, "pezzi_per_cartone": ppc or 0, "pezzi_totali": pzt,
                   "valore_unitario": vu, "valore_totale": vt, "fattura_riferimento": nf,
                   "note": f"Da fattura {nf}", "mese": mese, "anno": anno,
                   "created_at": datetime.now(timezone.utc).isoformat()}
            await db["sconti_merce"].insert_one(doc)
            imp += 1
    return {"success": True, "importati": imp, "valorizzati": val, "saltati": salt}

@router.get("/riepilogo/mensile")
async def riepilogo_mensile(anno: int = Query(...), db: AsyncIOMotorDatabase = Depends(get_database)):
    MESI=["","Gennaio","Febbraio","Marzo","Aprile","Maggio","Giugno",
          "Luglio","Agosto","Settembre","Ottobre","Novembre","Dicembre"]
    pipeline=[{"$match":{"anno":anno}},{"$group":{"_id":"$mese","valore_totale":{"$sum":"$valore_totale"},
              "num_righe":{"$sum":1},"cartoni_totali":{"$sum":"$cartoni"},"pezzi_totali":{"$sum":"$pezzi_totali"},
              "fornitori":{"$addToSet":"$fornitore"}}},{"$sort":{"_id":1}}]
    result = await db["sconti_merce"].aggregate(pipeline).to_list(12)
    md = {r["_id"]: {"mese":r["_id"],"nome_mese":MESI[r["_id"]] if r["_id"]<=12 else str(r["_id"]),
                      "valore_totale":round(r["valore_totale"],2),"num_righe":r["num_righe"],
                      "cartoni_totali":round(r["cartoni_totali"],2),"pezzi_totali":round(r["pezzi_totali"],2),
                      "num_fornitori":len(r["fornitori"])} for r in result}
    riepilogo=[md.get(m,{"mese":m,"nome_mese":MESI[m],"valore_totale":0,"num_righe":0,
                          "cartoni_totali":0,"pezzi_totali":0,"num_fornitori":0}) for m in range(1,13)]
    return {"anno":anno,"mesi":riepilogo,"totale_anno":round(sum(r["valore_totale"] for r in riepilogo),2)}

@router.get("/riepilogo/fornitori")
async def riepilogo_fornitori(anno: Optional[int]=None, mese: Optional[int]=None,
                               db: AsyncIOMotorDatabase = Depends(get_database)):
    match = {}
    if anno: match["anno"] = anno
    if mese: match["mese"] = mese
    pipeline = [{"$match": match} if match else {"$match":{}},
                {"$group":{"_id":"$fornitore","valore_totale":{"$sum":"$valore_totale"},
                           "cartoni_totali":{"$sum":"$cartoni"},"num_righe":{"$sum":1}}},
                {"$sort":{"valore_totale":-1}}]
    result = await db["sconti_merce"].aggregate(pipeline).to_list(100)
    for r in result: r["fornitore"]=r.pop("_id",""); r["valore_totale"]=round(r["valore_totale"],2)
    return result


@router.get("/prodotti-fornitore")
async def prodotti_fornitore(fornitore: Optional[str] = Query(None),
                              db: AsyncIOMotorDatabase = Depends(get_database)):
    """Lista prodotti trovati nelle fatture per un fornitore (per datalist form)."""
    if not fornitore or not fornitore.strip():
        return []
    forn = fornitore.strip().lower()
    # Cerca in fatture (formato tracciabilita)
    pipeline = [
        {"$match": {"fornitore": {"$regex": forn, "$options": "i"}}},
        {"$unwind": "$prodotti"},
        {"$group": {"_id": "$prodotti.descrizione"}},
        {"$match": {"_id": {"$ne": None, "$ne": ""}}},
        {"$sort": {"_id": 1}}, {"$limit": 500}
    ]
    docs = await db["fatture"].aggregate(pipeline).to_list(500)
    if not docs:
        # Fallback: fatture_passive (formato gestionale2)
        pipeline2 = [
            {"$match": {"fornitore_denominazione": {"$regex": forn, "$options": "i"}}},
            {"$unwind": "$linee"},
            {"$group": {"_id": "$linee.descrizione"}},
            {"$match": {"_id": {"$ne": None, "$ne": ""}}},
            {"$sort": {"_id": 1}}, {"$limit": 500}
        ]
        docs = await db["fatture_passive"].aggregate(pipeline2).to_list(500)
    return sorted({d["_id"].strip() for d in docs if d.get("_id") and d["_id"].strip()})


@router.post("/valorizza-da-fatture")
async def valorizza(db: AsyncIOMotorDatabase = Depends(get_database)):
    """Per sconti con valore_totale=0, cerca il prezzo nelle fatture dello stesso fornitore."""
    sconti = await db["sconti_merce"].find({"valore_totale": 0}, {"_id": 0}).to_list(5000)
    aggiornati = non_trovati = 0
    for s in sconti:
        forn = s.get("fornitore", "")
        nome = s.get("prodotto", "").strip().upper()
        qty = float(s.get("cartoni", 0) or s.get("pezzi_totali", 0) or 0)
        if not nome:
            non_trovati += 1
            continue
        # Cerca prezzo in fatture
        pipeline = [
            {"$match": {"fornitore": {"$regex": re.escape(forn[:15]), "$options": "i"}}},
            {"$unwind": "$prodotti"},
            {"$match": {"prodotti.prezzo": {"$gt": 0}}},
            {"$group": {"_id": {"$toUpper": "$prodotti.descrizione"},
                        "prezzo": {"$avg": {"$toDouble": "$prodotti.prezzo"}}}},
        ]
        prezzi = await db["fatture"].aggregate(pipeline).to_list(2000)
        pm = {d["_id"]: d["prezzo"] for d in prezzi if d.get("_id")}
        vu = pm.get(nome, 0)
        if not vu:
            # Match prime 2 parole
            w = nome.split()[:2]
            for k, v in pm.items():
                if k.split()[:2] == w:
                    vu = v
                    break
        if vu > 0:
            vt = round(vu * qty, 2) if qty else vu
            await db["sconti_merce"].update_one({"id": s["id"]},
                {"$set": {"valore_unitario": vu, "valore_totale": vt}})
            aggiornati += 1
        else:
            non_trovati += 1
    return {"success": True, "aggiornati": aggiornati, "non_trovati": non_trovati}
