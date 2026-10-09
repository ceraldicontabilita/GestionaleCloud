import asyncio


def run(coro):
    return asyncio.run(coro)


class FakeOutboxDatabase:
    def __init__(self, events):
        self.events = events
        self.claim_limit = None
        self.completed = []
        self.failed = []

    async def outbox_claim(self, limit):
        self.claim_limit = limit
        return list(self.events)

    async def outbox_complete(self, event_id, lock_token):
        self.completed.append((event_id, lock_token))
        return True

    async def outbox_fail(self, event_id, lock_token, error):
        self.failed.append((event_id, lock_token, error))
        return True


def test_worker_completa_la_proiezione_fattura(monkeypatch):
    from app.database import Database
    from app.services import domain_outbox_worker as worker

    fake = FakeOutboxDatabase([{
        "id": "event-1", "lock_token": "token-1",
        "event_type": "invoice.project", "aggregate_id": "invoice-1",
    }])
    monkeypatch.setattr(Database, "db", fake)

    async def alimenta(source_id):
        assert source_id == "invoice-1"
        return {"stato": "alimentata", "fattura_id": "lotti-1"}

    monkeypatch.setattr(
        "app.lotti.routers.gestionale_fatture.alimenta_lotti_da_fattura", alimenta,
    )

    assert run(worker.processa_domain_outbox()) == {
        "presi": 1, "completati": 1, "falliti": 0,
    }
    assert fake.completed == [("event-1", "token-1")]
    assert fake.failed == []


def test_worker_registra_errore_e_lascia_il_retry_al_database(monkeypatch):
    from app.database import Database
    from app.services import domain_outbox_worker as worker

    fake = FakeOutboxDatabase([{
        "id": "event-2", "lock_token": "token-2",
        "event_type": "invoice.project", "aggregate_id": "invoice-2",
    }])
    monkeypatch.setattr(Database, "db", fake)

    async def alimenta(_source_id):
        return {"stato": "errore", "motivo": "XML non valido"}

    monkeypatch.setattr(
        "app.lotti.routers.gestionale_fatture.alimenta_lotti_da_fattura", alimenta,
    )

    assert run(worker.processa_domain_outbox()) == {
        "presi": 1, "completati": 0, "falliti": 1,
    }
    assert fake.completed == []
    assert fake.failed[0][:2] == ("event-2", "token-2")
    assert "XML non valido" in fake.failed[0][2]


def test_worker_senza_backend_supabase_non_fallisce(monkeypatch):
    from app.database import Database
    from app.services import domain_outbox_worker as worker

    monkeypatch.setattr(Database, "db", object())
    assert run(worker.processa_domain_outbox()) == {
        "presi": 0, "completati": 0, "falliti": 0,
    }
