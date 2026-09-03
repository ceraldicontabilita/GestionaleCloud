"""
catalogo_forno.py — Cataloghi fornitori da forno (Il Pasticcere, Tre Marie, Bindi).
Collection DEDICATA 'catalogo_forno_prodotti', SEPARATA dalle giacenze: serve
SOLO per gli ordini futuri. Non tocca magazzino_bar_prodotti.
"""
import json
import logging
import os
import re
import httpx
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Body, Depends
from typing import List, Optional
from pydantic import BaseModel
from pymongo import UpdateOne
from app.lotti.db import database as db
from app.lotti.auth import require_admin

logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/catalogo-forno", tags=["catalogo_forno"])

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
# Cataloghi PDF caricati da Enzo (03/07/2026), trascritti prodotto per prodotto
# (nome/codice/grammi/pezzi per cartone — niente prezzo: qui non compare in
# questi cataloghi B2B, i prezzi restano SOLO da fatture reali per regola del
# progetto). Chiave fornitore -> nome file in backend/data/.
_CATALOGHI_PRECARICATI = {
    "pasticcere": "catalogo_forno_pasticcere_2026.json",
    "tremarie": "catalogo_forno_tremarie_2026.json",
    "bindi": "catalogo_forno_bindi_2022_2026.json",
}

# Come riconoscere le fatture di ciascun fornitore-catalogo (sottostringhe
# della ragione sociale in fattura, alternative separate da "|" — stesso
# formato di prezzi_fatture_per_fornitore già usato per Saima/MePA/Acquaviva).
# Tre Marie e Sammontana fatturano entrambe come "Sammontana Italia":
# la distinzione la fa il match sul NOME prodotto, non sul fornitore.
_FORNITORE_FATTURA_MATCH = {
    "pasticcere": "pasticcere",
    "tremarie": "tre marie|tremarie|sammontana",
    "sammontana": "sammontana",
    "bindi": "bindi",
}

_CATALOGHI_UFFICIALI = {
    "tremarie": {
        "api": "https://tremarie.sammontanaitalia.it/content/tremariecroissanterie-it/home/croissanterie/tutti-i-prodotti/_jcr_content.products.json",
        "base": "https://tremarie.sammontanaitalia.it",
        "fonte": "Catalogo ufficiale Tre Marie Croissanterie 2026",
    },
    "sammontana": {
        "api": "https://www.sammontana.it/content/sammontana-it/home/tutti-i-gelati/tutti-prodotti/_jcr_content.products.json",
        "base": "https://www.sammontana.it",
        "fonte": "Catalogo ufficiale Sammontana 2026",
    },
}


def _url_assoluto(base: str, value: str) -> str:
    value = str(value or "").strip()
    if not value:
        return ""
    return value if value.startswith("http") else f"{base.rstrip('/')}/{value.lstrip('/')}"


def _categoria_da_link(link: str) -> str:
    match = re.search(r"/tutti-i-prodotti/([^/]+)", str(link or ""))
    if not match:
        return "Catalogo"
    return match.group(1).replace("-", " ").replace("_", " ").title()


async def sincronizza_catalogo_ufficiale(fornitore: str) -> dict:
    """Scarica foto e descrizioni dal catalogo ufficiale e le persiste nel DB."""
    config = _CATALOGHI_UFFICIALI.get(fornitore)
    if not config:
        raise HTTPException(400, "Catalogo ufficiale non supportato")
    try:
        async with httpx.AsyncClient(timeout=40, follow_redirects=True) as client:
            response = await client.get(config["api"], headers={"User-Agent": "CeraldiApp/1.0"})
            response.raise_for_status()
            items = response.json().get("items") or []
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Catalogo ufficiale %s non raggiungibile: %s", fornitore, exc)
        raise HTTPException(502, "Catalogo ufficiale temporaneamente non raggiungibile") from exc
    now = datetime.now(timezone.utc).isoformat()
    records = {}
    for item in items:
        code = str(item.get("id") or "").strip()
        name = str(item.get("title") or "").strip()
        if not code or not name:
            continue
        renditions = item.get("renditions") or {}
        image = renditions.get("product-card-md") or renditions.get("product-detail-md") or renditions.get("product-detail-lg") or ""
        image = _url_assoluto(config["base"], image)
        link = _url_assoluto(config["base"], item.get("link"))
        records[code] = {
            "nome": name,
            "nome_completo": name,
            "descrizione": str(item.get("description") or "").strip(),
            "immagine_url": image,
            "link_prodotto": link,
            "fornitore": fornitore,
            "categoria_ufficiale": _categoria_da_link(link),
            "tempo_cottura": item.get("tempo") or "",
            "temperatura_cottura": item.get("temperatura") or "",
            "fonte_ufficiale": config["fonte"],
            "sincronizzato_il": now,
        }
    ops = []
    for code, source_fields in records.items():
        link = source_fields["link_prodotto"]
        ops.append(UpdateOne(
            {"fornitore": fornitore, "codice_articolo": code},
            {
                "$set": source_fields,
                "$setOnInsert": {
                    "codice_articolo": code,
                    "categoria": _categoria_da_link(link),
                    "grammi": "",
                    "pezzi_cartone": "",
                    "prezzo": 0.0,
                },
            },
            upsert=True,
        ))
    if ops:
        await db.catalogo_forno_prodotti.bulk_write(ops, ordered=False)
    con_foto = sum(bool(record.get("immagine_url")) for record in records.values())
    return {"ok": True, "fornitore": fornitore, "prodotti": len(ops), "con_foto": con_foto, "fonte": config["fonte"]}


def descrizione_catalogo_precaricato(prodotto: dict) -> str:
    """Descrizione sintetica composta solo dai dati presenti nel PDF fonte."""
    parti = []
    categoria = str(prodotto.get("categoria") or "").strip()
    grammi = str(prodotto.get("grammi") or "").strip()
    pezzi = str(prodotto.get("pezzi_cartone") or "").strip()
    if categoria:
        parti.append(f"Linea: {categoria}")
    if grammi:
        parti.append(f"Peso unitario: {grammi}")
    if pezzi:
        parti.append(f"Confezione: {pezzi}")
    return " \u00b7 ".join(parti)


async def importa_catalogo_precaricato(fornitore: str) -> dict:
    """Upsert idempotente di un catalogo incluso nel repository.

    E' usato sia dall'endpoint amministrativo sia all'avvio, quando una nuova
    base dati e' ancora vuota. I prezzi manuali o da fattura gia presenti non
    vengono cancellati, perche' ``$set`` aggiorna soltanto i campi del file.
    """
    filename = _CATALOGHI_PRECARICATI.get(fornitore)
    if not filename:
        raise HTTPException(400, f"Nessun catalogo precaricato per '{fornitore}'")
    path = os.path.join(_DATA_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(404, f"File catalogo mancante: {filename}")
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    operazioni = []
    for raw in payload.get("prodotti", []):
        p = ProdottoCatalogo(**raw)
        prodotto = p.model_dump()
        if not str(prodotto.get("descrizione") or "").strip():
            prodotto["descrizione"] = descrizione_catalogo_precaricato(prodotto)
        prodotto["arricchimento_fonte"] = payload.get("_fonte", "")
        operazioni.append(UpdateOne(
            {"fornitore": p.fornitore, "codice_articolo": p.codice_articolo},
            {"$set": prodotto},
            upsert=True,
        ))
    if operazioni:
        await db.catalogo_forno_prodotti.bulk_write(operazioni, ordered=False)
    return {"ok": True, "importati": len(operazioni), "fonte": payload.get("_fonte", "")}


async def inizializza_cataloghi_precaricati() -> dict:
    """Popola automaticamente solo i cataloghi ancora assenti.

    Rende i cataloghi disponibili dopo un ripristino o una nuova installazione,
    senza richiedere all'operatore di premere un pulsante e senza duplicati.
    """
    risultati = {}
    for fornitore, filename in _CATALOGHI_PRECARICATI.items():
        presenti = await db.catalogo_forno_prodotti.count_documents({"fornitore": fornitore})
        path = os.path.join(_DATA_DIR, filename)
        with open(path, "r", encoding="utf-8") as f:
            attesi = len(json.load(f).get("prodotti", []))
        mancanti_descrizione = await db.catalogo_forno_prodotti.count_documents({
            "fornitore": fornitore,
            "$or": [
                {"descrizione": ""},
                {"descrizione": {"$exists": False}},
            ],
        })
        if presenti >= attesi and not mancanti_descrizione:
            risultati[fornitore] = {"gia_presenti": presenti}
            continue
        risultati[fornitore] = await importa_catalogo_precaricato(fornitore)
    return risultati


class ProdottoCatalogo(BaseModel):
    codice_articolo: str
    nome: str
    nome_completo: Optional[str] = ""
    categoria: Optional[str] = ""
    grammi: Optional[str] = ""
    pezzi_cartone: Optional[str] = ""
    fornitore: str
    # Valorizzati anche dal connettore "incolla il link" (fonti_catalogo.py),
    # che scarica dati reali dai siti fornitore (JSON-LD/Open Graph) — il
    # vecchio import manuale da PDF non li aveva, restano opzionali qui.
    immagine_url: Optional[str] = ""
    prezzo: Optional[float] = 0.0
    descrizione: Optional[str] = ""
    link_prodotto: Optional[str] = ""


class ImportReq(BaseModel):
    prodotti: List[ProdottoCatalogo]


@router.post("/importa")
async def importa_catalogo(payload: ImportReq = Body(...), _admin=Depends(require_admin)):
    """Importa/aggiorna i prodotti catalogo. Chiave: (fornitore, codice_articolo).
    Upsert: ri-importare aggiorna senza duplicare."""
    n = 0
    for p in payload.prodotti:
        await db.catalogo_forno_prodotti.update_one(
            {"fornitore": p.fornitore, "codice_articolo": p.codice_articolo},
            {"$set": p.model_dump()},
            upsert=True,
        )
        n += 1
    return {"ok": True, "importati": n}


@router.post("/importa-precaricato")
async def importa_precaricato(fornitore: str, _admin=Depends(require_admin)):
    """Importa un catalogo già trascritto da un PDF caricato da Enzo
    (backend/data/catalogo_forno_*.json) — stesso upsert di /importa, solo
    con i dati bundlati nel repo invece che inviati dal client."""
    return await importa_catalogo_precaricato(fornitore)


@router.post("/sincronizza-ufficiale")
async def sincronizza_ufficiale(fornitore: str, _admin=Depends(require_admin)):
    return await sincronizza_catalogo_ufficiale(fornitore)


@router.get("/prodotti")
async def lista_prodotti(fornitore: Optional[str] = None, categoria: Optional[str] = None, cerca: Optional[str] = None):
    q = {}
    if fornitore:
        q["fornitore"] = fornitore
    if categoria:
        q["categoria"] = categoria
    if cerca:
        q["nome"] = {"$regex": cerca, "$options": "i"}
    prods = await db.catalogo_forno_prodotti.find(q, {"_id": 0}).sort("nome", 1).to_list(2000)
    if fornitore:
        attivi = await db.dizionario_prodotti.find(
            {"catalogo_fonte": fornitore, "attivo": {"$ne": False}},
            {"_id": 0, "catalogo_codice": 1},
        ).to_list(3000)
        codici_attivi = {str(p.get("catalogo_codice") or "") for p in attivi}
        for prodotto in prods:
            prodotto["in_ricette"] = str(prodotto.get("codice_articolo") or "") in codici_attivi
    # Aggancia prezzo e quantità realmente pagati dalle fatture XML (match per
    # nome) — stesso motore unico di Saima/MePA/Acquaviva: sfogliando il
    # catalogo, un prodotto col prezzo = già comprato davvero.
    if fornitore in _FORNITORE_FATTURA_MATCH:
        try:
            from app.lotti.routers.utils import prezzi_fatture_per_fornitore, applica_prezzo_da_fatture
            prezzi = await prezzi_fatture_per_fornitore(db, _FORNITORE_FATTURA_MATCH[fornitore])
            prods = applica_prezzo_da_fatture(prods, prezzi)
        except Exception:
            logger.debug("[catalogo_forno] aggancio prezzi fatture fallito (non bloccante)")
    return {"totale": len(prods), "prodotti": prods}


def _id_ingrediente_catalogo(fornitore: str, codice: str) -> str:
    parte = re.sub(r"[^a-z0-9]+", "_", f"{fornitore}_{codice}".lower()).strip("_")
    return f"catalogo_{parte}"[:120]


@router.post("/prodotti/{fornitore}/{codice}/usa-in-ricette")
async def usa_in_ricette(fornitore: str, codice: str, _admin=Depends(require_admin)):
    prodotto = await db.catalogo_forno_prodotti.find_one(
        {"fornitore": fornitore, "codice_articolo": codice}, {"_id": 0}
    )
    if not prodotto:
        raise HTTPException(404, "Prodotto del catalogo non trovato")
    identificativo = _id_ingrediente_catalogo(fornitore, codice)
    nome = prodotto.get("nome_completo") or prodotto.get("nome") or codice
    doc = {
        "id": identificativo,
        "nome": nome,
        "nome_normalizzato": str(nome).strip().lower(),
        "descrizione": prodotto.get("descrizione", ""),
        "categoria": prodotto.get("categoria", ""),
        "foto_url": prodotto.get("immagine_url", ""),
        "fornitore": fornitore,
        "codice_articolo": codice,
        "catalogo_fonte": fornitore,
        "catalogo_codice": codice,
        "fonte": fornitore,
        f"is_{fornitore}": True,
        "attivo": True,
        "data_aggiornamento": datetime.now(timezone.utc).isoformat(),
    }
    await db.dizionario_prodotti.update_one({"id": identificativo}, {"$set": doc}, upsert=True)
    return {"ok": True, "id": identificativo}


@router.delete("/prodotti/{fornitore}/{codice}/usa-in-ricette")
async def non_usare_in_ricette(fornitore: str, codice: str, _admin=Depends(require_admin)):
    await db.dizionario_prodotti.update_many(
        {"catalogo_fonte": fornitore, "catalogo_codice": codice},
        {"$set": {"attivo": False, f"is_{fornitore}": False, "data_aggiornamento": datetime.now(timezone.utc).isoformat()}},
    )
    return {"ok": True}


@router.get("/fornitori")
async def lista_fornitori():
    forn = await db.catalogo_forno_prodotti.distinct("fornitore")
    out = []
    for f in forn:
        n = await db.catalogo_forno_prodotti.count_documents({"fornitore": f})
        cats = await db.catalogo_forno_prodotti.distinct("categoria", {"fornitore": f})
        out.append({"fornitore": f, "prodotti": n, "categorie": sorted([c for c in cats if c])})
    return {"fornitori": out}


@router.delete("/prodotti/{codice}")
async def elimina(codice: str, fornitore: str, _admin=Depends(require_admin)):
    res = await db.catalogo_forno_prodotti.delete_one({"fornitore": fornitore, "codice_articolo": codice})
    if not res.deleted_count:
        raise HTTPException(404, "Prodotto non trovato")
    return {"ok": True}
