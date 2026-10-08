"""Identità degli articoli di fattura: il nome commerciale → l'articolo di casa.

In fattura c'è «COCA COLA VAP CL.33 REGULAR», «OLVA THERMO CREMA GATEAUX»,
«CREMA RIO TRADIZIONE PISTACCHIO»; in ricetta e al banco si dice «coca vetro»,
«margarina», «crema pistacchio». Il FIFO, gli ordini e le etichette devono
sapere che sono la stessa cosa, e non devono **mai** confondere cose diverse:
«olive in acqua e sale» non è sale, «nuova Biancalieve» non sono uova, la
granella di pistacchio non è la crema spalmabile.

Una sola tabella tiene l'associazione: ``nome_mapping`` (chiave =
``descrizione_key``, la descrizione di fattura in minuscolo). Ogni riga porta:

* ``nome_canc``            l'articolo di casa («Margarina», «Crema pistacchio»);
* ``ingredienti_ricetta``  i nomi degli ingredienti di ricetta che l'articolo serve;
* ``alimentare``           False per piastrelle, consulenze, spese…;
* ``confermato``           True solo quando lo ha detto una persona;
* ``fonte``                ``web`` (ricerca), ``ai``, ``manuale``;
* ``cosa_e`` / ``fonte_url`` / ``confidenza``  la prova della proposta.

Regola: **una proposta non scarica merce**. Il FIFO usa per primi i lotti la
cui descrizione ha un'associazione confermata per quell'ingrediente; senza
conferme ripiega sul nome, ma escludendo i lotti che una conferma (o una
proposta web ad alta confidenza) dice essere un'altra cosa.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

__all__ = [
    "chiave_descrizione",
    "carica_associazioni",
    "invalida_cache",
    "serve_ingrediente",
    "esclude_ingrediente",
    "ingredienti_da_testo",
    "conferma_articolo",
]

_TTL_SECONDI = 60.0
_cache: Dict[str, Any] = {"at": 0.0, "dati": None}


def chiave_descrizione(descrizione: Any) -> str:
    """La descrizione di fattura come chiave: prima riga, minuscolo, spazi unici.

    Le descrizioni di alcuni fornitori arrivano con la riga ripetuta dopo un a
    capo («NAVETTE FONDO ORO\\nNAVETTE FONDO ORO»): conta solo la prima.
    """
    testo = str(descrizione or "").strip().split("\n", 1)[0]
    return re.sub(r"\s+", " ", testo).strip().lower()


def ingredienti_da_testo(valori: Optional[Iterable[Any]]) -> list[str]:
    """Normalizza l'elenco degli ingredienti serviti: minuscolo, senza doppioni."""
    visti: list[str] = []
    for v in valori or []:
        n = re.sub(r"\s+", " ", str(v or "")).strip().lower()
        if n and n not in visti:
            visti.append(n)
    return visti


def invalida_cache() -> None:
    _cache["at"] = 0.0
    _cache["dati"] = None


async def carica_associazioni(db) -> Dict[str, Dict[str, Any]]:
    """Le associazioni di ``nome_mapping`` indicizzate per chiave di descrizione.

    Una lettura ogni 60 secondi al massimo: il FIFO le chiede per ogni
    ingrediente di ogni produzione.
    """
    adesso = time.monotonic()
    if _cache["dati"] is not None and adesso - _cache["at"] < _TTL_SECONDI:
        return _cache["dati"]
    dati: Dict[str, Dict[str, Any]] = {}
    proiezione = {
        "_id": 0, "descrizione_key": 1, "nome_canc": 1, "confermato": 1, "fonte": 1,
        "ingredienti_ricetta": 1, "alimentare": 1, "confidenza": 1,
    }
    cursore = db.nome_mapping.find({}, proiezione)
    righe = await cursore.to_list(None) if hasattr(cursore, "to_list") else [r async for r in cursore]
    for r in righe:
        chiave = chiave_descrizione(r.get("descrizione_key"))
        if not chiave:
            continue
        precedente = dati.get(chiave)
        # a parità di chiave vince la riga confermata
        if precedente and precedente.get("confermato") and not r.get("confermato"):
            continue
        dati[chiave] = {
            "nome_canc": str(r.get("nome_canc") or "").strip(),
            "confermato": r.get("confermato") is True,
            "fonte": r.get("fonte"),
            "ingredienti_ricetta": ingredienti_da_testo(r.get("ingredienti_ricetta")),
            "alimentare": r.get("alimentare"),
            "confidenza": r.get("confidenza"),
        }
    _cache["dati"] = dati
    _cache["at"] = adesso
    return dati


def _nomi_ingrediente(nome_ing: str, canonico: str = "") -> set[str]:
    return {n for n in (chiave_descrizione(nome_ing), chiave_descrizione(canonico)) if n}


def serve_ingrediente(associazione: Optional[Dict[str, Any]], nome_ing: str, canonico: str = "") -> bool:
    """L'articolo associato alla descrizione serve questo ingrediente di ricetta?

    Vale il nome dell'articolo uguale all'ingrediente, oppure l'ingrediente
    elencato fra quelli serviti. Nessun confronto per pezzo di parola.
    """
    if not associazione or associazione.get("alimentare") is False:
        return False
    nomi = _nomi_ingrediente(nome_ing, canonico)
    if not nomi:
        return False
    articolo = chiave_descrizione(associazione.get("nome_canc"))
    if articolo and articolo in nomi:
        return True
    return bool(nomi & set(associazione.get("ingredienti_ricetta") or []))


def esclude_ingrediente(associazione: Optional[Dict[str, Any]], nome_ing: str, canonico: str = "") -> bool:
    """Una prova dice che questa descrizione è **un'altra cosa**?

    Esclude dal ripiego per nome: una conferma che non serve l'ingrediente,
    un articolo dichiarato non alimentare, o una proposta web ad alta
    confidenza che non lo elenca. Una proposta incerta non esclude niente.
    """
    if not associazione:
        return False
    if associazione.get("alimentare") is False:
        return True
    if serve_ingrediente(associazione, nome_ing, canonico):
        return False
    if associazione.get("confermato"):
        return True
    return associazione.get("fonte") == "web" and associazione.get("confidenza") == "alta"


async def conferma_articolo(
    db, descrizione: Any, nome_canc: Any, *, ingredienti: Optional[Iterable[Any]] = None,
    alimentare: bool = True,
) -> Dict[str, Any]:
    """Scrive la conferma dell'articolo di una descrizione di fattura.

    Unico scrittore della conferma: lo chiamano ``/conferma-articolo`` di
    Lotti e la pagina Righe acquisti dell'ERP. I lotti con quella descrizione
    prendono il nome canonico (aggiornamento per id). Ritorna ``None`` in
    ``chiave`` se la descrizione o il nome mancano.
    """
    chiave = chiave_descrizione(descrizione)
    nome = str(nome_canc or "").strip()
    if not chiave or (alimentare and not nome):
        return {"chiave": None}
    adesso = datetime.now(timezone.utc).isoformat()
    elenco = ingredienti_da_testo(ingredienti)
    if alimentare and nome.lower() not in elenco:
        elenco.insert(0, nome.lower())
    await db.nome_mapping.update_one(
        {"descrizione_key": chiave},
        {"$set": {
            "descrizione_key": chiave,
            "nome_canc": nome or "Non alimentare",
            "ingredienti_ricetta": elenco if alimentare else [],
            "alimentare": alimentare,
            "confermato": True,
            "confermato_at": adesso,
            "aggiornato_at": adesso,
        }},
        upsert=True,
    )
    invalida_cache()
    aggiornati = 0
    lotti = await db.lotti_fornitori.find({}, {"_id": 0, "id": 1, "prodotto_nome": 1}).to_list(20000)
    for lotto in lotti:
        if lotto.get("id") and chiave_descrizione(lotto.get("prodotto_nome")) == chiave:
            await db.lotti_fornitori.update_one(
                {"id": lotto["id"]},
                {"$set": {"nome_canonico": nome if alimentare else "", "articolo_confermato": alimentare}},
            )
            aggiornati += 1
    return {"chiave": chiave, "nome_canc": nome, "ingredienti_ricetta": elenco,
            "lotti_aggiornati": aggiornati}
