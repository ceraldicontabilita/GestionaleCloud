"""P0.11 — L'area riservata è protetta lato BACKEND: ogni endpoint dati richiede
il codice nell'header (constant-time), fail-closed se non configurato, e il codice
non viene mai loggato."""
import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException

import app.routers.gestione_riservata as gr


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def test_accesso_negato_senza_codice(monkeypatch):
    monkeypatch.setattr(gr, "GESTIONE_RISERVATA_CODE", "SEGRETO-123")
    with pytest.raises(HTTPException) as e:
        _run(gr.richiedi_codice_riservato(x_reserved_code=None))
    assert e.value.status_code == 401


def test_accesso_negato_codice_errato(monkeypatch):
    monkeypatch.setattr(gr, "GESTIONE_RISERVATA_CODE", "SEGRETO-123")
    with pytest.raises(HTTPException) as e:
        _run(gr.richiedi_codice_riservato(x_reserved_code="sbagliato"))
    assert e.value.status_code == 401


def test_accesso_consentito_codice_giusto(monkeypatch):
    monkeypatch.setattr(gr, "GESTIONE_RISERVATA_CODE", "SEGRETO-123")
    # non deve sollevare
    assert _run(gr.richiedi_codice_riservato(x_reserved_code="SEGRETO-123")) is None


def test_fail_closed_se_codice_non_configurato(monkeypatch):
    monkeypatch.setattr(gr, "GESTIONE_RISERVATA_CODE", "")
    with pytest.raises(HTTPException) as e:
        _run(gr.richiedi_codice_riservato(x_reserved_code="qualsiasi"))
    assert e.value.status_code == 503


def test_il_codice_non_viene_mai_loggato_nel_sorgente():
    src = Path("app/routers/gestione_riservata.py").read_text(encoding="utf-8")
    # nessun f-string che interpola `code` o `x_reserved_code` in un log
    assert "con codice: {code}" not in src
    assert "{x_reserved_code}" not in src
    assert "compare_digest" in src  # confronto a tempo costante
