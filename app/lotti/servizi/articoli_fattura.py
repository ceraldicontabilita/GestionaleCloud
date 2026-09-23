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
from typing import Any, Dict, Iterable, Optional

__all__ = [
    "chiave_descrizione",
    "carica_associazioni",
    "invalida_cache",
    "serve_ingrediente",
    "esclude_ingrediente",
    "ingredienti_da_testo",
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
