"""Logout unico: chi esce dal Gestionale esce anche da HR, Lotti e Menu.

Il percorso completo, sullo stesso registro revoche (`token_blacklist`):
1. login ERP (token con `sid` di sessione);
2. HR, Lotti e Menu ricevono il loro token da `/auth/session`, senza PIN;
3. logout ERP;
4. una chiamata autenticata a ciascuna app risponde 401 — anche in un altro
   processo, che non ha visto il logout e legge solo il registro.

Si prova anche che la sessione sopravvive ai rinnovi del token ERP: il logout
fatto col token rinnovato chiude i token derivati dal token del login.
"""
import asyncio

import pytest
from fastapi import HTTPException, Response

from app.services import group_session
from app.utils.auth_tokens import create_access_token


def run(coro):
    return asyncio.run(coro)


class _Collezione:
    def __init__(self):
        self.righe = {}

    async def find_one(self, filtro, _proiezione=None):
        return self.righe.get(filtro.get("token_hash"))

    async def update_one(self, filtro, modifica, upsert=False):
        chiave = filtro["token_hash"]
        self.righe.setdefault(chiave, dict(modifica.get("$setOnInsert") or {}))


class _Db(dict):
    def __missing__(self, nome):
        self[nome] = _Collezione()
        return self[nome]


class Richiesta:
    """Quanto basta ai tre endpoint `/session`, al logout e ai gate."""

    def __init__(self, cookie="", bearer=""):
        self.headers = {}
        if cookie:
            self.headers["cookie"] = f"access_token={cookie}"
        if bearer:
            self.headers["authorization"] = f"Bearer {bearer}"
        self.cookies = {"access_token": cookie} if cookie else {}
        self.method = "GET"
        self.query_params = {}
        self.client = None
        self.scope = {"root_path": ""}
        self.state = type("S", (), {})()
        self.url = type("U", (), {"path": "/api/lotti"})()


@pytest.fixture
def db(monkeypatch):
    registro = _Db()
    group_session._azzera_cache()
    monkeypatch.setattr("app.database.Database.get_db", staticmethod(lambda: registro))
    yield registro
    group_session._azzera_cache()


def _apri_le_tre_app(token_erp, monkeypatch):
    from app.hr.routers import pin_login as hr_pin_login
    from app.lotti import auth as lotti_auth
    from app.menu.routes import qrcode_routes

    class _Identita:
        def as_user(self):
            return {"id": "admin-hr", "name": "Titolare", "email": "t@example.it", "role": "admin"}

    async def _admin_hr(*_a, **_k):
        return _Identita()

    monkeypatch.setattr(hr_pin_login.pin_authentication, "risolvi_identita_admin", _admin_hr)

    class _Operatori:
        def find(self, *_a, **_k):
            class _C:
                async def to_list(self, _n):
                    return []
            return _C()

    import app.lotti.db as lotti_db
    monkeypatch.setattr(lotti_db.database, "tablet_operatori", _Operatori(), raising=False)
    monkeypatch.setattr(qrcode_routes, "SECRET_KEY", "segreto-menu-di-prova-lungo-32-byte")

    richiesta = Richiesta(cookie=token_erp)
    hr = run(hr_pin_login.sessione_dal_gestionale(richiesta))["access_token"]
    lotti = run(lotti_auth.sessione_dal_gestionale(richiesta))["token"]
    menu = run(qrcode_routes.sessione_dal_gestionale(richiesta)).token
    return hr, lotti, menu


def _usa_le_tre_app(hr, lotti, menu):
    """Esito di una chiamata autenticata a ciascuna app: True se entra."""
    from app.hr.utils.dependencies import require_admin as hr_admin
    from app.lotti.auth import require_admin as lotti_admin
    from app.menu.routes.qrcode_routes import verify_token as menu_verify

    class _Cred:
        def __init__(self, t):
            self.credentials = t

    esiti = []
    for chiamata in (
        lambda: hr_admin(_Cred(hr)),
        lambda: lotti_admin(Richiesta(bearer=lotti)),
        lambda: menu_verify(f"Bearer {menu}"),
    ):
        try:
            run(chiamata())
            esiti.append(True)
        except HTTPException as exc:
            assert exc.status_code in (401, 403)
            esiti.append(False)
    return esiti


def _logout(token_erp):
    from app.routers.auth import auth_logout

    return run(auth_logout(Richiesta(cookie=token_erp, bearer=token_erp), Response()))


def test_login_unico_poi_logout_unico(db, monkeypatch):
    token_erp = create_access_token(user_id="u-1", email="t@example.it", name="Titolare", role="admin")
    hr, lotti, menu = _apri_le_tre_app(token_erp, monkeypatch)
    assert _usa_le_tre_app(hr, lotti, menu) == [True, True, True]

    assert _logout(token_erp) == {"ok": True}
    assert _usa_le_tre_app(hr, lotti, menu) == [False, False, False]

    # un altro processo non ha visto il logout: legge il registro e chiude
    group_session._azzera_cache()
    assert _usa_le_tre_app(hr, lotti, menu) == [False, False, False]


def test_il_logout_col_token_rinnovato_chiude_i_token_del_login(db, monkeypatch):
    from jose import jwt as jose_jwt
    from app.config import settings

    token_login = create_access_token(user_id="u-1", email="t@example.it", name="Titolare", role="admin")
    hr, lotti, menu = _apri_le_tre_app(token_login, monkeypatch)
    sid = jose_jwt.decode(token_login, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])["sid"]
    # rinnovo scorrevole: token nuovo, stessa sessione
    token_rinnovato = create_access_token(user_id="u-1", email="t@example.it", name="Titolare",
                                          role="admin", sid=sid, mfa_verified=True)
    assert token_rinnovato != token_login

    _logout(token_rinnovato)
    group_session._azzera_cache()
    assert _usa_le_tre_app(hr, lotti, menu) == [False, False, False]
    # e il vecchio token ERP della stessa sessione non riapre le app
    assert run(group_session.sessione_erp(Richiesta(cookie=token_login))) is None


def test_un_login_nuovo_apre_una_sessione_nuova(db, monkeypatch):
    primo = create_access_token(user_id="u-1", role="admin")
    _logout(primo)
    secondo = create_access_token(user_id="u-1", role="admin")
    hr, lotti, menu = _apri_le_tre_app(secondo, monkeypatch)
    assert _usa_le_tre_app(hr, lotti, menu) == [True, True, True]


def test_registro_giu_i_token_derivati_non_valgono(db, monkeypatch):
    token_erp = create_access_token(user_id="u-1", role="admin")
    hr, lotti, menu = _apri_le_tre_app(token_erp, monkeypatch)
    group_session._azzera_cache()

    class _Rotta:
        async def find_one(self, *_a, **_k):
            raise RuntimeError("registro irraggiungibile")

    db["token_blacklist"] = _Rotta()
    assert _usa_le_tre_app(hr, lotti, menu) == [False, False, False]


def test_il_token_dopo_il_codice_mfa_si_puo_firmare():
    """Il login MFA e lo step-up creano un token con `mfa_verified_at`: con un
    datetime dentro, jose sollevava TypeError e il login falliva."""
    from datetime import datetime, timezone
    from jose import jwt as jose_jwt
    from app.config import settings

    token = create_access_token(user_id="u-1", role="admin", mfa_verified=True,
                                mfa_verified_at=datetime(2026, 9, 26, tzinfo=timezone.utc), sid="abc")
    payload = jose_jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert payload["mfa_verified_at"] == int(datetime(2026, 9, 26, tzinfo=timezone.utc).timestamp())
    assert payload["sid"] == "abc"
