import httpx
from fastapi.testclient import TestClient

from obp_sandbox_probe import main


class FakeOBPClient:
    calls = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return httpx.Response(201, json={"token": "volatile-test-token"})

    async def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        if url.endswith("/users/current"):
            return httpx.Response(200, json={"user_id": "sandbox-user"})
        if url.endswith("/my/accounts"):
            return httpx.Response(
                200,
                json={
                    "accounts": [
                        {
                            "bank_id": "sandbox-bank",
                            "id": "sandbox-account",
                            "views_available": [{"id": "owner"}],
                        }
                    ]
                },
            )
        if url.endswith("/transactions"):
            return httpx.Response(200, json={"transactions": [{"id": "one"}, {"id": "two"}]})
        return httpx.Response(200, json={})


def _reset_memory_state():
    main._direct_token = None
    main._csrf_tokens.clear()
    main._last_probe = {
        "authenticated": False,
        "current_user": {},
        "accounts": {},
        "transactions": {},
        "ready": False,
    }
    FakeOBPClient.calls.clear()


def test_browser_direct_login_uses_env_consumer_key_and_returns_only_safe_results(monkeypatch):
    _reset_memory_state()
    monkeypatch.setenv("OBP_CONSUMER_KEY", "configured-consumer-key")
    monkeypatch.setattr(main.httpx, "AsyncClient", FakeOBPClient)
    username = "real-sandbox-user@example.test"
    password = "never-store-this-password"

    with TestClient(main.app, base_url="https://testserver") as client:
        form = client.get("/direct-login")
        assert form.status_code == 200
        csrf = client.cookies.get("__Host-obp_probe_csrf")
        assert csrf

        response = client.post(
            "/direct-login",
            data={"username": username, "password": password, "csrf_token": csrf},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/direct-result"

        result = client.get("/direct-probe")
        assert result.status_code == 200
        assert result.json() == {
            "authenticated": True,
            "login_status": 201,
            "current_user": {"ok": True, "status_code": 200},
            "accounts": {"ok": True, "status_code": 200, "count": 1},
            "transactions": {"ok": True, "status_code": 200, "count": 2, "limit": 5},
            "ready": True,
            "token_present_in_memory": True,
        }

        serialized = result.text + client.get("/diagnostic").text
        assert username not in serialized
        assert password not in serialized
        assert "volatile-test-token" not in serialized
        assert "configured-consumer-key" not in serialized

    login_call = next(call for call in FakeOBPClient.calls if call[0] == "POST")
    authorization = login_call[2]["headers"]["Authorization"]
    assert f'username="{username}"' in authorization
    assert f'password="{password}"' in authorization
    assert 'consumer_key="configured-consumer-key"' in authorization


def test_direct_login_rejects_missing_or_reused_csrf(monkeypatch):
    _reset_memory_state()
    monkeypatch.setenv("OBP_CONSUMER_KEY", "configured-consumer-key")
    monkeypatch.setattr(main.httpx, "AsyncClient", FakeOBPClient)

    with TestClient(main.app, base_url="https://testserver") as client:
        rejected = client.post(
            "/direct-login",
            data={"username": "user", "password": "password", "csrf_token": "invalid"},
        )
        assert rejected.status_code == 400
        assert not any(call[0] == "POST" for call in FakeOBPClient.calls)

        client.get("/direct-login")
        csrf = client.cookies.get("__Host-obp_probe_csrf")
        accepted = client.post(
            "/direct-login",
            data={"username": "user", "password": "password", "csrf_token": csrf},
            follow_redirects=False,
        )
        assert accepted.status_code == 303

        reused = client.post(
            "/direct-login",
            data={"username": "user", "password": "password", "csrf_token": csrf},
        )
        assert reused.status_code == 400


def test_logout_clears_volatile_token(monkeypatch):
    _reset_memory_state()
    main._direct_token = "temporary"
    main._last_probe["ready"] = True

    with TestClient(main.app, base_url="https://testserver") as client:
        response = client.post("/logout", follow_redirects=False)
        assert response.status_code == 303
        assert main._direct_token is None
        assert main._last_probe["ready"] is False
