"""Bonifica del solo ``canale`` sulle buste gia' in archivio (MINI-09.6).

Le buste scritte prima di MINI-01 non portano ``canale``. Qui lo si ricava dai
campi storici con **il normalizzatore unico** (``canale_documento.canale_ricavabile``,
costruito su ``canale_da_fonte``) e si scrive solo dove manca:

* la prima copia arrivata fissa il canale: una busta che ha gia' ``canale`` non si
  tocca mai, neppure se un'altra prova dice altro;
* se nessun campo lo dice resta vuoto (conteggiato ``non_ricavabile``): non si inventa;
* ``netto_fonte`` e il netto non si toccano (restano «Dato non disponibile»
  finche' il lettore per posizione del Libro Unico non c'e');
* ``dry_run`` per difetto; secondo giro 0; a lotti (``limite``) e riprendibile.

Due archivi, due chiavi (regola 10): il gestionale (collezione ``cedolini``, per
``id``) e HR (``app_cedolini``, ``id`` testo). Una riga HR che non dice niente di
suo prende il canale della busta del gestionale con la stessa
``cedolino_dedup_key``, solo se e' una sola.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from app.constants.canale_documento import CANALI, canale_da_fonte, canale_ricavabile

logger = logging.getLogger(__name__)

CHIAVE_STATO = "canale_cedolini_bonifica"
LIMITE_PREDEFINITO = 500
NON_RICAVABILE = "non_ricavabile"
ESEMPI_MAX = 20

PROIEZIONE_ERP = {
    "_id": 1, "id": 1, "canale": 1, "fonte": 1, "source": 1, "origine": 1, "import_source": 1,
    "source_module": 1, "source_container": 1, "source_path": 1, "drive_file_id": 1,
    "email_info": 1, "gmail_message_id": 1, "email_id": 1, "source_occurrences": 1,
    "cedolino_dedup_key": 1, "status": 1,
}
# HR: solo campi piccoli (mai `pdf_data`).
SQL_HR_LETTURA = (
    "select id, doc->>'canale' as canale, doc->>'fonte' as fonte, doc->>'source' as source, "
    "doc->>'origine' as origine, doc->>'import_source' as import_source, "
    "doc->>'source_container' as source_container, doc->>'gestionale_source' as gestionale_source, "
    "doc->>'source_path' as source_path, doc->>'drive_file_id' as drive_file_id, "
    "doc->>'cedolino_dedup_key' as cedolino_dedup_key from {tabella}"
)
# Mai sovrascrivere: se nel frattempo e' arrivato un canale, la riga non cambia.
SQL_HR_SCRIVI = ("update {tabella} set doc = doc || jsonb_build_object('canale', $2::text) "
                 "where id = $1 and coalesce(doc->>'canale', '') = ''")


def _t(valore: Any) -> str:
    return str(valore).strip() if valore is not None else ""


def _id_erp(doc: Dict[str, Any]) -> str:
    return _t(doc.get("id")) or _t(doc.get("_id"))


def _sintesi(esempi: List[Dict[str, Any]], archivio: str, ident: str, regola: Optional[str],
             canale: Optional[str]) -> None:
    # Solo id e regola: i nomi dei file contengono nomi di persona.
    if len(esempi) < ESEMPI_MAX:
        esempi.append({"archivio": archivio, "id": ident, "canale": canale, "regola": regola})


def decidi_erp(righe: List[Dict[str, Any]]) -> Tuple[List[Tuple[str, str, str]], Dict[str, Any]]:
    """Per ogni busta del gestionale: ``(id, canale, regola)`` da scrivere, e i contatori."""
    da_scrivere: List[Tuple[str, str, str]] = []
    per_canale: Counter = Counter()
    per_regola: Counter = Counter()
    gia = non_ricavabili = 0
    esempi_non: List[Dict[str, Any]] = []
    for doc in righe:
        ident = _id_erp(doc)
        if not ident:
            continue
        if canale_da_fonte(doc.get("canale")):
            gia += 1
            continue
        canale, regola = canale_ricavabile(doc)
        if not canale:
            non_ricavabili += 1
            _sintesi(esempi_non, "gestionale", ident, None, None)
            continue
        per_canale[canale] += 1
        per_regola[regola or ""] += 1
        da_scrivere.append((ident, canale, regola or ""))
    return da_scrivere, {
        "righe": len(righe), "gia_con_canale": gia, "da_scrivere": len(da_scrivere),
        "per_canale": {c: per_canale.get(c, 0) for c in CANALI},
        "per_regola": dict(sorted(per_regola.items())),
        NON_RICAVABILE: non_ricavabili, "esempi_non_ricavabili": esempi_non,
    }


def decidi_hr(righe: List[Dict[str, Any]], canale_per_chiave: Dict[str, str]) -> Tuple[List[Tuple[str, str, str]], Dict[str, Any]]:
    """Come ``decidi_erp`` per le righe HR; ``canale_per_chiave`` = canale della busta del
    gestionale con la stessa ``cedolino_dedup_key`` (solo le chiavi con una busta sola)."""
    da_scrivere: List[Tuple[str, str, str]] = []
    per_canale: Counter = Counter()
    per_regola: Counter = Counter()
    gia = non_ricavabili = 0
    esempi_non: List[Dict[str, Any]] = []
    for riga in righe:
        ident = _t(riga.get("id"))
        if not ident:
            continue
        if canale_da_fonte(riga.get("canale")):
            gia += 1
            continue
        canale, regola = canale_ricavabile(riga)
        if canale in (None, "altro"):
            ponte = canale_per_chiave.get(_t(riga.get("cedolino_dedup_key")))
            if ponte and canale is None:
                canale, regola = ponte, "gemella_gestionale"
        if not canale:
            non_ricavabili += 1
            _sintesi(esempi_non, "hr", ident, None, None)
            continue
        per_canale[canale] += 1
        per_regola[regola or ""] += 1
        da_scrivere.append((ident, canale, regola or ""))
    return da_scrivere, {
        "righe": len(righe), "gia_con_canale": gia, "da_scrivere": len(da_scrivere),
        "per_canale": {c: per_canale.get(c, 0) for c in CANALI},
        "per_regola": dict(sorted(per_regola.items())),
        NON_RICAVABILE: non_ricavabili, "esempi_non_ricavabili": esempi_non,
    }


def _canale_per_chiave(righe_erp: List[Dict[str, Any]], decisi: List[Tuple[str, str, str]]) -> Dict[str, str]:
    """Chiave di dedup -> canale della busta del gestionale (scritto o appena deciso).
    Due buste con la stessa chiave e canali diversi non danno ponte: ambiguo."""
    nuovo = {i: c for i, c, _ in decisi}
    visti: Dict[str, set] = {}
    for doc in righe_erp:
        chiave = _t(doc.get("cedolino_dedup_key"))
        if not chiave:
            continue
        canale = canale_da_fonte(doc.get("canale")) or nuovo.get(_id_erp(doc))
        if canale:
            visti.setdefault(chiave, set()).add(canale)
    return {k: next(iter(v)) for k, v in visti.items() if len(v) == 1}


async def _righe_hr(con, tabella: str) -> List[Dict[str, Any]]:
    return [dict(r) for r in await con.fetch(SQL_HR_LETTURA.format(tabella=tabella))]


async def esegui(db, *, dry_run: bool = True, limite: int = LIMITE_PREDEFINITO,
                 hr_con=None, tabella_hr: Optional[str] = None) -> Dict[str, Any]:
    """Anteprima o scrittura. ``hr_con`` e' una connessione asyncpg (o finta nei test);
    senza, l'HR non e' raggiungibile e si dichiara (mai un conteggio a zero al suo posto)."""
    righe_erp = await db["cedolini"].find({}, PROIEZIONE_ERP).to_list(length=None)
    righe_erp = [r for r in righe_erp if _t(r.get("status")).lower() not in {"eliminato"}]
    da_erp, esito_erp = decidi_erp(righe_erp)

    esito_hr: Dict[str, Any] = {"stato": "non_raggiungibile"}
    da_hr: List[Tuple[str, str, str]] = []
    if hr_con is not None and tabella_hr:
        try:
            righe_hr = await _righe_hr(hr_con, tabella_hr)
            da_hr, esito_hr = decidi_hr(righe_hr, _canale_per_chiave(righe_erp, da_erp))
            esito_hr["stato"] = "letto"
        except Exception as exc:  # noqa: BLE001 - l'HR e' a valle: si dichiara, non si azzera
            logger.warning("Bonifica canale: HR non letto: %s: %s", type(exc).__name__, exc)
            esito_hr = {"stato": "errore", "errore": f"{type(exc).__name__}: {exc}"}

    scritte_erp = scritte_hr = 0
    if not dry_run:
        budget = max(0, int(limite))
        for ident, canale, _regola in da_erp[:budget]:
            # `$in: [None]` non prende il campo assente (regola 11): la riga e' stata
            # appena letta senza canale, il filtro e' il solo id.
            await db["cedolini"].update_one({"id": ident}, {"$set": {"canale": canale}})
            scritte_erp += 1
        budget -= scritte_erp
        if hr_con is not None and tabella_hr and da_hr and budget > 0:
            for ident, canale, _regola in da_hr[:budget]:
                await hr_con.execute(SQL_HR_SCRIVI.format(tabella=tabella_hr), ident, canale)
                scritte_hr += 1
    return {
        "dry_run": dry_run, "limite": limite,
        "gestionale": esito_erp, "hr": esito_hr,
        "scritte_gestionale": scritte_erp, "scritte_hr": scritte_hr,
        "restanti": len(da_erp) + len(da_hr) - scritte_erp - scritte_hr,
        "netto_fonte": "non toccato",
    }


async def giro(db, *, dry_run: bool = True, limite: int = LIMITE_PREDEFINITO) -> Dict[str, Any]:
    """Il giro vero: apre HR se configurato, esegue, chiude. Lo stato resta in ``sistema_stato``."""
    from app.services import hr_cedolini_deposito as deposito

    con = None
    dsn = deposito.dsn_hr()
    if dsn:
        try:
            con = await deposito.connetti_hr(dsn)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Bonifica canale: connessione HR non riuscita: %s: %s", type(exc).__name__, exc)
    try:
        esito = await esegui(db, dry_run=dry_run, limite=limite, hr_con=con,
                             tabella_hr=deposito.TABELLA_CEDOLINI if con is not None else None)
    finally:
        if con is not None:
            try:
                await con.close()
            except Exception as exc:  # noqa: BLE001
                logger.debug("Bonifica canale: chiusura HR non riuscita: %s", type(exc).__name__)
    await db["sistema_stato"].update_one(
        {"chiave": CHIAVE_STATO},
        {"$set": {"chiave": CHIAVE_STATO, "esito": json.loads(json.dumps(esito, default=str)),
                  "errore": None, "in_corso": False}}, upsert=True)
    return esito


__all__ = ["CHIAVE_STATO", "decidi_erp", "decidi_hr", "esegui", "giro"]
