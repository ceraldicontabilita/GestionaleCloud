import asyncio

from app.services.sheets_document_store import MemorySheetsClient

from app.routers import dati_isa


def test_riepilogo_dati_isa_usa_dati_annuali_e_quadra_fasce(monkeypatch):
    async def scenario():
        db = MemorySheetsClient()["test_dati_isa"]
        await db["dati_isa_snapshot"].insert_one({
            "anno": 2025,
            "indicatori_acquisti": {"caffe_kg_acquistati": 2526},
            "provenienza": {"tipo": "fatture_gestionale"},
        })
        await db["consumi_energia"].insert_many([
            {"anno": 2025, "mese": 1, "f1_kwh": 10, "f2_kwh": 20, "f3_kwh": 30, "totale_kwh": 60},
            {"anno": 2025, "mese": 2, "f1_kwh": 4, "f2_kwh": 5, "f3_kwh": 6, "totale_kwh": 15},
            {"anno": 2024, "mese": 12, "f1_kwh": 999, "f2_kwh": 999, "f3_kwh": 999, "totale_kwh": 2997},
        ])
        monkeypatch.setattr(dati_isa.Database, "get_db", staticmethod(lambda: db))
        return await dati_isa.riepilogo_dati_isa(2025)

    result = asyncio.run(scenario())

    assert result["anno"] == 2025
    assert result["indicatori_acquisti"]["caffe_kg_acquistati"] == 2526
    assert result["indicatori_disponibili"] is True
    assert result["energia"]["disponibile"] is True
    assert len(result["energia"]["mensili"]) == 2
    assert result["energia"]["totali"] == {
        "f1_kwh": 14,
        "f2_kwh": 25,
        "f3_kwh": 36,
        "totale_kwh": 75,
    }
    assert sum(result["energia"]["totali"][k] for k in ("f1_kwh", "f2_kwh", "f3_kwh")) == 75


def test_riepilogo_dati_isa_distingue_assenza_dati_da_valore_zero(monkeypatch):
    async def scenario():
        db = MemorySheetsClient()["test_dati_isa_vuoto"]
        monkeypatch.setattr(dati_isa.Database, "get_db", staticmethod(lambda: db))
        return await dati_isa.riepilogo_dati_isa(2026)

    result = asyncio.run(scenario())

    assert result["indicatori_acquisti"] == {}
    assert result["indicatori_disponibili"] is False
    assert result["energia"]["mensili"] == []
    assert result["energia"]["disponibile"] is False
