import asyncio
from pathlib import Path

from app.config import settings
from app.routers import settings_router
from app.services import email_monitor_service, gmail_search
from app.services.gmail_credentials import get_gmail_environment_credentials
from app.utils.dependencies import get_current_admin_user


ROOT = Path(__file__).resolve().parents[2]


class _EmptyCollection:
    async def find_one(self, *args, **kwargs):
        return None


class _EmptyDb:
    def __getitem__(self, _name):
        return _EmptyCollection()


def test_tutti_gli_endpoint_gmail_richiedono_admin():
    gmail_routes = {
        (method, route.path): route
        for route in settings_router.router.routes
        for method in route.methods
        if route.path.startswith("/gmail")
    }
    assert set(gmail_routes) == {
        ("GET", "/gmail"),
        ("POST", "/gmail"),
        ("POST", "/gmail/test"),
    }
    for route in gmail_routes.values():
        assert get_current_admin_user in [dep.call for dep in route.dependant.dependencies]


def test_alias_render_gmail_sono_risolti_in_modo_unico(monkeypatch):
    for name in (
        "IMAP_USER", "EMAIL_USER", "EMAIL_ADDRESS", "GMAIL_EMAIL",
        "GMAIL_ACCOUNT_AMMINISTRATIVO", "IMAP_PASSWORD", "EMAIL_APP_PASSWORD",
        "EMAIL_PASSWORD", "GMAIL_APP_PASSWORD_AMMINISTRATIVO",
    ):
        monkeypatch.setattr(settings, name, None)
    monkeypatch.setattr(settings, "ADMIN_EMAIL", "amministrazione@example.test")
    monkeypatch.setattr(settings, "GMAIL_APP_PASSWORD", "segreto-test")
    monkeypatch.setattr(settings, "IMAP_HOST", "imap.gmail.com")

    env = get_gmail_environment_credentials()
    assert env.user == "amministrazione@example.test"
    assert env.password == "segreto-test"

    monitor_creds = asyncio.run(email_monitor_service._build_gmail_credentials(_EmptyDb()))
    search_creds = asyncio.run(gmail_search.get_gmail_credentials(_EmptyDb()))
    assert monitor_creds == search_creds == (
        "amministrazione@example.test", "segreto-test", "imap.gmail.com"
    )


def test_pagina_gmail_e_solo_admin_ed_e_nel_menu():
    main = (ROOT / "frontend/src/main.jsx").read_text(encoding="utf-8")
    nav = (ROOT / "frontend/src/navigation.config.js").read_text(encoding="utf-8")
    assert 'path: "impostazioni-f24-email", element: <RequireAdmin>' in main
    assert "to: '/impostazioni-f24-email'" in nav
    assert "label: 'Email automatica'" in nav


def test_template_render_usa_i_nomi_canonici():
    template = (ROOT / "render.env.template").read_text(encoding="utf-8")
    assert "ENABLE_GMAIL_IMAP=true" in template
    assert "ENABLE_EMAIL_CEDOLINI_SYNC=true" in template
    assert "ENABLE_EMAIL_F24_SYNC=true" in template
    assert "ENABLE_EMAIL_VERBALI_SYNC=true" in template
    assert "GMAIL_SCAN_ALL_FOLDERS=true" in template
    assert "GMAIL_SCAN_LOOKBACK_DAYS=30" in template
    assert "GMAIL_IMAP_ENABLED=false" not in template
