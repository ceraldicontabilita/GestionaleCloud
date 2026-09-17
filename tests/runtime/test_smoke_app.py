"""Regressioni del controllo runtime, che deve sempre produrre un report."""

import json

from scripts import smoke_app


def test_http_request_con_timeout_restituisce_esito_non_raggiungibile(monkeypatch):
    def timeout(*_args, **_kwargs):
        raise TimeoutError("read timed out")

    monkeypatch.setattr(smoke_app, "urlopen", timeout)

    status, body = smoke_app.http_request("https://example.invalid/api/health")

    assert status == 0
    assert "timed out" in body


def test_attende_il_commit_distribuito_prima_dello_smoke(monkeypatch):
    risposte = iter([
        (200, json.dumps({"deploy_commit": "precedente"})),
        (502, "Bad Gateway"),
        (200, json.dumps({"deploy_commit": "12345678"})),
    ])
    monkeypatch.setattr(smoke_app, "http_request", lambda *_args, **_kwargs: next(risposte))
    monkeypatch.setattr(smoke_app.time, "monotonic", lambda: 0)
    monkeypatch.setattr(smoke_app.time, "sleep", lambda _seconds: None)

    result = smoke_app.wait_for_expected_deploy("1234567890", 30, 1)

    assert result == {
        "ok": True,
        "expected_commit": "12345678",
        "live_commit": "12345678",
        "attempts": 3,
    }


def test_attesa_deploy_scade_con_diagnostica(monkeypatch):
    monkeypatch.setattr(
        smoke_app,
        "http_request",
        lambda *_args, **_kwargs: (200, json.dumps({"deploy_commit": "precedente"})),
    )
    monkeypatch.setattr(smoke_app.time, "monotonic", lambda: 10)

    result = smoke_app.wait_for_expected_deploy("12345678", 0, 1)

    assert result["ok"] is False
    assert result["expected_commit"] == "12345678"
    assert result["live_commit"] == "preceden"
    assert result["attempts"] == 1
