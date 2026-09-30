"""Orchestratore degli agganci che devono funzionare in qualunque ordine.

Documento e prova possono arrivare in momenti diversi. Ogni ingresso richiama
gli stessi motori idempotenti; nessun handler implementa matching alternativo.
"""
from __future__ import annotations

import asyncio
import calendar
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


async def riconcilia_documenti_e_pagamenti(
    db, *, anno: Optional[int] = None, movimento_ids=None,
) -> Dict[str, Any]:
    from app.routers.bank.assegni_auto_match import run_auto_match
    from app.services.assegni_fattura_intent import riprocessa_intenti_assegni
    from app.services.bonifici_pdf_ingest import riprocessa_bonifici_pendenti
    from app.services.finanziamenti_soci import scan_finanziamenti_da_ec
    from app.services.soci_accounting import riconcilia_attese_soci_da_ec
    from app.services.bank_payment_allocations import reconcile_deterministic_invoice_allocations
    from app.services.stipendi_bonifici import associa_bonifici_stipendi
    from app.routers.pagopa import auto_associa_ricevute_db
    from app.services.paypal_reconciliation_pipeline import riconcilia_paypal_importato

    assegni_intenti = await riprocessa_intenti_assegni(db, anno=anno)
    assegni_auto = await run_auto_match(db, dry_run=False, anno=anno)
    bonifici_pdf = await riprocessa_bonifici_pendenti(db, limit=2000)
    salari = await associa_bonifici_stipendi(db, anno=anno)
    # F24 ↔ banca (quietanze, modelli, ravvedimenti) non stanno qui: l'unico
    # motore ``riconcilia_f24_banca`` ha un job suo (``f24_quietanze_banca``
    # in scheduler.py), per lo stesso motivo dei versamenti di contante qui sotto.
    start_date = f"{anno}-01-01" if anno else None
    end_date = f"{anno}-12-31" if anno else None
    paypal = await riconcilia_paypal_importato(
        db, start_date=start_date, end_date=end_date,
    )
    cbill = await auto_associa_ricevute_db(db)

    # Prima collega le attese manuali gia' esistenti. Solo dopo crea eventuali
    # nuovi movimenti soci direttamente dalla banca. In questo ordine la stessa
    # entrata non puo' diventare sia "attesa manuale confermata" sia una seconda
    # riga auto-generata nel registro soci.
    soci_attese = await riconcilia_attese_soci_da_ec(
        db, anno=anno, movimento_ids=movimento_ids,
    )
    finanziamenti_soci = await scan_finanziamenti_da_ec(db, anno=anno)

    # Versamenti di contante e proiezione dei movimenti bancari non stanno
    # piu' qui: hanno un job loro (``banca_versamenti_proiezione`` in
    # scheduler.py), che gira pochi minuti dopo l'avvio. Questo giro dura ore e
    # riparte a ogni deploy: il 26/09/2026 non ha finito un turno dalle 13:52,
    # e le correzioni dei versamenti non arrivavano mai ai dati.
    allocazioni_fatture_banca = await reconcile_deterministic_invoice_allocations(
        db, anno=anno, movement_ids=movimento_ids,
    )
    # La carta SumUp non sta piu' qui: gira nel job bancario corto
    # (``banca_versamenti_proiezione``). Qui era in coda a un giro che ogni
    # deploy interrompe, e il 27/09/2026 non arrivava in fondo da ore.
    return {
        "assegni_intenti": assegni_intenti,
        "assegni_auto": assegni_auto,
        "bonifici_pdf": bonifici_pdf,
        "salari": salari,
        "paypal": {
            "fatture_prima": paypal["collegamenti_prima"],
            "banca": paypal["banca"],
            "fatture_dopo": paypal["collegamenti_dopo"],
        },
        "cbill_pagopa": cbill,
        "finanziamenti_soci": {
            "attese_riconciliate": soci_attese,
            "scan": finanziamenti_soci,
        },
        "allocazioni_fatture_banca": allocazioni_fatture_banca,
    }


async def on_cedolino_importato_riprocessa(event: Dict[str, Any], db):
    """Il cedolino conferma il maturato; il bonifico puo' essere gia' in banca,
    sul conto BPM o partito dalla carta SumUp."""
    from app.services.stipendi_bonifici import associa_bonifici_stipendi
    from app.services.sumup_conto import COLL_MOVIMENTI as COLL_CARTA_SUMUP

    anno = event.get("anno")
    anno = int(anno) if str(anno or "").isdigit() else None
    esito = await associa_bonifici_stipendi(db, anno=anno)
    esito["carta_sumup"] = await associa_bonifici_stipendi(
        db, anno=anno, collezione_movimenti=COLL_CARTA_SUMUP, ripassa_collegati=False,
    )
    return esito


async def on_f24_acquisito_riprocessa(event: Dict[str, Any], db):
    """Un F24 arrivato dopo l'addebito viene riesaminato per codice tributo."""
    from app.services.f24_controllo_incrociato import riconcilia_f24_arrivato

    return await riconcilia_f24_arrivato(db, event.get("importo_totale"))


async def on_estratto_conto_importato_riprocessa(event: Dict[str, Any], db):
    """Accoda il ripasso e torna subito: l'import non aspetta la riconciliazione.

    Il ripasso (`riprocessa_estratto_conto`) gira tutti i motori di aggancio e
    su un estratto conto puo' durare decine di minuti. Il bus aspetta ogni
    handler, quindi prima l'import restava fermo fin li': il 26/09/2026 il giro
    della cartella Drive e' rimasto 46 minuti su un solo estratto, e ogni
    deploy lo uccideva prima della fine — gli XML di fatture e chiusure RT in
    coda dietro di lui non sono mai stati letti. Gli estratti che arrivano
    mentre un ripasso gira si sommano in un ripasso solo.
    """
    movimenti = [m for m in event.get("movimenti") or [] if isinstance(m, dict)]
    if not movimenti:
        return {"action": "nessun_movimento"}
    loop = asyncio.get_running_loop()
    worker = _RIPASSO.get("task")
    if worker is None or worker.done() or worker.get_loop() is not loop:
        if worker is not None and worker.get_loop() is not loop:
            _IN_ATTESA.clear()  # resti di un loop chiuso (test): il giro dei 30 minuti li ripassa
        _IN_ATTESA.extend(movimenti)
        _RIPASSO["task"] = asyncio.create_task(_svuota_ripassi(db))
    else:
        _IN_ATTESA.extend(movimenti)
    return {"action": "riconciliazione_accodata", "movimenti": len(movimenti)}


_IN_ATTESA: list = []
_RIPASSO: Dict[str, Any] = {}


async def _svuota_ripassi(db) -> None:
    while _IN_ATTESA:
        lotto = list(_IN_ATTESA)
        _IN_ATTESA.clear()
        try:
            await riprocessa_estratto_conto({"movimenti": lotto}, db)
        except Exception as exc:  # noqa: BLE001 - il motivo va scritto, non ingoiato
            logger.warning(
                "Ripasso dopo estratto conto non riuscito su %d movimenti: %s: %s",
                len(lotto), type(exc).__name__, exc,
            )


async def attendi_riconciliazione_estratti() -> None:
    """Attende il ripasso in coda (test, spegnimento)."""
    worker = _RIPASSO.get("task")
    if worker is not None and worker.get_loop() is asyncio.get_running_loop():
        await asyncio.gather(worker, return_exceptions=True)


async def riprocessa_estratto_conto(event: Dict[str, Any], db):
    movimenti = event.get("movimenti") or []
    ids = [m.get("id") for m in movimenti if m.get("id")]
    anni = {
        int(str(m.get("data"))[:4]) for m in movimenti
        if str(m.get("data") or "")[:4].isdigit()
    }
    anno = next(iter(anni)) if len(anni) == 1 else None
    # Un estratto bancario resta bancario anche quando contiene PayPal. Prima
    # del matching acquisisce le transazioni ufficiali dei mesi interessati:
    # il checkpoint incrementale della pagina PayPal non copre gli anni passati.
    mesi_paypal = set()
    for movimento in movimenti:
        if not re.search(r"\bpaypal\b", str(movimento.get("descrizione") or ""), re.I):
            continue
        try:
            giorno = datetime.strptime(str(movimento.get("data") or "")[:10], "%Y-%m-%d")
        except ValueError:
            continue
        if giorno.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
            mesi_paypal.add((giorno.year, giorno.month))

    paypal_api = {"stato": "nessun_movimento_paypal", "periodi": []}
    if mesi_paypal:
        from app.config import settings

        if not (settings.PAYPAL_CLIENT_ID and settings.PAYPAL_CLIENT_SECRET):
            paypal_api = {"stato": "credenziali_assenti", "periodi": []}
        else:
            from app.services.paypal_api_sync import sync_paypal_period

            paypal_api = {"stato": "sincronizzato", "periodi": [], "errori": []}
            for year, month in sorted(mesi_paypal):
                start = datetime(year, month, 1, tzinfo=timezone.utc)
                last_day = calendar.monthrange(year, month)[1]
                end = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)
                end = min(end, datetime.now(timezone.utc))
                try:
                    result = await sync_paypal_period(db, start, end)
                    paypal_api["periodi"].append(result)
                except Exception as exc:  # La banca va comunque riconciliata.
                    logger.warning(
                        "Sync PayPal per estratto %04d-%02d fallita: %s",
                        year, month, type(exc).__name__,
                    )
                    paypal_api["errori"].append({
                        "mese": f"{year:04d}-{month:02d}",
                        "tipo": type(exc).__name__,
                    })
            if paypal_api["errori"]:
                paypal_api["stato"] = "parziale" if paypal_api["periodi"] else "errore"

    result = await riconcilia_documenti_e_pagamenti(
        db, anno=anno, movimento_ids=ids or None,
    )
    result["paypal_api"] = paypal_api
    return result
