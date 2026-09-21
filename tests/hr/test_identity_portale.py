"""Il fascicolo personale richiede un'identita' HR canonica e un ruolo valido."""

import asyncio
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException

from app.hr.config import settings
from app.hr.utils.identity import get_identity
from app.services.workforce_tokens import create_workforce_token


class _Credenziali:
    def __init__(self, token):
        self.credentials = token


def _identita(token):
    return asyncio.run(get_identity(_Credenziali(token)))


def test_token_hr_mantiene_id_canonico(monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", "segreto-hr-del-test-123456789")
    token = create_workforce_token(
        sub="dipendente-42",
        name="Persona HR",
        role="dipendente",
        secret=settings.SECRET_KEY,
        expires_in=timedelta(hours=1),
        auth_method="pin_dipendente",
    )
    identity = _identita(token)
    assert identity["id"] == "dipendente-42"
    assert identity["role"] == "dipendente"
    assert identity["auth_method"] == "pin_dipendente"


def test_token_senza_ruolo_non_diventa_dipendente(monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", "segreto-hr-del-test-123456789")
    token = jwt.encode(
        {"sub": "dipendente-42", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        settings.SECRET_KEY,
        algorithm="HS256",
    )
    with pytest.raises(HTTPException) as error:
        _identita(token)
    assert error.value.status_code == 401


def test_ruolo_hr_sconosciuto_non_apre_il_portale(monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", "segreto-hr-del-test-123456789")
    token = create_workforce_token(
        sub="dipendente-42",
        name="Persona HR",
        role="superadmin",
        secret=settings.SECRET_KEY,
        expires_in=timedelta(hours=1),
        auth_method="pin_dipendente",
    )
    with pytest.raises(HTTPException) as error:
        _identita(token)
    assert error.value.status_code == 401


def test_token_tablet_lotti_con_segreto_distinto_non_apre_il_portale(monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", "segreto-hr-del-test-123456789")
    token = create_workforce_token(
        sub="id-proiezione-operatore-lotti",
        name="Persona HR",
        role="operatore",
        secret="segreto-lotti-del-test-987654321",
        expires_in=timedelta(hours=1),
        auth_method="pin",
    )
    with pytest.raises(HTTPException) as error:
        _identita(token)
    assert error.value.status_code == 401
