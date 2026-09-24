"""Ordini → miglior fornitore per articolo, dalle fatture XML ricevute.

La regola sta in `servizi/confronto_fornitori.py`. La fonte sono le righe delle
fatture attive del gestionale (stesso processo, versione leggera in cache):
ci sono anche i fornitori del bar, che Lotti esclude dalla tracciabilita' HACCP
ma da cui si ordina ogni settimana.

Un accorpamento incerto non si fa da solo: `/da-confermare` elenca le coppie
probabili e `/decisione` registra «stesso» o «diverso», con chi l'ha detto.
"""
import hashlib
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.lotti.auth import request_actor
from app.lotti.db import database as db
from app.lotti.servizi import confronto_fornitori as cf

router = APIRouter(prefix="/confronto-fornitori", tags=["Confronto fornitori"])

COLLEZIONE_DECISIONI = "confronto_fornitori_decisioni"


async def _fatture() -> list:
    from app.routers.lotti_integration import _documents

    return await _documents()


async def _acquisti() -> List[cf.Acquisto]:
    if cf.cache_valida():
        return cf._cache["acquisti"]
    acquisti = cf.acquisti_da_fatture(await _fatture())
    cf.salva_cache(acquisti)
    return acquisti


async def _decisioni() -> cf.Decisioni:
    docs = await getattr(db, COLLEZIONE_DECISIONI).find({}, {"_id": 0}).to_list(None)
    return cf.Decisioni.da_documenti(docs)


def _corrisponde(articolo: dict, parole_ricerca: List[str]) -> bool:
    testo = " ".join([articolo["nome"]] + [r["descrizione"] for r in articolo["fornitori"]]
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
    acquisti = await _acquisti()
    gruppi, probabili = cf.raggruppa(acquisti, await _decisioni())
    articoli = [cf.riepilogo_gruppo(g) for g in gruppi.values()]
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
        "fonte": "righe delle fatture XML ricevute (fatture attive, note di credito escluse)",
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
    acquisti = await _acquisti()
    _gruppi, probabili = cf.raggruppa(acquisti, await _decisioni())
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
async def registra_decisione(body: Decisione, request: Request):
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
    return {"ok": True, "decisione": documento}
