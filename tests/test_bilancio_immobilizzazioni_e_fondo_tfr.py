"""Bug trovato lavorando sulla richiesta utente 15/07/2026 (voci di
bilancio manuali): GET /api/accounting/bilancio/stato-patrimoniale non
includeva MAI le immobilizzazioni (né i cespiti tracciati in
GestioneCespiti né eventuali voci inserite a mano) né il fondo TFR (un
debito reale verso i dipendenti) — lo stato patrimoniale ometteva intere
voci di bilancio, sovrastimando il patrimonio netto calcolato per
differenza."""
import asyncio

from app.routers.accounting import bilancio as mod


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
    def __init__(self, name, docs=None):
        self.name = name
        self.docs = docs or []

    def find(self, query=None, projection=None, *a, **k):
        return _FakeCursor([d for d in self.docs if self._matches_or(d, query or {})])

    def aggregate(self, pipeline, *a, **k):
        match = pipeline[0].get("$match", {}) if pipeline else {}
        matched = [d for d in self.docs if self._matches_or(d, match)]
        if not matched:
            return _FakeCursor([])
        if self.name in ("prima_nota_cassa", "prima_nota_banca"):
            entrate = sum(d.get("importo", 0) for d in matched if d.get("tipo") == "entrata")
            uscite = sum(d.get("importo", 0) for d in matched if d.get("tipo") == "uscita")
            return _FakeCursor([{"_id": None, "entrate": entrate, "uscite": uscite}])
        if self.name == "tfr_accantonamenti":
            totale = sum((d.get("quota") or 0) + (d.get("quota_annuale") or 0) for d in matched)
            return _FakeCursor([{"_id": None, "totale": totale}])
        totale = sum(d.get("total_amount") or d.get("importo_totale") or 0 for d in matched)
        return _FakeCursor([{"_id": None, "totale": totale}])

    @staticmethod
    def _matches(doc, query):
        for k, v in query.items():
            if isinstance(v, dict) and "$lte" in v:
                if doc.get(k) is None or doc.get(k) > v["$lte"]:
                    return False
            elif isinstance(v, dict) and "$nin" in v:
                if doc.get(k) in v["$nin"]:
                    return False
            elif isinstance(v, dict) and "$ne" in v:
                if doc.get(k) == v["$ne"]:
                    return False
            elif isinstance(v, dict) and "$exists" in v:
                if (k in doc) != v["$exists"]:
                    return False
            elif isinstance(v, dict) and "$lt" in v:
                if doc.get(k) is None or not (doc.get(k) < v["$lt"]):
                    return False
            else:
                if doc.get(k) != v:
                    return False
        return True

    def _matches_or(self, doc, query):
        if "$or" in query:
            return any(self._matches_or(doc, sub) for sub in query["$or"])
        return self._matches(doc, query)


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection(name))


def test_immobilizzazioni_da_cespiti_entrano_nell_attivo(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    db["prima_nota_cassa"].docs = []
    db["prima_nota_banca"].docs = []
    db["fatture_emesse"].docs = []
    db[mod.Collections.INVOICES].docs = []
    db["cespiti"].docs = [
        {"stato": "attivo", "data_acquisto": "2025-03-01", "valore_residuo": 4000.0},
        {"stato": "attivo", "data_acquisto": "2026-08-01", "valore_residuo": 1000.0},  # dopo data_fine
    ]
    db["voci_bilancio_manuali"].docs = []
    db["tfr_accantonamenti"].docs = []

    esito = _run(mod.get_stato_patrimoniale(anno=2026, mese=6, data_a=None))

    assert esito["attivo"]["immobilizzazioni"]["da_cespiti"] == 4000.0  # non 5000: il cespite di agosto non c'è ancora a giugno
    assert esito["attivo"]["totale_attivo"] == 4000.0


def test_fondo_tfr_entra_nel_passivo_fino_a_data_fine(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    db["prima_nota_cassa"].docs = []
    db["prima_nota_banca"].docs = []
    db["fatture_emesse"].docs = []
    db[mod.Collections.INVOICES].docs = []
    db["cespiti"].docs = []
    db["voci_bilancio_manuali"].docs = []
    db["tfr_accantonamenti"].docs = [
        {"anno": 2026, "mese": 3, "quota": 137.0},
        {"anno": 2026, "mese": 6, "quota": 137.0},
        {"anno": 2026, "mese": 9, "quota": 137.0},  # dopo data_fine (giugno)
    ]

    esito = _run(mod.get_stato_patrimoniale(anno=2026, mese=6, data_a=None))

    assert esito["passivo"]["fondo_tfr"] == 274.0  # marzo + giugno, non settembre
    assert esito["passivo"]["totale_passivo"] == esito["attivo"]["totale_attivo"]  # sempre in pareggio


def test_capitale_riserve_manuali_sono_informative_non_sommate(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    db["prima_nota_cassa"].docs = []
    db["prima_nota_banca"].docs = []
    db["fatture_emesse"].docs = []
    db[mod.Collections.INVOICES].docs = []
    db["cespiti"].docs = []
    db["tfr_accantonamenti"].docs = []
    db["voci_bilancio_manuali"].docs = [
        {"codice_cee": "23.01.01", "anno": 2026, "importo": 10000.0},
        {"codice_cee": "05.07.01", "anno": 2026, "importo": 2000.0},
    ]

    esito = _run(mod.get_stato_patrimoniale(anno=2026, mese=None, data_a=None))

    assert esito["attivo"]["immobilizzazioni"]["da_voci_manuali"] == 2000.0
    assert esito["attivo"]["totale_attivo"] == 2000.0
    # Capitale sociale mostrato per confronto, ma NON sommato nel plug:
    assert esito["passivo"]["patrimonio_netto_dettaglio_manuale"] == 10000.0
    assert esito["passivo"]["patrimonio_netto"] == 2000.0  # plug = attivo - passivo (nessun debito/tfr qui)
