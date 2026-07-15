"""Nuova sezione richiesta dall'utente 15/07/2026: voci di bilancio che il
sistema non può derivare da prima nota/fatture/cedolini (capitale sociale,
riserva legale, immobilizzazioni non tracciate da cespiti/XML). Usa SOLO
codici del piano dei conti CEE ufficiale (regola vincolante CLAUDE.md)."""
import asyncio

import pytest
from fastapi import HTTPException

from app.routers import voci_bilancio as mod


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    async def to_list(self, n=None):
        return list(self._docs[:n] if n else self._docs)


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    def find(self, query=None, projection=None, *a, **k):
        return _FakeCursor([d for d in self.docs if self._matches(d, query or {})])

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if self._matches(d, query):
                return dict(d)
        return None

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, *a, **k):
        for d in self.docs:
            if self._matches(d, query):
                d.update(update.get("$set", {}))

    async def delete_one(self, query, *a, **k):
        before = len(self.docs)
        self.docs = [d for d in self.docs if not self._matches(d, query)]

        class _Res:
            deleted_count = before - len(self.docs)
        return _Res()

    @staticmethod
    def _matches(doc, query):
        return all(doc.get(k) == v for k, v in query.items())


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


def test_crea_voce_capitale_sociale(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    esito = _run(mod.upsert_voce_bilancio(mod.VoceBilancioInput(
        codice_cee="23.01.01", importo=10000.0, anno=2026,
    )))

    assert esito["aggiornata"] is False
    voci = _run(mod.get_voci_bilancio(anno=2026))
    assert voci["totale_patrimonio_netto"] == 10000.0
    assert voci["voci"][0]["descrizione"] == "Capitale sociale"


def test_upsert_stesso_codice_stesso_anno_aggiorna_non_duplica(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    _run(mod.upsert_voce_bilancio(mod.VoceBilancioInput(
        codice_cee="23.01.05", importo=500.0, anno=2026,
    )))
    esito = _run(mod.upsert_voce_bilancio(mod.VoceBilancioInput(
        codice_cee="23.01.05", importo=800.0, anno=2026,
    )))

    assert esito["aggiornata"] is True
    voci = _run(mod.get_voci_bilancio(anno=2026))
    assert len(voci["voci"]) == 1
    assert voci["voci"][0]["importo"] == 800.0


def test_rifiuta_codice_fuori_stato_patrimoniale(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    with pytest.raises(HTTPException) as exc:
        _run(mod.upsert_voce_bilancio(mod.VoceBilancioInput(
            codice_cee="55.01.07", importo=100.0, anno=2026,  # Acquisti merci: Conto Economico
        )))
    assert exc.value.status_code == 400


def test_rifiuta_codice_sp_non_ammesso(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    with pytest.raises(HTTPException) as exc:
        _run(mod.upsert_voce_bilancio(mod.VoceBilancioInput(
            codice_cee="33.03.01", importo=100.0, anno=2026,  # Debiti fornitori: calcolati, non manuali
        )))
    assert exc.value.status_code == 400


def test_elimina_voce(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    creata = _run(mod.upsert_voce_bilancio(mod.VoceBilancioInput(
        codice_cee="05.07.01", importo=3000.0, anno=2026,
    )))
    _run(mod.delete_voce_bilancio(creata["id"]))

    voci = _run(mod.get_voci_bilancio(anno=2026))
    assert voci["voci"] == []


def test_totale_immobilizzazioni_somma_solo_macro_03_05_07(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    _run(mod.upsert_voce_bilancio(mod.VoceBilancioInput(codice_cee="05.07.01", importo=3000.0, anno=2026)))
    _run(mod.upsert_voce_bilancio(mod.VoceBilancioInput(codice_cee="23.01.01", importo=10000.0, anno=2026)))

    voci = _run(mod.get_voci_bilancio(anno=2026))
    assert voci["totale_immobilizzazioni"] == 3000.0
    assert voci["totale_patrimonio_netto"] == 10000.0
