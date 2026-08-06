import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.routers import riconciliazione_stats_api


def _run_stats(db, monkeypatch):
    monkeypatch.setattr(
        riconciliazione_stats_api.Database,
        "get_db",
        staticmethod(lambda: db),
    )
    return asyncio.run(riconciliazione_stats_api.stats_riconciliazione())


def test_dashboard_relazionale_legge_stato_live_e_quadra(monkeypatch):
    async def prepara():
        db = AsyncMongoMockClient()["test_dashboard_relazionale"]
        await db["estratto_conto_movimenti"].insert_many([
            {"id": "m1", "importo": 100, "riconciliato": True},
            {"id": "m2", "importo": -30, "riconciliato": False},
            {"id": "m3", "importo": -20},
        ])
        await db["operazioni_da_confermare"].insert_many([
            {"stato": "da_confermare"},
            {"stato": "confermata"},
        ])
        await db["partite_aperte"].insert_many([
            {"stato": "aperta"},
            {"stato": "parziale"},
            {"stato": "chiusa"},
        ])
        await db["riconciliazioni_match"].insert_one({
            "stato": "confermato",
            "importo_riconciliato": None,
        })
        return db

    db = asyncio.run(prepara())
    result = _run_stats(db, monkeypatch)

    assert result["stati"]["riconciliati"]["count"] == 1
    assert result["stati"]["da_riconciliare"]["count"] == 2
    assert result["stati"]["da_confermare"]["count"] == 1
    assert result["sezioni"]["partite"] == {
        "aperte_o_parziali": 2,
        "chiuse": 1,
        "totale": 3,
    }
    assert result["sezioni"]["match"]["confermato"]["totale"] == 0
    assert result["quadratura"]["ok"] is True
    assert result["quadratura"]["valori"] == "3 = 1 + 2"


def test_dashboard_relazionale_diminuisce_i_pendenti_dopo_riconciliazione(monkeypatch):
    async def prepara():
        db = AsyncMongoMockClient()["test_transizione_dashboard_relazionale"]
        await db["estratto_conto_movimenti"].insert_many([
            {"id": "m1", "importo": -10, "riconciliato": False},
            {"id": "m2", "importo": -20, "riconciliato": False},
        ])
        return db

    db = asyncio.run(prepara())
    prima = _run_stats(db, monkeypatch)

    asyncio.run(db["estratto_conto_movimenti"].update_one(
        {"id": "m1"},
        {"$set": {"riconciliato": True}},
    ))
    dopo = _run_stats(db, monkeypatch)

    assert prima["stati"]["da_riconciliare"]["count"] == 2
    assert dopo["stati"]["da_riconciliare"]["count"] == 1
    assert dopo["stati"]["riconciliati"]["count"] == 1
    assert prima["sezioni"]["estratto_conto"]["totale"] == dopo["sezioni"]["estratto_conto"]["totale"] == 2
    assert prima["quadratura"]["ok"] is dopo["quadratura"]["ok"] is True
