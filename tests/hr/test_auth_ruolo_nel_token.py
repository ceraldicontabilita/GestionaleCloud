"""Il token HR porta il ruolo, e i ruoli si validano.

Il login amministratore email/password dell'app HR non esiste piu': un token
admin vale solo se nasce dalla sessione del Gestionale (`sessione_erp` con il
`sid` della sessione), e un token admin di altra provenienza non apre niente
anche se non e' scaduto. `get_current_user` accetta solo il vocabolario dei
ruoli HR e fallisce chiuso.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from jose import jwt

from app.hr.config import settings
from app.services import group_session
from app.hr.utils.dependencies import get_current_user
from app.hr.utils.identity import RUOLI_VALIDI


def _run(coroutine):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


class _Credenziali:
    def __init__(self, token):
        self.credentials = token


def _token(**extra):
    payload = {
        "sub": "titolare@esempio.it",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        **extra,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


@pytest.fixture(autouse=True)
def _nessuna_revoca(monkeypatch):
    group_session._azzera_cache()

    async def _mai_revocata(chiave):
        return False

    monkeypatch.setattr(group_session, "sessione_revocata", _mai_revocata)


def _token_admin_da_gestionale():
    return _token(role="admin", auth_method="sessione_erp", sid="sid:prova")


def test_il_token_admin_dal_gestionale_supera_la_guardia_admin():
    """La prova che conta: il token passa davvero da `require_admin`."""
    from app.hr.utils.dependencies import require_admin

    esito = _run(require_admin(_Credenziali(_token_admin_da_gestionale())))
    assert esito.get("role") == "admin"


@pytest.mark.parametrize("via", ["pin", "password", "pin_dipendente", "google", ""])
def test_un_token_admin_fuori_dal_gestionale_non_passa(via):
    from app.hr.utils.dependencies import require_admin

    with pytest.raises(HTTPException) as e:
        _run(require_admin(_Credenziali(_token(role="admin", auth_method=via))))
    assert e.value.status_code == 401
    with pytest.raises(HTTPException):
        _run(get_current_user(_Credenziali(_token(role="admin", auth_method=via))))


def test_un_token_admin_senza_sid_non_passa():
    with pytest.raises(HTTPException):
        _run(get_current_user(_Credenziali(_token(role="admin", auth_method="sessione_erp"))))


@pytest.mark.parametrize("ruolo", sorted(RUOLI_VALIDI))
def test_i_ruoli_dell_app_passano(ruolo):
    token = _token_admin_da_gestionale() if ruolo == "admin" else _token(role=ruolo)
    utente = _run(get_current_user(_Credenziali(token)))
    assert utente["role"] == ruolo


@pytest.mark.parametrize("ruolo", ["user", "", "superadmin", "ADMINISTRATOR"])
def test_un_ruolo_fuori_vocabolario_non_passa(ruolo):
    with pytest.raises(HTTPException) as e:
        _run(get_current_user(_Credenziali(_token(role=ruolo))))
    assert e.value.status_code == 401


def test_un_token_senza_ruolo_non_passa():
    """Fallisce chiuso: prima diventava l'utente generico `"user"`."""
    with pytest.raises(HTTPException) as e:
        _run(get_current_user(_Credenziali(_token())))
    assert e.value.status_code == 401
