"""Aprire i turni non riscrive la relazione HR e non sceglie fra omonimi."""
import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.hr.routers import dipendenti_cloud as router


@pytest.fixture
def hr(monkeypatch):
    db = AsyncMongoMockClient()["turni_lettura_test"]
    monkeypatch.setattr(router, "get_db", lambda: db)
    asyncio.run(db.turni_config.insert_one({
        "dipendente_id": "id-storico", "nome_riferimento": "Prova Persona",
        "turno_id": "turno-test",
    }))
    return db


def _dip(id, **extra):
    return {"id": id, "nome": "Persona", "cognome": "Prova", "stato": "attivo", **extra}


def test_riferimento_univoco_si_normalizza_senza_scrivere(hr):
    async def run():
        await hr.dipendenti.insert_one(_dip("id-corrente"))
        prima = await hr.turni_config.find_one({})
        for _ in range(2):
            vista = await router.get_turni_config()
            assert vista[0]["dipendente_id"] == "id-corrente"
            assert vista[0]["riferimento_risolto_da"] == "id-storico"
            assert await hr.turni_config.find_one({}) == prima
        # Il salvataggio esplicito usa l'id corrente e la lettura successiva
        # da' priorita' alla configurazione salvata, senza ulteriori repair.
        await router.save_turni_config({"voci": [{"dipendente_id": "id-corrente", "turno_id": "turno-nuovo"}]})
        viste = await router.get_turni_config()
        correnti = [v for v in viste if v["dipendente_id"] == "id-corrente"]
        assert len(correnti) == 1 and correnti[0]["turno_id"] == "turno-nuovo"

    asyncio.run(run())


def test_due_omonimi_non_vengono_scelti_in_ordine_di_lettura(hr):
    async def run():
        await hr.dipendenti.insert_many([_dip("dip-a"), _dip("dip-b")])
        assert (await router.get_turni_config())[0]["dipendente_id"] == "id-storico"
        assert (await hr.turni_config.find_one({}))["dipendente_id"] == "id-storico"

    asyncio.run(run())


@pytest.mark.parametrize("stato", [{"stato": "inattivo"}, {"in_carico": False}])
def test_riferimento_non_si_sposta_su_rapporto_fuori_forza(hr, stato):
    async def run():
        await hr.dipendenti.insert_one(_dip("id-corrente", **stato))
        assert (await router.get_turni_config())[0]["dipendente_id"] == "id-storico"

    asyncio.run(run())


@pytest.mark.parametrize("inverti", [False, True])
def test_due_config_orfane_non_scelgono_un_turno_in_ordine_di_lettura(hr, inverti):
    async def run():
        await hr.turni_config.delete_many({})
        voci = [{"dipendente_id": "vecchio-a", "nome_riferimento": "Prova Persona", "turno_id": "mattina"},
                {"dipendente_id": "vecchio-b", "nome_riferimento": "Prova Persona", "turno_id": "sera"}]
        await hr.turni_config.insert_many(list(reversed(voci)) if inverti else voci)
        await hr.dipendenti.insert_one(_dip("id-corrente"))
        prima = await hr.turni_config.find({}).to_list(100)
        vista = await router.get_turni_config()
        assert all(c["dipendente_id"] != "id-corrente" for c in vista)
        assert all(c.get("riferimento_conflitto") for c in vista)
        assert await hr.turni_config.find({}).to_list(100) == prima
    asyncio.run(run())
