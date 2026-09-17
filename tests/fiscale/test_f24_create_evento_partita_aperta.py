"""Bug trovato in audit 15/07/2026: create_f24 (POST /api/f24) costruiva
l'evento F24_ACQUISITO leggendo chiavi ("importo_totale", "data_scadenza",
"periodo", "codice_tributo") diverse da quelle realmente salvate nel dict
f24 ("importo", "scadenza", "periodo_riferimento", "codici_tributo") —
sempre None. L'handler on_f24_acquisito_crea_partita
(app/services/handlers/f24_handlers.py) esce subito se importo è falsy,
quindi la partita aperta (debito verso Erario) non veniva mai creata per
gli F24 inseriti tramite questo endpoint, e l'except silenzioso non
segnalava nulla."""
import asyncio

from app.routers.f24 import f24_main as mod


class _FakeCollection:
    def __init__(self):
        self.docs = []

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))

    async def find_one(self, query, *a, **k):
        return None


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def test_create_f24_propaga_evento_con_chiavi_corrette(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    eventi = []

    async def fake_propagate_event(event_type, payload, db, source_module=None):
        eventi.append((event_type, payload))

    monkeypatch.setattr("app.services.event_bus.propagate_event", fake_propagate_event)

    payload_richiesta = {
        "importo": 1234.56,
        "scadenza": "2026-08-16",
        "periodo_riferimento": "07/2026",
        "codici_tributo": ["6001", "1001"],
    }

    esito = _run(mod.create_f24(data=payload_richiesta, current_user={"user_id": "u1"}))

    assert esito["importo"] == 1234.56
    assert len(eventi) == 1
    _, evento_payload = eventi[0]
    # Queste quattro chiavi erano SEMPRE None prima del fix.
    assert evento_payload["importo_totale"] == 1234.56
    assert evento_payload["data_scadenza"] == "2026-08-16"
    assert evento_payload["periodo"] == "07/2026"
    assert evento_payload["codice_tributo"] == "6001, 1001"
    assert evento_payload["f24_id"] == esito["id"]
