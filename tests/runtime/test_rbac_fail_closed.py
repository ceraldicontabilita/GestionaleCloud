"""Regressioni SEC-RBAC-001: nessun ruolo implicito diventa admin."""
import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from jose import jwt

from app.config import settings
from app.database import Database
from app.middleware.authentication import AuthenticationMiddleware
from app.models import UserLogin
from app.services.auth_service import AuthService
from app.exceptions import AuthenticationError
from app.utils import token_blacklist
from app.utils.ruoli import (
    ADMIN,
    NON_AUTORIZZATO,
    OPERATORE,
    SOLA_LETTURA,
    normalizza_ruolo,
    puo_amministrare,
    puo_scrivere,
)


def _token(role_marker=...):
    payload = {
        "sub": "utente-test",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    if role_marker is not ...:
        payload["role"] = role_marker
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def _client(monkeypatch):
    async def _non_revocato(_db, _token):
        return False

    monkeypatch.setattr(token_blacklist, "is_revocato", _non_revocato)
    monkeypatch.setattr(Database, "get_db", classmethod(lambda cls: object()))

    app = FastAPI()
    app.add_middleware(AuthenticationMiddleware)

    @app.api_route("/api/protected", methods=["GET", "POST"])
    async def protected(request: Request):
        return {"role": request.state.user_role}

    @app.get("/api/admin/diagnostica")
    async def admin_only(request: Request):
        return {"role": request.state.user_role}

    return TestClient(app)


def test_normalizzazione_ruoli_validi_e_legacy():
    assert normalizza_ruolo(" ADMIN ") == ADMIN
    assert normalizza_ruolo(OPERATORE) == OPERATORE
    assert normalizza_ruolo(SOLA_LETTURA) == SOLA_LETTURA
    assert normalizza_ruolo("user") == OPERATORE


def test_ruolo_assente_o_sconosciuto_non_ha_privilegi():
    for ruolo in (None, "", "responsabile", 123):
        assert normalizza_ruolo(ruolo) == NON_AUTORIZZATO
        assert puo_scrivere(ruolo) is False
        assert puo_amministrare(ruolo) is False


def test_permessi_ruoli_canonici():
    assert puo_scrivere(ADMIN) is True
    assert puo_scrivere(OPERATORE) is True
    assert puo_scrivere(SOLA_LETTURA) is False
    assert puo_amministrare(ADMIN) is True
    assert puo_amministrare(OPERATORE) is False


def test_middleware_rifiuta_ruolo_mancante_e_sconosciuto(monkeypatch):
    client = _client(monkeypatch)
    for token in (_token(), _token("responsabile")):
        response = client.get(
            "/api/protected", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 403
        assert response.json() == {"detail": "Ruolo utente non valido"}


def test_middleware_declassa_user_legacy_a_operatore(monkeypatch):
    client = _client(monkeypatch)
    headers = {"Authorization": f"Bearer {_token('user')}"}

    response = client.post("/api/protected", headers=headers)
    assert response.status_code == 200
    assert response.json()["role"] == OPERATORE

    response = client.get("/api/admin/diagnostica", headers=headers)
    assert response.status_code == 403


def test_sola_lettura_non_puo_scrivere(monkeypatch):
    client = _client(monkeypatch)
    headers = {"Authorization": f"Bearer {_token(SOLA_LETTURA)}"}

    assert client.get("/api/protected", headers=headers).status_code == 200
    assert client.post("/api/protected", headers=headers).status_code == 403


def test_admin_resta_esplicito(monkeypatch):
    client = _client(monkeypatch)
    headers = {"Authorization": f"Bearer {_token(ADMIN)}"}

    response = client.get("/api/admin/diagnostica", headers=headers)
    assert response.status_code == 200
    assert response.json()["role"] == ADMIN


def test_ponte_render_accetta_solo_segreto_dedicato_sugli_endpoint_esatti(monkeypatch):
    monkeypatch.setattr(settings, "RENDER_INGEST_SHARED_SECRET", "r" * 40)
    app = FastAPI()
    app.add_middleware(AuthenticationMiddleware)

    @app.post("/api/documenti/upload-auto/render/preview")
    async def render_preview(request: Request):
        return {
            "user_id": request.state.user_id,
            "auth_method": request.state.auth_method,
        }

    client = TestClient(app)
    assert client.post("/api/documenti/upload-auto/render/preview").status_code == 401
    assert client.post(
        "/api/documenti/upload-auto/render/preview",
        headers={"X-Render-Ingest-Token": "sbagliato"},
    ).status_code == 401
    accepted = client.post(
        "/api/documenti/upload-auto/render/preview",
        headers={"X-Render-Ingest-Token": "r" * 40},
    )
    assert accepted.status_code == 200
    assert accepted.json() == {
        "user_id": "render-document-ingest",
        "auth_method": "render_shared_secret",
    }


def test_ponte_render_fail_closed_se_segreto_non_configurato(monkeypatch):
    monkeypatch.setattr(settings, "RENDER_INGEST_SHARED_SECRET", None)
    app = FastAPI()
    app.add_middleware(AuthenticationMiddleware)

    @app.post("/api/documenti/upload-auto/render")
    async def render_upload():
        return {"ok": True}

    response = TestClient(app).post(
        "/api/documenti/upload-auto/render",
        headers={"X-Render-Ingest-Token": "qualsiasi"},
    )
    assert response.status_code == 503


def test_middleware_blocca_se_registro_revoche_non_disponibile(monkeypatch):
    async def _registro_non_disponibile(_db, _token):
        raise token_blacklist.TokenBlacklistUnavailable("simulato")

    monkeypatch.setattr(token_blacklist, "is_revocato", _registro_non_disponibile)
    monkeypatch.setattr(Database, "get_db", classmethod(lambda cls: object()))
    app = FastAPI()
    app.add_middleware(AuthenticationMiddleware)

    @app.get("/api/protected")
    async def protected():
        return {"ok": True}

    response = TestClient(app).get(
        "/api/protected", headers={"Authorization": f"Bearer {_token(ADMIN)}"}
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "Verifica sessione temporaneamente non disponibile"}


class _UserRepo:
    def __init__(self, role):
        self.user = {
            "id": "legacy-1",
            "email": "legacy@example.invalid",
            "name": "Legacy",
            "password_hash": "non-usato",
            "role": role,
            "is_active": True,
        }
        self.last_login_updates = 0

    async def find_by_email(self, _email):
        return self.user

    async def update_last_login(self, _user_id):
        self.last_login_updates += 1


def test_login_password_converte_user_legacy_nel_token(monkeypatch):
    repo = _UserRepo("user")
    service = AuthService(repo)
    monkeypatch.setattr(service, "_verify_password", lambda _plain, _hashed: True)

    response = asyncio.run(
        service.login(UserLogin(email=repo.user["email"], password="password-valida"))
    )
    payload = jwt.decode(
        response.access_token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
    )

    assert payload["role"] == OPERATORE
    assert repo.last_login_updates == 1


def test_login_password_rifiuta_ruolo_sconosciuto_prima_di_aggiornare(monkeypatch):
    repo = _UserRepo("responsabile")
    service = AuthService(repo)
    monkeypatch.setattr(service, "_verify_password", lambda _plain, _hashed: True)

    try:
        asyncio.run(
            service.login(UserLogin(email=repo.user["email"], password="password-valida"))
        )
    except AuthenticationError as exc:
        assert "role" in str(exc).lower()
    else:
        raise AssertionError("Il login con ruolo sconosciuto doveva essere rifiutato")

    assert repo.last_login_updates == 0
