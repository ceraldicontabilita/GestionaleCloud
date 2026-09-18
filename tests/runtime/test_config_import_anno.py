"""Anno di importazione attivo (richiesta utente 14/07/2026): un solo
selettore globale, condiviso da tutti i canali di import automatico che
supportano il filtro anno (Drive fatture, Drive corrispettivi)."""
import asyncio

from app.services import config_import as mod


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if all(d.get(k2) == v2 for k2, v2 in query.items()):
                return dict(d)
        return None

    async def update_one(self, query, update, *a, **k):
        for d in self.docs:
            if all(d.get(k2) == v2 for k2, v2 in query.items()):
                d.update(update.get("$set", {}))
                return
        nuovo = dict(query)
        nuovo.update(update.get("$set", {}))
        self.docs.append(nuovo)


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


def test_default_anno_solare_corrente_se_mai_impostato():
    from datetime import datetime, timezone
    db = _FakeDb()

    anno = _run(mod.get_anno_importazione_attivo(db))

    assert anno == datetime.now(timezone.utc).year


def test_set_poi_get_ritorna_anno_configurato():
    db = _FakeDb()

    _run(mod.set_anno_importazione_attivo(db, 2025))
    anno = _run(mod.get_anno_importazione_attivo(db))

    assert anno == 2025


def test_set_sovrascrive_valore_precedente():
    db = _FakeDb()

    _run(mod.set_anno_importazione_attivo(db, 2025))
    _run(mod.set_anno_importazione_attivo(db, 2026))
    anno = _run(mod.get_anno_importazione_attivo(db))

    assert anno == 2026
    assert len(db["sistema_stato"].docs) == 1  # upsert, non due doc


def test_set_rifiuta_anno_non_plausibile():
    import pytest
    db = _FakeDb()

    with pytest.raises(ValueError):
        _run(mod.set_anno_importazione_attivo(db, 1500))
