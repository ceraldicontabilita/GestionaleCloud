"""Bonifiche automatiche: alert falsi e verbali che non sono verbali.

Gira come ultimo passo del job bancario corto (``_banca_versamenti_proiezione_job``
in ``app/scheduler.py``: due minuti dopo l'avvio e poi ogni 30 minuti), perche'
nessuna pulizia deve restare un comando da lanciare a mano.

Regole comuni a tutti i passi:

* si tocca **solo per id**: gli alert si chiudono con
  ``alert_engine.risolvi_alert_per_id``, i verbali si mettono in quarantena
  con ``stato = STATO_QUARANTENA`` sul loro ``_id``; niente si cancella;
* ogni riga toccata porta il **motivo scritto** (``motivo_chiusura``,
  ``motivo_quarantena``);
* **idempotente**: un alert gia' chiuso o un verbale gia' in quarantena non
  rientra nel giro, il secondo passaggio conta zero;
* l'esito (conteggi ed errori) va nel log e in ``sistema_stato``
  (chiave ``bonifiche_automatiche``).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from app.services.alert_engine import (
    CODICI_ALERT_MOVIMENTO_DA_RICONCILIARE,
    COLL_ALERTS,
    risolvi_alert_per_id,
)

logger = logging.getLogger(__name__)

CHIAVE_STATO = "bonifiche_automatiche"
ATTORE = "bonifiche_automatiche"

MOTIVO_FATTURE_SENZA_SCADENZA = "le fatture fornitore non hanno scadenza"
MOTIVO_MOVIMENTO_RICONCILIATO = "il movimento bancario e' gia' riconciliato"
MOTIVO_DOC_CLASSIFICATO = "il documento ha gia' una categoria"


def _ora() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _alert_aperti(db, codici: Iterable[str]) -> List[Dict[str, Any]]:
    return await db[COLL_ALERTS].find(
        {"codice": {"$in": list(codici)}, "stato": "aperto"},
        {"_id": 0, "id": 1, "codice": 1, "entita_id": 1, "created_at": 1},
    ).to_list(None)


async def _chiudi(db, alert_id: Optional[str], motivo: str) -> int:
    return int(await risolvi_alert_per_id(alert_id, db, motivo, resolved_by=ATTORE))


# ── 1. FAT_DA_PAGARE_SCADUTA ────────────────────────────────────────────────

async def chiudi_alert_scadenza_fatture_fornitore(db) -> Dict[str, int]:
    """Chiude ogni FAT_DA_PAGARE_SCADUTA aperto: nascevano da una scadenza
    «+30» inventata, e le fatture fornitore non hanno scadenza."""
    aperti = await _alert_aperti(db, ("FAT_DA_PAGARE_SCADUTA",))
    chiusi = 0
    for alert in aperti:
        chiusi += await _chiudi(db, alert.get("id"), MOTIVO_FATTURE_SENZA_SCADENZA)
    return {"aperti": len(aperti), "chiusi": chiusi}


# ── 2. RIC_* del movimento bancario ─────────────────────────────────────────

async def chiudi_alert_movimenti_riconciliati(db) -> Dict[str, int]:
    """RIC_NON_RICONCILIATO, RIC_MATCH_AMBIGUO e RIC_PAGAMENTO_MULTIPLO:
    chiude i doppioni (stesso codice e stesso movimento, resta il piu'
    vecchio) e quelli il cui movimento e' ormai riconciliato. La collezione
    del movimento la dice il suo id (``collezione_del_movimento``)."""
    from app.services.sumup_conto import collezione_del_movimento

    aperti = await _alert_aperti(db, CODICI_ALERT_MOVIMENTO_DA_RICONCILIARE)
    esito = {"aperti": len(aperti), "doppioni_chiusi": 0, "riconciliati_chiusi": 0}

    per_chiave: Dict[tuple, List[Dict[str, Any]]] = {}
    for alert in aperti:
        per_chiave.setdefault((alert.get("codice"), str(alert.get("entita_id") or "")), []).append(alert)

    rimasti: List[Dict[str, Any]] = []
    for gruppo in per_chiave.values():
        gruppo.sort(key=lambda a: (str(a.get("created_at") or ""), str(a.get("id") or "")))
        tenuto, *doppi = gruppo
        rimasti.append(tenuto)
        for doppio in doppi:
            esito["doppioni_chiusi"] += await _chiudi(
                db, doppio.get("id"), f"doppione dell'alert {tenuto.get('id')}",
            )

    # Un prefetch per collezione, non una lettura per alert.
    ids_per_collezione: Dict[str, set] = {}
    for alert in rimasti:
        movimento_id = str(alert.get("entita_id") or "")
        if movimento_id:
            ids_per_collezione.setdefault(
                collezione_del_movimento({"id": movimento_id}), set(),
            ).add(movimento_id)
    riconciliati: set = set()
    for collezione, ids in ids_per_collezione.items():
        movimenti = await db[collezione].find(
            {"id": {"$in": sorted(ids)}}, {"_id": 0, "id": 1, "riconciliato": 1},
        ).to_list(None)
        riconciliati.update(str(m.get("id")) for m in movimenti if m.get("riconciliato") is True)

    for alert in rimasti:
        if str(alert.get("entita_id") or "") in riconciliati:
            esito["riconciliati_chiusi"] += await _chiudi(
                db, alert.get("id"), MOTIVO_MOVIMENTO_RICONCILIATO,
            )
    return esito


# ── 3. DOC_NON_CLASSIFICATO su documenti con categoria ──────────────────────

async def chiudi_alert_documenti_classificati(db) -> Dict[str, int]:
    """Chiude DOC_NON_CLASSIFICATO sui documenti che una categoria ce l'hanno:
    l'handler li riclassificava dal solo nome del file."""
    from app.services.handlers.documento_handlers import categoria_decisa

    aperti = await _alert_aperti(db, ("DOC_NON_CLASSIFICATO",))
    ids = sorted({str(a.get("entita_id")) for a in aperti if a.get("entita_id")})
    documenti = await db["documents_inbox"].find(
        {"id": {"$in": ids}}, {"_id": 0, "id": 1, "category": 1},
    ).to_list(None) if ids else []
    classificati = {str(d.get("id")) for d in documenti if categoria_decisa(d)}
    chiusi = 0
    for alert in aperti:
        if str(alert.get("entita_id") or "") in classificati:
            chiusi += await _chiudi(db, alert.get("id"), MOTIVO_DOC_CLASSIFICATO)
    return {"aperti": len(aperti), "chiusi": chiusi}


# ── 4. Verbali nati da numeri di fattura ────────────────────────────────────

#: Un verbale con una di queste prove proprie (PDF, email, pagamento, importo
#: letto dal documento) non nasce da un numero di fattura: non si tocca.
_PROVE_PROPRIE_VERBALE = (
    "pagamento_id", "paypal_transaction_id", "ricevuta_pagopa_id", "movimento_banca_id",
    "pdf_filename", "pdf_hash", "email_id", "message_id", "email_message_id",
    "quietanza_ricevuta", "importo", "data_verbale", "data_violazione", "iuv",
    # Campi scritti dai canali veri (PEC, scanner email, banca).
    "upec_id", "data_ricezione_notifica", "targa", "ente_creditore", "articolo_cds",
    "email_subject", "email_from", "email_date", "file_hash", "movimento_id",
    "importo_centesimi", "movimento_estratto_conto_id", "quietanza_pdf",
    "pdf_ricevuta_path",
)


def _codice(valore: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(valore or "").upper())


def numero_derivato_da_fattura(numero_verbale: Any, numeri_fattura: Iterable[Any]) -> Optional[str]:
    """Il numero di fattura da cui e' stato letto il «verbale», se lo e'.

    Uguale, oppure l'uno contenuto nell'altro (il pattern generico ritagliava
    «A25111540620» da «FT A25111540620/2026»): e' lo stesso codice.
    """
    verbale = _codice(numero_verbale)
    if not verbale:
        return None
    for numero in numeri_fattura:
        fattura = _codice(numero)
        if not fattura:
            continue
        if verbale == fattura or (len(verbale) >= 6 and len(fattura) >= 6
                                  and (verbale in fattura or fattura in verbale)):
            return str(numero)
    return None


async def quarantena_verbali_da_fattura(db) -> Dict[str, int]:
    """Mette in quarantena, per ``_id`` e con il motivo, i verbali che hanno
    per numero il numero (o un pezzo del numero) della fattura del
    noleggiatore a cui sono collegati: sono nati dalla fattura, non da una
    multa.

    Un verbale collegato a una fattura archiviata o sparita **non** si tocca:
    la dedup ha solo scelto l'altra copia, e va ricollegato, non nascosto
    (si conta in ``da_ricollegare``). Un verbale con prove proprie resta
    com'e', e uno che una persona ha ripristinato (``quarantena_revocata``)
    non torna in quarantena.
    """
    from app.constants.stati_verbale import STATO_QUARANTENA
    from app.services.noleggio.processors import FILTRO_FATTURA_ATTIVA

    proiezione = {
        "_id": 1, "id": 1, "numero_verbale": 1, "stato": 1,
        "fattura_id": 1, "fattura_associata_id": 1,
        "fattura_numero": 1, "numero_fattura": 1, "fattura_associata_numero": 1,
        "quarantena_revocata": 1,
        **{campo: 1 for campo in _PROVE_PROPRIE_VERBALE},
    }
    verbali = await db["verbali_noleggio"].find(
        {"stato": {"$ne": STATO_QUARANTENA}}, proiezione,
    ).to_list(None)
    esito = {"analizzati": len(verbali), "quarantena": 0, "con_prove_proprie": 0,
             "da_ricollegare": 0}

    collegati = [v for v in verbali if v.get("fattura_id") or v.get("fattura_associata_id")]
    ids_fattura = sorted({
        str(v.get("fattura_id") or v.get("fattura_associata_id")) for v in collegati
    })
    esistenti: Dict[str, Dict[str, Any]] = {}
    attive: set = set()
    if ids_fattura:
        proiezione_fattura = {"_id": 0, "id": 1, "invoice_number": 1, "numero_fattura": 1}
        for fattura in await db["invoices"].find(
            {"id": {"$in": ids_fattura}}, proiezione_fattura,
        ).to_list(None):
            esistenti[str(fattura.get("id"))] = fattura
        for fattura in await db["invoices"].find(
            {**FILTRO_FATTURA_ATTIVA, "id": {"$in": ids_fattura}}, {"_id": 0, "id": 1},
        ).to_list(None):
            attive.add(str(fattura.get("id")))

    ora = _ora()
    for verbale in collegati:
        fattura_id = str(verbale.get("fattura_id") or verbale.get("fattura_associata_id"))
        fattura = esistenti.get(fattura_id)
        numeri = [
            (fattura or {}).get("invoice_number"), (fattura or {}).get("numero_fattura"),
            verbale.get("fattura_numero"), verbale.get("numero_fattura"),
            verbale.get("fattura_associata_numero"),
        ]
        derivato = numero_derivato_da_fattura(verbale.get("numero_verbale"), numeri)
        if not derivato:
            if fattura is None or fattura_id not in attive:
                esito["da_ricollegare"] += 1
            continue
        motivo = f"il numero del verbale e' il numero della fattura {derivato}"
        if verbale.get("quarantena_revocata"):
            continue
        if any(verbale.get(campo) for campo in _PROVE_PROPRIE_VERBALE):
            esito["con_prove_proprie"] += 1
            continue
        if verbale.get("_id") is None:
            continue
        risultato = await db["verbali_noleggio"].update_one(
            {"_id": verbale["_id"], "stato": {"$ne": STATO_QUARANTENA}},
            {"$set": {
                "stato": STATO_QUARANTENA,
                "stato_precedente": verbale.get("stato"),
                "motivo_quarantena": motivo,
                "quarantena_at": ora,
                "quarantena_da": ATTORE,
            }},
        )
        esito["quarantena"] += int(risultato.modified_count > 0)
    return esito


# ── Orchestrazione ──────────────────────────────────────────────────────────

PASSI = (
    ("fatture_senza_scadenza", chiudi_alert_scadenza_fatture_fornitore),
    ("alert_movimenti", chiudi_alert_movimenti_riconciliati),
    ("documenti_classificati", chiudi_alert_documenti_classificati),
    ("verbali_da_fattura", quarantena_verbali_da_fattura),
)


async def esegui_bonifiche(db) -> Dict[str, Any]:
    """Esegue tutti i passi; un passo che fallisce non ferma gli altri."""
    conteggi: Dict[str, Any] = {}
    errori: Dict[str, str] = {}
    for nome, passo in PASSI:
        try:
            conteggi[nome] = await passo(db)
        except Exception as exc:  # noqa: BLE001 - il passo dopo gira comunque
            errori[nome] = f"{type(exc).__name__}: {exc}"
            logger.error("[BONIFICHE] %s: %s: %s", nome, type(exc).__name__, exc)
    logger.info("[BONIFICHE] %s", conteggi)
    esito = {"conteggi": conteggi, "errori": errori, "eseguita_at": _ora()}
    try:
        await db["sistema_stato"].update_one(
            {"chiave": CHIAVE_STATO},
            {"$set": {"chiave": CHIAVE_STATO, **esito, "updated_at": esito["eseguita_at"]}},
            upsert=True,
        )
    except Exception as exc:  # noqa: BLE001 - l'esito e' comunque nel log
        logger.error("[BONIFICHE] stato non salvato: %s: %s", type(exc).__name__, exc)
    return esito
