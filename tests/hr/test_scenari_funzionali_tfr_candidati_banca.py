"""Collaudo: i candidati bancari di un acconto TFR si trovano davvero.

Il filtro lavorava su `data_contabile_obj`, un campo che nessun importer scrive:
la lista dei candidati era sempre vuota. La data dei movimenti e' la stringa
`data` (YYYY-MM-DD).
"""
import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient

from tests.hr.scenari_base import mondo, run  # noqa: F401


def _movimenti():
    return [
        {"id": "m-giusto", "data": "2026-07-31", "importo": -1800.0, "tipo": "uscita",
         "descrizione": "BONIFICO FAVORE CAPEZZUTO ACCONTO"},
        {"id": "m-lontano", "data": "2026-09-30", "importo": -1800.0, "tipo": "uscita",
         "descrizione": "BONIFICO ALTRO"},
        {"id": "m-importo", "data": "2026-07-31", "importo": -1700.0, "tipo": "uscita",
         "descrizione": "BONIFICO ALTRO IMPORTO"},
    ]


def test_hr_candidati_banca_trova_il_movimento_per_data_stringa(mondo):
    run(mondo.hr.acconti_dipendenti.insert_one({
        "id": "a1", "dipendente_nome": "Capezzuto Mario", "importo": 1800.0,
        "data": "2026-07-31", "stato": "registrato"}))
    for m in _movimenti():
        run(mondo.hr.estratto_conto_movimenti.insert_one(dict(m)))
    r = mondo.client.get("/api/tfr/acconti/a1/candidati-banca")
    assert r.status_code == 200, r.text
    ids = [c["movimento_id"] for c in r.json()["candidati"]]
    assert ids == ["m-giusto"]
    assert r.json()["candidati"][0]["data"] == "2026-07-31"


def test_gestionale_candidati_banca_trova_il_movimento_per_data_stringa(monkeypatch):
    from app.database import Database
    from app.routers import tfr

    db = AsyncMongoMockClient()["gest_tfr_candidati"]
    monkeypatch.setattr(Database, "get_db", classmethod(lambda cls: db))
    asyncio.run(db["acconti_dipendenti"].insert_one({
        "id": "a1", "dipendente_nome": "Capezzuto Mario", "importo": 1800.0,
        "data": "2026-07-31", "stato": "registrato"}))
    for m in _movimenti():
        asyncio.run(db["estratto_conto_movimenti"].insert_one(dict(m)))
    esito = asyncio.run(tfr.candidati_banca_per_acconto("a1"))
    assert [c["movimento_id"] for c in esito["candidati"]] == ["m-giusto"]


def test_hr_saldo_tfr_non_sottrae_due_volte_gli_acconti(mondo):
    """`tfr_accantonato` e' gia' al netto: 5.000 maturati - 1.800 di acconto = 3.200, non 1.400."""
    run(mondo.hr.dipendenti.insert_one({
        "id": "d1", "nome_completo": "Capezzuto Mario", "tfr_accantonato": 3200.0}))
    run(mondo.hr.acconti_dipendenti.insert_one({
        "id": "a1", "dipendente_id": "d1", "tipo": "tfr", "importo": 1800.0, "data": "2026-07-31"}))
    r = mondo.client.get("/api/tfr/acconti/d1")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["tfr_saldo"] == 3200.0
    assert corpo["tfr_prima_degli_acconti"] == 5000.0
    assert corpo["tfr_acconti"] == 1800.0
