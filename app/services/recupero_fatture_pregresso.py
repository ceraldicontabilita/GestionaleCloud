"""Recupero del pregresso sulle fatture gia' in archivio.

**Niente scadenze.** Decisione del titolare del 19/09/2026: «decido io quando
pagare, non c'e' una data stabilita». Il gestionale non legge le condizioni
di pagamento dell'XML ne' le date stampate sulla fattura, e qui non si
ricalcola nessuna `data_scadenza`: le partite fornitore nascono senza
termine, e `check_scadenze_partite_task` le salta da solo.

**L'evento `fattura.created` mai propagato.** L'import massivo del
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

**Le scadenze gia' scritte.** Dal 19/09/2026 l'import non calcola piu'
nessuna scadenza, ma in archivio restano quelle inventate prima: 642
fatture e 971 partite fornitore le portano ancora, e sono loro a far
comparire «scaduto» dove il titolare non ha preso nessun impegno.
`azzera_scadenze_inventate` le toglie. Non tocca `pagamento_rate` — e' la
trascrizione fedele del blocco DatiPagamento dell'XML, cioe' il documento,
che resta leggibile — ne' `data_pagamento`, che e' un pagamento avvenuto.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services.eventi_fattura import costruisci_evento_fattura_created

logger = logging.getLogger(__name__)

__all__ = [
    "STATI_NON_ATTIVI",
    "ripubblica_fattura_created",
    "avvia_ripubblicazione",
    "stato_ripubblicazione",
    "azzera_scadenze_inventate",
    "avvia_azzeramento_scadenze",
    "stato_azzeramento_scadenze",
]

COLL = "invoices"
COLL_PARTITE = "partite_aperte"
_CHIAVE_JOB = "replay_fattura_created"
_CHIAVE_JOB_SCADENZE = "azzera_scadenze_fornitore"

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
    senza_metodo = 0
    motivi_errore: List[str] = []

    for fattura in da_rigiocare:
        if not fattura.get("metodo_pagamento"):
            senza_metodo += 1

        if dry_run:
            ripubblicate += 1
            continue

        evento = costruisci_evento_fattura_created(fattura)
        # Nessuna scadenza: la partita fornitore nasce senza termine, per
        # decisione del titolare. Va azzerata esplicitamente perche' 47 delle
        # candidate portano ancora la scadenza inventata dal vecchio import.
        evento["data_scadenza"] = None

        try:
            await propagate_event(
                EventTypes.FATTURA_CREATED, evento, db,
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
        "motivi_errore": motivi_errore,
    }


# ── 3. Le scadenze inventate rimaste in archivio ───────────────────────────

def _ha_scadenza(documento: Dict[str, Any]) -> bool:
    return bool(str(documento.get("data_scadenza") or "").strip())


async def azzera_scadenze_inventate(db, *, dry_run: bool = True) -> Dict[str, Any]:
    """Toglie la `data_scadenza` dalle fatture fornitore e dalle loro partite.

    Nessuna fattura fornitore ha una scadenza: il titolare decide quando
    pagare. Quelle in archivio le ha scritte il vecchio import leggendo le
    condizioni di pagamento dell'XML, ed e' proprio quel numero a far
    comparire «scaduto» su un impegno che non esiste.

    Un prefetch per collezione e una scrittura per sola riga da correggere:
    ripassarlo una seconda volta non scrive niente.
    """
    fatture = [
        f async for f in db[COLL].find({}, {"_id": 0, "id": 1, "data_scadenza": 1})
        if _ha_scadenza(f)
    ]
    partite = [
        p async for p in db[COLL_PARTITE].find(
            {"documento_collection": COLL},
            {"_id": 0, "id": 1, "tipo": 1, "data_scadenza": 1},
        )
        if _ha_scadenza(p)
    ]

    esito = {
        "dry_run": dry_run,
        "fatture_con_scadenza": len(fatture),
        "partite_con_scadenza": len(partite),
        "fatture_azzerate": 0,
        "partite_azzerate": 0,
        "errori": 0,
        "motivi_errore": [],
    }
    if dry_run:
        return esito

    for collezione, righe, contatore in (
        (COLL, fatture, "fatture_azzerate"),
        (COLL_PARTITE, partite, "partite_azzerate"),
    ):
        for riga in righe:
            try:
                await db[collezione].update_one(
                    {"id": riga.get("id")}, {"$set": {"data_scadenza": None}},
                )
                esito[contatore] += 1
            except Exception as exc:  # noqa: BLE001 — l'esito va riportato
                esito["errori"] += 1
                if len(esito["motivi_errore"]) < 10:
                    esito["motivi_errore"].append(f"{collezione}/{riga.get('id')}: {exc}")
                logger.exception("Azzeramento scadenza fallito su %s", riga.get("id"))
    return esito


# ── Il job in background ───────────────────────────────────────────────────
# Un solo runner per tutte le riparazioni di questo modulo: girano fuori dal
# timeout HTTP (§4: oltre i 5 minuti il proxy Render taglia la richiesta) e
# lasciano l'esito in `sistema_stato` sotto la propria chiave.

_LAVORI = {
    _CHIAVE_JOB: ripubblica_fattura_created,
    _CHIAVE_JOB_SCADENZE: azzera_scadenze_inventate,
}


async def _salva_stato(db, chiave: str, **campi) -> None:
    await db["sistema_stato"].update_one(
        {"chiave": chiave},
        {"$set": {**campi, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )


async def _esegui(db, chiave: str, dry_run: bool) -> None:
    async with _job_lock:
        iniziato = datetime.now(timezone.utc).isoformat()
        await _salva_stato(db, chiave, stato="in_corso", dry_run=dry_run,
                           iniziato_at=iniziato, terminato_at=None,
                           risultato=None, errore=None)
        try:
            risultato = await _LAVORI[chiave](db, dry_run=dry_run)
            await _salva_stato(db, chiave, stato="completato", dry_run=dry_run,
                               iniziato_at=iniziato,
                               terminato_at=datetime.now(timezone.utc).isoformat(),
                               risultato=risultato, errore=None)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Riparazione %s fallita", chiave)
            await _salva_stato(db, chiave, stato="errore", dry_run=dry_run,
                               iniziato_at=iniziato,
                               terminato_at=datetime.now(timezone.utc).isoformat(),
                               risultato=None, errore=str(exc))


async def _avvia(db, chiave: str, dry_run: bool) -> Dict[str, Any]:
    global _job_task
    if _job_lock.locked() or (_job_task is not None and not _job_task.done()):
        return {"avviato": False, **await _stato(db, chiave)}
    _job_task = asyncio.create_task(_esegui(db, chiave, dry_run))
    return {"avviato": True, "stato": "avvio", "dry_run": dry_run}


async def _stato(db, chiave: str) -> Dict[str, Any]:
    stato = await db["sistema_stato"].find_one({"chiave": chiave}, {"_id": 0})
    if not stato:
        return {"stato": "mai_avviato"}
    stato.pop("chiave", None)
    return stato


async def avvia_ripubblicazione(db, *, dry_run: bool = True) -> Dict[str, Any]:
    return await _avvia(db, _CHIAVE_JOB, dry_run)


async def stato_ripubblicazione(db) -> Dict[str, Any]:
    return await _stato(db, _CHIAVE_JOB)


async def avvia_azzeramento_scadenze(db, *, dry_run: bool = True) -> Dict[str, Any]:
    return await _avvia(db, _CHIAVE_JOB_SCADENZE, dry_run)


async def stato_azzeramento_scadenze(db) -> Dict[str, Any]:
    return await _stato(db, _CHIAVE_JOB_SCADENZE)
