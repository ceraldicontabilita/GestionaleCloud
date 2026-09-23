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


def test_modifica_ricetta_ricalcola_sempre_dagli_ingredienti(monkeypatch):
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

    client_vecchio = mod.RicettaCreate(
        nome="Impasto", ingredienti=["Latte"], allergeni=["Soia"],
        allergeni_confermati=True,
    )
    aggiornata = run(mod.update_ricetta("r3", client_vecchio, _admin={"nome": "Admin"}))
    assert aggiornata["allergeni"] == ["Latte"]
    assert aggiornata["allergeni_auto"] == ["Latte"]
    assert aggiornata["allergeni_da_confermare"] is True


# ─── Allergeni e Menu (RST-AV3-10) ───────────────────────────────────────────
# Il Menu dichiara gli allergeni per legge (Reg. UE 1169/2011): una conferma
# del titolare deve arrivarci subito e non puo' essere cancellata da un
# salvataggio che non cambia gli ingredienti.

def _registra_sync(monkeypatch):
    from app.lotti.routers import ricette as ricette_mod

    chiamate = []

    async def finto_sync(ricetta_id):
        chiamate.append(ricetta_id)
        return {"esito": "aggiornato"}

    monkeypatch.setattr(ricette_mod, "_sincronizza_menu", finto_sync)
    return chiamate


def test_ponte_pubblica_nessun_allergene_se_confermato_vuoto():
    from app.lotti.servizi.menu_bridge import allergeni_da_pubblicare

    confermata = {"allergeni": [], "allergeni_auto": ["Latte"], "allergeni_da_confermare": False}
    assert allergeni_da_pubblicare(confermata) == []
    # Solo una ricetta che il campo non l'ha mai avuto ripiega sul calcolo.
    assert allergeni_da_pubblicare({"allergeni_auto": ["Latte"]}) == ["Latte"]


def test_modifica_senza_cambiare_ingredienti_conserva_la_conferma(monkeypatch):
    from app.lotti.routers import ricette as mod

    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(mod, "db", database)
    _registra_sync(monkeypatch)
    run(database.ricette.insert_one({
        "id": "r4", "nome": "Crema", "ingredienti": ["Latte", "Zucchero"],
        "allergeni": [], "allergeni_auto": ["Latte"],
        "allergeni_verificato": True, "allergeni_da_confermare": False,
    }))

    # Stessi ingredienti, in ordine diverso: la conferma resta.
    stessa = mod.RicettaCreate(nome="Crema", ingredienti=["zucchero", "Latte"], prezzo_vendita=2.5)
    aggiornata = run(mod.update_ricetta("r4", stessa, _admin={"nome": "Admin"}))
    assert aggiornata["allergeni"] == []
    assert aggiornata["allergeni_da_confermare"] is False
    assert aggiornata["allergeni_auto"] == ["Latte"]

    # Ingredienti cambiati: la conferma non vale piu'.
    cambiata = mod.RicettaCreate(nome="Crema", ingredienti=["Latte", "Uova"])
    aggiornata = run(mod.update_ricetta("r4", cambiata, _admin={"nome": "Admin"}))
    assert aggiornata["allergeni"] == ["Uova", "Latte"]
    assert aggiornata["allergeni_da_confermare"] is True


def test_conferma_manuale_aggiorna_subito_il_menu(monkeypatch):
    from app.lotti.routers import food_cost as mod

    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(mod, "db", database)
    chiamate = _registra_sync(monkeypatch)
    run(database.ricette.insert_one({"id": "r5", "nome": "Crema", "ingredienti": ["Latte"]}))

    esito = run(mod.aggiorna_allergeni_ricetta({"ricetta_id": "r5", "allergeni": []}))

    assert chiamate == ["r5"]
    assert esito["menu_sync"] == {"esito": "aggiornato"}


def test_rilevamento_massivo_riallinea_il_menu_solo_dove_cambia(monkeypatch):
    from app.lotti.routers import food_cost as mod

    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(mod, "db", database)
    chiamate = _registra_sync(monkeypatch)
    run(database.ricette.insert_many([
        {"id": "cambia", "nome": "A", "ingredienti": ["Farina"], "allergeni": []},
        {"id": "uguale", "nome": "B", "ingredienti": ["Latte"], "allergeni": ["Latte"]},
        {"id": "confermata", "nome": "C", "ingredienti": ["Uova"], "allergeni": [],
         "allergeni_verificato": True, "allergeni_da_confermare": False},
    ]))

    primo = run(mod.auto_rileva_allergeni_tutte())
    assert chiamate == ["cambia"]
    assert primo["menu_riallineati"] == 1

    secondo = run(mod.auto_rileva_allergeni_tutte())
    assert chiamate == ["cambia"]
    assert secondo["menu_riallineati"] == 0
