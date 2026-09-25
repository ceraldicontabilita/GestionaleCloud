"""Orchestratore degli agganci che devono funzionare in qualunque ordine.

Documento e prova possono arrivare in momenti diversi. Ogni ingresso richiama
gli stessi motori idempotenti; nessun handler implementa matching alternativo.
"""
from __future__ import annotations

import logging
import calendar
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
    from app.services.f24_bank_reconciliation import riconcilia_f24_tributi_banca
    from app.services.finanziamenti_soci import scan_finanziamenti_da_ec
    from app.services.soci_accounting import riconcilia_attese_soci_da_ec
    from app.services.proiezione_bancaria import proietta_movimenti_bancari_semantici
    from app.services.bank_payment_allocations import reconcile_deterministic_invoice_allocations
    from app.services.stipendi_bonifici import associa_bonifici_stipendi
    from app.services.versamenti_contanti import riconosci_versamenti
    from app.routers.pagopa import auto_associa_ricevute_db
    from app.services.paypal_reconciliation_pipeline import riconcilia_paypal_importato

    assegni_intenti = await riprocessa_intenti_assegni(db, anno=anno)
    assegni_auto = await run_auto_match(db, dry_run=False, anno=anno)
    bonifici_pdf = await riprocessa_bonifici_pendenti(db, limit=2000)
    salari = await associa_bonifici_stipendi(db, anno=anno)
    f24 = await riconcilia_f24_tributi_banca(
        db, anno=anno, movimento_ids=movimento_ids,
    )
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

    # Versamenti e prelievi di contante: la riga di estratto conto e' la
    # prova, quindi le due gambe si scrivono da sole. Prima della proiezione,
    # cosi' la gamba di cassa esiste gia' quando il resto la cerca. Non c'e'
    # piu' nessun comando «ripara versamenti» da premere: quel bottone
    # sbagliava perche' creava la cassa anche quando c'era gia', e il contante
    # usciva due volte. Qui la cassa gia' scritta a mano si collega.
    versamenti = await riconosci_versamenti(db, anno=anno, dry_run=False)

    proiezione_banca = await proietta_movimenti_bancari_semantici(
        db, anno=anno, movimento_ids=movimento_ids,
    )
    allocazioni_fatture_banca = await reconcile_deterministic_invoice_allocations(
        db, anno=anno, movement_ids=movimento_ids,
    )
    # Il report del titolare dice come e' stata pagata ogni fattura: qui si
    # ripassano solo le righe ancora in attesa (XML arrivato dopo, assegno
    # comparso nel nuovo estratto conto).
    from app.services.pagamenti_dichiarati_titolare import applica_pagamenti_dichiarati

    try:
        pagamenti_dichiarati = await applica_pagamenti_dichiarati(db, solo_pendenti=True)
    except Exception as exc:  # noqa: BLE001 - gli altri agganci restano validi
        logger.exception(
            "Pagamenti dichiarati del titolare non ripassati (%s)", type(exc).__name__,
        )
        pagamenti_dichiarati = {"errore": f"{type(exc).__name__}: {exc}"}
    return {
        "assegni_intenti": assegni_intenti,
        "assegni_auto": assegni_auto,
        "bonifici_pdf": bonifici_pdf,
        "salari": salari,
        "f24": f24,
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
        "versamenti_contanti": versamenti,
        "proiezione_banca": proiezione_banca,
        "allocazioni_fatture_banca": allocazioni_fatture_banca,
        "pagamenti_dichiarati": pagamenti_dichiarati,
    }


async def on_cedolino_importato_riprocessa(event: Dict[str, Any], db):
    """Il cedolino conferma il maturato; il bonifico puo' essere gia' in banca."""
    from app.services.stipendi_bonifici import associa_bonifici_stipendi

    anno = event.get("anno")
    return await associa_bonifici_stipendi(
        db, anno=int(anno) if str(anno or "").isdigit() else None,
    )


async def on_f24_acquisito_riprocessa(event: Dict[str, Any], db):
    """Un F24 arrivato dopo l'addebito viene riesaminato per codice tributo."""
    from app.services.f24_bank_reconciliation import riconcilia_f24_tributi_banca

    anno = event.get("anno")
    return await riconcilia_f24_tributi_banca(
        db, anno=int(anno) if str(anno or "").isdigit() else None,
    )


async def on_estratto_conto_importato_riprocessa(event: Dict[str, Any], db):
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
