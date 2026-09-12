import asyncio

from app.hr.routers.dipendenti_cloud import _calcola_associazioni_bonifici


class _Cursor:
    def __init__(self, rows):
        self.rows = [dict(row) for row in rows]

    def __aiter__(self):
        self._iter = iter(self.rows)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _Collection:
    def __init__(self, rows):
        self.rows = rows

    def find(self, query=None, projection=None):
        query = query or {}
        return _Cursor(
            row for row in self.rows
            if all(row.get(key) == value for key, value in query.items())
        )


class _Db:
    def __init__(self, *, riconciliato):
        self.dipendenti = _Collection([
            {"id": "dip-1", "nome": "Mario", "cognome": "Rossi"},
        ])
        self.paghe_mensili = _Collection([
            {"dipendente_id": "dip-1", "anno": 2026, "mese": 8,
             "importo_busta": 1000, "bonifico_importo": 1000,
             "bonifico_riconciliato": riconciliato},
        ])
        self.pagamenti_esiti = _Collection([
            {"dipendente_id": "dip-1", "anno": 2026, "mese": 8,
             "importo": 1000, "data": "2026-09-01", "ha_pdf": True,
             "key": "prova-1"},
        ])
        self.cedolini = _Collection([
            {"id": "ced-1", "dipendente_id": "dip-1", "anno": 2026, "mese": 8},
        ])


def test_importo_nome_periodo_e_pdf_non_confermano_da_soli():
    result = asyncio.run(_calcola_associazioni_bonifici(_Db(riconciliato=False), 2026, 8))
    row = result["righe"][0]
    assert row["qualita"] == "da_verificare"
    assert row["stato"] == "da_verificare"
    assert row["stato_importo"] == "pagato"
    assert row["associato"] is False
    assert row["riconciliato"] is False
    assert result["totali"]["da_verificare"] == 1


def test_conferma_esplicita_rende_il_legame_associato_e_resta_tracciata():
    result = asyncio.run(_calcola_associazioni_bonifici(_Db(riconciliato=True), 2026, 8))
    row = result["righe"][0]
    assert row["qualita"] == "esatto"
    assert row["stato"] == "pagato"
    assert row["stato_importo"] == "pagato"
    assert row["associato"] is True
    assert row["riconciliato"] is True
    assert result["totali"]["associati"] == 1


def test_filtro_da_verificare_usa_lo_stato_probatorio_non_il_quadramento():
    result = asyncio.run(
        _calcola_associazioni_bonifici(
            _Db(riconciliato=False), 2026, 8, stato="da_verificare"
        )
    )
    assert len(result["righe"]) == 1
    assert result["righe"][0]["stato_importo"] == "pagato"


def test_filtro_pagato_esclude_il_candidato_non_riconciliato():
    result = asyncio.run(
        _calcola_associazioni_bonifici(
            _Db(riconciliato=False), 2026, 8, stato="pagato"
        )
    )
    assert result["righe"] == []
