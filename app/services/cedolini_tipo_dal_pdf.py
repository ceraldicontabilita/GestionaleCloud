"""Tredicesime e quattordicesime salvate come «mensile»: il tipo riletto dal PDF.

L'audit del 28/09/2026 sui cedolini dell'ERP ha trovato 157 casi con lo stesso
dipendente, anno e mese e netti diversi. In buona parte sono la mensile e la
13ª/14ª dello stesso mese salvate tutte e due come ``mensile``: il netto della
mensilita' aggiuntiva finisce contato come stipendio, e la busta vera sembra un
doppione. Altri sono varianti, rettifiche o periodi attribuiti al mese sbagliato.

Qui non si indovina dal mese o dall'importo: il PDF originale di ogni riga (e'
nella riga stessa) si rilegge con ``cedolini_motore.leggi_pdf``, l'unico lettore
dei cedolini, e il tipo lo dice la busta con lo **stesso codice fiscale, anno e
netto al centesimo**, verificato dalla cella. Una riga che il lettore non
ritrova, o ritrova in piu' buste di tipo diverso, resta com'e' col motivo.

Il giro va a lotti (``LOTTO`` righe per volta) e tiene il rapporto in
``sistema_stato`` (chiave ``cedolini_tipo_dal_pdf``). Si applica da solo solo
il verso scelto dal titolare (28/09/2026): una «mensile» che il PDF dice 13ª o
14ª (``DIREZIONI_APPLICATE``). Il verso contrario, e ogni altro cambio, resta
nel rapporto come ``da_decidere``. Quando si applica, la riga cambia
``tipo_cedolino`` (e il mese, se la busta ne porta un altro) e conserva il
valore di prima in ``tipo_cedolino_prima``.
"""
from __future__ import annotations

import asyncio
import base64
import logging
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.constants.stati_netto import NETTO_VERIFICATO_DA_CEDOLINO

logger = logging.getLogger(__name__)

COLL = "cedolini"
CHIAVE_STATO = "cedolini_tipo_dal_pdf"
VERSIONE = "tipo_dal_pdf_v2"
LOTTO = 40
APPLICA = True
# Il solo verso che il titolare ha fatto applicare da solo (28/09/2026).
DIREZIONI_APPLICATE = frozenset({("mensile", "tredicesima"), ("mensile", "quattordicesima")})
# Righe gia' marcate come copie da un giro precedente: non sono buste da tipizzare.
TIPI_ESCLUSI = frozenset({"copia_non_canonica"})


def _cent(valore: Any) -> Optional[Decimal]:
    if valore in (None, ""):
        return None
    try:
        return Decimal(str(valore)).quantize(Decimal("0.01"))
    except InvalidOperation:  # un netto illeggibile resta nullo, non zero
        return None


def _intero(valore: Any) -> Optional[int]:
    try:
        return int(str(valore).strip())
    except (TypeError, ValueError):
        return None


def _cf(valore: Any) -> str:
    return str(valore or "").strip().upper()


def _netto(doc: Dict[str, Any]) -> Optional[Decimal]:
    return _cent(doc.get("netto_mese", doc.get("netto")))


def _attiva(doc: Dict[str, Any]) -> bool:
    return (doc.get("entity_status") != "deleted"
            and str(doc.get("tipo_cedolino") or "").lower() not in TIPI_ESCLUSI)


def casi_da_rileggere(cedolini: Iterable[Dict[str, Any]]) -> Dict[Tuple[str, int, int], List[Dict[str, Any]]]:
    """Gruppi CF + anno + mese con almeno due netti diversi: le righe da rileggere."""
    gruppi: Dict[Tuple[str, int, int], List[Dict[str, Any]]] = defaultdict(list)
    for doc in cedolini:
        cf, anno, mese = _cf(doc.get("codice_fiscale")), _intero(doc.get("anno")), _intero(doc.get("mese"))
        if not (cf and anno and mese and doc.get("id")) or not _attiva(doc):
            continue
        gruppi[(cf, anno, mese)].append(doc)
    return {k: v for k, v in gruppi.items() if len({_netto(d) for d in v}) > 1}


def tipo_dalla_busta(riga: Dict[str, Any], buste: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Il tipo della busta del PDF che corrisponde alla riga, o il motivo per cui non c'e'."""
    cf, anno, netto = _cf(riga.get("codice_fiscale")), _intero(riga.get("anno")), _netto(riga)
    if netto is None:
        return {"esito": "riga_senza_netto"}
    candidate = [
        b for b in buste
        if _cf(b.get("codice_fiscale")) == cf and _intero(b.get("anno")) == anno
        and _cent(b.get("netto_mese", b.get("netto"))) == netto
    ]
    if not candidate:
        return {"esito": "non_ritrovata"}
    verificate = [b for b in candidate if b.get("stato_netto") == NETTO_VERIFICATO_DA_CEDOLINO]
    if not verificate:
        return {"esito": "netto_non_verificato"}
    tipi = {(str(b.get("tipo_cedolino") or "mensile").lower(), _intero(b.get("mese"))) for b in verificate}
    if len(tipi) > 1:
        return {"esito": "ambigua", "tipi": sorted(f"{t}/{m}" for t, m in tipi)}
    tipo, mese = tipi.pop()
    prima_tipo = str(riga.get("tipo_cedolino") or "mensile").lower()
    prima_mese = _intero(riga.get("mese"))
    if tipo == prima_tipo and (mese is None or mese == prima_mese):
        return {"esito": "confermato", "tipo": tipo, "mese": prima_mese}
    return {"esito": "da_riclassificare", "tipo": tipo, "mese": mese or prima_mese,
            "tipo_prima": prima_tipo, "mese_prima": prima_mese}


async def giro(db, *, applica: bool = APPLICA, lotto: int = LOTTO) -> Dict[str, Any]:
    """Rilegge al massimo ``lotto`` righe non ancora viste in questa versione."""
    from app.document_repository import metadata_projection
    from app.services.cedolini_motore import leggi_pdf

    stato = await db["sistema_stato"].find_one({"chiave": CHIAVE_STATO}, {"_id": 0}) or {}
    if stato.get("versione") != VERSIONE:
        stato = {"chiave": CHIAVE_STATO, "versione": VERSIONE, "viste": [], "esiti": [], "conteggi": {}}
    viste = set(stato.get("viste") or [])

    righe = await db[COLL].find({}, metadata_projection(COLL)).to_list(None)
    casi = casi_da_rileggere(righe)
    da_fare = [d for gruppo in casi.values() for d in gruppo if d["id"] not in viste][:lotto]

    conteggi = dict(stato.get("conteggi") or {})
    esiti = list(stato.get("esiti") or [])
    now = datetime.now(timezone.utc).isoformat()
    for riga in da_fare:
        try:
            completa = await db[COLL].find_one({"id": riga["id"]}, {"_id": 0, "pdf_data": 1}) or {}
            pdf = completa.get("pdf_data")
            if isinstance(pdf, str):
                pdf = base64.b64decode(pdf)
            if not pdf:
                esito = {"esito": "pdf_assente"}
            else:
                letto = await asyncio.to_thread(leggi_pdf, pdf)
                esito = tipo_dalla_busta(riga, letto.get("buste") or [])
        except Exception as exc:  # noqa: BLE001 - un PDF rotto non ferma il lotto
            logger.warning("Tipo dal PDF %s: PDF non letto: %s: %s", riga["id"], type(exc).__name__, exc)
            esito = {"esito": "pdf_illeggibile"}
        conteggi[esito["esito"]] = conteggi.get(esito["esito"], 0) + 1
        viste.add(riga["id"])
        voce = {"id": riga["id"], "cf": _cf(riga.get("codice_fiscale"))[:6] + "***",
                "anno": riga.get("anno"), "mese": riga.get("mese"),
                "netto": str(_netto(riga)), **esito}
        if esito["esito"] == "da_riclassificare":
            verso = (esito["tipo_prima"], esito["tipo"])
            voce["decisione"] = "applicata" if applica and verso in DIREZIONI_APPLICATE else "da_decidere"
        if esito["esito"] != "confermato":
            esiti.append(voce)
        if voce.get("decisione") == "applicata":
            await db[COLL].update_one({"id": riga["id"]}, {"$set": {
                "tipo_cedolino": esito["tipo"], "mese": esito["mese"],
                "tipo_cedolino_prima": {"tipo": esito["tipo_prima"], "mese": esito["mese_prima"],
                                        "fonte": VERSIONE, "at": now},
                "updated_at": now,
            }})
    rimaste = sum(1 for g in casi.values() for d in g if d["id"] not in viste)
    stato.update({"viste": sorted(viste), "esiti": esiti, "conteggi": conteggi, "gruppi": len(casi),
                  "rimaste": rimaste, "simulazione": not applica, "aggiornato_il": now})
    await db["sistema_stato"].update_one({"chiave": CHIAVE_STATO}, {"$set": stato}, upsert=True)
    return {"lette": len(da_fare), "rimaste": rimaste, "conteggi": conteggi, "simulazione": not applica}
