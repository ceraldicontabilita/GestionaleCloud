"""
Router Contabilità / Gestione Pagamenti — Ceraldi Group
========================================================
Porta dentro AppDipendenti la "centrale pagamenti" (fatture passive,
fornitori, documenti fiscali da PEC, scadenze "da pagare") recuperata
dall'app esterna https://ceraldi-gestione.onrender.com.

FASE 1 = sola lettura + import dello snapshot recuperato.

Collezioni (allineate agli handler event-bus già presenti):
- ``invoices``         → fatture passive
- ``fornitori``        → anagrafica fornitori (IBAN / metodo pagamento)
- ``documents_inbox``  → documenti ricevuti via PEC/email (Agenzia Riscossione,
                          INPS, INAIL, TARI, PagoPA, commercialista…)

I dati arrivano dal seed ``backend/app/data/contabilita_seed.json``,
caricato una tantum con POST ``/api/contabilita/importa-snapshot``.
"""
import os
import json
import logging
import unicodedata
import re as _re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

import httpx
from fastapi import APIRouter, HTTPException, Query, Body, UploadFile, File

from app.hr.database import Database

router = APIRouter()
logger = logging.getLogger(__name__)


def _norm(s: Optional[str]) -> str:
    s = (s or "").strip()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return _re.sub(r"\s+", " ", s).upper()


def _forn_id(nome: str) -> str:
    return "FORN_" + _norm(nome).replace(" ", "_")[:60]


def _match_key(s: Optional[str]) -> str:
    """Chiave robusta per collegare fatture e fornitori: solo alfanumerici
    maiuscoli (ignora punti/spazi/accenti, es. 'S.p.A.' == 'S P A' == 'SPA')."""
    s = (s or "")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return _re.sub(r"[^A-Z0-9]", "", s.upper())


def mese_competenza(data_iso: Optional[str], soglia_giorno: int = 5) -> Optional[str]:
    """Mese di competenza di un bonifico: se emesso nei primi giorni del mese
    (giorno <= soglia) si riferisce alla paga del mese PRECEDENTE.
    Ritorna 'YYYY-MM' oppure None."""
    if not data_iso or len(data_iso) < 10:
        return None
    try:
        anno, mese, giorno = int(data_iso[:4]), int(data_iso[5:7]), int(data_iso[8:10])
    except (ValueError, IndexError):
        return None
    if giorno <= soglia_giorno:
        mese -= 1
        if mese == 0:
            mese = 12
            anno -= 1
    return f"{anno:04d}-{mese:02d}"


async def _emit(event_type: str, payload: dict, db, source: str = "contabilita"):
    """Propaga un evento all'event-bus (handler partite/alert/audit già registrati)."""
    try:
        from app.hr.services.event_bus import propagate_event
        await propagate_event(event_type, payload, db, source_module=source)
    except Exception as e:  # non bloccare l'operazione utente
        logger.warning("Event-bus non disponibile (%s): %s", event_type, e)


async def _upsert_fornitore_da_fattura(f: dict, db):
    """Crea/aggiorna il fornitore a partire dai dati di una fattura."""
    nome = f.get("fornitore") or f.get("fornitore_ragione_sociale")
    if not nome:
        return None
    fid = _forn_id(nome)
    esiste = await db["fornitori"].find_one({"_id": fid})
    base = {
        "_id": fid, "nome": nome, "forn_norm": _norm(nome), "match_key": _match_key(nome),
        "piva": f.get("piva") or (esiste or {}).get("piva", ""),
    }
    if f.get("iban") and not (esiste or {}).get("iban"):
        base["iban"] = f["iban"]
    await db["fornitori"].update_one({"_id": fid}, {"$set": base}, upsert=True)
    if not esiste:
        await _emit("fornitore.created", {"fornitore_id": fid, "ragione_sociale": nome}, db)
    return fid

SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "contabilita_seed.json"

# Documenti considerati "da pagare/regolarizzare" quando ad alta priorità.
TIPI_DOCUMENTO = [
    "PAGHE_F24", "COMMERCIALISTA", "AGENZIA_RISCOSSIONE", "INPS",
    "INAIL", "TARI", "PAGOPA_NAPOLI", "RICEVUTA_PAGOPA",
]


# ============================================================
# IMPORT SNAPSHOT (admin) — idempotente
# ============================================================
@router.post("/importa-snapshot")
async def importa_snapshot(svuota: bool = Query(False, description="Svuota le collezioni prima di importare")):
    """Carica il seed recuperato nelle collezioni invoices/fornitori/documents_inbox.

    Idempotente: upsert per ``_id`` (id originale). Non duplica righe già presenti.
    """
    db = Database.get_db()
    if not SEED_PATH.exists():
        raise HTTPException(status_code=404, detail=f"Seed non trovato: {SEED_PATH}")

    try:
        seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Seed non leggibile: {e}")

    risultati = {}
    for coll_name in ("invoices", "fornitori", "documents_inbox", "bonifici"):
        records = seed.get(coll_name, [])
        coll = db[coll_name]
        if svuota:
            await coll.delete_many({"fonte": "snapshot_gestione"})
        nuovi = aggiornati = 0
        for r in records:
            _id = r.get("_id") or r.get("id")
            if not _id:
                continue
            res = await coll.update_one({"_id": _id}, {"$set": r}, upsert=True)
            if res.upserted_id is not None:
                nuovi += 1
            elif res.modified_count:
                aggiornati += 1
        risultati[coll_name] = {"totale": len(records), "nuovi": nuovi, "aggiornati": aggiornati}

    logger.info("Import snapshot contabilità: %s", risultati)
    return {"ok": True, "risultati": risultati, "meta": seed.get("_meta", {})}


# ============================================================
# DASHBOARD
# ============================================================
@router.get("/dashboard")
async def dashboard():
    db = Database.get_db()
    inv = db["invoices"]
    forn = db["fornitori"]
    docs = db["documents_inbox"]

    tot_fatture = await inv.count_documents({})
    fatture_da_pagare = await inv.count_documents({"stato_pagamento": "da_pagare"})
    fatture_pagate = await inv.count_documents({"stato_pagamento": "pagato"})

    # Importo totale da pagare
    importo_da_pagare = 0.0
    async for d in inv.find({"stato_pagamento": "da_pagare"}, {"importo_totale": 1}):
        importo_da_pagare += float(d.get("importo_totale") or 0)

    tot_fornitori = await forn.count_documents({})
    tot_documenti = await docs.count_documents({})
    documenti_da_pagare = await docs.count_documents({"da_pagare": True})

    # Documenti urgenti per tipo
    per_tipo = {}
    async for d in docs.find({"da_pagare": True}, {"tipo": 1}):
        t = d.get("tipo") or "ALTRO"
        per_tipo[t] = per_tipo.get(t, 0) + 1

    return {
        "fatture": {
            "totale": tot_fatture,
            "da_pagare": fatture_da_pagare,
            "pagate": fatture_pagate,
            "importo_da_pagare": round(importo_da_pagare, 2),
        },
        "fornitori": {"totale": tot_fornitori},
        "documenti": {
            "totale": tot_documenti,
            "da_pagare": documenti_da_pagare,
            "per_tipo": per_tipo,
        },
    }


# ============================================================
# FATTURE
# ============================================================
@router.get("/fatture")
async def lista_fatture(
    anno: Optional[int] = None,
    stato: Optional[str] = Query(None, description="da_pagare | pagato"),
    fornitore: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(200, le=2000),
    skip: int = 0,
):
    db = Database.get_db()
    q = {}
    if anno:
        q["anno"] = anno
    if stato in ("da_pagare", "pagato"):
        q["stato_pagamento"] = stato
    if fornitore:
        q["forn_norm"] = {"$regex": fornitore.upper(), "$options": "i"}
    if search:
        rx = {"$regex": search, "$options": "i"}
        q["$or"] = [{"fornitore": rx}, {"numero": rx}, {"piva": rx}]

    coll = db["invoices"]
    totale = await coll.count_documents(q)
    cursor = coll.find(q, {"fonte": 0}).sort("data", -1).skip(skip).limit(limit)
    items = await cursor.to_list(length=limit)
    for it in items:
        it.pop("_id", None)
    return {"totale": totale, "items": items}


# ============================================================
# FORNITORI
# ============================================================
@router.get("/fornitori")
async def lista_fornitori(search: Optional[str] = None):
    db = Database.get_db()
    q = {}
    if search:
        q["forn_norm"] = {"$regex": search.upper(), "$options": "i"}
    cursor = db["fornitori"].find(q).sort("nome", 1)
    items = await cursor.to_list(length=1000)
    return {"totale": len(items), "items": items}


@router.get("/fornitori/{forn_id}")
async def dettaglio_fornitore(forn_id: str):
    db = Database.get_db()
    f = await db["fornitori"].find_one({"_id": forn_id})
    if not f:
        raise HTTPException(status_code=404, detail="Fornitore non trovato")
    # Fatture collegate: per P.IVA (esatta) o match_key (nome super-normalizzato).
    mkey = f.get("match_key") or _match_key(f.get("nome"))
    ors = []
    if f.get("piva"):
        ors.append({"piva": f["piva"]})
    if mkey:
        ors.append({"match_key": mkey})
        ors.append({"forn_norm": f.get("forn_norm")})
    fatture = []
    if ors:
        fatture = await db["invoices"].find({"$or": ors}, {"fonte": 0}).sort("data", -1).to_list(length=2000)
    # Bonifici collegati (per match_key sul beneficiario o per fattura_id)
    fids = [x["_id"] for x in fatture]
    bon_ors = [{"fattura_id": {"$in": fids}}] if fids else []
    if mkey:
        bon_ors.append({"benef_norm": f.get("forn_norm")})
    bonifici = []
    if bon_ors:
        bonifici = await db["bonifici"].find({"$or": bon_ors}).sort("data", -1).to_list(length=2000)
    return {"fornitore": f, "fatture": fatture, "bonifici": bonifici}


# ============================================================
# DOCUMENTI FISCALI (PEC / email)
# ============================================================
@router.get("/documenti")
async def lista_documenti(
    tipo: Optional[str] = None,
    priorita: Optional[str] = None,
    da_pagare: Optional[bool] = None,
    search: Optional[str] = None,
    limit: int = Query(300, le=2000),
):
    db = Database.get_db()
    q = {}
    if tipo:
        q["tipo"] = tipo
    if priorita:
        q["priorita"] = priorita
    if da_pagare is not None:
        q["da_pagare"] = da_pagare
    if search:
        rx = {"$regex": search, "$options": "i"}
        q["$or"] = [{"oggetto": rx}, {"mittente": rx}]
    cursor = db["documents_inbox"].find(q).sort("data", -1).limit(limit)
    items = await cursor.to_list(length=limit)
    return {"totale": len(items), "items": items}


# ============================================================
# DA PAGARE — documenti urgenti raggruppati per tipo
# ============================================================
@router.get("/da-pagare")
async def da_pagare(search: Optional[str] = None):
    db = Database.get_db()
    q = {"da_pagare": True}
    if search:
        rx = {"$regex": search, "$options": "i"}
        q["$or"] = [{"oggetto": rx}, {"mittente": rx}]
    docs = await db["documents_inbox"].find(q).sort("data", -1).to_list(length=2000)
    gruppi: dict = {}
    for d in docs:
        gruppi.setdefault(d.get("tipo") or "ALTRO", []).append(d)

    fatture_da_pagare = await db["invoices"].count_documents({"stato_pagamento": "da_pagare"})
    return {
        "totale_documenti": len(docs),
        "gruppi": gruppi,
        "fatture_da_pagare": fatture_da_pagare,
    }


# ============================================================
# IMPORT XML FATTURA ELETTRONICA (scrittura)
# ============================================================
@router.post("/fatture/importa-xml")
async def importa_fatture_xml(files: List[UploadFile] = File(...)):
    """Importa una o più fatture elettroniche (.xml/.p7m/.zip)."""
    from app.hr.services.fattura_xml_parser import parse_upload
    from app.hr.services.event_bus import EventTypes

    db = Database.get_db()
    nuove = duplicate = errori = ignorati = 0
    dettagli = []
    for up in files:
        try:
            raw = await up.read()
            fatture = parse_upload(raw, up.filename or "")
            if not fatture:
                # metadati SDI / daticert / file non-fattura: si ignorano
                ignorati += 1
                continue
            for f in fatture:
                if await db["invoices"].find_one({"_id": f["_id"]}):
                    duplicate += 1
                    continue
                fornitore_id = await _upsert_fornitore_da_fattura(f, db)
                f["fornitore_id"] = fornitore_id
                f["match_key"] = _match_key(f.get("fornitore"))
                await db["invoices"].insert_one(f)
                nuove += 1
                await _emit(EventTypes.FATTURA_CREATED, {
                    "fattura_id": f["_id"],
                    "tipo_documento": f.get("tipo_documento", "TD01"),
                    "importo_totale": f.get("importo_totale", 0),
                    "fornitore_id": fornitore_id,
                    "fornitore_ragione_sociale": f.get("fornitore", ""),
                    "data_documento": f.get("data_documento", ""),
                    "data_scadenza": f.get("data_scadenza") or None,
                }, db)
        except Exception as e:
            errori += 1
            dettagli.append({"file": up.filename, "errore": str(e)})
            logger.warning("Import XML fallito (%s): %s", up.filename, e)

    return {"ok": True, "nuove": nuove, "duplicate": duplicate,
            "errori": errori, "ignorati": ignorati, "dettagli": dettagli}


# ============================================================
# STATO PAGAMENTO FATTURA + riconciliazione bonifico (scrittura)
# ============================================================
@router.post("/fatture/{fattura_id}/paga")
async def paga_fattura(fattura_id: str, payload: dict = Body(default={})):
    from app.hr.services.event_bus import EventTypes
    db = Database.get_db()
    f = await db["invoices"].find_one({"_id": fattura_id})
    if not f:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    bonifico_id = (payload or {}).get("bonifico_id")
    upd = {
        "stato_pagamento": "pagato",
        "data_pagamento": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }
    if bonifico_id:
        upd["bonifico_id"] = bonifico_id
        await db["bonifici"].update_one({"_id": bonifico_id}, {"$set": {"fattura_id": fattura_id}})
        await db["riconciliazioni_match"].update_one(
            {"bonifico_id": bonifico_id, "fattura_id": fattura_id},
            {"$set": {"bonifico_id": bonifico_id, "fattura_id": fattura_id,
                      "tipo": "fattura", "confermato": True,
                      "ts": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )
    await db["invoices"].update_one({"_id": fattura_id}, {"$set": upd})
    await _emit(EventTypes.FATTURA_PAGATA, {
        "fattura_id": fattura_id,
        "fornitore_id": f.get("fornitore_id"),
        "importo_totale": f.get("importo_totale", 0),
        "bonifico_id": bonifico_id,
    }, db)
    return {"ok": True, "stato_pagamento": "pagato"}


@router.post("/fatture/{fattura_id}/riapri")
async def riapri_fattura(fattura_id: str):
    db = Database.get_db()
    res = await db["invoices"].update_one(
        {"_id": fattura_id},
        {"$set": {"stato_pagamento": "da_pagare"}, "$unset": {"data_pagamento": "", "bonifico_id": ""}},
    )
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    return {"ok": True, "stato_pagamento": "da_pagare"}


# ============================================================
# FORNITORE: aggiorna IBAN / metodo pagamento (scrittura)
# ============================================================
@router.put("/fornitori/{forn_id}")
async def aggiorna_fornitore(forn_id: str, payload: dict = Body(...)):
    from app.hr.services.event_bus import EventTypes
    db = Database.get_db()
    f = await db["fornitori"].find_one({"_id": forn_id})
    if not f:
        raise HTTPException(status_code=404, detail="Fornitore non trovato")
    upd = {}
    for campo in ("iban", "metodo_pagamento", "piva"):
        if campo in payload:
            upd[campo] = payload[campo]
    if not upd:
        return {"ok": True, "modificato": False}
    await db["fornitori"].update_one({"_id": forn_id}, {"$set": upd})
    await _emit(EventTypes.FORNITORE_UPDATED, {"fornitore_id": forn_id, **upd}, db)
    return {"ok": True, "modificato": True}


# ============================================================
# BONIFICI (movimenti banca in uscita)
# ============================================================
@router.get("/bonifici")
async def lista_bonifici(
    categoria: Optional[str] = None,
    search: Optional[str] = None,
    non_assegnati: Optional[bool] = None,
    limit: int = Query(300, le=2000),
):
    db = Database.get_db()
    q = {}
    if categoria:
        q["categoria"] = categoria
    if non_assegnati:
        q["$or"] = [{"fattura_id": None}, {"fattura_id": {"$exists": False}}]
    if search:
        rx = {"$regex": search, "$options": "i"}
        q.setdefault("$and", []).append({"$or": [{"beneficiario": rx}, {"causale": rx}]})
    cursor = db["bonifici"].find(q).sort("data", -1).limit(limit)
    items = await cursor.to_list(length=limit)
    # Mese di competenza: bonifico nei primi giorni del mese = paga mese precedente
    for b in items:
        b["mese_competenza"] = mese_competenza(b.get("data"))
    return {"totale": len(items), "items": items}


@router.post("/bonifici/{bonifico_id}/assegna")
async def assegna_bonifico(bonifico_id: str, payload: dict = Body(...)):
    """Collega un bonifico a una fattura (o ne aggiorna la categoria)."""
    db = Database.get_db()
    b = await db["bonifici"].find_one({"_id": bonifico_id})
    if not b:
        raise HTTPException(status_code=404, detail="Bonifico non trovato")
    upd = {}
    if "categoria" in payload:
        upd["categoria"] = payload["categoria"]
    fattura_id = payload.get("fattura_id")
    if fattura_id:
        upd["fattura_id"] = fattura_id
        await paga_fattura(fattura_id, {"bonifico_id": bonifico_id})
    if upd:
        await db["bonifici"].update_one({"_id": bonifico_id}, {"$set": upd})
    return {"ok": True}


# ============================================================
# RICONCILIAZIONE — bonifici fornitore senza fattura + suggerimenti
# ============================================================
@router.get("/riconciliazione")
async def riconciliazione(limit: int = Query(100, le=500)):
    db = Database.get_db()
    da_verificare = await db["bonifici"].find({
        "categoria": "FORNITORE",
        "$or": [{"fattura_id": None}, {"fattura_id": {"$exists": False}}],
    }).sort("data", -1).limit(limit).to_list(length=limit)

    risultati = []
    for b in da_verificare:
        importo = float(b.get("importo") or 0)
        benef = _norm(b.get("beneficiario"))
        token = benef.split(" ")[0] if benef else ""
        # candidati: fattura da pagare con importo vicino o nome simile
        cand_q = {"stato_pagamento": "da_pagare"}
        candidati = await db["invoices"].find(cand_q, {"fonte": 0}).limit(500).to_list(length=500)
        suggeriti = []
        for c in candidati:
            tot = float(c.get("importo_totale") or 0)
            match_imp = abs(tot - importo) <= 0.5 and importo > 0
            match_nome = token and token in (c.get("forn_norm") or "")
            if match_imp or match_nome:
                suggeriti.append({
                    "fattura_id": c["_id"], "numero": c.get("numero"),
                    "fornitore": c.get("fornitore"), "totale": tot,
                    "motivo": "importo" if match_imp else "nome",
                })
        risultati.append({"bonifico": b, "suggerimenti": suggeriti[:5]})
    return {"totale": len(risultati), "items": risultati}


# ============================================================
# CALENDARIO scadenze (fatture + documenti da pagare)
# ============================================================
@router.get("/calendario")
async def calendario(mese: Optional[str] = Query(None, description="YYYY-MM")):
    db = Database.get_db()
    eventi = []
    inv_q = {"stato_pagamento": "da_pagare"}
    async for f in db["invoices"].find(inv_q, {"data_scadenza": 1, "data": 1, "fornitore": 1, "importo_totale": 1, "numero": 1}):
        giorno = f.get("data_scadenza") or f.get("data")
        if not giorno:
            continue
        if mese and not giorno.startswith(mese):
            continue
        eventi.append({
            "data": giorno, "tipo": "fattura",
            "titolo": f"{f.get('fornitore', '')} — fatt. {f.get('numero', '')}",
            "importo": f.get("importo_totale"), "ref_id": f["_id"],
        })
    async for d in db["documents_inbox"].find({"da_pagare": True}, {"data": 1, "oggetto": 1, "tipo": 1, "importo": 1}):
        giorno = d.get("data")
        if not giorno:
            continue
        if mese and not giorno.startswith(mese):
            continue
        eventi.append({
            "data": giorno, "tipo": "documento",
            "titolo": f"{(d.get('tipo') or '').replace('_', ' ')} — {d.get('oggetto', '')}",
            "importo": d.get("importo"), "ref_id": d["_id"],
        })
    eventi.sort(key=lambda e: e["data"])
    return {"totale": len(eventi), "eventi": eventi}


# ============================================================
# PAYPAL — transazioni (richiede credenziali in env Render)
# ============================================================
@router.get("/paypal/status")
async def paypal_status():
    configured = bool(os.environ.get("PAYPAL_CLIENT_ID") and os.environ.get("PAYPAL_CLIENT_SECRET"))
    return {"configurato": configured, "ambiente": os.environ.get("PAYPAL_ENV", "live")}


@router.get("/paypal/transactions")
async def paypal_transactions(start_date: str, end_date: str):
    """Elenca le transazioni PayPal nel periodo (Transaction Search API)."""
    cid = os.environ.get("PAYPAL_CLIENT_ID")
    secret = os.environ.get("PAYPAL_CLIENT_SECRET")
    if not (cid and secret):
        raise HTTPException(status_code=400, detail="PayPal non configurato (PAYPAL_CLIENT_ID/SECRET nelle env di Render)")
    base = "https://api-m.paypal.com" if os.environ.get("PAYPAL_ENV", "live") == "live" else "https://api-m.sandbox.paypal.com"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            tok = await client.post(f"{base}/v1/oauth2/token", auth=(cid, secret),
                                    data={"grant_type": "client_credentials"})
            tok.raise_for_status()
            access = tok.json()["access_token"]
            r = await client.get(
                f"{base}/v1/reporting/transactions",
                headers={"Authorization": f"Bearer {access}"},
                params={"start_date": f"{start_date}T00:00:00-0000",
                        "end_date": f"{end_date}T23:59:59-0000", "fields": "all", "page_size": 100},
            )
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Errore PayPal: {e}")

    tx = []
    for t in data.get("transaction_details", []):
        info = t.get("transaction_info", {})
        payer = t.get("payer_info", {})
        amt = info.get("transaction_amount", {})
        tx.append({
            "id": info.get("transaction_id"),
            "data": info.get("transaction_initiation_date", "")[:10],
            "importo": amt.get("value"), "valuta": amt.get("currency_code"),
            "stato": info.get("transaction_status"),
            "controparte": payer.get("payer_name", {}).get("alternate_full_name") or payer.get("email_address", ""),
            "nota": info.get("transaction_note", ""),
        })
    return {"totale": len(tx), "transazioni": tx}
