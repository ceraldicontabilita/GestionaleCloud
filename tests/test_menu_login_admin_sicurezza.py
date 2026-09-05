"""Login admin del Menu: niente più credenziali di ripiego scritte nel codice
(app/menu/routes/qrcode_routes.py).

[FIX 05/09/2026] Prima ADMIN_PASSWORD e SECRET_KEY avevano un valore di
ripiego hardcoded ("Ceraldi2024!" / "ceraldi_secret_key_change_in_production")
usato ogni volta che le env MENU_ADMIN_PASSWORD/MENU_JWT_SECRET non erano
configurate — e per anni la stessa password è stata anche stampata in chiaro
sulla pagina di login pubblica. Questi test verificano che, senza quelle env,
il login fallisca chiuso (503) invece di accettare il vecchio valore noto.
"""
import asyncio
import importlib

import pytest
from fastapi import HTTPException

from app.menu.models.qrcode_models import AdminLogin


def _reload_senza_env(monkeypatch):
    for chiave in ("MENU_ADMIN_PASSWORD", "ADMIN_PASSWORD", "MENU_JWT_SECRET", "JWT_SECRET"):
        monkeypatch.delenv(chiave, raising=False)
    import app.menu.routes.qrcode_routes as modulo
    return importlib.reload(modulo)


def _reload_con_env(monkeypatch, *, password, secret, username="admin"):
    monkeypatch.setenv("MENU_ADMIN_USERNAME", username)
    monkeypatch.setenv("MENU_ADMIN_PASSWORD", password)
    monkeypatch.setenv("MENU_JWT_SECRET", secret)
    import app.menu.routes.qrcode_routes as modulo
    return importlib.reload(modulo)


def test_senza_env_configurate_il_vecchio_default_non_funziona_piu(monkeypatch):
    modulo = _reload_senza_env(monkeypatch)
    assert modulo.ADMIN_PASSWORD == ""
    assert modulo.SECRET_KEY == ""

    login = AdminLogin(username="admin", password="Ceraldi2024!")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(modulo.admin_login(login))
    assert exc.value.status_code == 503


def test_con_env_configurate_le_credenziali_giuste_funzionano(monkeypatch):
    modulo = _reload_con_env(monkeypatch, password="una-password-vera-e-lunga", secret="un-segreto-jwt-vero-e-lungo")
    login = AdminLogin(username="admin", password="una-password-vera-e-lunga")
    esito = asyncio.run(modulo.admin_login(login))
    assert esito.success is True
    assert esito.token


def test_con_env_configurate_una_password_sbagliata_viene_rifiutata(monkeypatch):
    modulo = _reload_con_env(monkeypatch, password="una-password-vera-e-lunga", secret="un-segreto-jwt-vero-e-lungo")
    login = AdminLogin(username="admin", password="Ceraldi2024!")
    esito = asyncio.run(modulo.admin_login(login))
    assert esito.success is False
