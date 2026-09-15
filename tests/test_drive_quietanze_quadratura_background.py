"""15/09/2026: la quadratura quietanze F24 (POST /api/f24/quietanze/drive/
quadratura) girava sincrona dentro la richiesta HTTP. Con le decine di PDF
reali gia' in "Elaborate" (scaricati e confrontati uno per uno) supera il
timeout del gateway Render (~150s): osservato live, due tentativi finiti in
502 senza scrivere nulla. Stesso motivo per cui /drive/sync gira già in
background (start_background_sync) — ora anche la quadratura usa lo stesso
pattern lock+task, senza cambiare la logica di scansione.
"""
import asyncio

from app.services import drive_quietanze_ingest as dq


class _FakeCollection:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if all(d.get(k2) == v for k2, v in query.items()):
                return d
        return None

    async def update_one(self, query, update, *a, **k):
        for d in self.docs:
            if all(d.get(k2) == v for k2, v in query.items()):
                for k2, v in update.get("$set", {}).items():
                    d[k2] = v
                return
        doc = dict(query)
        for k2, v in update.get("$set", {}).items():
            doc[k2] = v
        self.docs.append(doc)


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


def test_start_background_quadratura_non_blocca_e_non_duplica(monkeypatch):
    db = _FakeDb()
    release = asyncio.Event()
    chiamate = []

    async def _finta_do_quadratura(_db):
        chiamate.append(1)
        await release.wait()
        return {"status": "ok", "controllati": 1, "quadrati": 0, "recuperati": 1, "errori": 0}

    monkeypatch.setattr(dq, "_do_quadratura", _finta_do_quadratura)

    async def scenario():
        assert dq.is_quadratura_running() is False
        primo = dq.start_background_quadratura(db)
        assert primo is True
        await asyncio.sleep(0)  # lascia partire il task appena creato
        assert dq.is_quadratura_running() is True

        # un secondo avvio mentre il primo e' ancora in corso non parte
        secondo = dq.start_background_quadratura(db)
        assert secondo is False
        assert len(chiamate) == 1

        release.set()
        await dq._quad_bg_task
        assert dq.is_quadratura_running() is False

    asyncio.run(scenario())


def test_verifica_quadratura_elaborate_segnala_running_se_gia_in_corso(monkeypatch):
    db = _FakeDb()
    release = asyncio.Event()

    async def _finta_do_quadratura(_db):
        await release.wait()
        return {"status": "ok"}

    monkeypatch.setattr(dq, "_do_quadratura", _finta_do_quadratura)

    async def scenario():
        primo = asyncio.create_task(dq.verifica_quadratura_elaborate(db))
        await asyncio.sleep(0)  # lascia entrare il primo nel lock

        secondo = await dq.verifica_quadratura_elaborate(db)
        assert secondo == {"status": "running", "message": "Quadratura gia' in corso"}

        release.set()
        risultato_primo = await primo
        assert risultato_primo == {"status": "ok"}

    asyncio.run(scenario())


def test_get_status_espone_quadratura_running_e_last_quadratura(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(dq, "is_configured", lambda: False)
    db["sistema_stato"].docs.append({
        "chiave": dq._STATO_KEY,
        "last_quadratura": {"quando": "2026-09-14T05:45:00Z", "controllati": 70, "recuperati": 3, "errori": 0},
    })

    stato = asyncio.run(dq.get_status(db))

    assert stato["quadratura_running"] is False
    assert stato["last_quadratura"]["recuperati"] == 3


def test_router_quadratura_avvia_in_background_e_risponde_subito(monkeypatch):
    from app.routers import drive_quietanze as router_mod

    monkeypatch.setattr(router_mod.Database, "get_db", staticmethod(lambda: object()))
    monkeypatch.setattr(router_mod.drive_quietanze_ingest, "is_configured", lambda: True)
    monkeypatch.setattr(router_mod.drive_quietanze_ingest, "start_background_quadratura", lambda _db: True)

    esito = asyncio.run(router_mod.drive_quadratura())

    assert esito == {"status": "started", "message": "Quadratura avviata"}


def test_router_quadratura_segnala_se_gia_in_corso(monkeypatch):
    from app.routers import drive_quietanze as router_mod

    monkeypatch.setattr(router_mod.Database, "get_db", staticmethod(lambda: object()))
    monkeypatch.setattr(router_mod.drive_quietanze_ingest, "is_configured", lambda: True)
    monkeypatch.setattr(router_mod.drive_quietanze_ingest, "start_background_quadratura", lambda _db: False)

    esito = asyncio.run(router_mod.drive_quadratura())

    assert esito == {"status": "running", "message": "Quadratura già in corso"}


def test_router_quadratura_not_configured_resta_sincrono(monkeypatch):
    from app.routers import drive_quietanze as router_mod

    monkeypatch.setattr(router_mod.Database, "get_db", staticmethod(lambda: object()))
    monkeypatch.setattr(router_mod.drive_quietanze_ingest, "is_configured", lambda: False)

    async def _finto_verifica(_db):
        return {"status": "not_configured"}

    monkeypatch.setattr(router_mod.drive_quietanze_ingest, "verifica_quadratura_elaborate", _finto_verifica)

    esito = asyncio.run(router_mod.drive_quadratura())

    assert esito == {"status": "not_configured"}
