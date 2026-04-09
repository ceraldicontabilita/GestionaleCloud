"""
Router Prima Nota — Cassa, Banca, Provvisoria.
Prefix: /api/prima-nota

Sezioni:
- CASSA: incassi giornalieri (da corrispettivi RT + manuali)
- BANCA: movimenti c/c (da estratto conto BPM + manuali)
- PROVVISORIA: fatture da pagare / crediti da incassare (auto da fatture + manuali)

Auto-alimentazione:
- Corrispettivi → cassa (incasso giornaliero)
- Estratto conto movimenti → banca
- Fatture passive non pagate → provvisoria (uscite previste)
- F24 → banca (versamenti tributi)
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase
import uuid, hashlib

from app.database import get_database

router = APIRouter(tags=["Prima Nota"])


# ══════════════════════════════════════════════════════════════════════════════
#  MODELLI
# ══════════════════════════════════════════════════════════════════════════════

class MovimentoIn(BaseModel):
    data: str                          # YYYY-MM-DD
    sezione: str                       # cassa | banca | provvisoria
    tipo: str = "manuale"              # manuale | auto_corrispettivo | auto_banca | auto_f24 | auto_fattura
    causale: str = ""                  # descrizione libera
    categoria: str = ""                # stipendio | fornitore | incasso | f24 | pos | prelievo | altro
    importo: float = 0                 # positivo=entrata, negativo=uscita
    riferimento: str = ""              # numero fattura, numero F24, ecc.
    fornitore: str = ""                # nome fornitore se applicabile
    note: str = ""

class MovimentoUpdate(BaseModel):
    causale: Optional[str] = None
    categoria: Optional[str] = None
    importo: Optional[float] = None
    riferimento: Optional[str] = None
    fornitore: Optional[str] = None
    note: Optional[str] = None
    confermato: Optional[bool] = None

COLL = "prima_nota"


def _dedup_key(sezione: str, data: str, causale: str, importo: float) -> str:
    raw = f"{sezione}|{data}|{causale[:40]}|{importo}"
    return hashlib.md5(raw.encode()).hexdigest()


# ══════════════════════════════════════════════════════════════════════════════
#  CRUD
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/movimenti")
async def lista_movimenti(
    sezione: str = Query(..., description="cassa | banca | provvisoria"),
    data_da: Optional[str] = None, data_a: Optional[str] = None,
    categoria: Optional[str] = None, tipo: Optional[str] = None,
    confermato: Optional[bool] = None,
    skip: int = 0, limit: int = Query(200, le=2000),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Lista movimenti per sezione con filtri."""
    filtro = {"sezione": sezione}
    if data_da:
        filtro.setdefault("data", {})["$gte"] = data_da
    if data_a:
        filtro.setdefault("data", {})["$lte"] = data_a
    if categoria:
        filtro["categoria"] = categoria
    if tipo:
        filtro["tipo"] = tipo
    if confermato is not None:
        filtro["confermato"] = confermato

    docs = await db[COLL].find(filtro, {"_id": 0}).sort("data", -1).skip(skip).limit(limit).to_list(limit)
    return docs


@router.get("/saldi")
async def get_saldi(
    sezione: str = Query(...),
    anno: Optional[int] = None, mese: Optional[int] = None,
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Saldo, totale entrate e uscite per sezione."""
    match = {"sezione": sezione}
    if anno:
        match["data"] = {"$regex": f"^{anno}"}
    if anno and mese:
        match["data"] = {"$regex": f"^{anno}-{mese:02d}"}

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": None,
            "saldo": {"$sum": "$importo"},
            "entrate": {"$sum": {"$cond": [{"$gt": ["$importo", 0]}, "$importo", 0]}},
            "uscite": {"$sum": {"$cond": [{"$lt": ["$importo", 0]}, {"$abs": "$importo"}, 0]}},
            "n_movimenti": {"$sum": 1},
        }},
    ]
    result = await db[COLL].aggregate(pipeline).to_list(1)
    if not result:
        return {"saldo": 0, "entrate": 0, "uscite": 0, "n_movimenti": 0, "sezione": sezione}
    r = result[0]
    return {
        "sezione": sezione,
        "saldo": round(r["saldo"], 2),
        "entrate": round(r["entrate"], 2),
        "uscite": round(r["uscite"], 2),
        "n_movimenti": r["n_movimenti"],
    }


@router.get("/saldi-mensili")
async def saldi_mensili(
    sezione: str = Query(...), anno: int = Query(...),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Saldi mese per mese."""
    pipeline = [
        {"$match": {"sezione": sezione, "data": {"$regex": f"^{anno}"}}},
        {"$addFields": {"mese": {"$substr": ["$data", 5, 2]}}},
        {"$group": {
            "_id": "$mese",
            "entrate": {"$sum": {"$cond": [{"$gt": ["$importo", 0]}, "$importo", 0]}},
            "uscite": {"$sum": {"$cond": [{"$lt": ["$importo", 0]}, {"$abs": "$importo"}, 0]}},
            "saldo": {"$sum": "$importo"},
            "n": {"$sum": 1},
        }},
        {"$sort": {"_id": 1}},
    ]
    result = await db[COLL].aggregate(pipeline).to_list(12)
    MESI = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
            "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
    mesi_map = {r["_id"]: r for r in result}
    out = []
    for m in range(1, 13):
        ms = f"{m:02d}"
        r = mesi_map.get(ms, {})
        out.append({
            "mese": m, "nome": MESI[m],
            "entrate": round(r.get("entrate", 0), 2),
            "uscite": round(r.get("uscite", 0), 2),
            "saldo": round(r.get("saldo", 0), 2),
            "n_movimenti": r.get("n", 0),
        })
    return {"anno": anno, "sezione": sezione, "mesi": out}


@router.post("/movimenti")
async def crea_movimento(m: MovimentoIn, db: AsyncIOMotorDatabase = Depends(get_database)):
    """Inserisce un movimento manuale."""
    doc = m.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["dedup_key"] = _dedup_key(m.sezione, m.data, m.causale, m.importo)
    doc["confermato"] = True  # i manuali sono confermati di default
    doc["created_at"] = datetime.now(timezone.utc).isoformat()

    # Estrai anno/mese
    try:
        doc["anno"] = int(m.data[:4])
        doc["mese"] = int(m.data[5:7])
    except Exception:
        pass

    await db[COLL].insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/movimenti/{movimento_id}")
async def aggiorna_movimento(
    movimento_id: str, upd: MovimentoUpdate,
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Aggiorna un movimento (manuale o conferma uno automatico)."""
    sets = {k: v for k, v in upd.model_dump().items() if v is not None}
    if not sets:
        raise HTTPException(400, "Nessun campo da aggiornare")
    sets["updated_at"] = datetime.now(timezone.utc).isoformat()

    r = await db[COLL].update_one({"id": movimento_id}, {"$set": sets})
    if r.matched_count == 0:
        raise HTTPException(404, "Movimento non trovato")
    return {"success": True}


@router.delete("/movimenti/{movimento_id}")
async def elimina_movimento(movimento_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    r = await db[COLL].delete_one({"id": movimento_id})
    if r.deleted_count == 0:
        raise HTTPException(404, "Movimento non trovato")
    return {"success": True}


# ══════════════════════════════════════════════════════════════════════════════
#  AUTO-ALIMENTAZIONE — Genera movimenti da documenti importati
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/genera-da-corrispettivi")
async def genera_da_corrispettivi(
    anno: Optional[int] = None,
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Genera movimenti CASSA dai corrispettivi RT importati."""
    filtro = {}
    if anno:
        filtro["anno"] = anno

    corrispettivi = await db["corrispettivi"].find(filtro, {"_id": 0}).to_list(5000)
    inseriti = duplicati = 0

    for c in corrispettivi:
        data = c.get("data", "")
        totale = c.get("totale_corrispettivi", 0)
        non_riscosso = c.get("totale_non_riscosso", 0)
        incasso = round(totale - non_riscosso, 2)
        if incasso <= 0:
            continue

        matricola = c.get("matricola_rt", "")
        chiusura = c.get("numero_chiusura", "")
        causale = f"Corrispettivo RT {matricola} chiusura #{chiusura}"
        dk = _dedup_key("cassa", data, causale, incasso)

        if await db[COLL].find_one({"dedup_key": dk}):
            duplicati += 1
            continue

        doc = {
            "id": str(uuid.uuid4()), "data": data, "sezione": "cassa",
            "tipo": "auto_corrispettivo", "causale": causale,
            "categoria": "incasso_corrispettivo",
            "importo": incasso,  # positivo = entrata
            "riferimento": f"RT {matricola} #{chiusura}",
            "note": f"Totale lordo {totale:.2f} — non riscosso {non_riscosso:.2f}",
            "dedup_key": dk, "confermato": False,
            "anno": int(data[:4]) if len(data) >= 4 else 0,
            "mese": int(data[5:7]) if len(data) >= 7 else 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db[COLL].insert_one(doc)
        inseriti += 1

    return {"success": True, "sezione": "cassa", "inseriti": inseriti, "duplicati": duplicati}


@router.post("/genera-da-estratto-conto")
async def genera_da_estratto_conto(
    anno: Optional[int] = None,
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Genera movimenti BANCA dai movimenti estratto conto importati."""
    filtro = {}
    if anno:
        filtro["data_operazione"] = {"$regex": f"^{anno}"}

    movimenti = await db["estratto_conto_movimenti"].find(filtro, {"_id": 0}).to_list(10000)
    inseriti = duplicati = 0

    for mov in movimenti:
        data = mov.get("data_operazione", "")
        importo = mov.get("importo", 0)
        descrizione = mov.get("descrizione", "")
        categoria = mov.get("categoria", "altro")

        dk = _dedup_key("banca", data, descrizione, importo)
        if await db[COLL].find_one({"dedup_key": dk}):
            duplicati += 1
            continue

        doc = {
            "id": str(uuid.uuid4()), "data": data, "sezione": "banca",
            "tipo": "auto_banca", "causale": descrizione,
            "categoria": categoria, "importo": importo,
            "riferimento": mov.get("chiave", ""),
            "note": f"Valuta: {mov.get('data_valuta', '')}",
            "dedup_key": dk, "confermato": False,
            "anno": int(data[:4]) if len(data) >= 4 else 0,
            "mese": int(data[5:7]) if len(data) >= 7 else 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db[COLL].insert_one(doc)
        inseriti += 1

    return {"success": True, "sezione": "banca", "inseriti": inseriti, "duplicati": duplicati}


@router.post("/genera-da-fatture")
async def genera_da_fatture(
    anno: Optional[int] = None,
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Genera movimenti PROVVISORIA dalle fatture passive (debiti verso fornitori)."""
    filtro = {"stato": {"$ne": "pagata"}}
    if anno:
        filtro["anno"] = anno

    fatture = await db["fatture_passive"].find(filtro, {"_id": 0}).to_list(5000)
    inseriti = duplicati = 0

    for f in fatture:
        data = f.get("data", "")
        importo = f.get("importo_totale", 0)
        fornitore = f.get("fornitore_denominazione", "")
        numero = f.get("numero", "")

        if importo <= 0:
            continue

        causale = f"Fattura {numero} — {fornitore}"
        dk = _dedup_key("provvisoria", data, causale, -importo)

        if await db[COLL].find_one({"dedup_key": dk}):
            duplicati += 1
            continue

        # Cerca data scadenza nei pagamenti
        scadenza = ""
        for pag in f.get("pagamenti", []):
            if pag.get("data_scadenza"):
                scadenza = pag["data_scadenza"]
                break

        doc = {
            "id": str(uuid.uuid4()),
            "data": scadenza or data,  # usa scadenza se disponibile
            "sezione": "provvisoria",
            "tipo": "auto_fattura",
            "causale": causale,
            "categoria": "fornitore",
            "importo": -abs(importo),  # negativo = debito da pagare
            "riferimento": f"Fat. {numero}",
            "fornitore": fornitore,
            "note": f"Data fattura: {data} — Importo: {importo:.2f}€",
            "dedup_key": dk, "confermato": False,
            "anno": int((scadenza or data)[:4]) if len(scadenza or data) >= 4 else 0,
            "mese": int((scadenza or data)[5:7]) if len(scadenza or data) >= 7 else 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db[COLL].insert_one(doc)
        inseriti += 1

    return {"success": True, "sezione": "provvisoria", "inseriti": inseriti, "duplicati": duplicati}


@router.post("/genera-da-f24")
async def genera_da_f24(
    anno: Optional[int] = None,
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Genera movimenti BANCA dai modelli F24 (versamenti tributi)."""
    filtro = {}
    if anno:
        filtro["data_versamento"] = {"$regex": f"^{anno}"}

    f24s = await db["f24"].find(filtro, {"_id": 0}).to_list(1000)
    inseriti = duplicati = 0

    for f in f24s:
        data = f.get("data_versamento", "")
        totale = f.get("totale", 0)
        n_tributi = f.get("n_tributi", 0)

        if totale <= 0:
            continue

        causale = f"F24 — {n_tributi} tributi — {data}"
        dk = _dedup_key("banca", data, causale, -totale)

        if await db[COLL].find_one({"dedup_key": dk}):
            duplicati += 1
            continue

        # Dettaglio tributi
        tributi_desc = []
        for sez_name, sez_key in [("Erario", "sezione_erario"), ("INPS", "sezione_inps"), ("Regioni", "sezione_regioni")]:
            for t in f.get(sez_key, []):
                cod = t.get("codice_tributo", "")
                imp = t.get("importo_debito", 0) or t.get("importo", 0)
                if cod:
                    tributi_desc.append(f"{cod}: {imp:.2f}€")

        doc = {
            "id": str(uuid.uuid4()), "data": data, "sezione": "banca",
            "tipo": "auto_f24", "causale": causale,
            "categoria": "f24",
            "importo": -abs(totale),  # negativo = uscita
            "riferimento": f.get("chiave", ""),
            "note": " | ".join(tributi_desc[:5]) if tributi_desc else "",
            "dedup_key": dk, "confermato": False,
            "anno": int(data[:4]) if len(data) >= 4 else 0,
            "mese": int(data[5:7]) if len(data) >= 7 else 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db[COLL].insert_one(doc)
        inseriti += 1

    return {"success": True, "sezione": "banca", "inseriti": inseriti, "duplicati": duplicati}


@router.post("/genera-tutto")
async def genera_tutto(
    anno: Optional[int] = None,
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Genera movimenti da TUTTE le fonti in un colpo."""
    r1 = await genera_da_corrispettivi(anno, db)
    r2 = await genera_da_estratto_conto(anno, db)
    r3 = await genera_da_fatture(anno, db)
    r4 = await genera_da_f24(anno, db)

    return {
        "success": True,
        "cassa_corrispettivi": r1,
        "banca_estratto_conto": r2,
        "provvisoria_fatture": r3,
        "banca_f24": r4,
        "totale_inseriti": r1["inseriti"] + r2["inseriti"] + r3["inseriti"] + r4["inseriti"],
    }


@router.post("/conferma-tutti")
async def conferma_tutti(
    sezione: str = Query(...),
    data_da: Optional[str] = None, data_a: Optional[str] = None,
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Conferma in blocco tutti i movimenti auto di una sezione."""
    filtro = {"sezione": sezione, "confermato": False}
    if data_da:
        filtro.setdefault("data", {})["$gte"] = data_da
    if data_a:
        filtro.setdefault("data", {})["$lte"] = data_a

    r = await db[COLL].update_many(filtro, {"$set": {"confermato": True, "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"success": True, "confermati": r.modified_count}


@router.get("/riepilogo-annuale")
async def riepilogo_annuale(anno: int = Query(...), db: AsyncIOMotorDatabase = Depends(get_database)):
    """Riepilogo delle 3 sezioni per un anno."""
    result = {}
    for sez in ["cassa", "banca", "provvisoria"]:
        pipeline = [
            {"$match": {"sezione": sez, "data": {"$regex": f"^{anno}"}}},
            {"$group": {
                "_id": None,
                "saldo": {"$sum": "$importo"},
                "entrate": {"$sum": {"$cond": [{"$gt": ["$importo", 0]}, "$importo", 0]}},
                "uscite": {"$sum": {"$cond": [{"$lt": ["$importo", 0]}, {"$abs": "$importo"}, 0]}},
                "n": {"$sum": 1},
                "da_confermare": {"$sum": {"$cond": [{"$eq": ["$confermato", False]}, 1, 0]}},
            }},
        ]
        rows = await db[COLL].aggregate(pipeline).to_list(1)
        r = rows[0] if rows else {}
        result[sez] = {
            "saldo": round(r.get("saldo", 0), 2),
            "entrate": round(r.get("entrate", 0), 2),
            "uscite": round(r.get("uscite", 0), 2),
            "n_movimenti": r.get("n", 0),
            "da_confermare": r.get("da_confermare", 0),
        }
    return {"anno": anno, **result}
