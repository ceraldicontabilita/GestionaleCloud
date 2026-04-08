"""
Router F24 — Ceraldi ERP
PREFIX: /api/f24

Collection MongoDB: f24

Endpoints:
  POST   /api/f24/upload-pdf          → import batch PDF
  GET    /api/f24                     → lista con filtri (anno, mese, stato, sezione)
  GET    /api/f24/{id}                → singolo documento
  GET    /api/f24/{id}/pdf            → PDF originale
  POST   /api/f24/{id}/segna-pagato   → marca pagato manualmente
  GET    /api/f24/ricerca-tributo     → cerca tributo per codice+anno (per avvisi)
  GET    /api/f24/riepilogo/{anno}    → totali annuali per sezione
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from datetime import datetime
import os, re

from app.database import get_database

router = APIRouter(prefix="/api/f24", tags=["F24"])

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "f24")
os.makedirs(UPLOAD_DIR, exist_ok=True)

AZIENDA_ID = "b0295759-35ce-4b34-a6b4-f01b883234ad"


def _oid(doc):
    doc["_id"] = str(doc["_id"])
    return doc


# ═══════════════════════════════════════════════════════
# POST /upload-pdf  — import batch PDF F24
# ═══════════════════════════════════════════════════════
@router.post("/upload-pdf")
async def upload_f24_pdf(
    files: list[UploadFile] = File(...),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    from app.parsers.f24_parser import parse_f24_pdf

    risultati = []
    for upload in files:
        pdf_bytes = await upload.read()
        filename = upload.filename or "f24.pdf"

        # Salva PDF originale
        safe_name = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", filename)
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        dest = os.path.join(UPLOAD_DIR, f"{ts}_{safe_name}")
        with open(dest, "wb") as f:
            f.write(pdf_bytes)

        try:
            documenti = parse_f24_pdf(pdf_bytes, filename)
        except Exception as e:
            risultati.append({"file": filename, "ok": False, "errore": str(e)})
            continue

        for doc in documenti:
            doc["azienda_id"] = AZIENDA_ID
            doc["pdf_path"] = dest
            doc["created_at"] = datetime.utcnow()
            doc["updated_at"] = datetime.utcnow()

            # Upsert su (codice_fiscale, scadenza, pagina)
            existing = await db["f24"].find_one({
                "codice_fiscale": doc.get("codice_fiscale"),
                "scadenza": doc.get("scadenza"),
                "pagina": doc.get("pagina", 1),
            })
            if existing:
                await db["f24"].update_one(
                    {"_id": existing["_id"]},
                    {"$set": {**doc, "updated_at": datetime.utcnow()}}
                )
                risultati.append({
                    "file": filename,
                    "ok": True,
                    "azione": "aggiornato",
                    "id": str(existing["_id"]),
                    "scadenza": doc.get("scadenza"),
                    "saldo_finale": doc.get("saldo_finale"),
                })
            else:
                res = await db["f24"].insert_one(doc)
                risultati.append({
                    "file": filename,
                    "ok": True,
                    "azione": "inserito",
                    "id": str(res.inserted_id),
                    "scadenza": doc.get("scadenza"),
                    "saldo_finale": doc.get("saldo_finale"),
                })

    return {"risultati": risultati, "totale": len(risultati)}


# ═══════════════════════════════════════════════════════
# GET /  — lista F24 con filtri
# ═══════════════════════════════════════════════════════
@router.get("")
async def lista_f24(
    anno: int = None,
    mese: int = None,
    sezione: str = None,
    codice_tributo: str = None,
    includi_scartati: bool = Query(False, description="Includi F24 scartati"),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    q = {"azienda_id": AZIENDA_ID, "stato": {"$ne": "scartato"}} if not includi_scartati else {"azienda_id": AZIENDA_ID}

    if anno:
        q["scadenza"] = {"$regex": f"^{anno}"}
    if mese and anno:
        q["scadenza"] = f"{anno}-{mese:02d}"

    if codice_tributo:
        q["tributi_flat.codice_tributo"] = codice_tributo
    if sezione:
        q["tributi_flat.sezione"] = sezione.upper()

    cursor = db["f24"].find(q).sort("scadenza", -1)
    docs = []
    async for doc in cursor:
        docs.append(_oid(doc))
    return docs




# ═══════════════════════════════════════════════════════
# POST /{id}/scarta  — scarta un F24 (non verrà usato)
# ═══════════════════════════════════════════════════════
@router.post("/{fid}/scarta")
async def scarta_f24(fid: str, body: dict, db: AsyncIOMotorDatabase = Depends(get_database)):
    """
    Scarta un F24 importato (da Gmail, upload manuale, ecc).
    Motivi tipici:
      - "F24 cumulativo, richiesta rateizzazione"
      - "Importo errato, versione corretta in arrivo"
      - "Doppio pagamento — primo F24 non andato a buon fine"
      - "Ravvedimento integrativo — già contabilizzato"
    Un F24 scartato:
      - NON appare nel totale versato
      - NON viene usato in riconciliazione estratto conto
      - NON compare nella lista standard
      - Rimane in DB con stato='scartato' per storico
    """
    motivo = body.get("motivo", "Scartato manualmente")
    res = await db["f24"].update_one(
        {"_id": ObjectId(fid)},
        {"$set": {
            "stato": "scartato",
            "motivo_scarto": motivo,
            "scartato_il": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }}
    )
    if res.matched_count == 0:
        raise HTTPException(404, "F24 non trovato")
    return {"ok": True, "motivo": motivo}


# ═══════════════════════════════════════════════════════
# POST /{id}/ripristina  — annulla scarto
# ═══════════════════════════════════════════════════════
@router.post("/{fid}/ripristina")
async def ripristina_f24(fid: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    """Riporta un F24 scartato allo stato 'pagato'."""
    res = await db["f24"].update_one(
        {"_id": ObjectId(fid), "stato": "scartato"},
        {"$set": {"stato": "pagato", "updated_at": datetime.utcnow()},
         "$unset": {"motivo_scarto": "", "scartato_il": ""}}
    )
    if res.matched_count == 0:
        raise HTTPException(404, "F24 non trovato o non scartato")
    return {"ok": True}


# ═══════════════════════════════════════════════════════
# GET /scartati  — lista F24 scartati
# ═══════════════════════════════════════════════════════
@router.get("/scartati")
async def lista_scartati(anno: int = None, db: AsyncIOMotorDatabase = Depends(get_database)):
    q = {"azienda_id": AZIENDA_ID, "stato": "scartato"}
    if anno:
        q["scadenza"] = {"$regex": f"^{anno}"}
    cursor = db["f24"].find(q).sort("scartato_il", -1)
    docs = []
    async for doc in cursor:
        docs.append(_oid(doc))
    return docs


# ═══════════════════════════════════════════════════════
# POST /riconcilia  — riconcilia F24 con estratto conto
# ═══════════════════════════════════════════════════════
@router.post("/riconcilia")
async def riconcilia_f24(body: dict, db: AsyncIOMotorDatabase = Depends(get_database)):
    """
    Riconcilia un F24 con un movimento dell'estratto conto.
    
    body: {
      "f24_id": "...",                    # ID del F24
      "estratto_conto_id": "...",         # ID del movimento EC
      "importo_ec": 9216.12,              # importo trovato in EC
      "data_valuta": "2025-02-17",        # data valuta EC
      "note": "..."                       # note facoltative
    }
    
    Logica:
    - Se importo_ec == saldo_finale F24 → stato 'riconciliato' ✅
    - Se importo_ec != saldo_finale F24 → stato 'discrepanza' ⚠️
    - Se F24 è 'scartato' → errore, non riconciliabile
    """
    fid = body.get("f24_id")
    importo_ec = body.get("importo_ec", 0)
    ec_id = body.get("estratto_conto_id")
    data_valuta = body.get("data_valuta")
    note = body.get("note", "")

    doc = await db["f24"].find_one({"_id": ObjectId(fid)})
    if not doc:
        raise HTTPException(404, "F24 non trovato")
    if doc.get("stato") == "scartato":
        raise HTTPException(400, "F24 scartato — non riconciliabile. Ripristinarlo prima se necessario.")

    saldo = doc.get("saldo_finale", 0)
    delta = round(abs(importo_ec - saldo), 2)
    
    if delta == 0:
        stato_ric = "riconciliato"
        esito = f"✅ Importo EC ({importo_ec}€) corrisponde al saldo F24 ({saldo}€)"
    elif delta <= 0.05:
        stato_ric = "riconciliato"  # tolleranza arrotondamenti
        esito = f"✅ Riconciliato con arrotondamento (delta {delta}€)"
    else:
        stato_ric = "discrepanza"
        esito = f"⚠️ Discrepanza: EC={importo_ec}€ vs F24={saldo}€ — delta={delta}€"

    await db["f24"].update_one(
        {"_id": ObjectId(fid)},
        {"$set": {
            "stato": stato_ric,
            "riconciliazione": {
                "estratto_conto_id": ec_id,
                "importo_ec": importo_ec,
                "data_valuta": data_valuta,
                "delta": delta,
                "esito": esito,
                "note": note,
                "riconciliato_il": datetime.utcnow(),
            },
            "updated_at": datetime.utcnow(),
        }}
    )
    return {
        "ok": True,
        "stato": stato_ric,
        "esito": esito,
        "delta": delta,
        "f24_id": fid,
        "ec_id": ec_id,
    }


# ═══════════════════════════════════════════════════════
# GET /alert-duplicati  — trova potenziali duplicati
# ═══════════════════════════════════════════════════════
@router.get("/alert-duplicati")
async def alert_duplicati(db: AsyncIOMotorDatabase = Depends(get_database)):
    """
    Trova F24 che condividono stesso codice tributo + anno_rif.
    Esclude i già scartati.
    Restituisce gruppi con le possibili interpretazioni:
      - DOPPIO_PAGAMENTO: stesso importo, stessa scadenza
      - RAVVEDIMENTO_INTEGRATIVO: stesso tributo, importo diverso, scadenza diversa
      - VERIFICA_BANCARIA: stesso importo ma scadenze diverse
    """
    pipeline = [
        {"$match": {"azienda_id": AZIENDA_ID, "stato": {"$ne": "scartato"}} if not includi_scartati else {"azienda_id": AZIENDA_ID}},
        {"$unwind": "$tributi_flat"},
        {"$group": {
            "_id": {
                "codice": "$tributi_flat.codice_tributo",
                "anno_rif": "$tributi_flat.anno_rif",
                "sezione": "$tributi_flat.sezione",
            },
            "f24_ids": {"$addToSet": "$_id"},
            "scadenze": {"$addToSet": "$scadenza"},
            "importi": {"$addToSet": "$saldo_finale"},
            "debiti": {"$addToSet": "$tributi_flat.debito"},
            "count": {"$sum": 1},
        }},
        {"$match": {"count": {"$gt": 1}}},
        {"$sort": {"_id.anno_rif": -1, "_id.codice": 1}},
    ]

    alerts = []
    async for doc in db["f24"].aggregate(pipeline):
        codice = doc["_id"]["codice"]
        anno = doc["_id"]["anno_rif"]
        sezione = doc["_id"]["sezione"]
        scadenze = sorted([s for s in doc["scadenze"] if s])
        importi = doc["importi"]
        debiti = doc["debiti"]

        # Classifica il tipo di anomalia
        importi_unici = list(set(round(x, 2) for x in importi if x))
        debiti_unici = list(set(round(x, 2) for x in debiti if x and x > 0))

        if len(importi_unici) == 1 and len(scadenze) <= 1:
            tipo = "DOPPIO_PAGAMENTO"
            desc = f"Stesso importo ({importi_unici[0]}€) e stessa scadenza — possibile doppio pagamento"
            urgenza = "alta"
        elif len(importi_unici) == 1 and len(scadenze) > 1:
            tipo = "VERIFICA_BANCARIA"
            desc = f"Stesso importo ({importi_unici[0]}€) su scadenze diverse — verificare addebito bancario"
            urgenza = "alta"
        elif len(debiti_unici) > 1:
            tipo = "RAVVEDIMENTO_INTEGRATIVO"
            desc = f"Importi diversi ({', '.join(str(x)+'€' for x in sorted(debiti_unici))}) — probabile integrazione/rettifica"
            urgenza = "bassa"
        else:
            tipo = "DA_VERIFICARE"
            desc = "Stesso codice tributo/anno presente in più F24"
            urgenza = "media"

        alerts.append({
            "codice_tributo": codice,
            "anno_rif": anno,
            "sezione": sezione,
            "tipo": tipo,
            "urgenza": urgenza,
            "descrizione": desc,
            "n_f24": doc["count"],
            "scadenze": scadenze,
            "importi_f24": importi_unici,
            "f24_ids": [str(x) for x in doc["f24_ids"]],
        })

    return {
        "totale_alert": len(alerts),
        "alta_urgenza": sum(1 for a in alerts if a["urgenza"] == "alta"),
        "alerts": alerts,
    }


# ═══════════════════════════════════════════════════════
# GET /{id}  — singolo F24
# ═══════════════════════════════════════════════════════
@router.get("/{fid}")
async def get_f24(fid: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    doc = await db["f24"].find_one({"_id": ObjectId(fid)})
    if not doc:
        raise HTTPException(404, "F24 non trovato")
    return _oid(doc)


# ═══════════════════════════════════════════════════════
# GET /{id}/pdf  — scarica PDF originale
# ═══════════════════════════════════════════════════════
@router.get("/{fid}/pdf")
async def download_f24_pdf(fid: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    doc = await db["f24"].find_one({"_id": ObjectId(fid)})
    if not doc:
        raise HTTPException(404, "F24 non trovato")
    path = doc.get("pdf_path", "")
    if not path or not os.path.exists(path):
        raise HTTPException(404, "PDF non disponibile")
    return FileResponse(path, media_type="application/pdf",
                        filename=f"F24_{doc.get('scadenza','')}.pdf")


# ═══════════════════════════════════════════════════════
# POST /{id}/segna-pagato  — marca pagato manualmente
# ═══════════════════════════════════════════════════════
@router.post("/{fid}/segna-pagato")
async def segna_pagato(fid: str, body: dict = {}, db: AsyncIOMotorDatabase = Depends(get_database)):
    upd = {"stato": "pagato", "updated_at": datetime.utcnow()}
    if body.get("data_pagamento"):
        upd["data_pagamento"] = body["data_pagamento"]
    res = await db["f24"].update_one({"_id": ObjectId(fid)}, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(404, "F24 non trovato")
    return {"ok": True}


# ═══════════════════════════════════════════════════════
# GET /ricerca-tributo  — per riconciliazione avvisi
# ═══════════════════════════════════════════════════════
@router.get("/ricerca-tributo")
async def ricerca_tributo(
    codice: str = Query(...),
    anno_rif: str = Query(None),
    mese_rif: str = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Cerca se un tributo è stato pagato.
    Ritorna tutti gli F24 che contengono quel codice tributo/anno/mese.
    Usato per rispondere a avvisi bonari, cartelle ADE/ADR.
    """
    q = {
        "azienda_id": AZIENDA_ID,
        "tributi_flat.codice_tributo": codice,
    }
    if anno_rif:
        q["tributi_flat.anno_rif"] = anno_rif
    if mese_rif:
        q["tributi_flat.mese_rif"] = mese_rif

    cursor = db["f24"].find(q).sort("scadenza", 1)
    risultati = []
    async for doc in cursor:
        # Filtra solo i righi rilevanti
        righi = [
            r for r in doc.get("tributi_flat", [])
            if r.get("codice_tributo") == codice
            and (not anno_rif or r.get("anno_rif") == anno_rif)
            and (not mese_rif or r.get("mese_rif") == mese_rif)
        ]
        risultati.append({
            "_id": str(doc["_id"]),
            "scadenza": doc.get("scadenza"),
            "data_pagamento": doc.get("data_pagamento"),
            "stato": doc.get("stato"),
            "pdf_path": doc.get("pdf_path"),
            "saldo_finale": doc.get("saldo_finale"),
            "banca": doc.get("banca"),
            "righi_trovati": righi,
        })

    return {
        "codice": codice,
        "anno_rif": anno_rif,
        "mese_rif": mese_rif,
        "trovati": len(risultati),
        "pagamenti": risultati,
        "esito": "PAGATO" if risultati else "NON TROVATO — verificare",
    }


# ═══════════════════════════════════════════════════════
# GET /riepilogo/{anno}  — totali annuali per sezione
# ═══════════════════════════════════════════════════════
@router.get("/riepilogo/{anno}")
async def riepilogo_annuale(anno: int, db: AsyncIOMotorDatabase = Depends(get_database)):
    pipeline = [
        {"$match": {
            "azienda_id": AZIENDA_ID,
            "scadenza": {"$regex": f"^{anno}"},
            "pagina": 1,
        }},
        {"$group": {
            "_id": None,
            "totale_versato": {"$sum": "$saldo_finale"},
            "n_f24": {"$sum": 1},
            "scadenze": {"$push": {
                "scadenza": "$scadenza",
                "data_pagamento": "$data_pagamento",
                "saldo_finale": "$saldo_finale",
                "stato": "$stato",
                "_id": {"$toString": "$_id"},
            }},
        }},
    ]
    async for doc in db["f24"].aggregate(pipeline):
        doc.pop("_id", None)
        return doc
    return {"totale_versato": 0, "n_f24": 0, "scadenze": []}
