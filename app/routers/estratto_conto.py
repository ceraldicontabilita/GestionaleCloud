"""
Estratto Conto — Upload PDF BPM, parse, salva movimenti.
Collection: estratto_conto_movimenti
Prefix: /api/estratto-conto
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime
from typing import Optional
import hashlib
import logging

from app.database import get_database
from app.parsers.estratto_conto_bpm import parse_estratto_conto_pdf

router = APIRouter()
logger = logging.getLogger(__name__)
COLL = "estratto_conto_movimenti"

# Categorie che rappresentano uscite stipendio (sia bonifico_uscita che stipendio)
CATEGORIE_STIPENDIO = {"bonifico_uscita", "stipendio"}


def _oid(doc):
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


def _chiave(mov: dict) -> str:
    raw = f"{mov['data_operazione']}|{mov['descrizione'][:30]}|{mov['importo']}"
    return hashlib.md5(raw.encode()).hexdigest()


@router.post("/upload-pdf")
async def upload_estratto_conto(file: UploadFile = File(...), db: AsyncIOMotorDatabase = Depends(get_database)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Solo PDF")
    content = await file.read()

    try:
        parsed = parse_estratto_conto_pdf(pdf_bytes=content)
    except Exception as e:
        raise HTTPException(400, f"Errore parsing PDF: {e}")

    movimenti = parsed.get("movimenti", [])
    if not movimenti:
        raise HTTPException(400, "Nessun movimento trovato nel PDF")

    importati = 0
    duplicati = 0

    for mov in movimenti:
        mov["chiave"] = _chiave(mov)
        mov["riconciliato"] = False
        if await db[COLL].find_one({"chiave": mov["chiave"]}):
            duplicati += 1
            continue
        mov["filename"] = file.filename
        mov["imported_at"] = datetime.utcnow()
        await db[COLL].insert_one(mov)
        importati += 1

    totale_entrate = round(sum(m["avere"] for m in movimenti), 2)
    totale_uscite = round(sum(m["dare"] for m in movimenti), 2)

    return {
        "ok": True,
        "importati": importati,
        "duplicati": duplicati,
        "totale_entrate": totale_entrate,
        "totale_uscite": totale_uscite,
        "saldo_netto": round(totale_entrate - totale_uscite, 2),
        "saldo_iniziale": parsed.get("saldo_iniziale", 0),
        "saldo_finale": parsed.get("saldo_finale", 0),
    }


@router.get("")
async def lista_movimenti(
    data_da: Optional[str] = None, data_a: Optional[str] = None,
    categoria: Optional[str] = None,
    riconciliato: Optional[bool] = None,
    skip: int = 0, limit: int = 100,
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    filtro = {}
    if data_da:
        filtro.setdefault("data_operazione", {})["$gte"] = data_da
    if data_a:
        filtro.setdefault("data_operazione", {})["$lte"] = data_a
    if categoria:
        filtro["categoria"] = categoria
    if riconciliato is not None:
        filtro["riconciliato"] = riconciliato

    cursor = db[COLL].find(filtro).sort("data_operazione", -1).skip(skip).limit(limit)
    items = [_oid(doc) async for doc in cursor]
    totale = await db[COLL].count_documents(filtro)
    return {"items": items, "totale": totale}


@router.get("/saldo")
async def saldo_banca(db: AsyncIOMotorDatabase = Depends(get_database)):
    pipeline = [
        {"$group": {"_id": None,
                    "saldo": {"$sum": "$importo"},
                    "entrate": {"$sum": {"$cond": [{"$gt": ["$importo", 0]}, "$importo", 0]}},
                    "uscite": {"$sum": {"$cond": [{"$lt": ["$importo", 0]}, {"$abs": "$importo"}, 0]}},
                    "n_movimenti": {"$sum": 1}}}
    ]
    agg = await db[COLL].aggregate(pipeline).to_list(1)
    r = agg[0] if agg else {}
    return {
        "saldo": round(r.get("saldo", 0), 2),
        "entrate": round(r.get("entrate", 0), 2),
        "uscite": round(r.get("uscite", 0), 2),
        "n_movimenti": r.get("n_movimenti", 0),
    }


@router.get("/stipendi")
async def lista_stipendi(
    anno: Optional[int] = None,
    mese: Optional[int] = None,
    riconciliato: Optional[bool] = None,
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Movimenti estratto conto classificati come stipendio/bonifico_uscita,
    arricchiti con i dati del cedolino riconciliato.
    """
    filtro: dict = {"categoria": {"$in": list(CATEGORIE_STIPENDIO)}}
    if riconciliato is not None:
        filtro["riconciliato"] = riconciliato
    if anno:
        filtro["data_operazione"] = {
            "$gte": f"{anno}-01-01",
            "$lte": f"{anno}-12-31"
        }
    if mese and anno:
        mese_str = f"{anno}-{mese:02d}"
        filtro["data_operazione"] = {
            "$gte": f"{mese_str}-01",
            "$lte": f"{mese_str}-31"
        }

    cursor = db[COLL].find(filtro).sort("data_operazione", -1).limit(500)
    movimenti = [_oid(doc) async for doc in cursor]

    # Arricchisci con dati cedolino se riconciliato
    for mov in movimenti:
        cedolino_cf = mov.get("cedolino_cf")
        movimento_data = mov.get("data_operazione", "")
        if cedolino_cf and mov.get("riconciliato"):
            # Stima mese/anno dal cedolino_id se presente, altrimenti dal mese del movimento
            ced = await db["cedolini"].find_one(
                {"codice_fiscale": cedolino_cf},
                sort=[("anno", -1), ("mese", -1)]
            )
            if ced:
                mov["cedolino_netto"] = ced.get("netto")
                mov["cedolino_mese"] = ced.get("mese")
                mov["cedolino_anno"] = ced.get("anno")
                mov["cedolino_nome"] = f"{ced.get('cognome', '')} {ced.get('nome', '')}".strip()
        elif not cedolino_cf and mov.get("dipendente"):
            # Prova a trovare il dipendente per nome anche se non riconciliato
            mov["cedolino_nome"] = mov.get("dipendente", "")

    return {"items": movimenti, "totale": len(movimenti)}


@router.post("/riconcilia-stipendi")
async def riconcilia_stipendi(db: AsyncIOMotorDatabase = Depends(get_database)):
    """
    Riconcilia movimenti stipendio/bonifico_uscita con cedolini.
    Strategia:
      1. Per ogni movimento non riconciliato in CATEGORIE_STIPENDIO:
         a. Estrai nome dipendente dal campo 'dipendente' (già parsato)
         b. Cerca dipendente in collection dipendenti per cognome+nome (fuzzy)
         c. Se trovato, cerca cedolino di quel CF con netto ≈ abs(importo) ±5€
            nel mese del movimento (±1 mese di tolleranza)
         d. Marca entrambi come riconciliati
    """
    movimenti = await db[COLL].find({
        "categoria": {"$in": list(CATEGORIE_STIPENDIO)},
        "riconciliato": False,
        "importo": {"$lt": 0}  # solo uscite
    }).sort("data_operazione", -1).to_list(500)

    riconciliati = 0
    non_trovati = []

    for mov in movimenti:
        importo_abs = abs(mov.get("importo", 0))
        nome_raw = mov.get("dipendente", "").strip()
        data_op = mov.get("data_operazione", "")  # YYYY-MM-DD

        # Stima anno e mese dal movimento
        try:
            dt = datetime.strptime(data_op, "%Y-%m-%d")
            anno_mov = dt.year
            mese_mov = dt.month
        except Exception:
            anno_mov = None
            mese_mov = None

        dipendente = None

        # Strategia 1: match per nome estratto dalla descrizione
        if nome_raw:
            parti = nome_raw.upper().split()
            if parti:
                # Prova prima cognome esatto
                query_parts = [
                    {"cognome": {"$regex": parti[0], "$options": "i"}},
                ]
                if len(parti) > 1:
                    query_parts.append({"nome": {"$regex": parti[-1], "$options": "i"}})
                dipendente = await db["dipendenti"].find_one({"$and": query_parts})

        # Strategia 2: se importo è unico tra i cedolini del mese, match diretto
        if not dipendente and anno_mov and mese_mov and importo_abs > 0:
            # Cerca cedolini del mese con netto ≈ importo
            mesi_cerca = [mese_mov]
            if mese_mov > 1:
                mesi_cerca.append(mese_mov - 1)

            candidati = await db["cedolini"].find({
                "anno": anno_mov,
                "mese": {"$in": mesi_cerca},
                "netto": {"$gte": importo_abs - 5, "$lte": importo_abs + 5},
                "riconciliato": False
            }).to_list(10)

            if len(candidati) == 1:
                # Unico match per importo → abbastanza sicuro
                ced_unico = candidati[0]
                dipendente = await db["dipendenti"].find_one(
                    {"codice_fiscale": ced_unico["codice_fiscale"]}
                )

        if not dipendente:
            non_trovati.append({
                "descrizione": mov.get("descrizione", ""),
                "importo": importo_abs,
                "data": data_op,
                "nome_estratto": nome_raw
            })
            continue

        cf = dipendente.get("codice_fiscale", "")

        # Cerca cedolino: stesso CF, stesso anno/mese (±1 mese), netto ≈ importo
        filtro_ced = {
            "codice_fiscale": cf,
            "riconciliato": False,
            "netto": {"$gte": importo_abs - 5, "$lte": importo_abs + 5},
        }
        if anno_mov:
            filtro_ced["anno"] = anno_mov
        if mese_mov:
            filtro_ced["mese"] = {"$in": [mese_mov, mese_mov - 1 if mese_mov > 1 else mese_mov]}

        cedolino = await db["cedolini"].find_one(filtro_ced)

        # Aggiorna movimento
        await db[COLL].update_one(
            {"_id": mov["_id"]},
            {"$set": {
                "riconciliato": True,
                "cedolino_cf": cf,
                "cedolino_nome": f"{dipendente.get('cognome', '')} {dipendente.get('nome', '')}".strip(),
                "cedolino_id": str(cedolino["_id"]) if cedolino else None,
                "riconciliato_at": datetime.utcnow()
            }}
        )

        # Aggiorna cedolino se trovato
        if cedolino:
            await db["cedolini"].update_one(
                {"_id": cedolino["_id"]},
                {"$set": {
                    "riconciliato": True,
                    "movimento_id": str(mov["_id"]),
                    "riconciliato_at": datetime.utcnow()
                }}
            )

        riconciliati += 1

    return {
        "ok": True,
        "riconciliati": riconciliati,
        "non_trovati": non_trovati,
        "totale_elaborati": len(movimenti)
    }
