import httpx
from fastapi.testclient import TestClient

from enable_banking_probe import main


class FakeEnableBankingClient:
    calls = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        if url.endswith("/aspsps"):
            return httpx.Response(
                200,
                json={"aspsps": [{"name": "Banco BPM - Corporate", "country": "IT"}]},
            )
        if url.endswith("/balances"):
            return httpx.Response(200, json={"balances": []})
        if url.endswith("/transactions"):
            return httpx.Response(200, json={"transactions": [{"entry_reference": "safe"}]})
        return httpx.Response(200, json={})

    async def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        if url.endswith("/auth"):
            return httpx.Response(200, json={"url": "https://auth.enablebanking.com/start"})
        if url.endswith("/sessions"):
            return httpx.Response(
                200,
                json={"session_id": "memory-session", "accounts": [{"uid": "memory-account"}]},
            )
        return httpx.Response(400, json={})


def _reset_state():
    main._csrf_tokens.clear()
    main._pending_states.clear()
    main._session_id = None
    main._account_uids = []
    main._last_result = {
        "connected": False,
        "session": {},
        "accounts": {},
        "balances": {},
        "transactions": {},
        "ready": False,
    }
    FakeEnableBankingClient.calls.clear()


def test_health_is_explicitly_isolated():
    _reset_state()
    with TestClient(main.app, base_url="https://testserver") as client:
        health = client.get("/health").json()
    assert health["supabase_connected"] is False
    assert health["session_present_in_memory"] is False


def test_connect_and_callback_keep_only_sanitized_results(monkeypatch):
    _reset_state()
    monkeypatch.setattr(main, "APPLICATION_ID", "application-id")
    monkeypatch.setattr(main, "PRIVATE_KEY_PEM", "private-key-never-returned")
    monkeypatch.setattr(main, "_api_headers", lambda: {"Authorization": "Bearer test"})
    monkeypatch.setattr(main.httpx, "AsyncClient", FakeEnableBankingClient)

    with TestClient(main.app, base_url="https://testserver") as client:
        home = client.get("/")
        csrf = client.cookies.get("__Host-banco_bpm_probe_csrf")
        assert csrf
        connect = client.post(
            "/connect",
            data={"csrf_token": csrf},
            follow_redirects=False,
        )
        assert connect.status_code == 303
        assert connect.headers["location"] == "https://auth.enablebanking.com/start"

        state = next(iter(main._pending_states))
        callback = client.get(
            f"/callback?code=one-time-code&state={state}",
            follow_redirects=False,
        )
        assert callback.status_code == 303
        result = client.get("/probe")
        assert result.json() == {
            "connected": True,
            "session": {"ok": True},
            "accounts": {"ok": True, "count": 1},
            "balances": {"ok": True, "count": 1},
            "transactions": {
                "ok": True,
                "accounts_checked": 1,
                "count": 1,
                "period_days": 90,
            },
            "ready": True,
            "session_present_in_memory": True,
        }
        exposed = result.text + client.get("/health").text
        assert "private-key-never-returned" not in exposed
        assert "one-time-code" not in exposed
        assert "memory-session" not in exposed
        assert "memory-account" not in exposed


def test_connect_rejects_invalid_csrf(monkeypatch):
    _reset_state()
    monkeypatch.setattr(main, "APPLICATION_ID", "application-id")
    monkeypatch.setattr(main, "PRIVATE_KEY_PEM", "private-key")
    monkeypatch.setattr(main.httpx, "AsyncClient", FakeEnableBankingClient)

    with TestClient(main.app, base_url="https://testserver") as client:
        response = client.post("/connect", data={"csrf_token": "invalid"})
    assert response.status_code == 400
    assert not FakeEnableBankingClient.calls
