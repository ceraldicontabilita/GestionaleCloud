"""Recupero del pregresso sulle fatture gia' in archivio.

Due riparazioni, entrambe nate da difetti misurati il 19/09/2026.

**1. Le scadenze sostituite dal ripiego.** Il canale automatico calcolava
`data_scadenza` come data fattura + 30 giorni anche quando l'XML ne
dichiarava una. Le `pagamento_rate` sono rimaste sulla fattura, quindi la
scadenza vera si ricalcola da li' senza rileggere nulla: 414 fatture attive
del canale Drive, 390 anticipate in media di 29 giorni e 24 posticipate fino
a 58.

**2. L'evento `fattura.created` mai propagato.** L'import massivo del
14/09/2026 05:27 (249 fatture) e le fatture entrate dal Drive senza
`data_documento` (47) non hanno fatto scattare nessuno dei suoi handler:
niente partita aperta verso il fornitore, niente alert, niente audit. Sono
296 fatture per 173.184,83 EUR e 22.989,82 EUR di IVA.

Il recupero **ripubblica lo stesso evento sugli stessi handler**, con lo
stesso payload dell'import (`costruisci_evento_fattura_created`): non e' un
secondo motore che rifa' il lavoro a mano. Gli handler sono idempotenti —
`crea_partita` per `documento_id`+`tipo`, `genera_alert` per
codice+entita — quindi rilanciarlo non duplica. L'audit invece registra
davvero una riga nuova, con `fonte` che dice che e' un replay: e' storia
onesta, non la data di creazione falsificata.

**Cosa non si tocca.** Le fatture di anni precedenti archiviate di proposito
da `archivia_fattura_storica` (`stato_import == "archivio_storico"`) non
hanno mai dovuto propagare l'evento: e' una scelta del titolare, non un
difetto, e il replay le salta.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services.eventi_fattura import costruisci_evento_fattura_created
from app.services.scadenza_fattura import scadenza_sintetica

logger = logging.getLogger(__name__)

__all__ = [
    "STATI_NON_ATTIVI",
    "ricalcola_scadenze",
    "ripubblica_fattura_created",
    "avvia_ripubblicazione",
    "stato_ripubblicazione",
]

COLL = "invoices"
COLL_PARTITE = "partite_aperte"
_CHIAVE_JOB = "replay_fattura_created"

#: In archivio convivono due parole per lo stesso stato.
STATI_NON_ATTIVI = frozenset({"archived", "archiviata"})

#: Marcatore delle fatture storiche archiviate di proposito: per loro
#: l'evento non e' mai stato propagato per scelta.
STATO_ARCHIVIO_STORICO = "archivio_storico"

_PROIEZIONE = {
    "_id": 0, "id": 1, "invoice_number": 1, "invoice_date": 1,
    "supplier_id": 1, "supplier_name": 1, "supplier_vat": 1, "fornitore": 1,
    "tipo_documento": 1, "total_amount": 1, "imponibile": 1, "iva": 1,
    "metodo_pagamento": 1, "data_scadenza": 1, "pagamento_rate": 1,
    "pagamento_rate_coerente": 1, "status": 1, "stato_pagamento": 1,
    "stato_import": 1, "linee": 1,
}

_job_lock = asyncio.Lock()
_job_task: Optional[asyncio.Task] = None


def _e_attiva(fattura: Dict[str, Any]) -> bool:
    return (fattura.get("status") or "") not in STATI_NON_ATTIVI


def _e_archivio_storico(fattura: Dict[str, Any]) -> bool:
    return (fattura.get("stato_import") or "") == STATO_ARCHIVIO_STORICO


# ── 1. Scadenze da ricalcolare ─────────────────────────────────────────────

async def ricalcola_scadenze(db, *, dry_run: bool = True, esempi: int = 20) -> Dict[str, Any]:
    """Riporta `data_scadenza` alla scadenza dichiarata nell'XML.

    Legge solo le `pagamento_rate` gia' conservate sulla fattura: non
    rilegge un XML ne' un file su Drive. Tocca una fattura solo se la
    scadenza ricalcolata e' **diversa** da quella salvata.
    """
    esaminate = corrette = invariate = senza_scadenza = 0
    anticipate = posticipate = 0
    campione: List[Dict[str, Any]] = []

    async for fattura in db[COLL].find({}, _PROIEZIONE):
        if not _e_attiva(fattura):
            continue
        esaminate += 1

        vecchia = fattura.get("data_scadenza")
        nuova = scadenza_sintetica(fattura)
        if nuova is None:
            senza_scadenza += 1
            continue
        if nuova == vecchia:
            invariate += 1
            continue

        if vecchia:
            if nuova > vecchia:
                anticipate += 1   # la salvata era PRIMA di quella vera
            else:
                posticipate += 1
        if len(campione) < esempi:
            campione.append({
                "id": fattura.get("id"),
                "numero": fattura.get("invoice_number"),
                "fornitore": fattura.get("supplier_name"),
                "scadenza_salvata": vecchia,
                "scadenza_dall_xml": nuova,
            })

        if not dry_run:
            await db[COLL].update_one(
                {"id": fattura.get("id")}, {"$set": {"data_scadenza": nuova}}
            )
        corrette += 1

    return {
        "dry_run": dry_run,
        "esaminate": esaminate,
        "corrette": corrette,
        "invariate": invariate,
        "senza_scadenza_determinabile": senza_scadenza,
        "di_cui_erano_anticipate": anticipate,
        "di_cui_erano_posticipate": posticipate,
        "esempi": campione,
    }


# ── 2. Replay di `fattura.created` ─────────────────────────────────────────

async def _fatture_senza_partita(db) -> List[Dict[str, Any]]:
    """Le fatture attive per cui l'evento non ha mai creato la partita.

    Un solo prefetch delle partite, poi il confronto in memoria: la regola
    del §4 vieta di interrogare il database una volta per fattura.
    """
    con_partita = set()
    async for partita in db[COLL_PARTITE].find(
        {"documento_collection": COLL}, {"_id": 0, "documento_id": 1}
    ):
        documento_id = partita.get("documento_id")
        if documento_id:
            con_partita.add(str(documento_id))

    da_rigiocare = []
    async for fattura in db[COLL].find({}, _PROIEZIONE):
        if not _e_attiva(fattura) or _e_archivio_storico(fattura):
            continue
        if str(fattura.get("id")) in con_partita:
            continue
        da_rigiocare.append(fattura)
    return da_rigiocare


async def ripubblica_fattura_created(db, *, dry_run: bool = True) -> Dict[str, Any]:
    """Ripubblica `fattura.created` per le fatture rimaste senza partita."""
    from app.services.event_bus import EventTypes, propagate_event

    da_rigiocare = await _fatture_senza_partita(db)

    ripubblicate = errori = 0
    senza_metodo = senza_scadenza = 0
    motivi_errore: List[str] = []

    for fattura in da_rigiocare:
        if not fattura.get("metodo_pagamento"):
            senza_metodo += 1
        # La scadenza si ricava come all'import: se non e' mai stata
        # calcolata, la partita nascerebbe senza termine e non invecchierebbe.
        scadenza = fattura.get("data_scadenza") or scadenza_sintetica(fattura)
        if not scadenza:
            senza_scadenza += 1

        if dry_run:
            ripubblicate += 1
            continue

        try:
            await propagate_event(
                EventTypes.FATTURA_CREATED,
                costruisci_evento_fattura_created(fattura, data_scadenza=scadenza),
                db,
                source_module="replay_pregresso",
            )
            ripubblicate += 1
        except Exception as exc:  # noqa: BLE001 — l'esito va riportato, non nascosto
            errori += 1
            if len(motivi_errore) < 10:
                motivi_errore.append(f"{fattura.get('id')}: {exc}")
            logger.exception("Replay fattura.created fallito per %s", fattura.get("id"))

    return {
        "dry_run": dry_run,
        "candidate": len(da_rigiocare),
        "ripubblicate": ripubblicate,
        "errori": errori,
        "senza_metodo_pagamento": senza_metodo,
        "senza_scadenza_determinabile": senza_scadenza,
        "motivi_errore": motivi_errore,
    }


# ── Il job in background ───────────────────────────────────────────────────

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
            risultato = await ripubblica_fattura_created(db, dry_run=dry_run)
            await _salva_stato(db, stato="completato", dry_run=dry_run,
                               iniziato_at=iniziato,
                               terminato_at=datetime.now(timezone.utc).isoformat(),
                               risultato=risultato, errore=None)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Replay fattura.created fallito")
            await _salva_stato(db, stato="errore", dry_run=dry_run,
                               iniziato_at=iniziato,
                               terminato_at=datetime.now(timezone.utc).isoformat(),
                               risultato=None, errore=str(exc))


async def avvia_ripubblicazione(db, *, dry_run: bool = True) -> Dict[str, Any]:
    """Un solo replay alla volta, fuori dal timeout HTTP (§4: oltre i 5
    minuti il proxy Render taglia la richiesta)."""
    global _job_task
    stato = await stato_ripubblicazione(db)
    if _job_lock.locked() or (_job_task is not None and not _job_task.done()):
        return {"avviato": False, **stato}
    _job_task = asyncio.create_task(_esegui(db, dry_run))
    return {"avviato": True, "stato": "avvio", "dry_run": dry_run}


async def stato_ripubblicazione(db) -> Dict[str, Any]:
    stato = await db["sistema_stato"].find_one({"chiave": _CHIAVE_JOB}, {"_id": 0})
    if not stato:
        return {"stato": "mai_avviato"}
    stato.pop("chiave", None)
    return stato
