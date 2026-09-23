"""Lo stesso movimento bancario scritto da due export diversi dello stesso conto.

Il vecchio archivio BPM importato a settembre scrive «REMUNERAZIONE DCC
03/26 …», l'export «Elenco entrate/uscite» della banca mette davanti la
categoria: «INC.POS CARTE CREDIT - REMUNERAZIONE DCC 03/26 …»; un assegno e'
«VOSTRO ASSEGNO N. 0208770635» da una parte e «PRELIEVO ASSEGNO - DM …
NUM: 0208770635» dall'altra. La chiave dell'import contiene la descrizione,
quindi il 23/09/2026 lo stesso gennaio–agosto e' entrato due volte (1.185
righe) e i motori a valle ne hanno ricavato Prima Nota ed esiti stipendio.

Due estratti dello **stesso conto** si confrontano come li confronta un
contabile: giorno, segno e importo al centesimo, e quante volte compaiono in
quel giorno. Dentro un giorno si accoppia prima la descrizione identica
(tolto il prefisso di categoria), poi il numero d'assegno, poi il resto in
ordine; **due assegni con numeri diversi non si accoppiano mai**. Le carte
(Nexi), PayPal e SumUp sono conti diversi e restano fuori.
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

COLLEZIONE = "estratto_conto_movimenti"
COLLEZIONE_QUARANTENA = "estratto_conto_movimenti_quarantena"

# Categoria che l'export «Elenco entrate/uscite» mette davanti alla causale.
_PREFISSO_CATEGORIA = re.compile(r"^[A-Z0-9 .,'/()]{2,40}? - ")
_NUMERO_ASSEGNO = re.compile(r"(?:ASSEGNO N\.?|NUM:)\s*(\d{6,})")


def conto_del_movimento(mov: Dict[str, Any]) -> str:
    """Il conto a cui appartiene la riga: le carte non sono il conto BPM."""
    banca = str(mov.get("banca") or "").lower()
    for conto in ("nexi", "paypal", "sumup"):
        if conto in banca:
            return conto
    if mov.get("tipo") == "carta_credito":
        return "nexi"
    return "bpm"


def _testo(mov: Dict[str, Any]) -> str:
    grezzo = mov.get("descrizione_originale") or mov.get("descrizione") or ""
    return re.sub(r"\s+", " ", str(grezzo)).strip().upper()


def descrizione_canonica(mov: Dict[str, Any]) -> str:
    return _PREFISSO_CATEGORIA.sub("", _testo(mov), count=1)


def numero_assegno(mov: Dict[str, Any]) -> Optional[str]:
    trovato = _NUMERO_ASSEGNO.search(_testo(mov))
    return trovato.group(1) if trovato else None


# Riferimento della banca («RIF. MB0B04742006/90192364», «RIF.MBVT40188610»)
# e codici lunghi della causale («W1052371461387/PAYPAL»): le due fonti li
# scrivono con parole e spazi diversi (l'API spezza la causale a larghezza
# fissa, il CSV aggiunge la nota del titolare), ma il codice e' quello.
_RIFERIMENTO = re.compile(r"RIF\.?\s*:?\s*([A-Z0-9][A-Z0-9/]{7,})")
_CODICE = re.compile(r"[A-Z0-9][A-Z0-9/\-]{9,}")


def codici(mov: Dict[str, Any]) -> set:
    """Codici che identificano l'operazione: lettere e cifre insieme, almeno
    10 caratteri. Restano fuori date, importi e numeri d'ordine di sole cifre,
    che due operazioni diverse possono condividere."""
    testo = _testo(mov)
    trovati = set()
    for token in _RIFERIMENTO.findall(testo) + _CODICE.findall(testo):
        token = token.strip("/-")
        cifre = sum(c.isdigit() for c in token)
        if len(token) >= 10 and cifre >= 3 and any(c.isalpha() for c in token):
            trovati.add(token)
    return trovati


def stesso_riferimento(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """Un codice dell'uno compare nel testo dell'altro (spazi esclusi)."""
    compatto_a = re.sub(r"\s+", "", _testo(a))
    compatto_b = re.sub(r"\s+", "", _testo(b))
    return any(c in compatto_b for c in codici(a)) or any(c in compatto_a for c in codici(b))


def _segno(mov: Dict[str, Any]) -> str:
    tipo = str(mov.get("tipo") or "").lower()
    if tipo in {"uscita", "entrata"}:
        return tipo
    try:
        return "uscita" if float(mov.get("importo") or 0) < 0 else "entrata"
    except (TypeError, ValueError):
        return "entrata"


def chiave_giorno(mov: Dict[str, Any]) -> Tuple[str, str, int, str]:
    try:
        centesimi = int(round(abs(float(mov.get("importo") or 0)) * 100))
    except (TypeError, ValueError):
        centesimi = -1
    return (str(mov.get("data") or "")[:10], _segno(mov), centesimi, conto_del_movimento(mov))


def accoppia(
    nuovi: Iterable[Dict[str, Any]], esistenti: Iterable[Dict[str, Any]],
) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """Coppie (nuovo, esistente) che sono la stessa riga dello stesso conto.

    Ogni esistente si usa una volta sola: tre addebiti uguali nello stesso
    giorno restano tre, e solo quelli in piu' rispetto all'altra fonte sono
    movimenti nuovi. Dentro il giorno vince prima il riferimento della banca:
    due commissioni da 1,10 dello stesso giorno, abbinate in ordine, finivano
    incrociate (ognuna col riferimento dell'altra).
    """
    per_giorno: Dict[Tuple, List[Dict[str, Any]]] = defaultdict(list)
    for mov in esistenti:
        per_giorno[chiave_giorno(mov)].append(mov)
    nuovi_per_giorno: Dict[Tuple, List[Dict[str, Any]]] = defaultdict(list)
    for mov in nuovi:
        nuovi_per_giorno[chiave_giorno(mov)].append(mov)

    coppie: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    for chiave, candidati in nuovi_per_giorno.items():
        liberi = list(per_giorno.get(chiave, []))
        if not liberi or chiave[2] < 0:
            continue
        rimasti = []
        for passo in ("riferimento", "testo", "assegno", "ordine"):
            ancora = []
            for nuovo in (candidati if passo == "riferimento" else rimasti):
                scelta = None
                for esistente in liberi:
                    a_nuovo, a_esistente = numero_assegno(nuovo), numero_assegno(esistente)
                    if a_nuovo and a_esistente and a_nuovo != a_esistente:
                        continue
                    if passo == "riferimento" and not stesso_riferimento(nuovo, esistente):
                        continue
                    if passo == "testo" and descrizione_canonica(nuovo) != descrizione_canonica(esistente):
                        continue
                    if passo == "assegno" and not (a_nuovo and a_nuovo == a_esistente):
                        continue
                    scelta = esistente
                    break
                if scelta is None:
                    ancora.append(nuovo)
                else:
                    liberi.remove(scelta)
                    coppie.append((nuovo, scelta))
            rimasti = ancora
            if not rimasti or not liberi:
                break
    return coppie


# ── pulizia dei doppioni gia' entrati ───────────────────────────────────────

# Import autorizzati alla pulizia dal titolare (23/09/2026, in chat): il solo
# CSV di quel giorno. Gli export del 16/09 si sovrappongono anch'essi al
# vecchio archivio ma non sono stati autorizzati: si contano, non si toccano.
IMPORT_AUTORIZZATI = ("ElencoEntrateUsciteAndamento_23-09-2026_08.54.25.csv",)

_PROIEZIONE_LEGGERA = {"_id": 0}


def _oggi() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _righe_prima_nota_da(db, ids: List[str]) -> List[Dict[str, Any]]:
    trovate: Dict[str, Dict[str, Any]] = {}
    for campo in ("estratto_conto_id", "movimento_bancario_id", "movimento_estratto_conto_id"):
        for riga in await db["prima_nota_banca"].find(
            {campo: {"$in": ids}, "status": {"$nin": ["deleted", "archived"]}},
            {"_id": 0, "id": 1, "fattura_id": 1, "fattura_ids": 1, "source": 1, campo: 1},
        ).to_list(len(ids) * 2 + 10):
            trovate[riga["id"]] = riga
    return list(trovate.values())


async def _storna_hr(ids: List[str], *, dry_run: bool) -> Dict[str, int]:
    """Esiti stipendio e code HR nati dai soli doppioni: il movimento
    originale aveva gia' prodotto il suo esito (o era stato giudicato non
    stipendio), quindi questi contano due volte lo stesso bonifico."""
    from app.services.hr_pagamenti_deposito import (
        PREFISSO_KEY_BANCA, _ricalcola_periodi, carica_contesto_hr,
    )

    ctx = await carica_contesto_hr()
    if ctx is None:
        return {"hr_non_configurato": 1}
    chiavi = {f"{PREFISSO_KEY_BANCA}:{mid}" for mid in ids}
    esiti = [ctx.per_key[k] for k in chiavi if k in ctx.per_key]
    coda = await ctx.db.bonifici_da_associare.find(
        {"gestionale_movimento_id": {"$in": ids}}, {"_id": 0, "id": 1},
    ).to_list(len(ids) + 10)
    if not dry_run:
        for esito in esiti:
            await ctx.db.pagamenti_esiti.delete_one({"key": esito["key"]})
            ctx.periodi_toccati.add(
                (esito["dipendente_id"], int(esito["anno"]), int(esito["mese"]))
            )
        for voce in coda:
            await ctx.db.bonifici_da_associare.delete_one({"id": voce["id"]})
        if esiti:
            await _ricalcola_periodi(ctx)
    return {"esiti_stipendio": len(esiti), "bonifici_da_associare": len(coda)}


async def ripulisci_import(
    db, source_filename: str, *, dry_run: bool = True, actor: str = "manutenzione",
) -> Dict[str, Any]:
    """Toglie le righe di un import che sono doppioni di un'altra fonte.

    Il doppione va in ``estratto_conto_movimenti_quarantena`` (copia intera,
    con ``duplicato_di``) e poi esce dall'estratto conto, per id. Le righe di
    Prima Nota Banca nate da lui si stornano (soft delete); quelle collegate a
    una fattura non si toccano e si elencano.
    """
    nuovi = await db[COLLEZIONE].find(
        {"source_filename": source_filename}, _PROIEZIONE_LEGGERA,
    ).to_list(20000)
    if not nuovi:
        return {"source_filename": source_filename, "righe_import": 0, "doppioni": 0}
    date = sorted(str(m.get("data") or "")[:10] for m in nuovi)
    esistenti = [
        m for m in await db[COLLEZIONE].find(
            {"data": {"$gte": date[0], "$lte": date[-1]}}, _PROIEZIONE_LEGGERA,
        ).to_list(50000)
        if m.get("source_filename") != source_filename
    ]
    coppie = accoppia(nuovi, esistenti)
    ids = [nuovo["id"] for nuovo, _ in coppie]
    righe_pn = await _righe_prima_nota_da(db, ids) if ids else []
    con_fattura = [r for r in righe_pn if r.get("fattura_id") or r.get("fattura_ids")]
    da_stornare = [r for r in righe_pn if r not in con_fattura]

    esito: Dict[str, Any] = {
        "source_filename": source_filename,
        "dry_run": dry_run,
        "righe_import": len(nuovi),
        "doppioni": len(coppie),
        "movimenti_nuovi_veri": len(nuovi) - len(coppie),
        "prima_nota_da_stornare": len(da_stornare),
        "prima_nota_con_fattura_non_toccate": [r["id"] for r in con_fattura][:50],
    }
    esito["hr"] = await _storna_hr(ids, dry_run=dry_run) if ids else {}
    if dry_run:
        esito["esempi"] = [
            {"nuovo": _testo(n)[:80], "originale": _testo(o)[:80],
             "data": n.get("data"), "importo": n.get("importo")}
            for n, o in coppie[:20]
        ]
        return esito

    adesso = _oggi()
    for riga in da_stornare:
        await db["prima_nota_banca"].update_one(
            {"id": riga["id"]},
            {"$set": {"status": "deleted", "deleted_at": adesso,
                      "deleted_reason": "doppione_estratto_conto_fra_export",
                      "deleted_by": actor}},
        )
    for nuovo, originale in coppie:
        await db[COLLEZIONE_QUARANTENA].update_one(
            {"id": nuovo["id"]},
            {"$set": {**nuovo, "duplicato_di": originale.get("id"),
                      "motivo_quarantena": "stesso movimento di un altro export dello stesso conto",
                      "quarantena_at": adesso, "quarantena_da": actor}},
            upsert=True,
        )
        await db[COLLEZIONE].delete_one({"id": nuovo["id"]})
    logger.info(
        "Doppioni estratto conto tolti da %s: %s in quarantena, %s righe Prima Nota stornate, HR %s",
        source_filename, len(coppie), len(da_stornare), esito["hr"],
    )
    return esito


async def applica(db, *, actor: str = "migrazione_avvio") -> Dict[str, Any]:
    """Una tantum: gli import autorizzati dal titolare."""
    return {
        nome: await ripulisci_import(db, nome, dry_run=False, actor=actor)
        for nome in IMPORT_AUTORIZZATI
    }


MARCATORE = "doppioni_estratto_conto_csv_20260923_v1"
_task_avvio = None


async def _applica_una_tantum(db) -> None:
    corrente = await db["migration_runs"].find_one({"id": MARCATORE})
    if corrente and corrente.get("status") == "completed":
        return
    stato = "failed"
    try:
        risultato = await applica(db, actor="migrazione_avvio")
        stato = "completed"
    except Exception as exc:  # noqa: BLE001 - l'esito resta in migration_runs
        logger.exception("Pulizia doppioni estratto conto non completata (%s)", type(exc).__name__)
        risultato = {"success": False, "reason": f"{type(exc).__name__}: {exc}"}
    await db["migration_runs"].update_one(
        {"id": MARCATORE},
        {"$set": {"id": MARCATORE, "status": stato,
                  "finished_at": _oggi(), "result": risultato}},
        upsert=True,
    )


def avvia_in_background(db) -> None:
    """All'avvio, fuori dal percorso dell'health check: sono centinaia di
    scritture e l'avvio non deve aspettarle."""
    import asyncio

    global _task_avvio
    if db is None or (_task_avvio is not None and not _task_avvio.done()):
        return
    _task_avvio = asyncio.create_task(_applica_una_tantum(db))
