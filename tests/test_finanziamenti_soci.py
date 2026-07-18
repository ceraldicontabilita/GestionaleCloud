"""Finanziamento Soci (richiesta utente 18/07/2026): prima nota dei
finanziamenti dei quattro soci — bonifici in entrata con nome socio =
apporto; uscite con causale di rimborso/restituzione = rimborso; le altre
uscite (es. stipendi) restano fuori."""
import asyncio

from app.services.finanziamenti_soci import (
    SOCI,
    scan_finanziamenti_da_ec,
    schede_soci,
    socio_in_testo,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def __aiter__(self):
        self._it = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class _Coll:
    def __init__(self):
        self.docs = []

    def find(self, q=None, proj=None):
        return _Cursor(list(self.docs))

    async def insert_one(self, doc):
        self.docs.append(dict(doc))


class _DB:
    def __init__(self):
        self._c = {}

    def __getitem__(self, name):
        return self._c.setdefault(name, _Coll())


def test_socio_in_testo_richiede_entrambi_i_token():
    assert socio_in_testo("BONIFICO DA VINCENZO CERALDI") is not None
    assert socio_in_testo("BONIFICO DA MARIO CERALDI") is None
    assert socio_in_testo("qualcosa di ignoto") is None


def test_scan_apporto_da_bonifico_entrata():
    db = _DB()
    db["estratto_conto_movimenti"].docs.append({
        "id": "ec1", "data_contabile": "2026-03-10", "tipo": "entrata",
        "importo": 5000.0, "descrizione_originale": "BONIFICO DA VINCENZO CERALDI",
    })
    stats = _run(scan_finanziamenti_da_ec(db))
    assert stats["apporti_nuovi"] == 1
    assert stats["per_socio"]["vincenzo_ceraldi"] == 1
    schede = _run(schede_soci(db))
    scheda = next(s for s in schede["schede"] if s["socio_id"] == "vincenzo_ceraldi")
    assert scheda["apporti"] == 5000.0
    assert scheda["saldo"] == 5000.0


def test_scan_rimborso_richiede_causale_esplicita():
    db = _DB()
    db["estratto_conto_movimenti"].docs.extend([
        {"id": "ec1", "data_contabile": "2026-03-10", "tipo": "uscita",
         "importo": 500.0, "descrizione_originale": "STIPENDIO ANTONIETTA CERALDI"},
        {"id": "ec2", "data_contabile": "2026-04-10", "tipo": "uscita",
         "importo": 1000.0, "descrizione_originale": "RIMBORSO FINANZIAMENTO SOCIO ANTONIETTA CERALDI"},
    ])
    stats = _run(scan_finanziamenti_da_ec(db))
    assert stats["uscite_ignorate_causale"] == 1
    assert stats["rimborsi_nuovi"] == 1
    schede = _run(schede_soci(db))
    scheda = next(s for s in schede["schede"] if s["socio_id"] == "antonietta_ceraldi")
    assert scheda["rimborsi"] == 1000.0
    assert scheda["apporti"] == 0


def test_scan_idempotente_non_duplica():
    db = _DB()
    db["estratto_conto_movimenti"].docs.append({
        "id": "ec1", "data_contabile": "2026-03-10", "tipo": "entrata",
        "importo": 2000.0, "descrizione_originale": "BONIFICO GIUSEPPINA PANE",
    })
    _run(scan_finanziamenti_da_ec(db))
    stats2 = _run(scan_finanziamenti_da_ec(db))
    assert stats2["apporti_nuovi"] == 0
    assert stats2["gia_presenti"] == 1


def test_soci_sono_i_quattro_dettati():
    nomi = {s["nome"] for s in SOCI}
    assert nomi == {"Vincenzo Ceraldi", "Giuseppina Pane", "Antonietta Ceraldi", "Valerio Ceraldi"}
