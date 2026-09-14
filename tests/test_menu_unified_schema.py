import pytest

from app.menu import supabase_client


class _Options:
    def __init__(self, *, schema):
        self.schema = schema


def test_menu_usa_schema_configurato(monkeypatch):
    chiamata = {}

    def crea(url, key, *, options):
        chiamata.update(url=url, key=key, schema=options.schema)
        return object()

    monkeypatch.setenv("MENU_SUPABASE_URL", "https://menu.test")
    monkeypatch.setenv("MENU_SUPABASE_KEY", "anon")
    monkeypatch.setenv("MENU_DB_SCHEMA", "menu")
    monkeypatch.setattr(supabase_client, "ClientOptions", _Options)
    monkeypatch.setattr(supabase_client, "create_client", crea)
    monkeypatch.setattr(supabase_client, "_client", None)

    supabase_client.get_supabase()

    assert chiamata == {"url": "https://menu.test", "key": "anon", "schema": "menu"}


def test_menu_rifiuta_schema_non_sicuro(monkeypatch):
    monkeypatch.setenv("MENU_SUPABASE_URL", "https://menu.test")
    monkeypatch.setenv("MENU_SUPABASE_KEY", "anon")
    monkeypatch.setenv("MENU_DB_SCHEMA", "menu;drop schema public")
    monkeypatch.setattr(supabase_client, "_client", None)

    with pytest.raises(RuntimeError, match="MENU_DB_SCHEMA non valido"):
        supabase_client.get_supabase()
