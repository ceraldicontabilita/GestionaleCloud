"""GET /api/tfr/situazione/{dipendente_id} aveva lo stesso bug già corretto
in get_riepilogo_tfr_aziendale (15/07/2026): leggeva il TFR accumulato SOLO
da dipendenti.tfr_accantonato (valorizzato solo dall'import manuale Libro
Unico, mai usato in pratica), mostrando sempre 0 per i dipendenti il cui
TFR viene accumulato dal canale realmente attivo (cedolini email/Drive,
handler_aggiorna_tfr, che scrive su tfr_maturato). Questo endpoint alimenta
il registro TFR mese per mese in UI: deve mostrare il dato reale."""
import asyncio

from app.routers import tfr as mod


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def _matches(doc, query):
    for k, v in query.items():
        if isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]:
                return False
        else:
            if doc.get(k) != v:
                return False
    return True


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

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if _matches(d, query or {}):
                return dict(d)
        return None

    def find(self, query=None, projection=None, *a, **k):
        return _FakeCursor([d for d in self.docs if _matches(d, query or {})])


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


def test_situazione_tfr_usa_tfr_maturato_canale_cedolini(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    db["dipendenti"].docs = [
        {"id": "dip-1", "nome_completo": "Mario Rossi",
         "tfr_accantonato": 0, "tfr_maturato": 411.0},
    ]
    db["tfr_accantonamenti"].docs = [
        {"dipendente_id": "dip-1", "anno": 2026, "mese": 5, "quota": 137.0},
        {"dipendente_id": "dip-1", "anno": 2026, "mese": 6, "quota": 137.0},
        {"dipendente_id": "dip-1", "anno": 2026, "mese": 7, "quota": 137.0},
    ]
    db["tfr_liquidazioni"].docs = []

    esito = _run(mod.get_situazione_tfr(dipendente_id="dip-1"))

    assert esito["tfr_accantonato"] == 411.0  # non 0
    periodi = [a["periodo"] for a in esito["accantonamenti"]]
    assert periodi == ["05/2026", "06/2026", "07/2026"]  # ordine mese per mese
    assert esito["accantonamenti"][0]["quota_mese"] == 137.0


def test_situazione_tfr_registro_misto_email_e_manuale_lul(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    db["dipendenti"].docs = [
        {"id": "dip-2", "nome_completo": "Anna Bianchi",
         "tfr_accantonato": 823.5, "tfr_maturato": 0},
    ]
    db["tfr_accantonamenti"].docs = [
        {"dipendente_id": "dip-2", "anno": 2025, "quota_annuale": 800.0},
        {"dipendente_id": "dip-2", "anno": 2026, "mese": 3, "quota": 23.5},
    ]
    db["tfr_liquidazioni"].docs = []

    esito = _run(mod.get_situazione_tfr(dipendente_id="dip-2"))

    assert esito["tfr_accantonato"] == 823.5
    periodi = [a["periodo"] for a in esito["accantonamenti"]]
    assert periodi == ["Anno 2025 (import manuale)", "03/2026"]
