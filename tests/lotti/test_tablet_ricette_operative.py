"""Separazione tra ricettari fornitori e card operative dolce/salato."""

import asyncio
import os

from mongomock_motor import AsyncMongoMockClient

os.environ.setdefault("AUTH_SECRET", "test-secret-non-usare-in-prod")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "Gestionale_Test")


_LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(_LOOP)


def run(coro):
    return _LOOP.run_until_complete(coro)


def test_riferimenti_fornitore_non_sono_operativi_finche_non_attivati():
    from app.lotti.routers.ricette import _ricetta_visibile_tablet

    assert _ricetta_visibile_tablet({"nome": "Pastiera Ceraldi"})
    assert not _ricetta_visibile_tablet({"nome": "Croissant", "origine": "saima"})
    assert not _ricetta_visibile_tablet({"nome": "Sfoglia", "origine": "acquaviva"})
    assert not _ricetta_visibile_tablet({"nome": "Ricetta", "ricettario_mepa_id": "mepa-1"})
    assert _ricetta_visibile_tablet({
        "nome": "Croissant adattato",
        "origine": "saima",
        "visibile_tablet": True,
    })
    assert not _ricetta_visibile_tablet({"nome": "Ricetta nascosta", "visibile_tablet": False})


def test_tablet_nasconde_fornitori_e_riordina_dolce_salato(monkeypatch):
    import app.lotti.routers.ricette as module
    import app.lotti.routers.lotti_produzione as lotti
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(module, "db", database)

    async def giacenza_vuota(_nomi):
        return {}

    monkeypatch.setattr(lotti, "giacenza_prodotti_finiti", giacenza_vuota)
    run(database.ricette.insert_many([
        {"id": "dolce", "nome": "Cheesecake al limone", "reparto": "rosticceria"},
        {"id": "salato", "nome": "Calzone con provola", "reparto": "pasticceria"},
        {"id": "saima-ref", "nome": "Apple Cake", "reparto": "pasticceria", "origine": "saima"},
        {"id": "saima-ok", "nome": "Brownie adattato", "reparto": "pasticceria", "origine": "saima", "visibile_tablet": True},
        {"id": "acq-ref", "nome": "Sfoglia Acquaviva", "reparto": "pasticceria", "origine": "acquaviva"},
    ]))

    dolci = run(module.get_tablet("pasticceria"))["prodotti"]
    salati = run(module.get_tablet("rosticceria"))["prodotti"]

    assert {item["id"] for item in dolci} == {"dolce", "saima-ok"}
    assert {item["id"] for item in salati} == {"salato"}
    assert all(item["reparto"] == "pasticceria" for item in dolci)
    assert all(item["reparto"] == "rosticceria" for item in salati)


def test_salvataggio_ricetta_fornitore_la_rende_operativa(monkeypatch):
    import app.lotti.routers.ricette as module
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(module, "db", database)
    run(database.ricette.insert_one({
        "id": "saima-ref",
        "nome": "Croissant pistacchio",
        "reparto": "pasticceria",
        "origine": "saima",
        "ricettario_saima_id": "croissant",
        "visibile_tablet": False,
    }))

    item = module.RicettaCreate(
        nome="Croissant pistacchio Ceraldi",
        reparto="pasticceria",
        porzioni=40,
        ingredienti=["Farina", "Pistacchio"],
        ingredienti_dettaglio=[
            {"nome": "Farina", "quantita": 1000, "unita_misura": "g"},
            {"nome": "Pistacchio", "quantita": 100, "unita_misura": "g"},
        ],
    )
    saved = run(module.update_ricetta("saima-ref", item))

    assert saved["origine"] == "saima"
    assert saved["ricettario_saima_id"] == "croissant"
    assert saved["visibile_tablet"] is True
    assert saved["ricetta_operativa"] is True
    assert saved["adattata_da_ricettario_fornitore_at"]


def test_riordino_persistente_esclude_riferimenti_e_crea_backup(monkeypatch):
    import app.lotti.routers.ricette as module
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(module, "db", database)
    run(database.ricette.insert_many([
        {"id": "dolce", "nome": "Tiramisù", "reparto": "rosticceria"},
        {"id": "salato", "nome": "Pizza margherita", "reparto": "pasticceria"},
        {"id": "saima", "nome": "Calzone SAIMA", "reparto": "pasticceria", "origine": "saima"},
    ]))

    result = run(module.auto_assegna_reparti(applica=True, _admin={"nome": "Ceraldi Vincenzo"}))

    assert result["aggiornate"] == 2
    assert run(database.ricette.find_one({"id": "dolce"}))["reparto"] == "pasticceria"
    assert run(database.ricette.find_one({"id": "salato"}))["reparto"] == "rosticceria"
    assert run(database.ricette.find_one({"id": "saima"}))["reparto"] == "pasticceria"
    backup = run(database.ricette_import_backup.find_one({"tipo": "riordino_reparti_operativi"}))
    assert backup["operatore"] == "Ceraldi Vincenzo"
    assert {item["id"] for item in backup["reparti_precedenti"]} == {"dolce", "salato"}
