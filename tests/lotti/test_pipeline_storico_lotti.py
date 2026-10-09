"""La pipeline marca scaduti senza cancellare lo storico HACCP."""

import asyncio
from datetime import date, timedelta

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.lotti.routers import pipeline


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def archivio(monkeypatch):
    db = AsyncMongoMockClient()["pipeline_storico_test"]
    monkeypatch.setattr(pipeline, "db", db)
    return db


def test_scadenza_canonica_senza_perdere_lotti_vecchi_o_richiamati(archivio):
    ieri = date.today() - timedelta(days=1)
    domani = date.today() + timedelta(days=1)
    run(archivio.lotti.insert_many([
        {"id": "italiano", "stato": "attivo", "data_scadenza": ieri.strftime("%d/%m/%Y")},
        {"id": "iso", "stato": "attivo", "data_scadenza": ieri.isoformat()},
        {"id": "valido", "stato": "attivo", "data_scadenza": domani.isoformat()},
        {"id": "storico", "stato": "esaurito", "data_produzione": "01/01/2020"},
        {"id": "richiamo", "stato": "bloccato_richiamo", "data_scadenza": ieri.isoformat()},
        {"id": "annullato", "stato": "annullato", "data_scadenza": ieri.isoformat()},
    ]))
    log = {}
    run(pipeline.step_lotti(log))
    assert log["lotti_scaduti_marcati"] == 2
    assert "lotti_vecchi_rimossi" not in log
    assert run(archivio.lotti.count_documents({})) == 6
    stati = {r["id"]: r["stato"] for r in run(archivio.lotti.find({}, {"_id": 0}).to_list(10))}
    assert stati == {
        "italiano": "scaduto", "iso": "scaduto", "valido": "attivo",
        "storico": "esaurito", "richiamo": "bloccato_richiamo", "annullato": "annullato",
    }
    secondo_log = {}
    run(pipeline.step_lotti(secondo_log))
    assert secondo_log["lotti_scaduti_marcati"] == 0
    assert run(archivio.lotti.count_documents({})) == 6
