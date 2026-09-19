"""Il token dell'amministratore HR porta il ruolo, e i ruoli si validano.

Due difetti trovati il 19/09/2026 confrontando `utils/dependencies.py` fra i
due rami. Le due copie di quel file restano separate per scelta — l'app HR ha
un proprio segreto JWT (`HR_JWT_SECRET`) e un proprio vocabolario di ruoli, e
`app/utils/ruoli.py` dice esplicitamente che un token del portale dipendenti
non vale mai su `/api/` del gestionale — ma la copia HR era rimasta indietro
sulla parte di sicurezza.

1. `app/hr/routers/auth.py::_make_token` firmava un token con `sub`, `iat` ed
   `exp` e basta. Ogni rotta amministrativa di HR passa da `require_admin`,
   che pretende `payload["role"] == "admin"`: quel token non apriva nulla
   dell'area riservata, mentre il corpo della risposta annunciava
   «role: admin».
2. `get_current_user` accettava qualunque stringa come ruolo, con default
   `"user"` — che non e' nemmeno un ruolo di questa app. La copia ERP il
   controllo ce l'aveva gia'.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from jose import jwt

from app.hr.config import settings
from app.hr.routers import auth as hr_auth
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


def test_il_login_amministratore_mette_il_ruolo_nel_token():
    payload = jwt.decode(
        hr_auth._make_token("titolare@esempio.it"),
        hr_auth.SECRET_KEY,
        algorithms=["HS256"],
    )
    assert payload.get("role") == "admin", (
        "Il token del login amministratore non porta il ruolo: `require_admin` "
        "pretende `role == 'admin'` e lo rifiuta, quindi l'area riservata di "
        "HR resta chiusa a chi ha appena fatto il login."
    )


def test_quel_token_supera_la_guardia_admin():
    """La prova che conta: il token passa davvero da `require_admin`."""
    from app.hr.utils.dependencies import require_admin

    esito = _run(require_admin(_Credenziali(hr_auth._make_token("titolare@esempio.it"))))
    assert esito.get("role") == "admin"


@pytest.mark.parametrize("ruolo", sorted(RUOLI_VALIDI))
def test_i_ruoli_dell_app_passano(ruolo):
    utente = _run(get_current_user(_Credenziali(_token(role=ruolo))))
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
