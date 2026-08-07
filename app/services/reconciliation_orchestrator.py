"""Orchestratore degli agganci che devono funzionare in qualunque ordine.

Documento e prova possono arrivare in momenti diversi. Ogni ingresso richiama
gli stessi motori idempotenti; nessun handler implementa matching alternativo.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


async def riconcilia_documenti_e_pagamenti(
    db, *, anno: Optional[int] = None, movimento_ids=None,
) -> Dict[str, Any]:
    from app.routers.bank.assegni_auto_match import run_auto_match
    from app.services.assegni_fattura_intent import riprocessa_intenti_assegni
    from app.services.bonifici_pdf_ingest import riprocessa_bonifici_pendenti
    from app.services.f24_bank_reconciliation import riconcilia_f24_tributi_banca
    from app.services.stipendi_bonifici import associa_bonifici_stipendi
    from app.routers.pagopa import auto_associa_ricevute_db
    from app.routers.paypal_statements import (
        _auto_riconcilia, riprocessa_collegamenti_paypal,
    )

    assegni_intenti = await riprocessa_intenti_assegni(db, anno=anno)
    assegni_auto = await run_auto_match(db, dry_run=False, anno=anno)
    bonifici_pdf = await riprocessa_bonifici_pendenti(db, limit=2000)
    salari = await associa_bonifici_stipendi(db, anno=anno)
    f24 = await riconcilia_f24_tributi_banca(
        db, anno=anno, movimento_ids=movimento_ids,
    )
    start_date = f"{anno}-01-01" if anno else None
    end_date = f"{anno}-12-31" if anno else None
    paypal_fatture_prima = await riprocessa_collegamenti_paypal(
        db, start_date=start_date, end_date=end_date,
    )
    paypal_banca = await _auto_riconcilia(db, anno=anno, applica=True)
    paypal_fatture_dopo = await riprocessa_collegamenti_paypal(
        db, start_date=start_date, end_date=end_date,
    )
    cbill = await auto_associa_ricevute_db(db)
    return {
        "assegni_intenti": assegni_intenti,
        "assegni_auto": assegni_auto,
        "bonifici_pdf": bonifici_pdf,
        "salari": salari,
        "f24": f24,
        "paypal": {
            "fatture_prima": paypal_fatture_prima,
            "banca": paypal_banca,
            "fatture_dopo": paypal_fatture_dopo,
        },
        "cbill_pagopa": cbill,
    }


async def on_fattura_created_riprocessa(event: Dict[str, Any], db):
    """Una fattura arrivata tardi puo' completare assegno o bonifico gia' noto."""
    from app.routers.bank.assegni_auto_match import run_auto_match
    from app.services.assegni_fattura_intent import riprocessa_intenti_assegni
    from app.services.bonifici_pdf_ingest import riprocessa_bonifici_pendenti
    from app.routers.paypal_statements import riprocessa_collegamenti_paypal

    anno = None
    data = event.get("data") or event.get("invoice_date") or ""
    if str(data)[:4].isdigit():
        anno = int(str(data)[:4])
    paypal = await riprocessa_collegamenti_paypal(
        db,
        start_date=f"{anno}-01-01" if anno else None,
        end_date=f"{anno}-12-31" if anno else None,
    )
    return {
        "assegni_intenti": await riprocessa_intenti_assegni(db, anno=anno),
        "assegni_auto": await run_auto_match(db, dry_run=False, anno=anno),
        "bonifici_pdf": await riprocessa_bonifici_pendenti(db, limit=2000),
        "paypal_fatture": paypal,
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
    return await riconcilia_documenti_e_pagamenti(
        db, anno=anno, movimento_ids=ids or None,
    )
