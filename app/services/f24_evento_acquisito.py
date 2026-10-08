"""L'evento ``f24.acquisito``: un fatto, pubblicato una volta sola, da ogni ingresso.

Un modello F24 che entra in archivio (posta, Drive, Documenti > Import,
creazione a mano) e' il fatto autorevole che apre il debito verso l'Erario:
l'handler ``on_f24_acquisito_crea_partita`` crea la partita aperta e, se la
scadenza e' vicina, l'alert ``F24_NON_PAGATO``/``F24_SCADUTO``;
``on_f24_acquisito_riprocessa`` cerca subito l'addebito in banca. Fino al
02/10/2026 l'evento partiva solo da ``POST /api/f24`` (creazione a mano):
nessun modello importato aveva la partita ne' l'alert.

Regole:

* il payload si costruisce **solo** qui (``costruisci_evento_f24_acquisito``),
  con le chiavi che gli handler leggono (``importo_totale``, ``data_scadenza``,
  ``periodo``, ``codice_tributo``); la scadenza e' quella delle righe a debito
  (``scadenza_modello``), mai inventata;
* lo pubblica ``salva_f24`` alla **prima** scrittura del modello: una copia
  successiva (stessa chiave, stesso contenuto) non lo ripubblica;
* **mai da una quietanza**: la quietanza e' una prova, non il fatto che crea
  l'obbligo (``e_quietanza``);
* il pregresso si recupera con ``ripubblica_f24_acquisito`` (admin,
  ``dry_run`` per difetto, in sottofondo, stato in ``sistema_stato``): lo
  stesso evento sugli stessi handler idempotenti (``crea_partita`` per
  documento e tipo, ``genera_alert`` per codice ed entita'). Un modello gia'
  provato in banca non rientra: la partita nascerebbe aperta su un debito
  gia' chiuso, e nessun motore la chiuderebbe piu'.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "MARCATORE_RIPUBBLICAZIONE",
    "costruisci_evento_f24_acquisito",
    "e_quietanza",
    "pubblica_f24_acquisito",
    "ripubblica_f24_acquisito",
    "avvia_ripubblicazione",
    "stato_ripubblicazione",
]

COLL_F24 = "f24_unificato"
COLL_PARTITE = "partite_aperte"
TIPO_PARTITA_F24 = "f24"
STATI_PARTITA_APERTA = ("aperta", "parziale")
STATI_MODELLO_ESCLUSI = frozenset({"eliminato", "deleted", "archiviato", "quarantena"})
#: Marcatore del replay: un modello che l'handler ha deciso di non aprire
#: (saldo zero, compensazione) non torna candidato a ogni giro.
MARCATORE_RIPUBBLICAZIONE = "evento_acquisito_ripubblicato_at"
_CHIAVE_JOB = "replay_f24_acquisito"
_PROIEZIONE = {"_id": 0, "pdf_data": 0}

_job_lock = asyncio.Lock()
_job_task: Optional[asyncio.Task] = None


def e_quietanza(doc: Dict[str, Any]) -> bool:
    """Una quietanza (o la stampa del Cassetto) non e' un modello: non apre un debito."""
    dg = doc.get("dati_generali") or {}
    natura = str(doc.get("natura_documento") or dg.get("natura_documento") or "").upper()
    if "QUIETANZA" in natura:
        return True
    categoria = str(doc.get("category") or doc.get("tipo_documento") or "").lower()
    return "quietanza" in categoria


def _importo_totale(doc: Dict[str, Any]) -> Optional[float]:
    from app.services.f24_controllo_incrociato import euro, saldo_modello_cents

    cents = saldo_modello_cents(doc)
    if cents is None:
        try:
            cents = int((Decimal(str(doc.get("importo") or 0)) * 100).quantize(Decimal("1")))
        except (ArithmeticError, ValueError):
            cents = None
    return euro(cents) if cents else None


def _codici_e_periodo(doc: Dict[str, Any]) -> tuple[str, str]:
    from app.services.f24_controllo_incrociato import righe_modello

    righe = righe_modello(doc)
    codici: List[str] = []
    periodi: List[str] = []
    for r in righe:
        if r["codice"] and r["codice"] not in codici:
            codici.append(r["codice"])
        periodo = r.get("periodo_riferimento") or ""
        if periodo and periodo not in periodi:
            periodi.append(periodo)
    if not codici:
        manuali = doc.get("codici_tributo") or []
        codici = [str(c) for c in manuali] if isinstance(manuali, list) else [str(manuali)]
    periodo = str(doc.get("periodo_riferimento") or "") or ", ".join(periodi)
    return ", ".join(c for c in codici if c), periodo


def _data_scadenza(doc: Dict[str, Any]) -> Optional[str]:
    """La scadenza dichiarata a mano o quella delle righe a debito; altrimenti nessuna."""
    manuale = str(doc.get("scadenza") or doc.get("data_scadenza") or "").strip()
    if manuale:
        return manuale
    from app.services.scadenzario_tributi import scadenza_modello

    scadenza, _fonte = scadenza_modello(doc)
    return scadenza.isoformat() if scadenza else None


def costruisci_evento_f24_acquisito(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Il payload di ``f24.acquisito``: lo stesso per ogni ingresso e per il replay."""
    codice_tributo, periodo = _codici_e_periodo(doc)
    return {
        "f24_id": doc.get("id"),
        "importo_totale": _importo_totale(doc),
        "data_scadenza": _data_scadenza(doc),
        "periodo": periodo,
        "codice_tributo": codice_tributo,
        "data_acquisizione": doc.get("created_at") or doc.get("import_date"),
    }


async def pubblica_f24_acquisito(db, doc: Dict[str, Any], *, source_module: str) -> bool:
    """Pubblica l'evento per un modello appena scritto. Mai per una quietanza.

    Un guasto di un handler non annulla l'import del modello: resta nel log
    con il tipo dell'eccezione.
    """
    if not doc.get("id") or e_quietanza(doc):
        return False
    from app.services.event_bus import EventTypes, propagate_event

    try:
        await propagate_event(EventTypes.F24_ACQUISITO, costruisci_evento_f24_acquisito(doc), db,
                              source_module=source_module)
        return True
    except Exception as exc:  # noqa: BLE001 - il modello resta importato
        logger.exception("f24.acquisito non propagato per %s (%s)", doc.get("id"), type(exc).__name__)
        return False


# ── Il pregresso ───────────────────────────────────────────────────────────

def _modello_candidato(f24: Dict[str, Any]) -> bool:
    from app.services.f24_payment_evidence import stato_evidenza_pagamento

    if str(f24.get("status") or "").lower() in STATI_MODELLO_ESCLUSI:
        return False
    if f24.get("entity_status") == "deleted" or e_quietanza(f24):
        return False
    if f24.get(MARCATORE_RIPUBBLICAZIONE):
        return False
    return not stato_evidenza_pagamento(f24)["verificato_banca"]


async def _modelli_senza_partita(db) -> List[Dict[str, Any]]:
    """Un prefetch per collezione, poi il confronto in memoria (§4)."""
    con_partita = set()
    async for p in db[COLL_PARTITE].find(
        {"documento_collection": COLL_F24, "tipo": TIPO_PARTITA_F24},
        {"_id": 0, "documento_id": 1, "stato": 1},
    ):
        if p.get("documento_id") and str(p.get("stato") or "") in STATI_PARTITA_APERTA + ("chiusa",):
            con_partita.add(str(p["documento_id"]))
    candidati = []
    async for f24 in db[COLL_F24].find({}, _PROIEZIONE):
        if str(f24.get("id") or "") in con_partita or not _modello_candidato(f24):
            continue
        candidati.append(f24)
    return candidati


async def ripubblica_f24_acquisito(db, *, dry_run: bool = True) -> Dict[str, Any]:
    """Ripubblica ``f24.acquisito`` per i modelli rimasti senza partita aperta."""
    candidati = await _modelli_senza_partita(db)
    esito: Dict[str, Any] = {"dry_run": dry_run, "candidati": len(candidati), "ripubblicati": 0,
                             "errori": 0, "motivi_errore": [],
                             "ids": [str(f.get("id")) for f in candidati[:200]]}
    if dry_run:
        return esito
    for f24 in candidati:
        if await pubblica_f24_acquisito(db, f24, source_module="replay_pregresso"):
            await db[COLL_F24].update_one({"id": f24["id"]}, {"$set": {
                MARCATORE_RIPUBBLICAZIONE: datetime.now(timezone.utc).isoformat()}})
            esito["ripubblicati"] += 1
        else:
            esito["errori"] += 1
            if len(esito["motivi_errore"]) < 10:
                esito["motivi_errore"].append(str(f24.get("id")))
    return esito


async def _salva_stato(db, **campi) -> None:
    await db["sistema_stato"].update_one(
        {"chiave": _CHIAVE_JOB},
        {"$set": {**campi, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )


async def _esegui(db, dry_run: bool) -> None:
    async with _job_lock:
        iniziato = datetime.now(timezone.utc).isoformat()
        await _salva_stato(db, stato="in_corso", dry_run=dry_run, iniziato_at=iniziato,
                           terminato_at=None, risultato=None, errore=None)
        try:
            risultato = await ripubblica_f24_acquisito(db, dry_run=dry_run)
            await _salva_stato(db, stato="completato", dry_run=dry_run, iniziato_at=iniziato,
                               terminato_at=datetime.now(timezone.utc).isoformat(),
                               risultato=risultato, errore=None)
        except Exception as exc:  # noqa: BLE001 - l'esito va scritto, non nascosto
            logger.exception("Replay f24.acquisito fallito (%s)", type(exc).__name__)
            await _salva_stato(db, stato="errore", dry_run=dry_run, iniziato_at=iniziato,
                               terminato_at=datetime.now(timezone.utc).isoformat(),
                               risultato=None, errore=f"{type(exc).__name__}: {exc}")


async def avvia_ripubblicazione(db, *, dry_run: bool = True) -> Dict[str, Any]:
    """Avvia il replay in sottofondo (oltre i 5 minuti il proxy Render taglia la richiesta)."""
    global _job_task
    if _job_lock.locked() or (_job_task is not None and not _job_task.done()):
        return {"avviato": False, **await stato_ripubblicazione(db)}
    _job_task = asyncio.create_task(_esegui(db, dry_run))
    return {"avviato": True, "stato": "avvio", "dry_run": dry_run}


async def stato_ripubblicazione(db) -> Dict[str, Any]:
    stato = await db["sistema_stato"].find_one({"chiave": _CHIAVE_JOB}, {"_id": 0})
    if not stato:
        return {"stato": "mai_avviato"}
    stato.pop("chiave", None)
    return stato
