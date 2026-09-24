"""Login admin email/password dell'app HR.

Prima: nessun blocco dei tentativi (il login PIN lo aveva), confronto della
password con `==`, cookie `access_token` senza `secure` e con path "/", cioe'
inviato anche al gestionale sullo stesso dominio.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.hr.routers import auth as hr_auth
from app.utils import login_lockout


def _client(monkeypatch):
    monkeypatch.setattr(hr_auth, "ADMIN_EMAIL", "titolare@esempio.it")
    monkeypatch.setattr(hr_auth, "ADMIN_PASSWORD", "giusta-123")
    monkeypatch.setattr(hr_auth, "ADMIN_PASSWORD_HASH", "")
    login_lockout._FAILED.clear()
    app = FastAPI()
    app.include_router(hr_auth.router, prefix="/api/auth")
    return TestClient(app, base_url="https://testserver")


def _login(client, password, ip="10.0.0.1"):
    return client.post(
        "/api/auth/api/login",
        json={"email": "titolare@esempio.it", "password": password},
        headers={"x-forwarded-for": ip, "x-forwarded-proto": "https"},
    )


def test_login_riuscito_cookie_sicuro_sotto_hr(monkeypatch):
    risposta = _login(_client(monkeypatch), "giusta-123")
    assert risposta.status_code == 200
    cookie = [v for k, v in risposta.headers.multi_items() if k == "set-cookie" and v.startswith("access_token=")][0]
    assert "Path=/hr" in cookie
    assert "Secure" in cookie
    assert "HttpOnly" in cookie


def test_troppi_tentativi_bloccano_anche_la_password_giusta(monkeypatch):
    client = _client(monkeypatch)
    for _ in range(login_lockout.MAX_ATTEMPTS):
        assert _login(client, "sbagliata").status_code == 401
    assert _login(client, "giusta-123").status_code == 429
    assert _login(client, "giusta-123", ip="10.0.0.2").status_code == 200
    login_lockout._FAILED.clear()


def test_alias_auth_login_stesse_regole(monkeypatch):
    client = _client(monkeypatch)
    risposta = client.post(
        "/api/auth/api/auth/login",
        json={"email": "TITOLARE@esempio.it", "password": "giusta-123"},
        headers={"x-forwarded-proto": "https"},
    )
    assert risposta.status_code == 200
    assert risposta.json()["access_token"]
