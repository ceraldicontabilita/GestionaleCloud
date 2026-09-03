import asyncio
from datetime import datetime, timezone

from mongomock_motor import AsyncMongoMockClient


def run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def test_riordino_crea_una_sola_bozza_con_provenienza(monkeypatch):
    import app.lotti.routers.ordini_fornitori as ordini
    import app.lotti.routers.corrispettivi as corrispettivi
    import app.lotti.routers.prodotti_master as prodotti_master
    import app.lotti.routers.chiusure as chiusure
    database = AsyncMongoMockClient()["Gestionale_Test"]
    for modulo in (ordini, corrispettivi, prodotti_master, chiusure):
        monkeypatch.setattr(modulo, "db", database)

    class DataFissa(datetime):
        @classmethod
        def now(cls, tz=None):
            valore = cls(2026, 8, 23, 8, 0, tzinfo=timezone.utc)
            return valore.astimezone(tz) if tz else valore.replace(tzinfo=None)

    monkeypatch.setattr(ordini, "datetime", DataFissa)
    run(database.magazzino_bar_prodotti.insert_one({
        "id": "P1", "nome": "Farina prova", "stock": 0,
        "soglia_minima": 5, "quantita_riordino": 10,
        "unita": "pz", "fornitore": "Fornitore Test",
    }))
    run(database.fornitori_anagrafica.insert_one({
        "nome": "Fornitore Test", "procedura_ordini_attiva": True,
        "giorni_consegna_settimana": [0, 3], "lead_time_giorni": 1,
    }))

    primo = run(ordini.esegui_riordino_automatico(False))
    secondo = run(ordini.esegui_riordino_automatico(False))
    assert len(primo["bozze_create"]) == 1
    assert secondo["bozze_create"] == []
    assert run(database.ordini_fornitori.count_documents({})) == 1
    bozza = run(database.ordini_fornitori.find_one({}, {"_id": 0}))
    assert bozza["id"].startswith("riordino-auto:2026-08-23:")
    assert bozza["stato"] == "bozza"
    assert bozza["pianificazione"]["calendario_verificato"] is True
    assert bozza["prodotti"][0]["quantita_base"] == 10
    assert bozza["prodotti"][0]["pianificazione"]["corrispettivi_verificati"] is False
