"""Audit 19/09/2026, punto 1 — soglia unica per i cespiti.

Prima esistevano due soglie scollegate: 200 € in `app/handlers/cespiti.py`
(SOGLIA_VALORE) e 516,46 € (art. 102 TUIR) in
`app/services/learning_machine_cdc.py`. Uno stesso bene da, per esempio,
350 € poteva diventare cespite per l'handler automatico e restare piccola
attrezzatura deducibile per intero per il centro di costo — due sistemi in
disaccordo sullo stesso fatto. Ora la soglia e' UNA sola costante condivisa
(`app.services.piano_conti_ufficiale.SOGLIA_CESPITE_TUIR`, 516,46 €).
"""
import asyncio

from app.handlers import cespiti as handler_mod
from app.services.piano_conti_ufficiale import SOGLIA_CESPITE_TUIR


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


class _FakeCollection:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, *a, **k):
        return None

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, upsert=False, *a, **k):
        class Result:
            upserted_id = None

        if upsert:
            doc = dict(update.get("$setOnInsert") or {})
            self.docs.append(doc)
            Result.upserted_id = doc.get("id")
        return Result()


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


def test_soglia_e_quella_fiscale_516_46():
    assert SOGLIA_CESPITE_TUIR == 516.46


def test_bene_appena_sotto_soglia_non_diventa_cespite():
    """350 €: sopra la vecchia soglia (200€) ma sotto quella corretta
    (516,46€) — con la soglia unica NON deve diventare cespite."""
    db = _FakeDb()
    esito = _run(handler_mod.handler_auto_cespite_da_fattura({
        "fattura_id": "fatt-soglia-1",
        "data_documento": "2026-06-10",
        "righe_linee": [
            {"descrizione": "Forno da tavolo compatto", "prezzo_totale": 350.0},
        ],
    }, db))
    assert esito["skipped"] is True
    assert db["cespiti"].docs == []


def test_bene_appena_sopra_soglia_diventa_cespite():
    db = _FakeDb()
    esito = _run(handler_mod.handler_auto_cespite_da_fattura({
        "fattura_id": "fatt-soglia-2",
        "data_documento": "2026-06-10",
        "righe_linee": [
            {"descrizione": "Forno da tavolo compatto", "prezzo_totale": 520.0},
        ],
    }, db))
    assert len(esito["cespiti_creati"]) == 1
    assert db["cespiti"].docs[0]["valore_acquisto"] == 520.0


def test_bene_esattamente_alla_soglia_resta_deducibile_per_intero():
    """L'art. 102 TUIR deduce per intero i beni di costo NON superiore alla
    soglia: 516,46 € esatti restano costo, non cespite."""
    db = _FakeDb()
    esito = _run(handler_mod.handler_auto_cespite_da_fattura({
        "fattura_id": "fatt-soglia-3",
        "data_documento": "2026-06-10",
        "righe_linee": [
            {"descrizione": "Forno da tavolo compatto", "prezzo_totale": 516.46},
        ],
    }, db))
    assert esito["skipped"] is True
    assert db["cespiti"].docs == []


def test_scan_manuale_usa_di_default_la_stessa_soglia_fiscale():
    import inspect
    from app.routers.cespiti import scan_fatture_per_cespiti

    default = inspect.signature(scan_fatture_per_cespiti).parameters["soglia_valore"].default
    # Query(...) di FastAPI espone il default effettivo tramite .default
    valore_default = getattr(default, "default", default)
    assert valore_default == SOGLIA_CESPITE_TUIR


def test_learning_machine_usa_la_stessa_costante_condivisa():
    import app.services.learning_machine_cdc as lm
    assert lm.SOGLIA_CESPITE_TUIR == SOGLIA_CESPITE_TUIR
