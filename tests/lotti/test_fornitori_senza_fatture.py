"""Le anagrafiche e le decisioni di magazzino restano visibili senza acquisti."""
import asyncio
import pytest
from mongomock_motor import AsyncMongoMockClient


@pytest.fixture
def archivio(monkeypatch):
    from app.lotti.routers import fornitori

    db = AsyncMongoMockClient()["fornitori_isolati"]
    monkeypatch.setattr(fornitori, "db", db)
    monkeypatch.setattr(fornitori, "_CACHE_FORNITORI", {"dati": None, "scade": 0.0})
    return fornitori, db


def test_esclusione_senza_fatture_visibile_anche_nei_filtri(archivio):
    async def scenario():
        router, db = archivio
        await router.imposta_esclusione("Servizi Alfa SRL", True, "01234567890")

        elenco = await router.get_fornitori()
        assert len(elenco) == 1
        scheda = elenco[0]
        assert scheda["nome"] == "Servizi Alfa SRL"
        assert scheda["stato"] == "escluso"
        assert scheda["tipo_fornitura"] == "escluso"
        assert scheda["in_attesa"] is False
        assert scheda["piva"] == "01234567890"
        assert scheda["num_fatture"] == 0
        assert scheda["ultima_fattura"] == ""
        assert await router.get_fornitori(stato="escluso", search="alfa") == elenco
        assert await router.get_fornitori(stato="attivo") == []
        assert await db.fatture.count_documents({}) == 0

    asyncio.run(scenario())


def test_anagrafica_erp_senza_scelta_resta_in_attesa(archivio):
    async def scenario():
        router, db = archivio
        await db.fornitori.insert_one({"ragione_sociale": "Nuovo fornitore"})

        elenco = await router.get_fornitori(stato="in_attesa")
        assert len(elenco) == 1
        assert elenco[0]["nome"] == "Nuovo fornitore"
        assert elenco[0]["in_attesa"] is True
        assert elenco[0]["escluso"] is False
        assert await db.fornitori_decisioni.count_documents({}) == 0

    asyncio.run(scenario())


def test_varianti_nome_non_duplicano_scheda_e_conservano_statistiche(archivio):
    async def scenario():
        router, db = archivio
        await router.imposta_esclusione("ALFA SERVICE S.R.L.", True, "01234567890")
        await db.fornitori.insert_one({"denominazione": '"ALFA  SERVICE S.R.L"'})
        await db.fatture.insert_many([
            {"fornitore": '"Alfa Service S.R.L"', "data_fattura": "15/09/2026"},
            {"fornitore": "ALFA  SERVICE S.R.L.", "data_fattura": "01/10/2026"},
            {"fornitore": "Solo fattura", "data_fattura": "02/10/2026"},
        ])

        elenco = await router.get_fornitori()
        assert len(elenco) == 2
        alfa = next(f for f in elenco if f["stato"] == "escluso")
        assert alfa["piva"] == "01234567890"
        assert alfa["num_fatture"] == 2
        assert alfa["ultima_fattura"] == "01/10/2026"
        nuovo = next(f for f in elenco if f["nome"] == "Solo fattura")
        assert nuovo["stato"] == "in_attesa"
        assert nuovo["num_fatture"] == 1

    asyncio.run(scenario())
