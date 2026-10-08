"""Versioni della stessa busta: quale vale, quale e' superata, quale decide il titolare.

Nel registro ``cedolini`` la stessa busta (codice fiscale, anno, mese, tipo)
esiste spesso in piu' righe con **netti diversi**: la «STAMPA DI CONTROLLO»
del consulente e poi la definitiva, la «Variante 1» e la «Variante 2», la
pagina del Libro Unico letta a meta'. Al 30/09/2026 erano 108 gruppi su 1.764
righe, nessuno ancora in Prima Nota salari. Due righe attive per la stessa
busta contano due volte il costo del personale e attaccano il bonifico alla
copia sbagliata.

Un motore solo decide (``decidi``), con le regole del minisito del titolare:

1. la **definitiva batte la stampa di controllo** (riconosciuta dal testo della
   busta, ``cedolini_stampe_controllo.e_stampa_di_controllo``, o dal nome file);
2. una **«Variante N» piu' alta batte la piu' bassa o assente** (dal nome file o
   dal testo, ``VARIANTE\\s*(\\d+)``);
3. se nessuna regola distingue due netti diversi **non si decide niente**: le
   righe restano tutte e due, marcate ``varianti_da_decidere``, e l'esito lo
   elenca perche' il titolare scelga.

Chi perde diventa ``status="sostituito"`` (``sostituito_da``,
``sostituito_motivo``); chi vince porta ``versioni_scartate``,
``n_versioni_totali``, ``rettificato`` e una voce in ``storico_netto`` (stesso
schema di ``cedolini_hr_riverifica``). Non si cancella nulla, e una riga
**pagata** o con una riga di Prima Nota salari (``cedolino_id``) non si
sostituisce mai: in quel caso il gruppo resta ``varianti_da_decidere``.

Lo stesso motore gira all'arrivo di una busta (``cedolini_manager``, sotto il
lock della busta: se la busta in arrivo e' la perdente si salva subito
sostituita, mai come secondo cedolino attivo) e sull'archivio
(``rapporto_archivio`` in sola lettura, ``giro`` a lotti con lo stato in
``sistema_stato``, chiave ``cedolini_versioni``).
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from app.services.cedolini_stampe_controllo import _CONTROLLO, e_stampa_di_controllo
from app.services.doppioni_archivio import _punteggio_cedolino

logger = logging.getLogger(__name__)

COLL = "cedolini"
CHIAVE_STATO = "cedolini_versioni"
VERSIONE = "cedolini_versioni_v1"
FONTE_STORICO = "cedolini_versioni"
LOTTO = 50

#: Lo ``status`` della riga superata da un'altra versione della stessa busta.
STATUS_SOSTITUITO = "sostituito"
#: Gli ``status`` che tolgono una riga dal conto delle buste vive.
STATI_NON_ATTIVI = ("deleted", "archived", "archiviata", STATUS_SOSTITUITO)

ESITO_VINCITORE = "vincitore"
ESITO_DA_DECIDERE = "da_decidere"
ESITO_STESSO_NETTO = "stesso_netto"
ESITO_UNICA = "unica"

_VARIANTE = re.compile(r"VARIANTE\s*(\d+)", re.IGNORECASE)
_PROIEZIONE = {
    "_id": 0, "id": 1, "codice_fiscale": 1, "anno": 1, "mese": 1, "tipo_cedolino": 1,
    "netto": 1, "netto_mese": 1, "lordo": 1, "totale_trattenute": 1, "stato_netto": 1,
    "netto_fonte": 1, "filename": 1, "canale": 1, "pagato": 1, "importo_pagato": 1,
    "pagamenti": 1, "riconciliato": 1, "riconciliato_auto": 1, "status": 1,
    "entity_status": 1, "drive_file_id": 1, "pdf_disponibile": 1, "voci": 1,
    "created_at": 1, "variante": 1, "stampa_di_controllo": 1, "varianti_da_decidere": 1,
}

Chiave = Tuple[str, int, int, str]


def _ora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cent(valore: Any) -> Optional[Decimal]:
    if valore in (None, ""):
        return None
    try:
        return Decimal(str(valore)).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def _intero(valore: Any) -> Optional[int]:
    try:
        return int(str(valore).strip())
    except (TypeError, ValueError):
        return None


def netto_di(doc: Dict[str, Any]) -> Optional[Decimal]:
    return _cent(doc.get("netto_mese", doc.get("netto")))


def chiave_busta(doc: Dict[str, Any]) -> Optional[Chiave]:
    """(CF, anno, mese, tipo): la busta di cui una riga e' una versione."""
    cf = str(doc.get("codice_fiscale") or "").strip().upper()
    anno, mese = _intero(doc.get("anno")), _intero(doc.get("mese"))
    if not (cf and anno and mese):
        return None
    tipo = str(doc.get("tipo_cedolino") or "mensile").strip().lower()
    return cf, anno, mese, tipo


def attiva(doc: Dict[str, Any]) -> bool:
    return (doc.get("entity_status") != "deleted"
            and str(doc.get("status") or "").lower() not in STATI_NON_ATTIVI)


def variante_di(doc: Dict[str, Any]) -> Optional[int]:
    """«Variante N» dal nome file o dal testo della busta; assente = None."""
    if isinstance(doc.get("variante"), int):
        return doc["variante"]
    for testo in (doc.get("filename"), doc.get("_raw_text"), doc.get("pdf_text")):
        m = _VARIANTE.search(str(testo or ""))
        if m:
            return int(m.group(1))
    return None


def stampa_di_controllo(doc: Dict[str, Any]) -> bool:
    """Bozza del consulente: dal testo della busta o dal nome del file."""
    if doc.get("stampa_di_controllo") is not None:
        return bool(doc["stampa_di_controllo"])
    testo = re.sub(r"\s+", " ", str(doc.get("_raw_text") or doc.get("pdf_text") or "").upper())
    if e_stampa_di_controllo(testo):
        return True
    return bool(_CONTROLLO.search(str(doc.get("filename") or "").upper()))


def marcatori(doc: Dict[str, Any]) -> Dict[str, Any]:
    """I due marcatori letti una volta e scritti sulla riga, cosi' l'archivio
    non deve rileggere il PDF. La stampa di controllo si fissa sulla riga solo
    se e' stata letta dal testo o dal nome (un «no» dedotto dal solo nome di
    una riga d'archivio non e' una prova: si ricalcola al giro seguente)."""
    esito: Dict[str, Any] = {"variante": variante_di(doc)}
    letto_dal_testo = bool(doc.get("_raw_text") or doc.get("pdf_text"))
    if doc.get("stampa_di_controllo") is not None or letto_dal_testo or stampa_di_controllo(doc):
        esito["stampa_di_controllo"] = stampa_di_controllo(doc)
    return esito


def intoccabile(doc: Dict[str, Any], con_prima_nota: Set[str]) -> Optional[str]:
    """Perche' una riga non si puo' sostituire (``None`` se si puo')."""
    if doc.get("pagato") or (doc.get("importo_pagato") or 0) > 0 or doc.get("pagamenti"):
        return "pagata"
    if doc.get("id") and doc["id"] in con_prima_nota:
        return "in Prima Nota salari"
    return None


def _riassunto(doc: Dict[str, Any]) -> Dict[str, Any]:
    netto = netto_di(doc)
    return {
        "id": doc.get("id"), "filename": doc.get("filename"),
        "netto": float(netto) if netto is not None else None,
        "stato_netto": doc.get("stato_netto"), "tipo": (chiave_busta(doc) or ("", 0, 0, ""))[3],
        "canale": doc.get("canale"), "pagato": bool(doc.get("pagato")),
        "variante": variante_di(doc), "stampa_di_controllo": stampa_di_controllo(doc),
    }


def decidi(righe: List[Dict[str, Any]]) -> Dict[str, Any]:
    """La versione che vale fra righe della stessa busta, o ``da_decidere``.

    Ritorna ``esito`` (``vincitore`` | ``da_decidere`` | ``stesso_netto`` |
    ``unica``), ``vincitore`` (la riga), ``perdenti`` (le righe con netto
    diverso dal vincitore) e ``motivo``.
    """
    righe = [r for r in righe if r is not None]
    if len(righe) < 2:
        return {"esito": ESITO_UNICA, "vincitore": righe[0] if righe else None, "perdenti": [], "motivo": ""}
    if len({netto_di(r) for r in righe}) < 2:
        # Stesso netto: sono copie, e delle copie si occupa doppioni_archivio.
        return {"esito": ESITO_STESSO_NETTO, "vincitore": None, "perdenti": [], "motivo": "stesso netto"}

    candidate = list(righe)
    motivi: List[str] = []
    definitive = [r for r in candidate if not stampa_di_controllo(r)]
    if definitive and len(definitive) < len(candidate):
        candidate = definitive
        motivi.append("la busta definitiva batte la stampa di controllo")

    if len({netto_di(r) for r in candidate}) > 1:
        massimo = max(variante_di(r) or 0 for r in candidate)
        migliori = [r for r in candidate if (variante_di(r) or 0) == massimo]
        if massimo > 0 and len({netto_di(r) for r in migliori}) == 1:
            candidate = migliori
            motivi.append(f"la Variante {massimo} batte le versioni precedenti")

    if len({netto_di(r) for r in candidate}) > 1:
        netti = sorted({str(netto_di(r)) for r in candidate})
        return {"esito": ESITO_DA_DECIDERE, "vincitore": None, "perdenti": [],
                "motivo": "netti diversi (" + ", ".join(netti) + ") senza stampa di controllo ne' Variante: decide il titolare"}

    vincitore = min(candidate, key=_punteggio_cedolino)
    perdenti = [r for r in righe if netto_di(r) != netto_di(vincitore)]
    return {"esito": ESITO_VINCITORE, "vincitore": vincitore, "perdenti": perdenti,
            "motivo": "; ".join(motivi)}


# ── archivio ────────────────────────────────────────────────────────────────

async def _ids_in_prima_nota(db) -> Set[str]:
    righe = await db["prima_nota_salari"].find(
        {"cedolino_id": {"$exists": True}}, {"_id": 0, "cedolino_id": 1}).to_list(None)
    return {str(r["cedolino_id"]) for r in righe if r.get("cedolino_id")}


async def righe_della_busta(db, doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Le righe attive del registro con la stessa chiave della busta ``doc``."""
    chiave = chiave_busta(doc)
    if chiave is None:
        return []
    candidati = await db[COLL].find(
        {"codice_fiscale": chiave[0], "anno": chiave[1], "mese": chiave[2]}, _PROIEZIONE,
    ).to_list(None)
    return [c for c in candidati if attiva(c) and chiave_busta(c) == chiave]


def gruppi_con_netti_diversi(righe: Iterable[Dict[str, Any]]) -> Dict[Chiave, List[Dict[str, Any]]]:
    gruppi: Dict[Chiave, List[Dict[str, Any]]] = defaultdict(list)
    for doc in righe:
        chiave = chiave_busta(doc)
        if chiave and doc.get("id") and attiva(doc):
            gruppi[chiave].append(doc)
    return {k: v for k, v in gruppi.items() if len({netto_di(d) for d in v}) > 1}


def _voce_gruppo(chiave: Chiave, gruppo: List[Dict[str, Any]], decisione: Dict[str, Any],
                 con_prima_nota: Set[str]) -> Dict[str, Any]:
    bloccate = {r["id"]: intoccabile(r, con_prima_nota) for r in decisione.get("perdenti", [])
                if intoccabile(r, con_prima_nota)}
    esito = decisione["esito"]
    motivo = decisione.get("motivo") or ""
    if esito == ESITO_VINCITORE and bloccate:
        esito = ESITO_DA_DECIDERE
        motivo = "la versione superata e' " + ", ".join(sorted(set(bloccate.values()))) + ": decide il titolare"
    return {
        "chiave": {"codice_fiscale": chiave[0][:6] + "***", "anno": chiave[1], "mese": chiave[2], "tipo": chiave[3]},
        "righe": [_riassunto(r) for r in sorted(gruppo, key=lambda r: str(r.get("created_at") or ""))],
        "esito": esito,
        "vincitore": (decisione.get("vincitore") or {}).get("id") if esito == ESITO_VINCITORE else None,
        "perdenti": [r["id"] for r in decisione.get("perdenti", [])] if esito == ESITO_VINCITORE else [],
        "motivo": motivo,
    }


async def rapporto_archivio(db) -> Dict[str, Any]:
    """Sola lettura: i gruppi con netti diversi e la decisione proposta."""
    from app.document_repository import metadata_projection

    righe = await db[COLL].find({}, metadata_projection(COLL)).to_list(None)
    con_prima_nota = await _ids_in_prima_nota(db)
    gruppi = gruppi_con_netti_diversi(righe)
    voci = [_voce_gruppo(chiave, gruppo, decidi(gruppo), con_prima_nota)
            for chiave, gruppo in sorted(gruppi.items())]
    conteggi: Dict[str, int] = defaultdict(int)
    for v in voci:
        conteggi[v["esito"]] += 1
    return {"righe_totali": len(righe), "gruppi": len(voci), "conteggi": dict(conteggi),
            "voci": voci, "dry_run": True}


async def applica(db, gruppo: List[Dict[str, Any]], decisione: Dict[str, Any], *,
                  con_prima_nota: Optional[Set[str]] = None, dry_run: bool = False,
                  aggiorna_hr: bool = True) -> Dict[str, Any]:
    """Scrive la decisione sulle righe del gruppo; mai cancellazioni.

    Con ``da_decidere`` (o una perdente intoccabile) marca tutte le righe
    ``varianti_da_decidere``; con un vincitore marca le perdenti
    ``sostituito`` e arricchisce il vincitore. ``dry_run`` non scrive.
    """
    if con_prima_nota is None:
        con_prima_nota = await _ids_in_prima_nota(db)
    chiave = chiave_busta(gruppo[0])
    voce = _voce_gruppo(chiave, gruppo, decisione, con_prima_nota)
    if dry_run:
        return voce
    now = _ora()
    if voce["esito"] == ESITO_DA_DECIDERE:
        for r in gruppo:
            await db[COLL].update_one({"id": r["id"]}, {"$set": {
                "varianti_da_decidere": True, "varianti_motivo": voce["motivo"],
                **marcatori(r), "updated_at": now}})
        return voce
    if voce["esito"] != ESITO_VINCITORE:
        return voce

    vincitore, perdenti = decisione["vincitore"], decisione["perdenti"]
    scartate = []
    for r in perdenti:
        motivo = voce["motivo"] or "versione superata"
        await db[COLL].update_one({"id": r["id"]}, {"$set": {
            "status": STATUS_SOSTITUITO, "sostituito_da": vincitore["id"],
            "sostituito_motivo": motivo, "sostituito_at": now,
            "varianti_da_decidere": False, **marcatori(r), "updated_at": now}})
        netto = netto_di(r)
        scartate.append({"id": r["id"], "filename": r.get("filename"),
                         "netto": float(netto) if netto is not None else None, "motivo": motivo})
    netto_vincitore = netto_di(vincitore)
    storico = [{"prima": s["netto"], "dopo": float(netto_vincitore) if netto_vincitore is not None else None,
                "at": now, "fonte": FONTE_STORICO, "id_precedente": s["id"]} for s in scartate]
    attuale = await db[COLL].find_one({"id": vincitore["id"]}, {"_id": 0, "versioni_scartate": 1,
                                                                 "storico_netto": 1}) or {}
    gia = [s for s in (attuale.get("versioni_scartate") or []) if s.get("id") not in {x["id"] for x in scartate}]
    patch = {
        "versioni_scartate": gia + scartate,
        "n_versioni_totali": len(gia) + len(gruppo),
        "rettificato": True,
        "storico_netto": list(attuale.get("storico_netto") or []) + storico,
        "varianti_da_decidere": False,
        **marcatori(vincitore), "updated_at": now,
    }
    await db[COLL].update_one({"id": vincitore["id"]}, {"$set": patch})
    voce["scartate"] = scartate
    if aggiorna_hr:
        # La riga HR segue il vincitore: netto aggiornato, il vecchio in storico_netto.
        try:
            from app.services.hr_cedolini_deposito import deposita_cedolino_in_hr
            completo = await db[COLL].find_one({"id": vincitore["id"]}, {"_id": 0}) or {}
            voce["hr"] = (await deposita_cedolino_in_hr({**completo, "rettificato": True})).get("esito")
        except Exception as exc:  # noqa: BLE001 - l'HR e' a valle, la decisione resta scritta
            logger.warning("Versione vincente %s non riportata in HR: %s: %s",
                           vincitore["id"], type(exc).__name__, exc)
            voce["hr"] = "errore"
    return voce


# ── all'arrivo di una busta ─────────────────────────────────────────────────

async def decidi_arrivo(db, busta: Dict[str, Any], *, filename: str) -> Dict[str, Any]:
    """Prima di scrivere la busta in arrivo: chi vince fra lei e le righe gia' in archivio.

    ``esito``: ``nessuna_versione`` (niente in archivio con netto diverso),
    ``arrivo_vincitore``, ``arrivo_perdente`` (con ``vincitore``),
    ``da_decidere``. ``esistenti`` e ``decisione`` servono ad ``applica_arrivo``.
    """
    esistenti = await righe_della_busta(db, busta)
    in_arrivo = {**busta, "id": None, "filename": filename, "pagato": False}
    if not esistenti or len({netto_di(r) for r in [*esistenti, in_arrivo]}) < 2:
        return {"esito": "nessuna_versione", "esistenti": esistenti, "decisione": None}
    decisione = decidi([*esistenti, in_arrivo])
    con_prima_nota = await _ids_in_prima_nota(db)
    if decisione["esito"] == ESITO_VINCITORE:
        perdenti_bloccate = [r for r in decisione["perdenti"] if r.get("id") and intoccabile(r, con_prima_nota)]
        if perdenti_bloccate:
            return {"esito": ESITO_DA_DECIDERE, "esistenti": esistenti, "decisione": decisione,
                    "motivo": "la versione superata e' " + ", ".join(
                        sorted({intoccabile(r, con_prima_nota) for r in perdenti_bloccate})) + ": decide il titolare"}
        if decisione["vincitore"] is in_arrivo:
            return {"esito": "arrivo_vincitore", "esistenti": esistenti, "decisione": decisione,
                    "motivo": decisione["motivo"]}
        if any(r is in_arrivo for r in decisione["perdenti"]):
            return {"esito": "arrivo_perdente", "esistenti": esistenti, "decisione": decisione,
                    "vincitore": decisione["vincitore"], "motivo": decisione["motivo"]}
        # La busta in arrivo ha lo stesso netto del vincitore: e' una sua copia
        # (doppioni_archivio), ma le perdenti vanno comunque superate.
        return {"esito": "arrivo_vincitore", "esistenti": esistenti, "decisione": decisione,
                "motivo": decisione["motivo"]}
    return {"esito": ESITO_DA_DECIDERE, "esistenti": esistenti, "decisione": decisione,
            "motivo": decisione.get("motivo") or ""}


async def applica_arrivo(db, arrivo: Dict[str, Any], cedolino_id: str) -> Dict[str, Any]:
    """Dopo che la busta in arrivo e' scritta con ``cedolino_id``: applica la decisione."""
    scritta = await db[COLL].find_one({"id": cedolino_id}, _PROIEZIONE)
    if not scritta:
        return {"esito": "riga_non_trovata"}
    gruppo = [*arrivo["esistenti"], scritta]
    if arrivo["esito"] == ESITO_DA_DECIDERE:
        decisione = {"esito": ESITO_DA_DECIDERE, "vincitore": None, "perdenti": [],
                     "motivo": arrivo.get("motivo") or ""}
        return await applica(db, gruppo, decisione)
    decisione = decidi(gruppo)
    return await applica(db, gruppo, decisione)


# ── giro a lotti sull'archivio ──────────────────────────────────────────────

def _chiave_testo(chiave: Chiave) -> str:
    return "|".join(str(c) for c in chiave)


async def giro(db, *, dry_run: bool = True, lotto: int = LOTTO) -> Dict[str, Any]:
    """Un lotto di gruppi per volta, stato in ``sistema_stato`` (``cedolini_versioni``).

    Con ``dry_run`` il lotto si valuta e basta: l'esito va nel campo
    ``simulazione`` dello stato, senza toccare l'avanzamento (``viste``). Senza,
    ogni gruppo lavorato entra in ``viste`` e il giro seguente riparte dai rimasti.
    """
    from app.document_repository import metadata_projection

    stato = await db["sistema_stato"].find_one({"chiave": CHIAVE_STATO}, {"_id": 0}) or {}
    if stato.get("versione") != VERSIONE:
        stato = {"chiave": CHIAVE_STATO, "versione": VERSIONE, "viste": [], "esiti": [], "conteggi": {}}
    viste = set(stato.get("viste") or [])

    righe = await db[COLL].find({}, metadata_projection(COLL)).to_list(None)
    gruppi = gruppi_con_netti_diversi(righe)
    con_prima_nota = await _ids_in_prima_nota(db)
    da_fare = [(k, g) for k, g in sorted(gruppi.items()) if _chiave_testo(k) not in viste][:lotto]

    conteggi: Dict[str, int] = {} if dry_run else dict(stato.get("conteggi") or {})
    esiti: List[Dict[str, Any]] = [] if dry_run else list(stato.get("esiti") or [])
    for chiave, gruppo in da_fare:
        try:
            voce = await applica(db, gruppo, decidi(gruppo), con_prima_nota=con_prima_nota, dry_run=dry_run)
        except Exception as exc:  # noqa: BLE001 - un gruppo non ferma il lotto
            logger.warning("Versioni cedolino %s non decise: %s: %s", _chiave_testo(chiave),
                           type(exc).__name__, exc)
            voce = {"chiave": _chiave_testo(chiave), "esito": "errore",
                    "motivo": f"{type(exc).__name__}: {exc}"}
        conteggi[voce["esito"]] = conteggi.get(voce["esito"], 0) + 1
        esiti.append(voce)
        if not dry_run:
            viste.add(_chiave_testo(chiave))
    now = _ora()
    rimasti = sum(1 for k in gruppi if _chiave_testo(k) not in viste)
    esito = {"lavorati": len(da_fare), "rimasti": rimasti, "gruppi": len(gruppi),
             "conteggi": conteggi, "dry_run": dry_run}
    if dry_run:
        stato.update({"simulazione": {**esito, "esiti": esiti[-500:], "at": now},
                      "gruppi": len(gruppi), "aggiornato_il": now})
    else:
        stato.update({"viste": sorted(viste), "esiti": esiti[-500:], "conteggi": conteggi,
                      "gruppi": len(gruppi), "rimasti": rimasti, "simulazione": None,
                      "aggiornato_il": now})
    await db["sistema_stato"].update_one({"chiave": CHIAVE_STATO}, {"$set": stato}, upsert=True)
    return esito


__all__ = [
    "STATUS_SOSTITUITO", "STATI_NON_ATTIVI", "CHIAVE_STATO", "decidi", "variante_di",
    "stampa_di_controllo", "chiave_busta", "attiva", "gruppi_con_netti_diversi",
    "rapporto_archivio", "applica", "decidi_arrivo", "applica_arrivo", "giro",
]
