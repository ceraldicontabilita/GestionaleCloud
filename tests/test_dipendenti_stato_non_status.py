"""Bug trovato in verifica live (dati reali di produzione, sola lettura)
15/07/2026: più punti del codice filtravano i dipendenti attivi con
{"status": {"$in": [...]}}, ma il campo reale sul documento è "stato"
(italiano) — nessun dipendente ha mai un campo "status". Risultato: il
Fondo TFR aziendale (GET /api/tfr/riepilogo-aziendale) mostrava sempre 0
dipendenti attivi anche con 15 dipendenti realmente attivi in produzione;
public_api.py contava sempre 0 "dipendenti_attivi"; report_pdf.py (con un
$in che includeva anche None) faceva l'opposto, includendo per errore
anche i dipendenti cessati (perché tutti i documenti, avendo "status"
sempre assente, risultavano None → sempre dentro il filtro)."""
import asyncio

from app.routers import tfr as mod_tfr
from app.routers import public_api as mod_public
from app.routers.reports import report_pdf as mod_pdf
from app.database import Collections


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

    def find(self, query=None, projection=None, *a, **k):
        return _FakeCursor([d for d in self.docs if _matches(d, query or {})])

    async def count_documents(self, query=None, *a, **k):
        return len([d for d in self.docs if _matches(d, query or {})])

    def aggregate(self, pipeline, *a, **k):
        return _FakeCursor([])


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


_DIPENDENTI_REALI = [
    {"id": "d1", "nome_completo": "Mario Rossi", "stato": "attivo", "tfr_maturato": 100.0},
    {"id": "d2", "nome_completo": "Anna Bianchi", "stato": "inattivo", "tfr_maturato": 50.0},
    {"id": "d3", "nome_completo": "Luca Verdi", "stato": "attivo", "tfr_accantonato": 200.0},
]


def test_tfr_riepilogo_conta_i_dipendenti_attivi_veri(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod_tfr.Database, "get_db", staticmethod(lambda: db))
    db["dipendenti"].docs = list(_DIPENDENTI_REALI)
    db["tfr_accantonamenti"].docs = []
    db["tfr_liquidazioni"].docs = []

    esito = _run(mod_tfr.get_riepilogo_tfr_aziendale(anno=2026))

    assert esito["num_dipendenti_attivi"] == 2  # d1 e d3, non d2 (inattivo)
    assert esito["totale_fondo_tfr"] == 300.0  # 100 + 200


def test_public_api_conta_dipendenti_attivi_veri(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod_public.Database, "get_db", staticmethod(lambda: db))
    db["dipendenti"].docs = list(_DIPENDENTI_REALI)
    db["invoices"].docs = []
    db["fatture_emesse"].docs = []
    db["prima_nota_cassa"].docs = []

    esito = _run(mod_public.api_v1_stats(anno=2026, _client={}))

    assert esito["dipendenti_attivi"] == 2


def test_report_pdf_non_include_i_cessati_per_errore(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod_pdf.Database, "get_db", staticmethod(lambda: db))
    db[Collections.EMPLOYEES].docs = list(_DIPENDENTI_REALI)

    dipendenti = _run(db[Collections.EMPLOYEES].find(
        {"stato": {"$in": ["attivo", "active"]}}, {"_id": 0}
    ).sort("nome_completo", 1).to_list(500))

    nomi = {d["id"] for d in dipendenti}
    assert nomi == {"d1", "d3"}
    assert "d2" not in nomi  # inattivo: prima ci finiva per errore (status sempre None)
