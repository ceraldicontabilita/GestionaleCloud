"""Contratti del workflow HACCP indipendente del repository Lotti."""

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient
from starlette.requests import Request


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def dbmock(monkeypatch):
    import app.lotti.servizi.automatismi_mattutini as morning
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(morning, "db", database)
    return database


def _stub_modules(monkeypatch, reorder):
    import app.lotti.routers.haccp_auto as haccp
    import app.lotti.routers.ordini_fornitori as ordini
    import app.lotti.routers.task_dipendenti as tasks
    async def daily():
        return {"ok": True, "generato": False}

    async def missed():
        return {"temperature_positive": 0, "temperature_negative": 0, "sanificazione": 0}

    async def employee_tasks():
        return {"ok": True, "create": 0}

    monkeypatch.setattr(haccp, "verifica_e_popola_oggi", daily)
    monkeypatch.setattr(haccp, "marca_giorni_non_rilevati", missed)
    monkeypatch.setattr(tasks, "genera_task_giornalieri", employee_tasks)
    monkeypatch.setattr(ordini, "esegui_riordino_automatico", reorder)


def test_due_chiamate_creano_una_sola_esecuzione(dbmock, monkeypatch):
    import app.lotti.servizi.automatismi_mattutini as morning
    async def reorder():
        return {"bozze_create": []}

    _stub_modules(monkeypatch, reorder)
    now = datetime(2026, 8, 25, 7, 0, tzinfo=ZoneInfo("Europe/Rome"))
    first = run(morning.run_morning_automation(source="external_workflow", now=now))
    second = run(morning.run_morning_automation(source="internal_scheduler", now=now))

    assert first["ok"] is True and first["skipped"] is False
    assert second["ok"] is True and second["reason"] == "already_successful"
    assert run(dbmock.scheduler_executions.count_documents({})) == 1
    assert run(dbmock.scheduler_logs.count_documents({"job": "haccp_daily"})) == 1


def test_esecuzione_parziale_viene_recuperata(dbmock, monkeypatch):
    import app.lotti.servizi.automatismi_mattutini as morning
    calls = {"count": 0}

    async def reorder():
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("errore simulato")
        return {"bozze_create": []}

    _stub_modules(monkeypatch, reorder)
    now = datetime(2026, 8, 26, 7, 0, tzinfo=ZoneInfo("Europe/Rome"))
    first = run(morning.run_morning_automation(source="external_workflow", now=now))
    second = run(morning.run_morning_automation(source="retry", now=now))

    assert first["ok"] is False and first["execution"]["status"] == "partial"
    assert second["ok"] is True and second["execution"]["status"] == "success"
    assert second["execution"]["attempt"] == 2


def test_tentativo_anticipato_non_scrive_nulla(dbmock):
    import app.lotti.servizi.automatismi_mattutini as morning
    now = datetime(2026, 1, 10, 6, 0, tzinfo=ZoneInfo("Europe/Rome"))
    result = run(morning.run_morning_automation(source="external_workflow", now=now))

    assert result == {
        "ok": True,
        "skipped": True,
        "reason": "too_early_europe_rome",
        "local_time": now.isoformat(),
    }
    assert run(dbmock.scheduler_executions.count_documents({})) == 0


def _request(secret: str) -> Request:
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/scheduler/morning/run",
        "headers": [(b"x-automation-key", secret.encode())],
        "query_string": b"",
        "scheme": "https",
        "server": ("test", 443),
        "client": ("127.0.0.1", 1234),
    })


def test_endpoint_accetta_solo_il_secret_lotti(monkeypatch):
    import app.lotti.auth as auth
    monkeypatch.setenv("AUTOMATION_SECRET", "segreto-lotti-test")
    valid = _request("segreto-lotti-test")
    run(auth.auth_dependency(valid))
    assert valid.state.user["ruolo"] == "automazione"

    with pytest.raises(HTTPException) as exc:
        run(auth.auth_dependency(_request("secret-errato")))
    assert exc.value.status_code == 401
