"""A6 — Copertura cespiti e chiusura esercizio (scrivono stato contabile).

Test di caratterizzazione della logica fiscale:
- classify_asset: esclusioni, keyword→categoria, fallback prezzo ≥ 2000€
- calcolo ammortamenti: primo anno quota dimezzata (prassi fiscale), anni
  successivi quota piena, cap al valore residuo, skip anni già ammortizzati
- verifica preliminare chiusura: fatture non contabilizzate = problema bloccante
- esegui chiusura: conferma obbligatoria + guardia doppia chiusura (409)
"""
import asyncio

import pytest
from fastapi import HTTPException

from app.routers import cespiti as cespiti_mod
from app.routers import chiusura_esercizio as chiusura_mod
from app.routers.cespiti import classify_asset


# ---------- fake db minimale ----------

class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    def skip(self, n):
        return self

    def limit(self, n):
        return self

    async def to_list(self, n=None):
        return list(self._docs)


class _Coll:
    def __init__(self, docs=None):
        self.docs = list(docs or [])
        self.inserted = []

    def find(self, query=None, projection=None):
        return _Cursor(self.docs)

    async def find_one(self, query=None, projection=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in (query or {}).items()
                   if not isinstance(v, dict)):
                return d
        return None

    async def count_documents(self, query=None):
        return len(self.docs)

    def aggregate(self, pipeline):
        return _Cursor(self.docs)

    async def insert_one(self, doc):
        self.inserted.append(doc)
        self.docs.append(doc)


class _Db:
    def __init__(self, colls):
        self._colls = colls

    def __getitem__(self, name):
        return self._colls.setdefault(name, _Coll())


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def _patch_db(monkeypatch, module, colls):
    db = _Db(colls)
    monkeypatch.setattr(module.Database, "get_db", staticmethod(lambda: db))
    return db


# ---------- classify_asset ----------

def test_classify_asset_keyword_categoria():
    assert classify_asset("Forno elettrico ventilato", 3500) == "forni"
    assert classify_asset("Abbattitore di temperatura", 4000) == "frigoriferi"
    assert classify_asset("Notebook per ufficio", 900) == "macchine_ufficio"


def test_classify_asset_esclusioni_vincono():
    # keyword di categoria presente ma il bene è escluso (consumo/servizio)
    assert classify_asset("Noleggio forno a piastra", 5000) is None
    assert classify_asset("Caffè in grani Kimbo", 2500) is None


def test_classify_asset_fallback_prezzo():
    # nessuna keyword primaria: sopra 2000€ scatta il fallback attrezzature
    assert classify_asset("Cappa aspirante inox", 2500) == "attrezzature"
    assert classify_asset("Cappa aspirante inox", 500) is None
    assert classify_asset("Merce varia", 9999) is None


# ---------- calcolo ammortamenti ----------

def _cespite(anno_acquisto=2025, valore=1000.0, coeff=20, fondo=0.0, piano=None):
    return {
        "id": "c1", "descrizione": "Forno", "categoria": "forni",
        "stato": "attivo", "ammortamento_completato": False,
        "valore_acquisto": valore, "coefficiente_ammortamento": coeff,
        "fondo_ammortamento": fondo, "anno_acquisto": anno_acquisto,
        "piano_ammortamento": piano or [],
    }


def test_ammortamento_primo_anno_dimezzato(monkeypatch):
    _patch_db(monkeypatch, cespiti_mod, {"cespiti": _Coll([_cespite(anno_acquisto=2025)])})
    r = _run(cespiti_mod.calcola_ammortamenti_anno(2025))
    assert r["num_cespiti"] == 1
    # 1000 * 20% = 200 → primo anno dimezzato = 100
    assert r["ammortamenti"][0]["quota_anno"] == 100.0
    assert r["ammortamenti"][0]["primo_anno"] is True


def test_ammortamento_anni_successivi_quota_piena(monkeypatch):
    _patch_db(monkeypatch, cespiti_mod,
              {"cespiti": _Coll([_cespite(anno_acquisto=2024, fondo=100.0)])})
    r = _run(cespiti_mod.calcola_ammortamenti_anno(2026))
    assert r["ammortamenti"][0]["quota_anno"] == 200.0
    assert r["ammortamenti"][0]["primo_anno"] is False


def test_ammortamento_cap_al_residuo(monkeypatch):
    # fondo 950 su 1000: la quota piena (200) va limitata al residuo (50)
    _patch_db(monkeypatch, cespiti_mod,
              {"cespiti": _Coll([_cespite(anno_acquisto=2023, fondo=950.0)])})
    r = _run(cespiti_mod.calcola_ammortamenti_anno(2026))
    assert r["ammortamenti"][0]["quota_anno"] == 50.0
    assert r["ammortamenti"][0]["completato"] is True


def test_ammortamento_skip_anno_gia_registrato(monkeypatch):
    _patch_db(monkeypatch, cespiti_mod,
              {"cespiti": _Coll([_cespite(piano=[{"anno": 2026, "quota": 200.0}])])})
    r = _run(cespiti_mod.calcola_ammortamenti_anno(2026))
    assert r["num_cespiti"] == 0
    assert r["totale_ammortamenti"] == 0


# ---------- chiusura esercizio ----------

class _CollCount(_Coll):
    """count_documents parametrico per query (chiavi ordinate)."""
    def __init__(self, count_map=None, default=0):
        super().__init__([])
        self.count_map = count_map or {}
        self.default = default

    async def count_documents(self, query=None):
        chiave = tuple(sorted((query or {}).keys()))
        return self.count_map.get(chiave, self.default)


def test_verifica_preliminare_fatture_non_contabilizzate_bloccano(monkeypatch):
    colls = {
        "invoices": _CollCount(default=3),   # 3 fatture non contabilizzate
        "corrispettivi": _Coll([]),
        "cedolini": _CollCount(default=1),
        "prima_nota_salari": _CollCount(default=1),
        "tfr_accantonamenti": _Coll([{"anno": 2026}]),
        "cespiti": _CollCount(default=0),
        "estratto_conto_movimenti": _CollCount(default=10),
    }
    _patch_db(monkeypatch, chiusura_mod, colls)
    r = _run(chiusura_mod.verifica_preliminare_chiusura(2026))
    assert r["pronto_per_chiusura"] is False
    assert any(p["tipo"] == "fatture_non_contabilizzate" for p in r["problemi_bloccanti"])
    assert r["step_successivo"] == "risolvere_problemi"


def test_verifica_preliminare_tutto_ok(monkeypatch):
    corrisp = [{"_id": f"{m:02d}"} for m in range(1, 13)]  # 12 mesi registrati
    colls = {
        "invoices": _CollCount(default=0),
        "corrispettivi": _Coll(corrisp),
        "cedolini": _CollCount(default=12),
        "prima_nota_salari": _CollCount(default=12),
        "tfr_accantonamenti": _Coll([{"anno": 2026}]),
        "cespiti": _CollCount(default=0),
        "estratto_conto_movimenti": _CollCount(default=100),
    }
    _patch_db(monkeypatch, chiusura_mod, colls)
    r = _run(chiusura_mod.verifica_preliminare_chiusura(2026))
    assert r["pronto_per_chiusura"] is True
    assert r["problemi_bloccanti"] == []
    assert r["step_successivo"] == "bilancino_verifica"


def test_esegui_chiusura_richiede_conferma(monkeypatch):
    _patch_db(monkeypatch, chiusura_mod, {})
    with pytest.raises(HTTPException) as exc:
        _run(chiusura_mod.esegui_chiusura_esercizio(
            chiusura_mod.ChiusuraEsercizioInput(anno=2026, conferma_scritture=False)))
    assert exc.value.status_code == 400


def test_esegui_chiusura_guardia_doppia_chiusura(monkeypatch):
    """A6: senza guardia, la seconda chiusura duplicherebbe il movimento
    di risultato d'esercizio."""
    colls = {"chiusure_esercizio": _Coll([
        {"id": "ch-1", "anno": 2026, "created_at": "2027-01-05T10:00:00"}
    ])}
    _patch_db(monkeypatch, chiusura_mod, colls)
    with pytest.raises(HTTPException) as exc:
        _run(chiusura_mod.esegui_chiusura_esercizio(
            chiusura_mod.ChiusuraEsercizioInput(anno=2026, conferma_scritture=True)))
    assert exc.value.status_code == 409
    assert "già chiuso" in exc.value.detail
