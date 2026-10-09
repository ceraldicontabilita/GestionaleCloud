import asyncio

from fastapi import BackgroundTasks
from mongomock_motor import AsyncMongoMockClient

from app.lotti.routers import acquaviva


def run(coro):
    return asyncio.run(coro)


def test_stato_in_corso_di_un_vecchio_processo_diventa_riprendibile(monkeypatch):
    database = AsyncMongoMockClient()["acquaviva_scraping_ripresa"]
    monkeypatch.setattr(acquaviva, "db", database)
    run(database.sync_status.insert_one({
        "_id": "scraping_acquaviva",
        "stato": "in_corso",
        "processo": "processo-terminato",
    }))

    stato = run(acquaviva.stato_scraping_acquaviva())

    assert stato["stato"] == "interrotto"
    assert "riavvio" in stato["errore"]


def test_avvio_riprende_un_task_interrotto_e_blocca_un_doppio_click(monkeypatch):
    database = AsyncMongoMockClient()["acquaviva_scraping_avvio"]
    monkeypatch.setattr(acquaviva, "db", database)
    monkeypatch.setattr(acquaviva, "_scraping_acquaviva_attivo", False)
    run(database.sync_status.insert_one({
        "_id": "scraping_acquaviva",
        "stato": "in_corso",
        "processo": "processo-terminato",
    }))
    tasks = BackgroundTasks()

    primo = run(acquaviva.avvia_scraping_acquaviva(tasks, True, _admin={}))
    secondo = run(acquaviva.avvia_scraping_acquaviva(BackgroundTasks(), True, _admin={}))

    assert primo["avviato"] is True
    assert primo["ripreso"] is True
    assert len(tasks.tasks) == 1
    assert secondo["avviato"] is False
