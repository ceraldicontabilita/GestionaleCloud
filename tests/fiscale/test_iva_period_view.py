import asyncio
import re

from app.database import Database
from app.routers import iva as iva_router


def _matches(document, query):
    for key, expected in query.items():
        value = document.get(key)
        if isinstance(expected, dict) and "$regex" in expected:
            if value is None or re.search(expected["$regex"], str(value)) is None:
                return False
        elif value != expected:
            return False
    return True


class _Cursor:
    def __init__(self, documents):
        self.documents = documents

    def sort(self, *_args):
        return self

    async def to_list(self, limit):
        return [dict(document) for document in self.documents[:limit]]


class _Collection:
    def __init__(self, documents):
        self.documents = documents

    def find(self, query, _projection):
        return _Cursor([document for document in self.documents if _matches(document, query)])


class _Database:
    def __init__(self, invoices):
        self.invoices = invoices

    def __getitem__(self, name):
        assert name == "invoices"
        return _Collection(self.invoices)


def _run(coroutine):
    return asyncio.run(coroutine)


def test_percentuale_detraibilita_non_inventa_zero_percento():
    non_classificata = iva_router._arricchisci_fattura_iva({"iva": 22})
    non_classificata_con_zero_tecnico = iva_router._arricchisci_fattura_iva(
        {"iva": 22, "iva_detraibile": 0, "stato_detrazione_iva": "DA_VERIFICARE"}
    )
    classificata_zero = iva_router._arricchisci_fattura_iva(
        {
            "iva": 22,
            "iva_detraibile": 0,
            "stato_detrazione_iva": "DA_VERIFICARE",
            "stato_classificazione": "classificata",
        }
    )
    classificata_quaranta = iva_router._arricchisci_fattura_iva(
        {"iva": 220, "iva_detraibile": 88}
    )
    classificata_percentuale_storica = iva_router._arricchisci_fattura_iva(
        {"iva": 220, "percentuale_detraibilita_iva": 0.4}
    )

    assert non_classificata["percentuale_detraibilita_iva"] is None
    assert non_classificata["detraibilita_valutata"] is False
    assert non_classificata_con_zero_tecnico["percentuale_detraibilita_iva"] == 0
    assert non_classificata_con_zero_tecnico["detraibilita_valutata"] is False
    assert classificata_zero["percentuale_detraibilita_iva"] == 0
    assert classificata_zero["detraibilita_valutata"] is True
    assert classificata_quaranta["percentuale_detraibilita_iva"] == 40
    assert classificata_percentuale_storica["percentuale_detraibilita_iva"] == 40
    assert classificata_percentuale_storica["detraibilita_valutata"] is True
    assert classificata_percentuale_storica["iva_detraibile"] == 88


def test_vista_periodo_restituisce_solo_fatture_del_mese(monkeypatch):
    database = _Database([
        {
            "id": "febbraio",
            "periodo_iva_attribuito": "2026-02",
            "iva": 220,
            "iva_detraibile": 88,
            "stato_detrazione_iva": "DA_INSERIRE",
            "iva_utilizzata": False,
        },
        {
            "id": "marzo",
            "periodo_iva_attribuito": "2026-03",
            "iva": 22,
            "iva_detraibile": 22,
            "stato_detrazione_iva": "DA_INSERIRE",
            "iva_utilizzata": False,
        },
    ])
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: database))

    result = _run(iva_router.fatture_iva(periodo="2026-02", anno=None, limit=5000))

    assert result["totale"] == 1
    assert result["fatture"][0]["id"] == "febbraio"
    assert result["totale_iva_esposta"] == 220
    assert result["totale_iva_detraibile"] == 88
    assert result["fatture"][0]["percentuale_detraibilita_iva"] == 40


def test_pagine_di_fatture_con_totali_dell_intero_periodo(monkeypatch):
    """La pagina Gestione IVA chiede 200 fatture alla volta: i totali restano
    quelli di tutto il periodo, uguali alla somma di tutte le righe."""
    from decimal import Decimal

    fatture = [
        {
            "id": f"f{n}", "periodo_iva_attribuito": "2026-04",
            "data_documento": f"2026-04-{n % 28 + 1:02d}",
            "iva": 10 + n / 100, "iva_detraibile": 5 + n / 100,
            "stato_detrazione_iva": "DA_VERIFICARE" if n % 3 == 0 else "DA_INSERIRE",
            "iva_utilizzata": n % 5 == 0,
        }
        for n in range(7)
    ]
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: _Database(fatture)))

    intera = _run(iva_router.fatture_iva(periodo="2026-04", anno=None, limit=5000, skip=0))
    pagine = [
        _run(iva_router.fatture_iva(periodo="2026-04", anno=None, limit=3, skip=skip))
        for skip in (0, 3, 6)
    ]
    assert [len(p["fatture"]) for p in pagine] == [3, 3, 1]
    assert [f["id"] for p in pagine for f in p["fatture"]] == [f["id"] for f in intera["fatture"]]
    campi = ("totale", "totale_iva_esposta", "totale_iva_detraibile", "totale_iva_disponibile",
             "totale_iva_utilizzata", "totale_da_verificare")
    for pagina in pagine:
        assert {c: pagina[c] for c in campi} == {c: intera[c] for c in campi}
    assert intera["totale"] == 7
    assert Decimal(str(intera["totale_iva_esposta"])) == sum(Decimal(str(f["iva"])) for f in fatture)
    assert Decimal(str(intera["totale_iva_detraibile"])) == sum(
        Decimal(str(f["iva_detraibile"])) for f in fatture)
    assert intera["totale_da_verificare"] == 3
