"""
Router Fornitori — Ceraldi ERP
PREFIX: /api/fornitori

Scheda fornitore modulare con 5 tab:
  Tab 1: Anagrafica (auto da XML fatture)
  Tab 2: Schede tecniche & scraping (URL + PDF)
  Tab 3: Lista prodotti (aggregata da XML)
  Tab 4: Listino prezzi / storico (da XML)
  Tab 5: Metodo di pagamento (manuale)

REGOLA: collection si chiama "fornitori".
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, Query
from fastapi.responses import FileResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from datetime import datetime
import os, re

from app.database import get_database
from app.parsers.fornitore_xml_parser import parse_fornitore_da_xml, aggiorna_fornitore_da_fatture
from app.parsers.fornitore_scraper import scrapa_scheda_prodotto, scrapa_con_claude_fallback

router = APIRouter(prefix="/api/fornitori", tags=["Fornitori"])

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "fornitori")
os.makedirs(UPLOAD_DIR, exist_ok=True)

AZIENDA_ID = "b0295759-35ce-4b34-a6b4-f01b883234ad"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

METODI_PAGAMENTO = {"cassa", "banca", "carta", "assegno"}


def _oid(doc):
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


def _slug(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", s)[:40]


# ════════════════════════════════════════════════════════════
# CRUD base
# ════════════════════════════════════════════════════════════
@router.get("")
async def lista_fornitori(
    stato: str = "attivo",
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    q = {"azienda_id": AZIENDA_ID}
    if stato != "tutti":
        q["stato"] = stato
    cursor = db["fornitori"].find(q).sort("anagrafica.ragione_sociale", 1)
    return [_oid(doc) async for doc in cursor]


@router.get("/{fid}")
async def get_fornitore(fid: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    doc = await db["fornitori"].find_one({"_id": ObjectId(fid)})
    if not doc:
        raise HTTPException(404, "Fornitore non trovato")
    return _oid(doc)


@router.post("")
async def crea_fornitore(body: dict, db: AsyncIOMotorDatabase = Depends(get_database)):
    """Crea fornitore manualmente (di solito creato auto da XML)."""
    doc = {
        "azienda_id": AZIENDA_ID,
        "anagrafica": body.get("anagrafica", {}),
        "schede_tecniche": {"urls_scraping": [], "pdf_tecnici": []},
        "prodotti": [],
        "storico_prezzi": [],
        "pagamento": {"metodo": "banca", "ereditato_automaticamente": True},
        "stato": "attivo",
        "note_interne": "",
        "tags": [],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    res = await db["fornitori"].insert_one(doc)
    return {"ok": True, "id": str(res.inserted_id)}


# ════════════════════════════════════════════════════════════
# TAB 1 — Anagrafica: import da XML fattura
# ════════════════════════════════════════════════════════════
@router.post("/import-xml")
async def import_da_xml(
    files: list[UploadFile] = File(...),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Importa una o più fatture XML SDI e aggiorna automaticamente:
      - Anagrafica fornitore (Tab 1)
      - Lista prodotti (Tab 3)
      - Storico prezzi (Tab 4)
    Se il fornitore non esiste viene creato automaticamente.
    """
    risultati = []
    for upload in files:
        xml_bytes = await upload.read()
        parsed = parse_fornitore_da_xml(xml_bytes)
        if not parsed:
            risultati.append({"file": upload.filename, "ok": False, "errore": "XML non valido"})
            continue

        piva = parsed["anagrafica"].get("piva") or parsed["anagrafica"].get("codice_fiscale")
        if not piva:
            risultati.append({"file": upload.filename, "ok": False, "errore": "P.IVA non trovata"})
            continue

        # Trova o crea il fornitore
        fornitore = await db["fornitori"].find_one({"azienda_id": AZIENDA_ID, "anagrafica.piva": piva})
        if not fornitore:
            fornitore = {
                "azienda_id": AZIENDA_ID,
                "anagrafica": parsed["anagrafica"],
                "schede_tecniche": {"urls_scraping": [], "pdf_tecnici": []},
                "prodotti": [],
                "storico_prezzi": [],
                "pagamento": {
                    "metodo": "banca",
                    "ereditato_automaticamente": True,
                    **parsed.get("pagamento_xml", {}),
                },
                "stato": "attivo",
                "note_interne": "",
                "tags": [],
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
            azione = "creato"
        else:
            # Aggiorna anagrafica (mantieni dati manuali)
            fornitore["anagrafica"].update(parsed["anagrafica"])
            azione = "aggiornato"

        # Aggiorna prodotti e storico prezzi
        fornitore = aggiorna_fornitore_da_fatture(fornitore, parsed)

        # Ereditarietà metodo pagamento su nuove fatture
        metodo = fornitore.get("pagamento", {}).get("metodo", "banca")

        if "_id" in fornitore:
            fid = fornitore.pop("_id")
            await db["fornitori"].replace_one({"_id": fid}, {**fornitore, "_id": fid})
            fid_str = str(fid)
        else:
            res = await db["fornitori"].insert_one(fornitore)
            fid_str = str(res.inserted_id)

        # Registra la fattura in fatture_passive con struttura standard (compatibile con fatture.py)
        numero_fatt = parsed["fattura"].get("numero", "")
        await db["fatture_passive"].update_one(
            {"numero": numero_fatt, "fornitore_piva": piva},
            {"$set": {
                "numero": numero_fatt,
                "fornitore_piva": piva,
                "fornitore_denominazione": parsed["anagrafica"].get("ragione_sociale", ""),
                "data": parsed["fattura"].get("data", ""),
                "anno": int(parsed["fattura"].get("data", "2000")[:4]) if parsed["fattura"].get("data") else 0,
                "importo_totale": parsed["fattura"].get("totale", 0),
                "metodo_pagamento": metodo,
                "updated_at": datetime.utcnow(),
            }},
            upsert=True
        )

        risultati.append({
            "file": upload.filename, "ok": True, "azione": azione,
            "fornitore_id": fid_str,
            "ragione_sociale": parsed["anagrafica"]["ragione_sociale"],
            "n_prodotti": len(parsed["prodotti_fattura"]),
            "totale_fattura": parsed["fattura"]["totale"],
        })

    return {"risultati": risultati}


# ════════════════════════════════════════════════════════════
# TAB 2 — Schede tecniche & Scraping
# ════════════════════════════════════════════════════════════
@router.post("/{fid}/scraping")
async def avvia_scraping(
    fid: str,
    body: dict,
    background_tasks: BackgroundTasks,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Avvia lo scraping di un URL per questo fornitore.
    body: { "url": "https://...", "label": "Passata 400g", "selettori": {} }
    """
    url = body.get("url", "").strip()
    if not url.startswith("http"):
        raise HTTPException(400, "URL non valido")

    fornitore = await db["fornitori"].find_one({"_id": ObjectId(fid)})
    if not fornitore:
        raise HTTPException(404, "Fornitore non trovato")

    # Aggiunge URL in stato "in_corso"
    entry = {
        "url": url,
        "label": body.get("label", url),
        "stato": "in_corso",
        "ultimo_scraping": datetime.utcnow(),
        "selettori": body.get("selettori", {}),
        "dati_estratti": {},
    }

    await db["fornitori"].update_one(
        {"_id": ObjectId(fid)},
        {"$push": {"schede_tecniche.urls_scraping": entry}}
    )

    # Esegui scraping in background
    background_tasks.add_task(
        _esegui_scraping_background, fid, url, body.get("selettori", {}), db
    )

    return {"ok": True, "messaggio": f"Scraping avviato per {url}"}


async def _esegui_scraping_background(
    fid: str, url: str, selettori: dict, db: AsyncIOMotorDatabase
):
    """Esegue lo scraping e aggiorna il documento fornitore."""
    try:
        risultato = await scrapa_scheda_prodotto(url, selettori)

        # Se mancano dati chiave, prova Claude API
        dati = risultato.get("dati_estratti", {})
        ha_dati = dati.get("prezzo_unitario") or dati.get("ingredienti")
        if not ha_dati and ANTHROPIC_API_KEY:
            async with __import__("httpx").AsyncClient(timeout=15) as client:
                try:
                    resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                    extra = await scrapa_con_claude_fallback(url, resp.text, ANTHROPIC_API_KEY)
                    dati.update({k: v for k, v in extra.items() if v and not dati.get(k)})
                    risultato["fonte_dati"] = "claude_fallback"
                except Exception:
                    pass

        await db["fornitori"].update_one(
            {"_id": ObjectId(fid), "schede_tecniche.urls_scraping.url": url},
            {"$set": {
                "schede_tecniche.urls_scraping.$.stato": risultato.get("stato", "ok"),
                "schede_tecniche.urls_scraping.$.dati_estratti": risultato.get("dati_estratti", {}),
                "schede_tecniche.urls_scraping.$.ultimo_scraping": datetime.utcnow(),
                "schede_tecniche.urls_scraping.$.fonte_dati": risultato.get("fonte_dati", "scraping"),
                "updated_at": datetime.utcnow(),
            }}
        )
    except Exception as exc:
        await db["fornitori"].update_one(
            {"_id": ObjectId(fid), "schede_tecniche.urls_scraping.url": url},
            {"$set": {"schede_tecniche.urls_scraping.$.stato": "errore",
                      "schede_tecniche.urls_scraping.$.errore": str(exc)}}
        )


@router.put("/{fid}/scraping/selettori")
async def aggiorna_selettori(
    fid: str,
    body: dict,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Salva/aggiorna i selettori CSS per un URL specifico.
    body: { "url": "...", "selettori": { "prezzo": ".price", ... } }
    Permette all'utente di correggere i selettori dopo il primo scraping.
    """
    url = body.get("url")
    selettori = body.get("selettori", {})
    await db["fornitori"].update_one(
        {"_id": ObjectId(fid), "schede_tecniche.urls_scraping.url": url},
        {"$set": {"schede_tecniche.urls_scraping.$.selettori": selettori}}
    )
    return {"ok": True}


@router.post("/{fid}/pdf")
async def upload_pdf_tecnico(
    fid: str,
    files: list[UploadFile] = File(...),
    tipo: str = Query("scheda_tecnica"),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Upload PDF tecnico (scheda tecnica, certificato, listino)."""
    fornitore = await db["fornitori"].find_one({"_id": ObjectId(fid)})
    if not fornitore:
        raise HTTPException(404)

    pdf_dir = os.path.join(UPLOAD_DIR, fid, "pdf")
    os.makedirs(pdf_dir, exist_ok=True)

    salvati = []
    for upload in files:
        pdf_bytes = await upload.read()
        dest = os.path.join(pdf_dir, _slug(upload.filename or "doc"))
        with open(dest, "wb") as f:
            f.write(pdf_bytes)

        entry = {
            "filename": upload.filename,
            "path": dest,
            "tipo": tipo,
            "caricato_il": datetime.utcnow(),
            "generato_da_scraping": False,
        }
        await db["fornitori"].update_one(
            {"_id": ObjectId(fid)},
            {"$push": {"schede_tecniche.pdf_tecnici": entry}}
        )
        salvati.append(upload.filename)

    return {"ok": True, "salvati": salvati}


@router.get("/{fid}/pdf/{filename}")
async def scarica_pdf(fid: str, filename: str,
                      db: AsyncIOMotorDatabase = Depends(get_database)):
    path = os.path.join(UPLOAD_DIR, fid, "pdf", _slug(filename))
    if not os.path.exists(path):
        raise HTTPException(404)
    return FileResponse(path, media_type="application/pdf", filename=filename)


# ════════════════════════════════════════════════════════════
# TAB 3 — Lista prodotti
# ════════════════════════════════════════════════════════════
@router.get("/{fid}/prodotti")
async def lista_prodotti(fid: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    doc = await db["fornitori"].find_one(
        {"_id": ObjectId(fid)}, {"prodotti": 1, "storico_prezzi": 1}
    )
    if not doc:
        raise HTTPException(404)
    prodotti = doc.get("prodotti", [])
    storico = {s["codice_articolo"] or s["descrizione"]: s
               for s in doc.get("storico_prezzi", [])}
    for p in prodotti:
        chiave = p.get("codice_articolo") or p.get("descrizione", "")
        if chiave in storico:
            p["prezzo_attuale"] = storico[chiave].get("prezzo_attuale")
            p["trend"] = storico[chiave].get("trend")
    return prodotti


# ════════════════════════════════════════════════════════════
# TAB 4 — Listino prezzi / storico
# ════════════════════════════════════════════════════════════
@router.get("/{fid}/listino")
async def listino_prezzi(
    fid: str,
    codice: str = None,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    doc = await db["fornitori"].find_one(
        {"_id": ObjectId(fid)}, {"storico_prezzi": 1}
    )
    if not doc:
        raise HTTPException(404)
    storico = doc.get("storico_prezzi", [])
    if codice:
        storico = [s for s in storico
                   if s.get("codice_articolo") == codice or codice in s.get("descrizione", "")]
    return storico


# ════════════════════════════════════════════════════════════
# TAB 5 — Metodo di pagamento
# ════════════════════════════════════════════════════════════
@router.put("/{fid}/pagamento")
async def aggiorna_pagamento(
    fid: str,
    body: dict,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Aggiorna il metodo di pagamento del fornitore.
    Da quel momento tutte le nuove fatture di questo fornitore
    ereditano automaticamente questa impostazione.
    body: { "metodo": "banca|cassa|carta|assegno", "conto_banca": "...", "iban_fornitore": "..." }
    """
    metodo = body.get("metodo", "banca").lower()
    if metodo not in METODI_PAGAMENTO:
        raise HTTPException(400, f"Metodo non valido. Opzioni: {METODI_PAGAMENTO}")

    pagamento = {
        "metodo": metodo,
        "conto_banca": body.get("conto_banca", ""),
        "iban_fornitore": body.get("iban_fornitore", ""),
        "termini_pagamento": body.get("termini_pagamento", ""),
        "note": body.get("note", ""),
        "ereditato_automaticamente": True,
        "aggiornato_il": datetime.utcnow(),
    }
    await db["fornitori"].update_one(
        {"_id": ObjectId(fid)},
        {"$set": {"pagamento": pagamento, "updated_at": datetime.utcnow()}}
    )

    # Propaga il metodo alle fatture future (aggiorna quelle non pagate)
    await db["fatture_passive"].update_many(
        {"fornitore_id": fid, "pagato": {"$ne": True}},
        {"$set": {"metodo_pagamento": metodo}}
    )

    return {"ok": True, "metodo": metodo}
