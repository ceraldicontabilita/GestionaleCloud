"""La campana degli alert e la pagina «Alert operativi» contano gli stessi
aperti. 25/09/2026: 3.023 contro 6.224, perche' gli alert senza gravita'
sovrascrivevano il conteggio degli «info» invece di sommarsi."""
import asyncio

from mongomock_motor import AsyncMongoMockClient


def test_totale_campana_uguale_alla_lista(monkeypatch):
    import app.routers.alerts as mod

    db = AsyncMongoMockClient()["t"]
    docs = (
        [{"id": f"i{i}", "stato": "aperto", "risolto": False, "severita": "info"} for i in range(5)]
        + [{"id": f"w{i}", "stato": "aperto", "risolto": False, "severita": "warning"} for i in range(3)]
        + [{"id": f"c{i}", "stato": "aperto", "risolto": False, "severita": "critical"} for i in range(2)]
        + [{"id": f"x{i}", "risolto": False} for i in range(2)]          # legacy, senza gravita'
        + [{"id": f"r{i}", "stato": "risolto", "risolto": True, "severita": "info"} for i in range(4)]
    )
    asyncio.run(db["alerts"].insert_many(docs))
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    riepilogo = asyncio.run(mod.alerts_summary())
    lista = asyncio.run(mod.lista_alerts(tipo=None, severita=None, modulo=None, alert_id=None,
                                         stato="aperto", letto=None, risolto=None, limit=50, offset=0))
    assert riepilogo["totale_aperti"] == 12
    assert lista["stats"]["totale_filtrato"] == 12
    assert riepilogo["per_severita"] == {"critical": 2, "warning": 3, "info": 7}
