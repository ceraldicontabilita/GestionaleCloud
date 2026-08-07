import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.services.f24_bank_reconciliation import riconcilia_f24_tributi_banca


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _f24():
    return {
        "id": "f24-isa",
        "anno": 2026,
        "pagato": False,
        "sezione_erario": [
            {"codice_tributo": "2001", "anno": "2025", "importo_debito": 4613.50},
            {"codice_tributo": "6494", "anno": "2025", "importo_debito": 449.00},
        ],
        "totali": {"saldo_netto": 5062.50},
        "dati_generali": {"data_versamento": "2026-08-04"},
    }


def test_servizio_associa_solo_il_codice_tributo_pagato_e_marca_la_prova_bancaria():
    async def scenario():
        db = AsyncMongoMockClient()["f24_service_partial"]
        await db.f24_unificato.insert_one(_f24())
        await db.estratto_conto_movimenti.insert_one({
            "id": "mov-2001",
            "data": "2026-08-04",
            "data_contabile": "2026-08-04",
            "importo": 4613.50,
            "tipo": "uscita",
            "descrizione": "I24 AGENZIA ENTRATE",
            "livello_evidenza": "ufficiale",
            "riconciliato": False,
        })
        risultato = await riconcilia_f24_tributi_banca(db, anno=2026)
        f24 = await db.f24_unificato.find_one({"id": "f24-isa"}, {"_id": 0})
        movimento = await db.estratto_conto_movimenti.find_one({"id": "mov-2001"}, {"_id": 0})
        return risultato, f24, movimento

    risultato, f24, movimento = _run(scenario())
    assert risultato["f24_parziali"] == 1
    assert risultato["movimenti_associati"] == 1
    assert f24["pagato"] is False
    assert f24["importo_residuo"] == 449.0
    assert f24["allocazioni_banca"][0]["codici_tributo"] == ["2001"]
    assert movimento["riconciliato"] is True
    assert movimento["tipo_riconciliazione"] == "f24_tributi"


def test_servizio_non_sceglie_fra_due_f24_compatibili():
    async def scenario():
        db = AsyncMongoMockClient()["f24_service_ambiguous"]
        uno = _f24()
        due = {**_f24(), "id": "f24-altro"}
        await db.f24_unificato.insert_many([uno, due])
        await db.estratto_conto_movimenti.insert_one({
            "id": "mov-2001",
            "data": "2026-08-04",
            "data_contabile": "2026-08-04",
            "importo": 4613.50,
            "tipo": "uscita",
            "descrizione": "I24 AGENZIA ENTRATE",
            "livello_evidenza": "ufficiale",
            "riconciliato": False,
        })
        risultato = await riconcilia_f24_tributi_banca(db, anno=2026)
        movimento = await db.estratto_conto_movimenti.find_one({"id": "mov-2001"}, {"_id": 0})
        return risultato, movimento

    risultato, movimento = _run(scenario())
    assert risultato["movimenti_associati"] == 0
    assert risultato["ambigui_o_non_compatibili"] == 1
    assert movimento["riconciliato"] is False
