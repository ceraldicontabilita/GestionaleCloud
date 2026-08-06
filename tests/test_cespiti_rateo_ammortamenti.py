"""Richiesta utente 15/07/2026: per il bilancio provvisorio (infra-annuale)
serve un ammortamento a rateo mensile, non la quota annuale intera. Rateo
lineare da inizio anno: quota annuale ordinaria / 12 * mesi trascorsi. Solo
preview, come /calcolo/{anno}: non scrive mai su cespiti."""
import asyncio

import pytest
from fastapi import HTTPException

from app.routers import cespiti as mod


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, n=None):
        return list(self._docs[:n] if n else self._docs)


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    def find(self, query=None, projection=None, *a, **k):
        def matches(d):
            return all(d.get(k2) == v2 for k2, v2 in (query or {}).items())
        return _FakeCursor([d for d in self.docs if matches(d)])


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


def test_rateo_a_giugno_e_meta_della_quota_annuale(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    db["cespiti"].docs = [
        {
            "id": "c1", "descrizione": "Forno industriale", "categoria": "forni",
            "stato": "attivo", "ammortamento_completato": False,
            "valore_acquisto": 12000.0, "coefficiente_ammortamento": 12,
            "fondo_ammortamento": 0, "anno_acquisto": 2024,
            "data_entrata_funzione": "2024-01-01",
            "piano_ammortamento": [],
        },
    ]

    esito = _run(mod.calcola_rateo_ammortamenti(anno=2026, mese=6))

    quota_annua = 12000.0 * 12 / 100  # 1440, non è l'anno di acquisto: quota intera
    assert esito["cespiti"][0]["quota_annua_ordinaria"] == quota_annua
    assert esito["totale_rateo"] == round(quota_annua / 12 * 6, 2)  # 720.0


def test_rateo_anno_di_acquisto_usa_quota_dimezzata(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    db["cespiti"].docs = [
        {
            "id": "c2", "descrizione": "Frigo nuovo", "categoria": "frigoriferi",
            "stato": "attivo", "ammortamento_completato": False,
            "valore_acquisto": 6000.0, "coefficiente_ammortamento": 12,
            "fondo_ammortamento": 0, "anno_acquisto": 2026,
            "data_entrata_funzione": "2026-02-01",
            "piano_ammortamento": [],
        },
    ]

    esito = _run(mod.calcola_rateo_ammortamenti(anno=2026, mese=12))

    quota_ordinaria = 6000.0 * 12 / 100  # 720
    quota_annua_dimezzata = quota_ordinaria / 2  # 360 (primo anno)
    assert esito["cespiti"][0]["quota_annua_ordinaria"] == quota_annua_dimezzata
    assert esito["totale_rateo"] == round(quota_annua_dimezzata, 2)  # a dicembre, rateo = quota intera dimezzata


def test_cespite_gia_ammortizzato_definitivamente_escluso(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    db["cespiti"].docs = [
        {
            "id": "c3", "descrizione": "Lavastoviglie", "categoria": "attrezzature",
            "stato": "attivo", "ammortamento_completato": False,
            "valore_acquisto": 3000.0, "coefficiente_ammortamento": 15,
            "fondo_ammortamento": 450, "anno_acquisto": 2025,
            "data_entrata_funzione": "2025-01-01",
            "piano_ammortamento": [{"anno": 2026, "quota_anno": 450}],
        },
    ]

    esito = _run(mod.calcola_rateo_ammortamenti(anno=2026, mese=6))

    assert esito["cespiti"] == []
    assert esito["totale_rateo"] == 0


def test_cespite_acquistato_dopo_l_anno_richiesto_escluso(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    db["cespiti"].docs = [
        {
            "id": "c4", "descrizione": "Insegna", "categoria": "insegne",
            "stato": "attivo", "ammortamento_completato": False,
            "valore_acquisto": 2000.0, "coefficiente_ammortamento": 20,
            "fondo_ammortamento": 0, "anno_acquisto": 2027,
            "data_entrata_funzione": "2027-01-01",
            "piano_ammortamento": [],
        },
    ]

    esito = _run(mod.calcola_rateo_ammortamenti(anno=2026, mese=6))

    assert esito["cespiti"] == []


def test_rifiuta_mese_non_valido(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    db["cespiti"].docs = []

    with pytest.raises(HTTPException) as exc:
        _run(mod.calcola_rateo_ammortamenti(anno=2026, mese=13))
    assert exc.value.status_code == 400
