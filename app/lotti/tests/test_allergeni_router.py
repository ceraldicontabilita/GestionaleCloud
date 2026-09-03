import asyncio

from mongomock_motor import AsyncMongoMockClient


def run(coro):
    return asyncio.run(coro)


def test_motore_legge_formato_legacy_dettaglio_e_componenti():
    from app.lotti.allergeni import estrai_nomi_ingredienti, rileva_allergeni

    nomi = estrai_nomi_ingredienti({
        "ingredienti": ["Farina 00", {"nome": "Latte"}],
        "ingredienti_dettaglio": [{"nome": "Uova"}],
        "componenti": [{"nome": "Pasta di pistacchio"}],
    })
    allergeni, trovati_da = rileva_allergeni(nomi)

    assert allergeni == ["Glutine", "Uova", "Latte", "Frutta a guscio"]
    assert trovati_da["Glutine"] == ["Farina 00"]


def test_router_singola_legge_ingredienti_legacy_e_la_bozza(monkeypatch):
    from app.lotti.routers import food_cost as mod

    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(mod, "db", database)
    run(database.ricette.insert_one({
        "id": "r1", "nome": "Crema semplice", "ingredienti": ["Latte", "Tuorlo"]
    }))

    archivio = run(mod.auto_rileva_allergeni_singola("r1"))
    bozza = run(mod.auto_rileva_allergeni_singola(
        "r1", {"ingredienti_dettaglio": [{"nome": "Farina"}, {"nome": "Sesamo"}]}
    ))

    assert archivio["allergeni_suggeriti"] == ["Uova", "Latte"]
    assert bozza["allergeni_suggeriti"] == ["Glutine", "Sesamo"]
    assert bozza["ingredienti_analizzati"] == ["Farina", "Sesamo"]


def test_nome_ricetta_non_genera_falso_crostacei_e_bulk_e_idempotente(monkeypatch):
    from app.lotti.routers import food_cost as mod

    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(mod, "db", database)
    run(database.ricette.insert_one({
        "id": "r2", "nome": "Coda d'aragosta", "ingredienti": ["Farina", "Panna"]
    }))

    primo = run(mod.auto_rileva_allergeni_tutte())
    secondo = run(mod.auto_rileva_allergeni_tutte())
    salvata = run(database.ricette.find_one({"id": "r2"}, {"_id": 0}))

    assert primo["aggiornate"] == 1
    assert secondo["aggiornate"] == 1
    assert salvata["allergeni"] == ["Glutine", "Latte"]
    assert "Crostacei" not in salvata["allergeni"]


def test_bulk_non_sovrascrive_una_conferma_umana_anche_se_vuota(monkeypatch):
    from app.lotti.routers import food_cost as mod

    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(mod, "db", database)
    run(database.ricette.insert_one({
        "id": "r-manuale", "nome": "Preparazione verificata", "ingredienti": ["Latte"],
        "allergeni": [], "allergeni_verificato": True, "allergeni_da_confermare": False,
    }))

    run(mod.auto_rileva_allergeni_tutte(force=False))
    salvata = run(database.ricette.find_one({"id": "r-manuale"}, {"_id": 0}))

    assert salvata["allergeni"] == []
    assert salvata["allergeni_auto"] == ["Latte"]
    assert salvata["allergeni_da_confermare"] is False


def test_modifica_ricetta_ricalcola_salvo_conferma_manualizzata(monkeypatch):
    from app.lotti.routers import ricette as mod

    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(mod, "db", database)
    run(database.ricette.insert_one({
        "id": "r3", "nome": "Impasto", "ingredienti": ["Farina"],
        "allergeni": ["Glutine"], "allergeni_auto": ["Glutine"],
    }))

    automatico = mod.RicettaCreate(
        nome="Impasto", ingredienti=["Latte"], allergeni=["Glutine"],
        allergeni_confermati=False,
    )
    aggiornata = run(mod.update_ricetta("r3", automatico, _admin={"nome": "Admin"}))
    assert aggiornata["allergeni"] == ["Latte"]
    assert aggiornata["allergeni_auto"] == ["Latte"]
    assert aggiornata["allergeni_da_confermare"] is True

    manuale = mod.RicettaCreate(
        nome="Impasto", ingredienti=["Latte"], allergeni=["Soia"],
        allergeni_confermati=True,
    )
    aggiornata = run(mod.update_ricetta("r3", manuale, _admin={"nome": "Admin"}))
    assert aggiornata["allergeni"] == ["Soia"]
    assert aggiornata["allergeni_auto"] == ["Latte"]
    assert aggiornata["allergeni_da_confermare"] is False
