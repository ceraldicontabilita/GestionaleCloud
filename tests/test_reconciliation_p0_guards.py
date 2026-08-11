"""Regressioni P0 per conferme ambigue, ignoramento e stipendi."""

import asyncio

import pytest
from fastapi import HTTPException

from app.routers.operazioni_module import _ignora_movimento, _riconcilia_stipendio
from app.routers.operazioni_module import smart
from app.services.stipendi_bonifici import _candidati_univoci


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _Result:
    def __init__(self, matched_count=0):
        self.matched_count = matched_count


class _Collection:
    def __init__(self, matched_count=0):
        self.matched_count = matched_count
        self.updates = []

    async def update_one(self, query, update):
        self.updates.append((query, update))
        return _Result(self.matched_count)


class _Db:
    def __init__(self, matched_count=0):
        self.collections = {
            "estratto_conto_movimenti": _Collection(matched_count),
            "bank_movements": _Collection(matched_count),
            "prima_nota_salari": _Collection(matched_count),
        }

    def __getitem__(self, name):
        return self.collections[name]


def test_manual_reconciliation_never_chooses_first_candidate(monkeypatch):
    class _DbNoRead:
        def __getitem__(self, name):
            raise AssertionError("il movimento non deve essere letto con candidati ambigui")

    monkeypatch.setattr(smart.Database, "get_db", staticmethod(lambda: _DbNoRead()))
    request = smart.RiconciliaManuale(
        movimento_id="M1",
        tipo="fattura",
        associazioni=[{"id": "F1"}, {"id": "F2"}],
    )
    with pytest.raises(HTTPException) as exc:
        _run(smart.riconcilia_manuale(request))
    assert exc.value.status_code == 409


def test_ignore_requires_reason_and_stores_audit_fields(monkeypatch):
    db = _Db(matched_count=1)
    monkeypatch.setattr("app.database.Database.get_db", lambda: db)
    with pytest.raises(HTTPException) as exc:
        _run(_ignora_movimento({"movimento_id": "M1"}))
    assert exc.value.status_code == 400
    assert not any(coll.updates for coll in db.collections.values())

    result = _run(_ignora_movimento({
        "movimento_id": "M1",
        "codice_motivo": "duplicato",
        "motivo": "duplicato già presente nell'estratto",
    }))
    assert result["movimento_id"] == "M1"
    update = db.collections["estratto_conto_movimenti"].updates[0][1]["$set"]
    assert update["ignorato"] is True
    assert update["codice_motivo_ignoramento"] == "duplicato"
    assert update["motivo_ignoramento"]


def test_salary_confirmation_requires_explicit_mode(monkeypatch):
    monkeypatch.setattr("app.database.Database.get_db", lambda: object())
    with pytest.raises(HTTPException) as exc:
        _run(_riconcilia_stipendio({"stipendio_id": "S1"}))
    assert exc.value.status_code == 409


def test_salary_saldo_does_not_accept_partial_amount():
    rows = [{
        "id": "S1",
        "dipendente": "Mario Rossi",
        "anno": 2026,
        "mese": 6,
        "importo_busta": 1000.0,
        "importo_bonifico": 0.0,
    }]
    assert _candidati_univoci(
        "FAVORE Mario Rossi",
        900.0,
        rows,
        data_movimento="2026-07-05",
        allow_partial=False,
    ) == []
