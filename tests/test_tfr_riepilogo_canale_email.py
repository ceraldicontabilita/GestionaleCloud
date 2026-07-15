"""Bug trovato nell'audit funzionale del 15/07/2026: il Fondo TFR di
GET /api/tfr/riepilogo-aziendale leggeva SOLO dipendenti.tfr_accantonato
(campo scritto esclusivamente dall'import manuale Libro Unico, un percorso
che l'utente non usa) e sommava SOLO tfr_accantonamenti.quota_annuale
(idem). Il canale realmente usato — cedolini via email/Drive,
handler_aggiorna_tfr — accumula invece su dipendenti.tfr_maturato e scrive
tfr_accantonamenti.quota: il Fondo TFR mostrava sempre 0 per ogni
dipendente il cui cedolino arriva solo da quel canale."""
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
        elif isinstance(v, dict) and "$regex" in v:
            if not str(doc.get(k, "")).startswith(v["$regex"].lstrip("^")):
                return False
        else:
            if doc.get(k) != v:
                return False
    return True


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, n=None):
        return list(self._docs[:n] if n else self._docs)


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    def find(self, query=None, projection=None, *a, **k):
        return _FakeCursor([d for d in self.docs if _matches(d, query or {})])

    def aggregate(self, pipeline, *a, **k):
        match = pipeline[0].get("$match", {}) if pipeline else {}
        matched = [d for d in self.docs if _matches(d, match)]
        if not matched:
            return _FakeCursor([])
        totale_quota = sum((d.get("quota_annuale") or 0) + (d.get("quota") or 0) for d in matched)
        totale_riv = sum(d.get("rivalutazione") or 0 for d in matched)
        totale_acc = sum((d.get("totale_accantonamento") or 0) + (d.get("quota") or 0) for d in matched)
        return _FakeCursor([{
            "_id": None, "totale_quota": totale_quota, "totale_rivalutazione": totale_riv,
            "totale_accantonato": totale_acc, "num_dipendenti": len(matched),
        }])


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


def test_fondo_tfr_include_i_dipendenti_solo_canale_email(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    db["dipendenti"].docs = [
        # Mai passato dall'import manuale LUL: solo il canale email/Drive
        # (handler_aggiorna_tfr) ha accumulato il suo TFR.
        {"id": "dip-1", "status": "attivo", "nome_completo": "Mario Rossi",
         "tfr_accantonato": 0, "tfr_maturato": 411.0},
        # Dipendente storico, passato solo dall'import manuale LUL.
        {"id": "dip-2", "status": "attivo", "nome_completo": "Anna Bianchi",
         "tfr_accantonato": 823.5, "tfr_maturato": 0},
    ]
    db["tfr_accantonamenti"].docs = []
    db["tfr_liquidazioni"].docs = []

    esito = _run(mod.get_riepilogo_tfr_aziendale(anno=2026))

    assert esito["totale_fondo_tfr"] == 1234.5  # 411.0 + 823.5, non 823.5
    nomi = {d["nome"]: d["tfr_accantonato"] for d in esito["dettaglio_dipendenti"]}
    assert nomi["Mario Rossi"] == 411.0
    assert nomi["Anna Bianchi"] == 823.5


def test_accantonamenti_anno_somma_entrambi_gli_schemi_campo(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    db["dipendenti"].docs = []
    db["tfr_liquidazioni"].docs = []
    db["tfr_accantonamenti"].docs = [
        # Canale email/Drive: campo "quota".
        {"anno": 2026, "quota": 100.0},
        # Import manuale LUL: campo "quota_annuale".
        {"anno": 2026, "quota_annuale": 250.0},
    ]

    esito = _run(mod.get_riepilogo_tfr_aziendale(anno=2026))

    assert esito["accantonamenti_anno"]["totale_quota"] == 350.0
