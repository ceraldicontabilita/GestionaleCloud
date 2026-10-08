"""Ordini → miglior fornitore per articolo, dalle fatture XML e dai listini.

La regola sta in `servizi/confronto_fornitori.py`. Le fonti sono le righe delle
fatture attive del gestionale (stesso processo, versione leggera in cache):
ci sono anche i fornitori del bar, che Lotti esclude dalla tracciabilita' HACCP
ma da cui si ordina ogni settimana; e i listini caricati nei cataloghi
(`catalogo_forno_prodotti` con `prezzo_listino`, per esempio Barone). La
lettura AI delle descrizioni (`servizi/lettura_articoli_ai.py`) completa i
formati e unisce le descrizioni diverse dello stesso articolo.

Un accorpamento incerto non si fa da solo: `/da-confermare` elenca le coppie
probabili e `/decisione` registra «stesso» o «diverso», con chi l'ha detto.
"""
import hashlib
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from pydantic import BaseModel

from app.lotti.auth import request_actor
from app.lotti.db import database as db
from app.lotti.servizi import confronto_fornitori as cf
from app.lotti.auth import require_admin
from fastapi import Depends

router = APIRouter(prefix="/confronto-fornitori", tags=["Confronto fornitori"])

COLLEZIONE_DECISIONI = "confronto_fornitori_decisioni"


async def _fatture() -> list:
    from app.routers.lotti_integration import _documents

    return await _documents()


async def _listini() -> List[cf.Acquisto]:
    prodotti = await db.catalogo_forno_prodotti.find(
        {"fonte_catalogo": "listino", "nel_listino": {"$ne": False}}, {"_id": 0}
    ).to_list(None)
    if not prodotti:
        return []
    fonti = await db.fonti_catalogo_esterne.find({"tipo": "listino"}, {"_id": 0}).to_list(None)
    return cf.acquisti_da_listini(prodotti, fonti)


async def acquisti_grezzi() -> List[cf.Acquisto]:
    """Fatture + listini, senza lettura AI (serve anche al giro della lettura)."""
    return cf.acquisti_da_fatture(await _fatture()) + await _listini()


async def _acquisti() -> List[cf.Acquisto]:
    if cf.cache_valida():
        return cf._cache["acquisti"]
    from app.lotti.servizi import lettura_articoli_ai as lettura

    letture = lettura.letture_per_impronta(
        await getattr(db, lettura.COLLEZIONE).find({}, {"_id": 0}).to_list(None)
    )
    acquisti = cf.applica_letture(await acquisti_grezzi(), letture)
    cf.salva_cache(acquisti)
    return acquisti


async def _riepiloghi() -> tuple:
    """Acquisti, gruppi, coppie probabili e riepiloghi: calcolati una volta per
    giro di cache (catalogo e carrello li chiedono a ogni tocco)."""
    acquisti = await _acquisti()
    pronto = cf._cache.get("riepiloghi")
    if pronto is not None and pronto[0] is acquisti:
        return pronto
    gruppi, probabili = cf.raggruppa(acquisti, await _decisioni())
    via_ai = getattr(gruppi, "via_ai", set())
    articoli = [cf.riepilogo_gruppo(g, abbinato_ai=radice in via_ai) for radice, g in gruppi.items()]
    cf._cache["riepiloghi"] = (acquisti, gruppi, probabili, articoli)
    return cf._cache["riepiloghi"]


async def _decisioni() -> cf.Decisioni:
    docs = await getattr(db, COLLEZIONE_DECISIONI).find({}, {"_id": 0}).to_list(None)
    return cf.Decisioni.da_documenti(docs)


def _corrisponde(articolo: dict, parole_ricerca: List[str]) -> bool:
    testo = " ".join([articolo["nome"], articolo.get("nome_standard") or ""]
                     + [r["descrizione"] for r in articolo["fornitori"]]
                     + [r["fornitore"] for r in articolo["fornitori"]])
    testo = cf.pulisci(testo)
    return all(p in testo for p in parole_ricerca)


@router.get("")
async def elenco_articoli(
    q: str = Query("", description="Parole da cercare nel nome o nel fornitore"),
    solo_confronti: bool = Query(False, description="Solo articoli con almeno due fornitori"),
    fornitore: str = Query("", description="Solo articoli venduti da questo fornitore"),
    limit: int = Query(200, ge=1, le=1000),
):
    """Articoli con l'ultimo prezzo di ogni fornitore e il piu' conveniente."""
    _acquisti_tutti, _gruppi, probabili, articoli = await _riepiloghi()
    con_confronto = sum(1 for a in articoli if a["migliore"] and not a["pari_merito"])

    parole = [p for p in cf.pulisci(q).split() if p]
    chiave_forn = cf.chiave_fornitore(fornitore) if fornitore.strip() else ""
    filtrati = []
    for a in articoli:
        if solo_confronti and a["n_fornitori"] < 2:
            continue
        if chiave_forn and not any(cf.chiave_fornitore(r["fornitore"]) == chiave_forn or r["fornitore_id"] == fornitore
                                   for r in a["fornitori"]):
            continue
        if parole and not _corrisponde(a, parole):
            continue
        filtrati.append(a)
    # prima gli articoli dove scegliere conviene, poi i piu' recenti
    filtrati.sort(key=lambda a: (
        0 if a["migliore"] else (1 if a["n_fornitori"] > 1 else 2),
        a["nome"],
    ))
    fornitori = sorted({r["fornitore"] for a in articoli for r in a["fornitori"]}, key=str.upper)
    return {
        "fonte": "righe delle fatture XML ricevute (fatture attive, note di credito escluse) e listini dei fornitori",
        "valuta": cf.VALUTA,
        "totale_articoli": len(articoli),
        "con_confronto": con_confronto,
        "da_confermare": len(probabili),
        "trovati": len(filtrati),
        "fornitori": fornitori,
        "articoli": filtrati[:limit],
    }


@router.get("/da-confermare")
async def coppie_da_confermare(limit: int = Query(100, ge=1, le=500)):
    """Coppie di descrizioni che sembrano lo stesso articolo: decide una persona."""
    acquisti, _gruppi, probabili, _articoli = await _riepiloghi()
    per_chiave: dict = {}
    for a in acquisti:
        per_chiave.setdefault(a.articolo.chiave, []).append(a)
    proposte = [cf.proposta(a, b, per_chiave) for a, b in probabili]
    proposte.sort(key=lambda p: max(p["a"]["data"], p["b"]["data"]), reverse=True)
    return {"totale": len(proposte), "proposte": proposte[:limit]}


class Decisione(BaseModel):
    chiavi: List[str]
    esito: str  # "stesso" | "diverso"


@router.post("/decisione")
async def registra_decisione(body: Decisione, request: Request, _admin=Depends(require_admin)):
    """«Stesso articolo» o «articoli diversi» per una coppia proposta."""
    if body.esito not in ("stesso", "diverso"):
        raise HTTPException(status_code=422, detail="esito deve essere «stesso» o «diverso»")
    chiavi = sorted({str(c) for c in body.chiavi})
    if len(chiavi) != 2:
        raise HTTPException(status_code=422, detail="servono due articoli diversi")
    articoli = {a.articolo.chiave: a.articolo for a in await _acquisti()}
    mancanti = [c for c in chiavi if c not in articoli]
    if mancanti:
        raise HTTPException(status_code=404, detail=f"Articolo non trovato nelle fatture: {mancanti}")
    if body.esito == "stesso" and cf.confronta(articoli[chiavi[0]], articoli[chiavi[1]]) is None:
        # formato o confezione diversi: non e' una scelta, e' un altro articolo
        raise HTTPException(
            status_code=409,
            detail="Formato, confezione o variante diversi: non possono essere lo stesso articolo.",
        )
    attore = request_actor(request) or {}
    doc_id = hashlib.sha256("|".join(chiavi).encode("utf-8")).hexdigest()[:32]
    documento = {
        "id": doc_id,
        "chiavi": chiavi,
        "descrizioni": [articoli[c].descrizione for c in chiavi],
        "esito": body.esito,
        "deciso_da": {"id": str(attore.get("id") or ""), "nome": str(attore.get("nome") or "")},
        "deciso_il": datetime.now(timezone.utc).isoformat(),
    }
    await getattr(db, COLLEZIONE_DECISIONI).update_one({"id": doc_id}, {"$set": documento}, upsert=True)
    cf._cache["riepiloghi"] = None
    return {"ok": True, "decisione": documento}


# ── dal catalogo al carrello: chi lo vende a meno ───────────────────────────


def _consiglio(articolo: dict, fornitore: str) -> dict:
    """Il fornitore da cui ordinare l'articolo e quanto si risparmia rispetto
    a quello da cui lo si stava prendendo."""
    righe = articolo["fornitori"]
    chiave = cf.chiave_fornitore(fornitore)
    attuale = next((r for r in righe if cf.chiave_fornitore(r["fornitore"]) == chiave
                    or r.get("fornitore_key") == fornitore or r["fornitore_id"] == fornitore), None)
    if not articolo["migliore"] or articolo["pari_merito"]:
        return {"cambia": False, "attuale": attuale, "migliore": None}
    migliore = righe[0]
    cambia = attuale is None or migliore["fornitore_id"] != attuale["fornitore_id"]
    risparmio = None
    if cambia and attuale is not None:
        risparmio = f"{(cf._decimale(attuale['prezzo_pezzo']) - cf._decimale(migliore['prezzo_pezzo'])).quantize(cf.Q4):f}"
    return {"cambia": cambia, "attuale": attuale, "migliore": migliore, "risparmio_pezzo": risparmio}


def _radice_per_descrizioni(gruppi: dict, descrizioni: List[str]):
    for descrizione in descrizioni:
        if not str(descrizione or "").strip():
            continue
        cercata = cf.pulisci(descrizione)
        impronta = cf.impronta_descrizione(descrizione)
        chiave = cf.leggi(descrizione).chiave
        for k, lista in gruppi.items():
            if any(cf.impronta_descrizione(a.descrizione_originale or a.articolo.descrizione) == impronta
                   or a.articolo.chiave == chiave or cf.pulisci(a.articolo.descrizione) == cercata for a in lista):
                return k
    return None


@router.get("/migliore")
async def miglior_fornitore_per(
    descrizione: str = Query("", description="Nome dell'articolo come lo scrive il catalogo"),
    fornitore: str = Query("", description="Fornitore o chiave del catalogo da cui lo si sta ordinando"),
    codice: str = Query("", description="Codice articolo del catalogo, se c'e'"),
    prodotto_master_id: str = Query("", description="Articolo del catalogo Ordini: si cercano anche le sue descrizioni di fattura"),
):
    """Per un articolo scelto da un catalogo: il suo gruppo nel confronto e da
    chi conviene ordinarlo. Nessun gruppo = nessun confronto (non si inventa)."""
    if not descrizione.strip() and not codice.strip() and not prodotto_master_id.strip():
        raise HTTPException(status_code=422, detail="Serve la descrizione o il codice dell'articolo")
    acquisti, gruppi, _probabili, _articoli = await _riepiloghi()
    radice = None
    if codice.strip():
        for k, lista in gruppi.items():
            if any(a.codice_articolo == codice.strip() and (not fornitore or a.fornitore_key == fornitore
                   or cf.chiave_fornitore(a.fornitore) == cf.chiave_fornitore(fornitore)) for a in lista):
                radice = k
                break
    descrizioni = [descrizione]
    if prodotto_master_id.strip():
        master = await db.prodotti_master.find_one({"id": prodotto_master_id.strip()},
                                                   {"_id": 0, "aliases": 1, "nome_canonico": 1})
        if master:
            descrizioni += list(master.get("aliases") or []) + [master.get("nome_canonico") or ""]
    if radice is None:
        radice = _radice_per_descrizioni(gruppi, descrizioni)
    if radice is None:
        return {"trovato": False, "consiglio": {"cambia": False}}
    via_ai = getattr(gruppi, "via_ai", set())
    articolo = cf.riepilogo_gruppo(gruppi[radice], abbinato_ai=radice in via_ai)
    return {"trovato": True, "articolo": articolo, "consiglio": _consiglio(articolo, fornitore)}


@router.get("/per-catalogo")
async def confronto_per_catalogo(fornitore: str = Query(..., description="Chiave del catalogo, es. barone")):
    """Per ogni articolo di un catalogo venduto anche da altri: chi costa meno.
    Serve a vedere a colpo d'occhio, sfogliando il catalogo, dove conviene."""
    acquisti, gruppi, _probabili, _articoli = await _riepiloghi()
    via_ai = getattr(gruppi, "via_ai", set())
    out = {}
    for radice, lista in gruppi.items():
        codici = {a.codice_articolo for a in lista if a.origine == "listino" and a.fornitore_key == fornitore}
        if not codici or len({a.fornitore_id for a in lista}) < 2:
            continue
        articolo = cf.riepilogo_gruppo(lista, abbinato_ai=radice in via_ai)
        questo = next((r for r in articolo["fornitori"] if r.get("fornitore_key") == fornitore), None)
        migliore = articolo["fornitori"][0] if articolo["migliore"] else None
        sintesi = {
            "n_fornitori": articolo["n_fornitori"],
            "confrontabile": articolo["confrontabile"],
            "questo_migliore": bool(migliore and questo and migliore["fornitore_id"] == questo["fornitore_id"]),
            "prezzo_pezzo": questo["prezzo_pezzo"] if questo else None,
            "migliore": migliore["fornitore"] if migliore else None,
            "migliore_prezzo_pezzo": migliore["prezzo_pezzo"] if migliore else None,
            "migliore_origine": migliore["origine"] if migliore else None,
            "migliore_data": migliore["data"] if migliore else None,
            "abbinato_ai": articolo["abbinato_ai"],
            "chiave": articolo["chiave"],
        }
        for c in codici:
            out[c] = sintesi
    return {"fornitore": fornitore, "articoli": out}


# ── lettura AI delle descrizioni ────────────────────────────────────────────


async def esegui_lettura_ai(limite: int = 3000) -> dict:
    """Legge con l'AI le descrizioni non ancora lette (fatture e listini)."""
    from app.lotti.servizi import lettura_articoli_ai as lettura

    grezzi = await acquisti_grezzi()
    esito = await lettura.leggi_mancanti(db, [a.descrizione_originale or a.articolo.descrizione for a in grezzi],
                                         limite=limite)
    if esito.get("letti"):
        cf.invalida_cache()
    return esito


@router.post("/lettura-ai/avvia")
async def avvia_lettura_ai(background: BackgroundTasks, _admin=Depends(require_admin)):
    """Avvia in sottofondo la lettura AI delle descrizioni nuove."""
    background.add_task(esegui_lettura_ai)
    return {"avviato": True, "stato": "/confronto-fornitori/lettura-ai/stato"}


@router.get("/lettura-ai/stato")
async def stato_lettura_ai():
    from app.lotti.servizi import lettura_articoli_ai as lettura

    stato = await db.sync_status.find_one({"_id": lettura.STATO_ID}, {"_id": 0}) or {"stato": "mai_eseguita"}
    stato["letture_salvate"] = await getattr(db, lettura.COLLEZIONE).count_documents({"versione": lettura.VERSIONE})
    return stato
