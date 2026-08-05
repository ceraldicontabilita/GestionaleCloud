"""Regressioni emerse dal collaudo pagina-per-pagina del 5 agosto 2026."""

import asyncio

from app.routers.accounting import contabilita_gestionale as cg
from app.routers.accounting import centri_costo
from app.routers import fiscalita_italiana


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _Cursor:
    def __init__(self, docs):
        self.docs = list(docs)

    def sort(self, *args, **kwargs):
        return self

    async def to_list(self, limit=None):
        return self.docs[:limit] if limit else self.docs


class _Collection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    def find(self, *args, **kwargs):
        return _Cursor(self.docs)

    async def count_documents(self, query):
        return len(self.docs)


class _Db:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _Collection())


def test_bilancio_verifica_legge_solo_il_registro_definitivo():
    db = _Db()
    db["movimenti_contabili"].docs = [{
        "id": "M1", "anno": 2026, "data_documento": "2026-01-10",
        "descrizione": "Fattura 1", "numero_registrazione": 1,
        "righe": [
            {"conto_codice": "05.01.01", "conto_nome": "Acquisti", "dare": 100, "avere": 0},
            {"conto_codice": "01.04.01", "conto_nome": "IVA credito", "dare": 22, "avere": 0},
            {"conto_codice": "02.01.01", "conto_nome": "Debiti fornitori", "dare": 0, "avere": 122},
        ],
    }]
    # Le fonti operative contengono dati, ma non devono essere risommate.
    db[cg.Collections.INVOICES].docs = [{"total_amount": 122}]
    db[cg.Collections.CORRISPETTIVI].docs = []

    result = _run(cg._bilancio_verifica_da_registro(db, 2026, True))

    assert result["fonte"] == "movimenti_contabili"
    assert result["quadratura"] is True
    assert result["totali"]["dare"] == result["totali"]["avere"] == 122
    assert result["completezza_registro"]["fatture_da_registrare"] == 1
    assert sum(c["n_movimenti"] for c in result["conti"]) == 3


def test_calendario_periodico_usa_mese_successivo_e_agosto_20():
    scadenze = fiscalita_italiana.genera_scadenze_anno(2026)
    per_id = {s["id"]: s for s in scadenze}

    assert per_id["ritenute_2026_07"]["data"] == "2026-08-20"
    assert per_id["inps_2026_07"]["data"] == "2026-08-20"
    assert per_id["iva_liq_2026_07"]["data"] == "2026-08-20"
    assert per_id["ritenute_2026_08"]["data"] == "2026-09-16"
    # L'azienda usa solo la liquidazione mensile: nessuna seconda logica
    # trimestrale deve comparire nel calendario operativo.
    assert not any(key.startswith("iva_trim_") for key in per_id)


def test_percentuale_target_annuo_non_usa_target_prorata(monkeypatch):
    class _Agg:
        def __init__(self, value):
            self.value = value

        async def to_list(self, _n):
            return [{"totale": self.value}]

    class _C:
        def __init__(self, value=0):
            self.value = value

        async def find_one(self, *args, **kwargs):
            return {"anno": 2026, "utile_target_annuo": 25000,
                    "giorni_lavorativi_anno": 300, "margine_medio_atteso": .35}

        def aggregate(self, pipeline):
            return _Agg(self.value)

    class _TargetDb:
        def __getitem__(self, name):
            if name == "corrispettivi":
                return _C(350000)
            if name == centri_costo.Collections.INVOICES:
                return _C(0)
            return _C()

    monkeypatch.setattr(centri_costo.Database, "get_db", staticmethod(lambda: _TargetDb()))
    result = _run(centri_costo.get_utile_obiettivo(2026))

    assert result["analisi"]["percentuale_target_annuo"] == 1400.0
    assert result["analisi"]["gap_target_annuo"] == 0
    assert result["analisi"]["surplus_target_annuo"] == 325000
