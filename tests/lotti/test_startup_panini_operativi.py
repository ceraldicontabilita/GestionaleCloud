"""Il riavvio non ricrea né sovrascrive panini operativi per omonimia."""

import asyncio
import importlib

from mongomock_motor import AsyncMongoMockClient

from app.lotti import server


def test_riavvio_non_rigenera_panino_eliminato_o_modificato(monkeypatch):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(server, "db", database)

    async def nessuna_scrittura(*_args, **_kwargs):
        return None

    def nessuna_azione(*_args, **_kwargs):
        return None

    for modulo, attributo, sostituto in [
        ("app.lotti.eventi", "registra_handlers", nessuna_azione),
        ("app.lotti.routers.scheduler", "setup_scheduler", nessuna_azione),
        ("app.lotti.routers.tablet_operatori", "seed_operatori", nessuna_scrittura),
        ("app.lotti.routers.magazzino_bar", "seed_magazzino_bar", nessuna_scrittura),
        ("app.lotti.routers.ricette", "seed_ricette_solo_nome", nessuna_scrittura),
        ("app.lotti.routers.catalogo_forno", "inizializza_cataloghi_precaricati", nessuna_scrittura),
        ("app.lotti.routers.acquaviva", "inizializza_mapping_vandemoortele_2026", nessuna_scrittura),
        ("app.lotti.routers.indici", "crea_indici", nessuna_scrittura),
    ]:
        monkeypatch.setattr(importlib.import_module(modulo), attributo, sostituto)
    monkeypatch.setattr(
        importlib.import_module("app.lotti.routers.cataloghi_arricchimento"), "FONTI", []
    )

    async def scenario():
        await database.ricette.insert_one({
            "id": "id-operativo", "nome": "Panino Prosciutto Crudo e Fiordilatte",
            "note": "Procedimento corretto internamente",
        })
        # Il Caprese è stato eliminato: nessun record rimane nella raccolta.
        await server.startup_event()
        await server.startup_event()
        assert await database.ricette.count_documents({}) == 1
        assert await database.ricette.find_one({"nome": "Panino Caprese"}) is None
        panino = await database.ricette.find_one({"id": "id-operativo"})
        assert panino["note"] == "Procedimento corretto internamente"

    asyncio.run(scenario())
