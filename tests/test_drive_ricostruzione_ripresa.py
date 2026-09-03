"""Ripresa automatica della ricostruzione fatture da Drive (audit 03/09/2026).

La ricostruzione a lotti salva un cursore in `drive_sync_state`; prima di
questo job il lotto successivo partiva solo da un click in Admin e un
processo interrotto lasciava lo stato a `processing` per sempre (64 fatture
su 754, archivio `invoices` vuoto). Il job riprende SOLO gli stati
incompleti e non tocca mai una ricostruzione conclusa o in errore.
"""
import asyncio

import pytest

from app.services import drive_invoice_ingest as drive
from app.services.sheets_document_store import MemorySheetsClient


@pytest.fixture
def db():
    return MemorySheetsClient()["test_ripresa"]


@pytest.fixture
def lotto_finto(monkeypatch):
    chiamate = []

    async def _lotto(db, *, batch_size=10, reset=False):
        chiamate.append({"batch_size": batch_size, "reset": reset})
        return {"status": "pending", "processed": 84, "total": 754}

    monkeypatch.setattr(drive, "is_configured", lambda: True)
    monkeypatch.setattr(drive, "ricostruisci_archivio_drive_lotto", _lotto)
    return chiamate


async def _stato(db, last_rebuild_result):
    await db[drive._SYNC_STATE_COLLECTION].update_one(
        {"_id": drive._SYNC_STATE_ID},
        {"$set": {"last_rebuild_result": last_rebuild_result}},
        upsert=True,
    )


@pytest.mark.parametrize("stato", ["processing", "pending"])
def test_riprende_un_lotto_se_la_ricostruzione_e_incompleta(db, lotto_finto, stato):
    asyncio.run(_stato(db, {
        "status": stato, "cursor": "17i8gzvj", "processed": 64, "total": 754,
        "inflight": {"id": "17ih91et", "name": "IT07832841212_00KL9.xml"},
    }))

    esito = asyncio.run(drive.riprendi_ricostruzione_se_incompleta(db))

    assert esito["status"] == "pending"
    assert lotto_finto == [{"batch_size": 20, "reset": False}]


@pytest.mark.parametrize("stato", ["ok", "error", "running", None])
def test_non_tocca_una_ricostruzione_conclusa_o_in_errore(db, lotto_finto, stato):
    if stato is not None:
        asyncio.run(_stato(db, {"status": stato, "processed": 754, "total": 754}))

    esito = asyncio.run(drive.riprendi_ricostruzione_se_incompleta(db))

    assert esito == {"status": "skipped", "stato_precedente": stato}
    assert lotto_finto == []


def test_senza_drive_configurato_non_fa_nulla(db, lotto_finto, monkeypatch):
    monkeypatch.setattr(drive, "is_configured", lambda: False)
    asyncio.run(_stato(db, {"status": "processing", "cursor": "x"}))

    esito = asyncio.run(drive.riprendi_ricostruzione_se_incompleta(db))

    assert esito["status"] == "not_configured"
    assert lotto_finto == []


def test_non_si_accavalla_a_un_sync_in_corso(db, lotto_finto):
    asyncio.run(_stato(db, {"status": "processing", "cursor": "x"}))

    async def _con_lock():
        async with drive._sync_lock:
            return await drive.riprendi_ricostruzione_se_incompleta(db)

    esito = asyncio.run(_con_lock())

    assert esito["status"] == "running"
    assert lotto_finto == []


def test_il_job_e_registrato_nello_scheduler():
    from pathlib import Path

    sorgente = Path(__file__).resolve().parents[1] / "app" / "scheduler.py"
    testo = sorgente.read_text(encoding="utf-8")
    assert 'id="drive_fatture_ricostruzione_ripresa"' in testo
    assert "riprendi_ricostruzione_se_incompleta" in testo
