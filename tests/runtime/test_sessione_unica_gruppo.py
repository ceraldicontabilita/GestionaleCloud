"""Sessione unica: il login del Gestionale apre HR, Lotti e Menu senza PIN.

Si verifica il servizio centrale (`app/services/group_session.py`) e i tre
endpoint `/auth/session`: cookie ERP da amministratore valido → token
dell'app; nessun cookie, ruolo non amministratore, token revocato o cookie di
un'altra app → 401.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from app.config import settings


def run(coro):
    return asyncio.run(coro)


def _token_erp(role="admin", secret=None, **extra):
    now = datetime.now(timezone.utc)
    payload = {"sub": "u-1", "email": "titolare@example.it", "name": "Titolare", "role": role,
               "iat": now, "exp": now + timedelta(minutes=30), **extra}
    return jwt.encode(payload, secret or settings.SECRET_KEY, algorithm=settings.ALGORITHM)


class Richiesta:
    def __init__(self, cookie=""):
        self.headers = {"cookie": cookie}
        self.client = None


@pytest.fixture(autouse=True)
def niente_revoche(monkeypatch):
    import app.utils.token_blacklist as tb

    async def mai(_db, _token):
        return False

    async def mai_hash(_db, _chiave):
        return False

    from app.services import group_session

    group_session._azzera_cache()
    monkeypatch.setattr(tb, "is_revocato", mai)
    monkeypatch.setattr(tb, "is_hash_revocato", mai_hash)
    monkeypatch.setattr("app.database.Database.get_db", staticmethod(lambda: None))


def test_valori_cookie_ripetuto():
    from app.services.group_session import valori_cookie
    assert valori_cookie("a=1; access_token=hr; access_token=erp") == ["hr", "erp"]


def test_amministratore_erp_riconosciuto_anche_dietro_il_cookie_hr():
    from app.services.group_session import sessione_erp
    cookie_hr = _token_erp(secret="segreto-diverso-di-hr")
    cookie = f"access_token={cookie_hr}; access_token={_token_erp()}"
    identita = run(sessione_erp(Richiesta(cookie)))
    assert identita and identita["user_id"] == "u-1" and identita["role"] == "admin"


@pytest.mark.parametrize("cookie", [
    "",
    "access_token=spazzatura",
    f"access_token={_token_erp(role='operatore')}",
    f"access_token={_token_erp(purpose='mfa_login')}",
])
def test_senza_sessione_amministratore_niente(cookie):
    from app.services.group_session import sessione_erp
    assert run(sessione_erp(Richiesta(cookie))) is None


def test_token_revocato_non_apre(monkeypatch):
    import app.utils.token_blacklist as tb
    from app.services.group_session import sessione_erp

    async def sempre(_db, _token):
        return True

    monkeypatch.setattr(tb, "is_revocato", sempre)
    assert run(sessione_erp(Richiesta(f"access_token={_token_erp()}"))) is None


def test_registro_revoche_giu_chiude(monkeypatch):
    import app.utils.token_blacklist as tb
    from app.services.group_session import sessione_erp

    async def guasto(_db, _token):
        raise tb.TokenBlacklistUnavailable("giu")

    monkeypatch.setattr(tb, "is_revocato", guasto)
    assert run(sessione_erp(Richiesta(f"access_token={_token_erp()}"))) is None


def test_lotti_session_rilascia_token_del_titolare(monkeypatch):
    from fastapi import HTTPException
    from mongomock_motor import AsyncMongoMockClient

    import app.lotti.db as lotti_db
    from app.lotti import auth

    db = AsyncMongoMockClient()["l"]
    run(db.tablet_operatori.insert_one({"hr_id": "hr-vince", "nome": "Ceraldi Vincenzo",
                                        "ruolo": "amministratore", "attivo": True}))
    monkeypatch.setattr(lotti_db, "database", db)
    esito = run(auth.sessione_dal_gestionale(Richiesta(f"access_token={_token_erp()}")))
    dati = auth.verify_token(esito["token"])
    assert dati["sub"] == "hr-vince" and dati["ruolo"] == "amministratore" and dati["via"] == "sessione_erp"
    assert esito["operatore"]["dipendente_id"] == "hr-vince"
    with pytest.raises(HTTPException) as exc:
        run(auth.sessione_dal_gestionale(Richiesta("")))
    assert exc.value.status_code == 401


def test_lotti_senza_titolare_univoco_il_token_non_firma(monkeypatch):
    from mongomock_motor import AsyncMongoMockClient

    import app.lotti.db as lotti_db
    from app.lotti import auth
    from app.lotti.servizi.registro_haccp import firma_registrazione

    db = AsyncMongoMockClient()["l"]
    monkeypatch.setattr(lotti_db, "database", db)
    esito = run(auth.sessione_dal_gestionale(Richiesta(f"access_token={_token_erp()}")))
    assert esito["operatore"]["dipendente_id"] is None

    class ConToken:
        headers = {"authorization": f"Bearer {esito['token']}"}
        query_params = {}
        state = type("S", (), {})()
        client = None

    firma = run(firma_registrazione(ConToken(), "", ""))
    assert firma["firma_verificata"] is False


def test_menu_session(monkeypatch):
    from fastapi import HTTPException

    import app.menu.routes.qrcode_routes as menu

    monkeypatch.setattr(menu, "SECRET_KEY", "segreto-menu-test")
    esito = run(menu.sessione_dal_gestionale(Richiesta(f"access_token={_token_erp()}")))
    assert esito.success and run(menu.verify_token(f"Bearer {esito.token}")) == menu.ADMIN_USERNAME
    with pytest.raises(HTTPException) as exc:
        run(menu.sessione_dal_gestionale(Richiesta("")))
    assert exc.value.status_code == 401


def test_hr_session(monkeypatch):
    from fastapi import HTTPException

    import app.hr.routers.pin_login as hr
    from app.services import pin_authentication

    async def identita(*_a, **_k):
        return pin_authentication.PinIdentity(id="adm-1", email="t@example.it", name="Titolare",
                                              role="admin", source="admin_pin")

    monkeypatch.setattr(pin_authentication, "risolvi_identita_admin", identita)
    monkeypatch.setattr(hr.Database, "get_db", staticmethod(lambda: None))
    esito = run(hr.sessione_dal_gestionale(Richiesta(f"access_token={_token_erp()}")))
    assert esito["role"] == "admin" and esito["access_token"] and esito["auth_method"] == "sessione_erp"
    with pytest.raises(HTTPException) as exc:
        run(hr.sessione_dal_gestionale(Richiesta("")))
    assert exc.value.status_code == 401
