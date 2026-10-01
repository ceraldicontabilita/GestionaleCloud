"""Collegamenti del protocollo Drive verso entita' che non ci sono piu' (DRV-03).

Il protocollo scrive ``collegamento_tipo/collegamento_id`` sulla riga di ogni file
che riconosce come originale di una fattura, un modello F24 o una quietanza. Se
quell'entita' viene poi fusa con una copia dello stesso contenuto (la stessa
quietanza stampata due volte e' una sola, ``f24_doppioni``), il suo id sparisce e
il collegamento resta puntato nel vuoto: un protocollo non dimentica, quindi la riga
di Drive non va toccata altro che per **riagganciarla**, per id, alla entita' che ha
preso il suo posto.

Il riaggancio e' certo solo con una prova di identita' del *file*:

* l'entita' porta fra le sue ``source_occurrences`` (o come ``drive_md5`` /
  ``pdf_hash``) l'MD5 di quel file Drive, e una sola entita' viva dello stesso tipo
  lo porta; oppure
* l'entita' scomparsa e' in quarantena e dichiara lei stessa ``doppione_di`` una
  entita' viva.

Zero candidati o piu' di uno: si elenca (``senza_entita``, ``ambigui``), non si
applica. L'MD5 qui serve solo a ritrovare la copia identica su Drive (regola di
progetto), mai a decidere altro. Niente si cancella: l'UPDATE tocca una riga per
``drive_id`` e solo se il collegamento e' ancora quello letto. ``dry_run`` per
difetto; secondo giro 0.
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence, Set

from app.services.relazioni_documentali import (
    SORGENTI, TIPI_COLLEGAMENTO, entita_viva, _id_di, _t)

logger = logging.getLogger(__name__)

CHIAVE_STATO = "protocollo_collegamenti"
ESEMPI_MAX = 50
# i tipi del protocollo che hanno un archivio dove cercare l'entita' che ha preso il posto
_COLLEZIONI = {s.tipo: s for s in SORGENTI if s.tipo in ("invoice", "f24_model", "f24_receipt")}
_MD5_RE = re.compile(r"^[0-9a-f]{32}$")
SQL_RIAGGANCIA = (
    "update gestionale.protocollo_drive set collegamento_id = $3, aggiornato_il = now() "
    "where drive_id = $1 and collegamento_tipo = $2 and collegamento_id = $4"
)


def _md5_dell_entita(doc: Dict[str, Any]) -> Dict[str, str]:
    """md5 -> come lo porta l'entita': ``propria`` o ``occorrenza``."""
    out: Dict[str, str] = {}
    for campo in ("drive_md5", "pdf_hash"):
        h = _t(doc.get(campo)).lower()
        if _MD5_RE.match(h):
            out[h] = "propria"
    occorrenze = doc.get("source_occurrences")
    for occ in occorrenze if isinstance(occorrenze, list) else []:
        if isinstance(occ, dict):
            h = _t(occ.get("md5")).lower()
            if _MD5_RE.match(h):
                out.setdefault(h, "occorrenza")
    return out


async def _archivio_per_tipo(db) -> Dict[str, Dict[str, Any]]:
    """Per tipo: tutti gli id che esistono (con lo stato), gli id vivi, md5 -> id vivi."""
    risultato: Dict[str, Dict[str, Any]] = {}
    for tipo, s in _COLLEZIONI.items():
        righe = await db[s.collezione].find({}, {
            "_id": 1, "id": 1, "status": 1, "stato_import": 1, "entity_status": 1, "deleted": 1,
            "drive_md5": 1, "pdf_hash": 1, "source_occurrences": 1, "doppione_di": 1}).to_list(length=None)
        esistenti: Dict[str, Dict[str, Any]] = {}
        vivi: Set[str] = set()
        per_md5: Dict[str, Dict[str, str]] = defaultdict(dict)
        for doc in righe:
            ident = _id_di(doc, s.id_preferito)
            if not ident:
                continue
            viva = entita_viva(s, doc)
            for chiave in {ident, _t(doc.get("id"))} - {""}:
                esistenti[chiave] = {"viva": viva, "doppione_di": _t(doc.get("doppione_di")), "id": ident}
            if viva:
                vivi.add(ident)
                for h, come in _md5_dell_entita(doc).items():
                    per_md5[h][ident] = come
        risultato[tipo] = {"esistenti": esistenti, "vivi": vivi, "per_md5": per_md5}
    return risultato


def decidi(righe_protocollo: Sequence[Dict[str, Any]], archivio: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Per ogni collegamento verso un'entita' non viva: riaggancio certo, senza entita', ambiguo."""
    conteggi: Dict[str, int] = defaultdict(int)
    riagganci: List[Dict[str, Any]] = []
    senza: List[Dict[str, Any]] = []
    ambigui: List[Dict[str, Any]] = []
    for r in righe_protocollo:
        tipo = TIPI_COLLEGAMENTO.get(_t(r.get("collegamento_tipo")))
        if tipo not in _COLLEZIONI:
            continue
        a = archivio[tipo]
        vecchio = _t(r.get("collegamento_id"))
        if not vecchio:
            continue
        conteggi["collegamenti_controllati"] += 1
        if vecchio in a["vivi"]:
            conteggi["vivi"] += 1
            continue
        conteggi["orfani"] += 1
        stato_vecchio = a["esistenti"].get(vecchio)
        conteggi["id_ancora_presente_ma_fuori" if stato_vecchio else "id_scomparso"] += 1
        drive_id, md5 = _t(r.get("drive_id")), _t(r.get("md5")).lower()
        voce = {"drive_id": drive_id, "tipo": _t(r.get("collegamento_tipo")), "id_vecchio": vecchio}
        candidati: Dict[str, str] = {}
        if stato_vecchio and stato_vecchio["doppione_di"] in a["vivi"]:
            candidati[stato_vecchio["doppione_di"]] = "doppione_di"
        if _MD5_RE.match(md5):
            for ident, come in a["per_md5"].get(md5, {}).items():
                candidati.setdefault(ident, f"md5_{come}")
        if len(candidati) == 1:
            nuovo, prova = next(iter(candidati.items()))
            riagganci.append({**voce, "id_nuovo": nuovo, "prova": prova})
            conteggi[f"riagganciabili_{prova}"] += 1
        elif not candidati:
            senza.append({**voce, "motivo": "nessuna_entita_viva_con_questo_file"})
        else:
            ambigui.append({**voce, "candidati": sorted(candidati)})
    conteggi["riagganciabili"] = len(riagganci)
    conteggi["senza_entita"] = len(senza)
    conteggi["ambigui"] = len(ambigui)
    return {"conteggi": dict(conteggi), "riagganci": riagganci, "senza_entita": senza, "ambigui": ambigui}


async def esegui(db, *, dry_run: bool = True, protocollo: Optional[Sequence[Dict[str, Any]]] = None,
                 conn=None) -> Dict[str, Any]:
    """Anteprima o riaggancio. ``protocollo`` (righe attive canoniche) e ``conn`` si iniettano nei test."""
    from app.services import postgres_diretto
    from app.services.relazioni_documentali import leggi_protocollo

    if protocollo is None:
        protocollo = await leggi_protocollo()
    if protocollo is None:
        return {"dry_run": dry_run, "protocollo": "non_disponibile"}
    archivio = await _archivio_per_tipo(db)
    esito = decidi(protocollo, archivio)
    applicati = 0
    if not dry_run and esito["riagganci"]:
        chiudi = conn is None
        if conn is None:
            dsn = postgres_diretto.dsn()
            if not dsn:
                return {"dry_run": dry_run, "protocollo": "non_disponibile", **esito["conteggi"]}
            conn = await postgres_diretto.connetti(dsn)
        try:
            for v in esito["riagganci"]:
                risposta = await conn.execute(
                    SQL_RIAGGANCIA, v["drive_id"], v["tipo"], v["id_nuovo"], v["id_vecchio"])
                try:
                    applicati += int(str(risposta).split()[-1])
                except (ValueError, IndexError):
                    logger.warning("Riaggancio protocollo: esito non leggibile (%s)", type(risposta).__name__)
        finally:
            if chiudi:
                await conn.close()
    return {
        "dry_run": dry_run, "protocollo": "letto", **esito["conteggi"], "applicati": applicati,
        "esempi_riagganci": esito["riagganci"][:ESEMPI_MAX],
        "senza_entita_elenco": esito["senza_entita"][:ESEMPI_MAX],
        "ambigui_elenco": esito["ambigui"][:ESEMPI_MAX],
    }


__all__ = ["CHIAVE_STATO", "decidi", "esegui"]
