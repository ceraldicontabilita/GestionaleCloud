"""ID prodotto unico (PRD-000123): lo stesso codice in Menu, B&B e Lotti."""
import asyncio
from pathlib import Path

from app.lotti.servizi import menu_bridge
from app.menu import carta_qromo
from app.menu.routes import menu_routes

ROOT = Path(__file__).resolve().parents[2]
SQL = (ROOT / "supabase" / "migrations" / "20261005150000_menu_codice_prodotto.sql").read_text(encoding="utf-8")


class _Risposta:
    def __init__(self, data):
        self.data = data


class _Tabella:
    def __init__(self, righe):
        self.righe = righe

    def select(self, *_):
        return self

    def limit(self, *_):
        return self

    def execute(self):
        return _Risposta(self.righe)


class _Supabase:
    def __init__(self, righe):
        self.righe = righe

    def table(self, _nome):
        return _Tabella(self.righe)


def test_lotti_legge_il_codice_per_ricetta_e_ignora_i_prodotti_qromo(monkeypatch):
    monkeypatch.setenv("MENU_SUPABASE_URL", "https://menu.test.supabase.co")
    monkeypatch.setattr(menu_bridge, "supabase", _Supabase([
        {"lotti_ref": "ricetta:abc", "codice_prodotto": "PRD-000007"},
        {"lotti_ref": "ricetta:def", "codice_prodotto": None},
        {"lotti_ref": None, "codice_prodotto": "PRD-000001"},
    ]))
    assert asyncio.run(menu_bridge.codici_prodotti_ricette()) == {"abc": "PRD-000007"}


def test_il_menu_espone_il_codice_e_la_carta_lo_porta_agli_item():
    riga = {"id": 1000001, "category_id": 1, "subcategory_id": 2, "name": "Babà", "name_it": "Babà",
            "price": "3.50€", "allergens": [], "visible": True, "origine": "lotti",
            "lotti_ref": "ricetta:abc", "codice_prodotto": "PRD-000007"}
    assert menu_routes.prod_out(riga)["codice_prodotto"] == "PRD-000007"
    sub = [{"id": 2, "category_id": 1, "name": "Pastry", "nameIT": "Pasticceria"}]
    cat = [{"id": 1, "name": "Produzione Ceraldi", "nameIT": "Produzione Ceraldi"}]
    carta = carta_qromo.carta_da_menu(cat, sub, [menu_routes.prod_out(riga)], {"menus": [], "cats": [], "items": []}, {})
    assert [i["cod"] for i in carta["items"]] == ["PRD-000007"]


def test_la_migrazione_non_si_puo_aggirare():
    # registro mai cancellato, codice assegnato dal trigger e fisso, vista pubblica rifatta
    assert "create table if not exists menu.prodotti_codici" in SQL
    assert "before insert on menu.menu_products" in SQL and "before update on menu.menu_products" in SQL
    assert "create or replace view public.menu_products" in SQL
    assert "delete from menu.prodotti_codici" not in SQL
    # una ricetta si riconosce per lotti_ref, mai per un id che si puo' riusare
    assert "where lotti_ref = new.lotti_ref" in SQL
