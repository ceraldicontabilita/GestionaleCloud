import asyncio

from mongomock_motor import AsyncMongoMockClient


def run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def test_salva_calendario_e_procedura_ordine_senza_periodi_invalidi(monkeypatch):
    import app.lotti.routers.fornitori_anagrafica as fornitori
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(fornitori, "db", database)
    payload = fornitori.ContattoFornitore(
        nome="Fornitore Test",
        metodo_pagamento=" RiBa 30 giorni ",
        giorni_consegna_settimana=[3, 0, 3, 9],
        lead_time_giorni=99,
        ora_limite_ordine="10:30",
        procedura_ordini_attiva=False,
        chiusure_programmate=[
            {"dal": "2026-12-24", "al": "2027-01-06", "motivo": "Festivita"},
            {"dal": "non-valida", "al": "2027-01-10", "motivo": "scarta"},
        ],
    )

    run(fornitori.aggiorna_contatto("Fornitore Test", payload))
    doc = run(database.fornitori_anagrafica.find_one({"nome": "Fornitore Test"}, {"_id": 0}))

    assert doc["metodo_pagamento"] == "RiBa 30 giorni"
    assert doc["giorni_consegna_settimana"] == [0, 3]
    assert doc["lead_time_giorni"] == 30
    assert doc["procedura_ordini_attiva"] is False
    assert doc["chiusure_programmate"] == [
        {"dal": "2026-12-24", "al": "2027-01-06", "motivo": "Festivita"}
    ]
