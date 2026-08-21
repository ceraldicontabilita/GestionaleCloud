"""Regressioni del controllo runtime, che deve sempre produrre un report."""

from scripts import smoke_app


def test_http_request_con_timeout_restituisce_esito_non_raggiungibile(monkeypatch):
    def timeout(*_args, **_kwargs):
        raise TimeoutError("read timed out")

    monkeypatch.setattr(smoke_app, "urlopen", timeout)

    status, body = smoke_app.http_request("https://example.invalid/api/health")

    assert status == 0
    assert "timed out" in body
