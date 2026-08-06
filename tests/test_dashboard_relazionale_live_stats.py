import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.routers import partite_aperte_api, riconciliazione_stats_api


def _run_stats(db, monkeypatch, anno=None):
    monkeypatch.setattr(
        riconciliazione_stats_api.Database,
        "get_db",
        staticmethod(lambda: db),
    )
    return asyncio.run(riconciliazione_stats_api.stats_riconciliazione(anno=anno))


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


def test_dashboard_relazionale_filtra_anno_sulle_fonti_contabili(monkeypatch):
    async def prepara():
        db = AsyncMongoMockClient()["test_dashboard_relazionale_anno"]
        await db["estratto_conto_movimenti"].insert_many([
            {"id": "m25", "data": "31/12/2025", "importo": -25, "riconciliato": True},
            {"id": "m26", "data": "2026-01-02", "importo": -26, "riconciliato": False},
        ])
        await db["operazioni_da_confermare"].insert_many([
            {"id": "p25", "data": "2025-12-31", "stato": "da_confermare"},
            {"id": "p26", "data": "02/01/2026", "stato": "da_confermare"},
        ])
        await db["partite_aperte"].insert_many([
            {"id": "pa25", "data_documento": "2025-12-20", "stato": "chiusa"},
            {"id": "pa26", "data_documento": "20/01/2026", "stato": "aperta"},
        ])
        await db["riconciliazioni_match"].insert_many([
            {"id": "r25", "movimento_id": "m25", "stato": "confermato", "importo_riconciliato": 25},
            {"id": "r26", "movimento_id": "m26", "stato": "candidato", "importo_riconciliato": 26},
        ])
        return db

    db = asyncio.run(prepara())
    result = _run_stats(db, monkeypatch, anno=2026)

    assert result["anno"] == 2026
    assert result["sezioni"]["estratto_conto"]["totale"] == 1
    assert result["stati"]["da_riconciliare"]["count"] == 1
    assert result["stati"]["da_confermare"]["count"] == 1
    assert result["sezioni"]["partite"] == {
        "aperte_o_parziali": 1,
        "chiuse": 0,
        "totale": 1,
    }
    assert result["sezioni"]["match"] == {
        "candidato": {"count": 1, "totale": 26},
    }


def test_partite_aperte_stats_e_lista_rispettano_anno(monkeypatch):
    async def scenario():
        db = AsyncMongoMockClient()["test_partite_anno"]
        await db["partite_aperte"].insert_many([
            {
                "id": "pa25",
                "tipo": "fattura_fornitore",
                "data_documento": "2025-10-01",
                "stato": "aperta",
                "residuo": 10,
            },
            {
                "id": "pa26",
                "tipo": "fattura_fornitore",
                "data_documento": "01/02/2026",
                "stato": "aperta",
                "residuo": 20,
            },
        ])
        monkeypatch.setattr(
            partite_aperte_api.Database,
            "get_db",
            staticmethod(lambda: db),
        )
        stats = await partite_aperte_api.stats_partite(anno=2026)
        lista = await partite_aperte_api.lista_partite(
            tipo=None,
            stato="aperta",
            controparte_id=None,
            limit=50,
            anno=2026,
        )
        return stats, lista

    stats, lista = asyncio.run(scenario())
    assert stats == {
        "fattura_fornitore": {"count": 1, "totale_residuo": 20},
    }
    assert [p["id"] for p in lista["partite"]] == ["pa26"]
