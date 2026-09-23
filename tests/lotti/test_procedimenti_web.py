"""Procedimenti presi da fonti web: solo dove mancano, sempre con la fonte,
«da verificare» finche' il titolare non li conferma o li riscrive."""
import asyncio

from mongomock_motor import AsyncMongoMockClient


def run(coro):
    return asyncio.run(coro)


def _db(monkeypatch):
    from app.lotti.routers import ricette as mod

    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(mod, "db", database)

    async def finto_sync(ricetta_id):
        return {"esito": "aggiornato"}

    monkeypatch.setattr(mod, "_sincronizza_menu", finto_sync)
    return mod, database


VOCE = {
    "ricetta_id": "vuota", "procedimento": "1. Montare le uova con lo zucchero.\n2. Incorporare la farina.",
    "fonte_url": "https://ricette.giallozafferano.it/Pan-di-Spagna.html", "fonte_titolo": "Pan di Spagna",
    "compatibilita": "la fonte usa la fecola",
}


def test_simulazione_non_scrive_e_la_scrittura_e_idempotente(monkeypatch):
    mod, database = _db(monkeypatch)
    run(database.ricette.insert_many([
        {"id": "vuota", "nome": "Pan di Spagna", "ingredienti": ["Uova", "Zucchero", "Farina"]},
        {"id": "manuale", "nome": "Crema", "procedimento_testo": "Il mio procedimento."},
    ]))
    voci = [VOCE, {**VOCE, "ricetta_id": "manuale"}, {**VOCE, "ricetta_id": "x", "fonte_url": "non-un-link"}]

    simulazione = run(mod.importa_procedimenti_web({"voci": voci}, _admin={"nome": "Admin"}))
    assert simulazione["dry_run"] is True and simulazione["scritte"] == 1
    assert simulazione["gia_presenti"] == 1 and simulazione["scartate"] == 1
    assert "procedimento_testo" not in run(database.ricette.find_one({"id": "vuota"}, {"_id": 0}))

    scrittura = run(mod.importa_procedimenti_web({"voci": voci, "dry_run": False}, _admin={"nome": "Admin"}))
    assert scrittura["scritte"] == 1
    salvata = run(database.ricette.find_one({"id": "vuota"}, {"_id": 0}))
    assert salvata["procedimento_testo"].startswith("1. Montare")
    assert salvata["procedimento_origine"] == "web"
    assert salvata["procedimento_da_verificare"] is True
    assert salvata["procedimento_fonte"]["url"] == VOCE["fonte_url"]
    assert salvata["procedimento_fonte"]["compatibilita"] == "la fonte usa la fecola"
    # Il procedimento del titolare non si tocca.
    assert run(database.ricette.find_one({"id": "manuale"}, {"_id": 0}))["procedimento_testo"] == "Il mio procedimento."

    seconda = run(mod.importa_procedimenti_web({"voci": voci, "dry_run": False}, _admin={"nome": "Admin"}))
    assert seconda["scritte"] == 0 and seconda["gia_presenti"] == 2


def test_modifica_a_mano_rende_il_procedimento_del_titolare(monkeypatch):
    mod, database = _db(monkeypatch)
    run(database.ricette.insert_one({
        "id": "r", "nome": "Pan di Spagna", "ingredienti": ["Uova"],
        "procedimento_testo": "Dal web.", "procedimento_origine": "web",
        "procedimento_fonte": {"url": "https://esempio.it/r"}, "procedimento_da_verificare": True,
    }))

    # Stesso testo e client che prova a scrivere la provenienza: resta web.
    uguale = mod.RicettaCreate(nome="Pan di Spagna", ingredienti=["Uova"], procedimento_testo="Dal web.",
                               procedimento_origine="manuale", procedimento_da_verificare=False)
    salvata = run(mod.update_ricetta("r", uguale, _admin={"nome": "Admin"}))
    assert salvata["procedimento_origine"] == "web"
    assert salvata["procedimento_da_verificare"] is True

    riscritta = mod.RicettaCreate(nome="Pan di Spagna", ingredienti=["Uova"], procedimento_testo="Il mio.")
    salvata = run(mod.update_ricetta("r", riscritta, _admin={"nome": "Admin"}))
    assert salvata["procedimento_origine"] == "manuale"
    assert salvata["procedimento_da_verificare"] is False


def test_conferma_del_titolare(monkeypatch):
    mod, database = _db(monkeypatch)
    run(database.ricette.insert_one({
        "id": "r", "nome": "X", "procedimento_testo": "Dal web.", "procedimento_origine": "web",
        "procedimento_da_verificare": True,
    }))
    confermata = run(mod.conferma_procedimento("r", _admin={"nome": "Admin"}))
    assert confermata["procedimento_da_verificare"] is False
    assert confermata["procedimento_origine"] == "web"
    assert confermata["procedimento_confermato_il"]
