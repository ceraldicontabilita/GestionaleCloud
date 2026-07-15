"""Bug "gravissimo" trovato nell'audit funzionale del 15/07/2026:
apertura_nuovo_esercizio() calcolava il saldo cassa/banca del solo anno
precedente e lo inseriva come movimento "Riporto" in prima_nota_cassa/banca
per il nuovo anno. Ma calcola_saldo_anni_precedenti() (prima_nota_module/
common.py, la funzione UNICA di saldo §6.4) somma già TUTTI i movimenti
reali con data < 1/1/anno per calcolare il riporto — è automaticamente
cumulativo. Il movimento "Riporto" si sommava quindi IN PIÙ al saldo già
riportato dai movimenti reali, raddoppiando permanentemente il saldo ad ogni
apertura d'esercizio (e l'errore si accumulava a ogni chiusura successiva).

Verificato in produzione (letture autorizzate) che nessuna chiusura era mai
stata eseguita (storico vuoto): nessun dato reale è stato corrotto, ma il
bottone "Apri nuovo esercizio" lo avrebbe fatto alla prima chiusura d'anno.

Il fix rimuove la scrittura duplicata: il riepilogo saldi resta comunque
salvato in aperture_esercizio (letto da GET /saldi-iniziali/{anno})."""
import asyncio

from app.routers import chiusura_esercizio as mod


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def _matches(doc, query):
    for k, v in query.items():
        if isinstance(v, dict) and "$ne" in v:
            if doc.get(k) == v["$ne"]:
                return False
        elif isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]:
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

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if _matches(d, query):
                return dict(d)
        return None

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))

    def aggregate(self, pipeline, *a, **k):
        match = pipeline[0].get("$match", {}) if pipeline else {}
        matched = [d for d in self.docs if _matches(d, match)]
        totale = sum(d.get("importo", 0) for d in matched)
        return _FakeCursor([{"_id": None, "totale": totale}] if matched else [])


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


def test_apertura_esercizio_non_crea_movimenti_riporto(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    db["chiusure_esercizio"].docs = [{"anno": 2025}]
    db["prima_nota_cassa"].docs = [
        {"anno": 2025, "tipo": "entrata", "importo": 5000.0},
        {"anno": 2025, "tipo": "uscita", "importo": 2000.0},
    ]
    db["prima_nota_banca"].docs = [
        {"anno": 2025, "tipo": "entrata", "importo": 8000.0},
        {"anno": 2025, "tipo": "uscita", "importo": 1000.0},
    ]

    n_cassa_prima = len(db["prima_nota_cassa"].docs)
    n_banca_prima = len(db["prima_nota_banca"].docs)

    esito = _run(mod.apertura_nuovo_esercizio(2026))

    assert esito["saldi_riportati"]["saldo_cassa"] == 3000.0
    assert esito["saldi_riportati"]["saldo_banca"] == 7000.0
    # Nessun movimento aggiuntivo creato in Prima Nota: il riporto resta
    # solo nel documento aperture_esercizio, non duplicato come scrittura.
    assert len(db["prima_nota_cassa"].docs) == n_cassa_prima
    assert len(db["prima_nota_banca"].docs) == n_banca_prima

    apertura = db["aperture_esercizio"].docs[0]
    assert apertura["saldi_riportati"]["saldo_cassa"] == 3000.0
    assert apertura["saldi_riportati"]["saldo_banca"] == 7000.0


def test_saldi_iniziali_letti_da_aperture_esercizio_non_da_prima_nota(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    db["aperture_esercizio"].docs = [{
        "anno": 2026, "data": "2026-01-01", "anno_precedente": 2025,
        "saldi_riportati": {"saldo_cassa": 3000.0, "saldo_banca": 7000.0},
    }]

    esito = _run(mod.get_saldi_iniziali(2026))

    assert esito["saldi"]["saldo_cassa"] == 3000.0
