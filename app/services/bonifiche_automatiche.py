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
    from app.services.verbali_collegamento_fattura import fattura_id_del_verbale

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

    collegati = [v for v in verbali if fattura_id_del_verbale(v)]
    ids_fattura = sorted({fattura_id_del_verbale(v) for v in collegati})
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
        fattura_id = fattura_id_del_verbale(verbale)
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


# ── F24: la rata non e' un mese ─────────────────────────────────────────────

SEZIONI_F24 = ("sezione_erario", "sezione_regioni", "sezione_tributi_locali", "sezione_imu")


def riga_f24_riallineata(riga: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """La riga corretta se porta una rata letta come mese, altrimenti None.

    «0101» e «03/03 2021» sono rate (``tributi_engine.riga_rateizzata``): il
    periodo resta l'anno, la rata va in ``rateazione``, il mese a «00»."""
    from app.engines.tributi_engine import riga_rateizzata

    if not riga_rateizzata(riga):
        return None
    periodo = str(riga.get("periodo_riferimento") or "")
    anno = str(riga.get("anno") or "").strip()
    if not anno:
        m = re.search(r"(\d{4})", periodo or str(riga.get("periodo_raw") or ""))
        anno = m.group(1) if m else ""
    nuova = dict(riga)
    if not nuova.get("rateazione"):
        grezzo = str(riga.get("periodo_raw") or "").split()[0]
        nuova["rateazione"] = grezzo.replace("/", "")
    if nuova.get("mese") not in (None, "", "00"):
        nuova["mese"] = "00"
    if anno:
        nuova["periodo_riferimento"] = anno
    return None if nuova == riga else nuova


async def riallinea_rate_f24(db) -> Dict[str, int]:
    """Righe di modelli F24 e quietanze archiviate con la rata al posto del
    mese: si riscrive la sezione, per id, conservando ogni altro campo."""
    esito = {"documenti": 0, "righe": 0}
    for coll in ("f24_unificato", "quietanze_f24"):
        proiezione = {"_id": 0, "id": 1, **{s: 1 for s in SEZIONI_F24}}
        for doc in await db[coll].find({}, proiezione).to_list(None):
            if not doc.get("id"):
                continue
            aggiornamento: Dict[str, Any] = {}
            for sezione in SEZIONI_F24:
                righe = doc.get(sezione)
                if not isinstance(righe, list):
                    continue
                nuove, cambiate = [], 0
                for riga in righe:
                    corretta = riga_f24_riallineata(riga) if isinstance(riga, dict) else None
                    nuove.append(corretta or riga)
                    cambiate += corretta is not None
                if cambiate:
                    aggiornamento[sezione] = nuove
                    esito["righe"] += cambiate
            if aggiornamento:
                aggiornamento["rate_riallineate_at"] = _ora()
                await db[coll].update_one({"id": doc["id"]}, {"$set": aggiornamento})
                esito["documenti"] += 1
    return esito


async def numeri_fattura_senza_spazi(db) -> Dict[str, int]:
    """Numeri di fattura salvati con spazi attorno (« 13719»): chi cerca per
    numero non li trova. Si riscrive il numero ripulito, per id, e si conserva
    quello letto dall'XML in ``invoice_number_originale``."""
    esito = {"fatture": 0}
    righe = await db["invoices"].find({}, {"_id": 0, "id": 1, "invoice_number": 1}).to_list(None)
    for riga in righe:
        numero = riga.get("invoice_number")
        if not riga.get("id") or not isinstance(numero, str) or numero == numero.strip():
            continue
        await db["invoices"].update_one({"id": riga["id"]}, {"$set": {
            "invoice_number": numero.strip(), "invoice_number_originale": numero,
            "numero_ripulito_at": _ora(),
        }})
        esito["fatture"] += 1
    return esito


#: Cosa scrive l'allineamento: i cinque campi di pagamento concordi e la data
#: dell'addebito in banca. Il metodo di pagamento no: lo dice l'anagrafica.
CAMPI_FATTURA_PAGATA = {
    "stato": "pagata", "stato_pagamento": "pagata", "payment_status": "paid",
    "pagato": True, "paid": True,
}


def _quote_assegno(assegno: Dict[str, Any]) -> Dict[str, int]:
    """{fattura_id: centesimi} che l'assegno paga."""
    from app.services.doppioni_archivio import centesimi

    quote: Dict[str, int] = {}
    for riga in assegno.get("fatture_collegate") or []:
        if isinstance(riga, dict) and riga.get("fattura_id"):
            quota = centesimi(riga.get("quota"))
            if quota:
                quote[str(riga["fattura_id"])] = quota
    unica = assegno.get("fattura_id") or assegno.get("fattura_collegata")
    if not quote and unica:
        quota = centesimi(assegno.get("importo_assegnato") or assegno.get("importo"))
        if quota:
            quote[str(unica)] = abs(quota)
    return quote


async def fatture_pagate_con_assegno(db) -> Dict[str, int]:
    """Fatture pagate da assegni addebitati in banca: i campi di stato si allineano.

    Lo stato di pagamento vive in cinque campi e sulle fatture pagate con
    assegno ne restava qualcuno fermo a «in attesa banca» o «da pagare»,
    con la data della fattura al posto di quella dell'addebito. Vale solo la
    prova ufficiale: assegno incassato, evidenza bancaria ufficiale e
    movimento d'estratto, e le quote degli assegni fanno il totale della
    fattura al centesimo. Per id; il secondo giro non scrive niente.
    """
    from app.constants.fattura_attiva import fattura_attiva
    from app.services.doppioni_archivio import centesimi

    assegni = await db["assegni"].find(
        {"stato": "incassato", "evidenza_bancaria_ufficiale": True},
        {"_id": 0, "id": 1, "fatture_collegate": 1, "fattura_id": 1, "fattura_collegata": 1,
         "importo": 1, "importo_assegnato": 1, "data_incasso": 1,
         "movimento_estratto_conto_id": 1},
    ).to_list(None)
    per_fattura: Dict[str, Dict[str, Any]] = {}
    for assegno in assegni:
        if not assegno.get("movimento_estratto_conto_id") or not assegno.get("data_incasso"):
            continue
        for fattura_id, quota in _quote_assegno(assegno).items():
            voce = per_fattura.setdefault(fattura_id, {"cent": 0, "assegni": [], "date": []})
            voce["cent"] += quota
            voce["assegni"].append(assegno.get("id"))
            voce["date"].append(str(assegno["data_incasso"])[:10])
    esito = {"fatture": 0, "totale_diverso": 0}
    for fattura_id, voce in per_fattura.items():
        fattura = await db["invoices"].find_one({"id": fattura_id}, {"_id": 0, "id": 1, "status": 1,
            "stato_import": 1, "entity_status": 1, "deleted": 1, "total_amount": 1,
            "data_pagamento": 1, **{campo: 1 for campo in CAMPI_FATTURA_PAGATA}})
        if not fattura or not fattura_attiva(fattura):
            continue
        if centesimi(fattura.get("total_amount")) != voce["cent"]:
            esito["totale_diverso"] += 1
            continue
        atteso = {**CAMPI_FATTURA_PAGATA, "data_pagamento": max(voce["date"])}
        if all(fattura.get(k) == v for k, v in atteso.items()):
            continue
        await db["invoices"].update_one({"id": fattura_id}, {"$set": {
            **atteso, "pagamento_prova": {"tipo": "assegno", "assegni": voce["assegni"]},
            "stato_allineato_banca_at": _ora(),
        }})
        esito["fatture"] += 1
    return esito


# ── Orchestrazione ──────────────────────────────────────────────────────────

PASSI = (
    ("fatture_senza_scadenza", chiudi_alert_scadenza_fatture_fornitore),
    ("alert_movimenti", chiudi_alert_movimenti_riconciliati),
    ("documenti_classificati", chiudi_alert_documenti_classificati),
    ("verbali_da_fattura", quarantena_verbali_da_fattura),
    ("rate_f24", riallinea_rate_f24),
    ("numeri_fattura_con_spazi", numeri_fattura_senza_spazi),
    ("fatture_pagate_con_assegno", fatture_pagate_con_assegno),
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
