"""Il tablet e lo scheduler emettono lo stesso task per un lotto utilizzabile."""

import asyncio
from datetime import date, timedelta

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

from app.lotti.routers import task_dipendenti


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def archivio(monkeypatch):
    database = AsyncMongoMockClient()["task_scadenza_test"]
    monkeypatch.setattr(task_dipendenti, "db", database)
    return database


def test_usa_oggi_riusa_task_per_lotto_e_giorno(archivio):
    domani = (date.today() + timedelta(days=1)).isoformat()
    run(archivio.lotti.insert_one({
        "id": "lotto-1", "numero_lotto": "BISC-001", "prodotto": "Biscotti",
        "quantita": 4, "data_scadenza": domani,
    }))

    primo = run(task_dipendenti.usa_oggi_lotto("lotto-1"))
    secondo = run(task_dipendenti.usa_oggi_lotto("lotto-1"))

    assert primo["creato"] is True
    assert secondo["creato"] is False
    assert primo["task"]["id"] == secondo["task"]["id"]
    assert primo["task"]["lotto_id"] == "lotto-1"
    assert run(archivio.task_dipendenti.count_documents({"tipo": "scadenza"})) == 1


def test_scaduto_e_scadenza_ignota_non_diventano_task_di_uso(archivio):
    run(archivio.lotti.insert_many([
        {"id": "scaduto", "prodotto": "Babà", "quantita": 1,
         "data_scadenza": (date.today() - timedelta(days=1)).isoformat()},
        {"id": "ignoto", "prodotto": "Crema", "quantita": 1,
         "data_scadenza": ""},
    ]))
    for lotto_id in ("scaduto", "ignoto"):
        with pytest.raises(HTTPException) as errore:
            run(task_dipendenti.usa_oggi_lotto(lotto_id))
        assert errore.value.status_code == 409
    assert run(archivio.task_dipendenti.count_documents({})) == 0


def test_scheduler_riusa_il_task_manuale_e_salta_lotto_scaduto(archivio):
    run(archivio.lotti.insert_many([
        {"id": "valido", "numero_lotto": "ARAN-001", "prodotto": "Arancini",
         "quantita": 2, "data_scadenza": date.today().isoformat()},
        {"id": "scaduto", "numero_lotto": "BAB-001", "prodotto": "Babà",
         "quantita": 1, "data_scadenza": (date.today() - timedelta(days=1)).isoformat()},
    ]))
    manuale = run(task_dipendenti.usa_oggi_lotto("valido"))["task"]

    risultato = run(task_dipendenti.genera_task_giornalieri())
    tasks = run(archivio.task_dipendenti.find({}, {"_id": 0}).to_list(20))

    assert risultato["ok"] is True
    assert [t["id"] for t in tasks if t["tipo"] == "scadenza"] == [manuale["id"]]
    assert all(t.get("lotto_id") != "scaduto" for t in tasks)
    assert any(t["tipo"] == "temperatura" for t in tasks)


def test_task_errato_si_annulla_senza_cancellarne_la_provenienza(archivio):
    task_id = "vecchio-task-scaduto"
    run(archivio.task_dipendenti.insert_one({
        "id": task_id, "data": date.today().isoformat(),
        "titolo": "Usa prima: Babà", "tipo": "scadenza", "fonte": "auto_scadenza",
        "lotto_id": "BAB-001", "completato": False,
    }))

    risultato = run(task_dipendenti.annulla_task(
        task_id, "Lotto già scaduto: non utilizzare", _admin=None,
    ))
    vista = run(task_dipendenti.get_task_oggi())
    storico = run(archivio.task_dipendenti.find_one({"id": task_id}))

    assert risultato["ok"] is True
    assert vista["totale"] == 0
    assert storico["annullato"] is True
    assert storico["motivo_annullamento"] == "Lotto già scaduto: non utilizzare"
    assert storico["lotto_id"] == "BAB-001"
