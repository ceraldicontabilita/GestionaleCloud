"""
Router Tributi Locali — Ceraldi ERP
PREFIX: /api/tributi

Gestisce avvisi di pagamento TARI/IMU/altri tributi comunali per:
  - Ceraldi Group SRL (collection "tributi_azienda")
  - Persone fisiche famiglia Ceraldi (collection "tributi_privati")

REGOLA CHIAVE: i documenti intestati a privati (Ceraldi Antonietta, Ceraldi Michele, ecc.)
vanno nella pagina privata — NON nella contabilità aziendale.
Il sistema determina automaticamente la destinazione dal CF, ma se ambiguo chiede.

Codici tributo appresi:
  3944 = TARI (Tassa Rifiuti Napoli, ente F839)
  TEFA = Tributo Provinciale Ambientale
  3847/3848 = IMU acconto/saldo

Struttura F24 TARI Napoli:
  Sezione: E L (Elementi Identificativi)
  Codice ente: F839 (Napoli) o B990 (altro comune già visto)
  Mese/rata: 01=Unica, 0103=R1/3, 0203=R2/3, 0303=R3/3

Endpoints:
  POST /api/tributi/upload-pdf      → import avviso PDF
  GET  /api/tributi/azienda         → tributi Ceraldi Group SRL
  GET  /api/tributi/privati         → tutti i tributi persone fisiche
  GET  /api/tributi/privati/{cf}    → tributi specifico CF
  GET  /api/tributi/scadenze        → tutte scadenze ordinate per data
  POST /api/tributi/{id}/paga       → segna rata come pagata (print F24)
  GET  /api/tributi/{id}/f24-pdf    → scarica F24 pre-compilato per stampa
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from datetime import datetime, date
import os, re

from app.database import get_database

router = APIRouter(prefix="/api/tributi", tags=["Tributi Locali"])

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "tributi")
os.makedirs(UPLOAD_DIR, exist_ok=True)

CF_AZIENDA = "04523831214"

CF_PRIVATI_NOTI = {cf: v["nome"] for cf, v in PRIVATI_CF.items()}


def _oid(doc):
    if "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


def _collezione_da_cf(cf: str) -> str:
    if cf == CF_AZIENDA:
        return "tributi_azienda"
    return "tributi_privati"


@router.post("/upload-pdf")
async def upload_avviso_tributo(
    files: list[UploadFile] = File(...),
    forza_privato: bool = False,
    forza_azienda: bool = False,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Upload avviso di pagamento TARI/IMU PDF.
    Il sistema determina automaticamente la collection dal CF nel documento.
    Se il CF non è riconosciuto, viene restituita una risposta con richiesta di conferma.
    """
    from app.parsers.tari_parser import parse_avviso_tari_pdf

    risultati = []
    for upload in files:
        pdf_bytes = await upload.read()
        filename = upload.filename or "avviso.pdf"

        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        dest = os.path.join(UPLOAD_DIR, f"{ts}_{re.sub(r'[^a-zA-Z0-9_.]', '_', filename)}")
        with open(dest, "wb") as f:
            f.write(pdf_bytes)

        try:
            doc = parse_avviso_tari_pdf(pdf_bytes, filename)
        except Exception as e:
            risultati.append({"file": filename, "ok": False, "errore": str(e)})
            continue

        if not doc:
            risultati.append({"file": filename, "ok": False, "errore": "Non riconosciuto come avviso tributo locale"})
            continue

        doc["pdf_path"] = dest
        doc["created_at"] = datetime.utcnow()

        # Determina collection
        cf = doc.get("codice_fiscale", "")
        if forza_privato:
            collection = "tributi_privati"
        elif forza_azienda:
            collection = "tributi_azienda"
        else:
            collection = _collezione_da_cf(cf)

        # Se CF non noto e non forzato, chiedi conferma
        if cf not in (CF_AZIENDA,) and cf not in CF_PRIVATI_NOTI and not forza_privato and not forza_azienda:
            risultati.append({
                "file": filename,
                "ok": False,
                "richiesta_conferma": True,
                "cf": cf,
                "nome_rilevato": doc.get("intestatario", {}).get("nome", cf),
                "tipo_tributo": doc.get("tipo_tributo"),
                "totale": doc.get("totale_acconto"),
                "messaggio": f"CF {cf} non riconosciuto. Specificare se è privato (forza_privato=true) o aziendale (forza_azienda=true).",
            })
            continue

        doc["collection"] = collection

        # Upsert su protocollo + CF
        proto = doc.get("protocollo", "")
        query = {"codice_fiscale": cf}
        if proto:
            query["protocollo"] = proto

        existing = await db[collection].find_one(query)
        if existing:
            await db[collection].update_one({"_id": existing["_id"]}, {"$set": {**doc, "updated_at": datetime.utcnow()}})
            azione = "aggiornato"
            doc_id = str(existing["_id"])
        else:
            res = await db[collection].insert_one(doc)
            azione = "inserito"
            doc_id = str(res.inserted_id)

        risultati.append({
            "file": filename, "ok": True, "azione": azione, "id": doc_id,
            "collection": collection,
            "intestatario": doc.get("intestatario", {}).get("nome"),
            "tipo_tributo": doc.get("tipo_tributo"),
            "anno": doc.get("anno"),
            "totale_acconto": doc.get("totale_acconto"),
            "rate": len(doc.get("rate", [])),
            "nota": "⚠️ Documento privato — salvato in pagina privati" if collection == "tributi_privati" else "📁 Documento aziendale",
        })

    return {"risultati": risultati}


@router.get("/scadenze")
async def tutte_le_scadenze(
    include_privati: bool = True,
    include_azienda: bool = True,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Tutte le scadenze tributi locali ordinate per data."""
    scadenze = []
    oggi = date.today().isoformat()

    collections = []
    if include_azienda:
        collections.append("tributi_azienda")
    if include_privati:
        collections.append("tributi_privati")

    for coll in collections:
        cursor = db[coll].find({"stato": {"$ne": "annullato"}}).sort("anno", -1)
        async for doc in cursor:
            intestatario = doc.get("intestatario", {}).get("nome", doc.get("codice_fiscale", "?"))
            for rata in doc.get("rate", []):
                if rata.get("stato") == "pagata":
                    continue
                scad = rata.get("scadenza", "")
                scadenze.append({
                    "id_documento": str(doc["_id"]),
                    "collection": coll,
                    "intestatario": intestatario,
                    "tipo_tributo": doc.get("tipo_tributo"),
                    "anno": doc.get("anno"),
                    "rata": rata.get("numero"),
                    "importo": rata.get("importo_totale", 0),
                    "scadenza": scad,
                    "id_operazione": rata.get("id_operazione"),
                    "in_ritardo": scad < oggi if scad else False,
                    "privato": coll == "tributi_privati",
                })
            # Aggiungi anche scadenza saldo
            sc_saldo = doc.get("scadenza_saldo")
            if sc_saldo:
                scadenze.append({
                    "id_documento": str(doc["_id"]),
                    "collection": coll,
                    "intestatario": intestatario,
                    "tipo_tributo": f"{doc.get('tipo_tributo')} — saldo/conguaglio",
                    "anno": doc.get("anno"),
                    "rata": "SALDO",
                    "importo": None,
                    "scadenza": sc_saldo.replace("/", "-")[:10] if sc_saldo else None,
                    "in_ritardo": False,
                    "privato": coll == "tributi_privati",
                    "nota": "Importo da definire con avviso separato",
                })

    scadenze.sort(key=lambda x: x.get("scadenza") or "9999")
    return scadenze


@router.get("/azienda")
async def tributi_azienda(db: AsyncIOMotorDatabase = Depends(get_database)):
    cursor = db["tributi_azienda"].find().sort("anno", -1)
    return [_oid(doc) async for doc in cursor]


@router.get("/privati")
async def tributi_privati(db: AsyncIOMotorDatabase = Depends(get_database)):
    cursor = db["tributi_privati"].find().sort("anno", -1)
    return [_oid(doc) async for doc in cursor]


@router.get("/privati/{cf}")
async def tributi_privati_cf(cf: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    cursor = db["tributi_privati"].find({"codice_fiscale": cf}).sort("anno", -1)
    docs = [_oid(doc) async for doc in cursor]
    nome = CF_PRIVATI_NOTI.get(cf, f"CF {cf}")
    return {"cf": cf, "nome": nome, "totale_documenti": len(docs), "documenti": docs}


@router.post("/{doc_id}/paga-rata")
async def segna_rata_pagata(
    doc_id: str,
    rata_numero: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Segna una rata come pagata. Ritorna i dati per la stampa del F24."""
    # Cerca in entrambe le collection
    doc = None
    coll = None
    for c in ("tributi_azienda", "tributi_privati"):
        doc = await db[c].find_one({"_id": ObjectId(doc_id)})
        if doc:
            coll = c
            break
    if not doc:
        raise HTTPException(404, "Documento non trovato")

    rate = doc.get("rate", [])
    rata_target = None
    for r in rate:
        if r.get("numero") == rata_numero:
            r["stato"] = "pagata"
            r["data_pagamento"] = date.today().isoformat()
            rata_target = r
            break

    if not rata_target:
        raise HTTPException(404, f"Rata {rata_numero} non trovata")

    await db[coll].update_one(
        {"_id": ObjectId(doc_id)},
        {"$set": {"rate": rate, "updated_at": datetime.utcnow()}}
    )

    return {
        "ok": True,
        "rata": rata_target,
        "intestatario": doc.get("intestatario", {}),
        "tipo_tributo": doc.get("tipo_tributo"),
        "anno": doc.get("anno"),
        "collection": coll,
        "privato": coll == "tributi_privati",
        "id_operazione": rata_target.get("id_operazione"),
        "nota_stampa": "F24 Semplificato pre-compilato — Sezione EL, codice ente F839",
        "dati_f24": {
            "sezione": "E L",
            "codice_tributo_tari": "3944",
            "codice_tributo_tefa": "TEFA",
            "codice_ente": "F839",
            "anno": doc.get("anno"),
            "importo_tari": rata_target.get("importo_tari"),
            "importo_tefa": rata_target.get("importo_tefa"),
            "saldo_finale": rata_target.get("importo_totale"),
        }
    }
