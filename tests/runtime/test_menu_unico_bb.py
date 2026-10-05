from pathlib import Path
import asyncio


ROOT = Path(__file__).resolve().parents[2]


def test_menu_pubblico_aggiunge_il_carrello_solo_con_codice_bb():
    js = (ROOT / "frontend_menu" / "public" / "carta" / "carta.js").read_text(encoding="utf-8")
    css = (ROOT / "frontend_menu" / "public" / "carta" / "carta.css").read_text(encoding="utf-8")

    assert "CC_BB" in js
    assert "/api/colazioni/menu-ospite/catalogo" in js
    assert "/api/colazioni/menu-ospite/ordine" in js
    assert "Aggiungi al carrello" in js
    assert "stessa carta, prezzi specifici della struttura" in js
    assert ".cc-cart-button" in css
    assert ".cc-cart-panel.open" in css


def test_gestione_hotel_usa_solo_il_catalogo_menu():
    html = (ROOT / "frontend_colazioni" / "index.html").read_text(encoding="utf-8")
    sql = (ROOT / "supabase" / "migrations" / "20261002150500_convenzioni_menu_unico_carrello.sql").read_text(encoding="utf-8")

    assert html.count('fetch("/menu/api/menu/carta?destinazione=bb"') == 2
    assert "bb_tit_menu_prodotti_struttura" in html
    assert "bb_tit_menu_prodotti_salva" in html
    assert "bb_struttura_menu_prodotti" in sql
    assert "join menu.menu_products" in sql
    assert "bb_ospite_menu_salva" in sql
    assert "revoke all on public.bb_struttura_menu_prodotti" in sql


def test_catalogo_bb_montato_non_richiede_la_sessione_erp(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.middleware.authentication import AuthenticationMiddleware
    from app.menu import carta_menu

    def dataset():
        return carta_menu._seme()

    async def catalogo(**kwargs):
        assert kwargs == {"catalogo_bb": True}
        return [], [], []

    monkeypatch.setattr(carta_menu, "_dataset", dataset)
    monkeypatch.setattr(carta_menu.menu_routes, "_fetch_all", catalogo)
    menu = FastAPI()
    menu.include_router(carta_menu.router_pubblico)
    erp = FastAPI()
    erp.add_middleware(AuthenticationMiddleware)
    erp.mount("/menu", menu)
    with TestClient(erp) as client:
        assert client.get("/api/menu/carta?destinazione=bb").status_code == 401
        risposta = client.get("/menu/api/menu/carta?destinazione=bb")
        assert risposta.status_code == 200
        assert risposta.json()["items"] == []


def test_ricette_nuove_sono_preselezionate_per_il_menu():
    form = (ROOT / "frontend_lotti" / "src" / "components" / "haccp" / "backoffice" / "FormRicetta.jsx").read_text(encoding="utf-8")
    backend = (ROOT / "app" / "lotti" / "routers" / "ricette.py").read_text(encoding="utf-8")

    assert "menu_pubblico:true" in form
    assert 'item.menu_pubblico is not False' in backend


def test_catalogo_ospite_filtra_la_carta_e_applica_il_prezzo_hotel(monkeypatch):
    from app.routers import colazioni
    from app.menu import carta_menu

    async def rpc(_fn, _args):
        return {"struttura": "Hotel Prova", "prodotti": [{"prodotto_id": 20, "prezzo": "2.50"}]}

    async def carta(*, destinazione):
        assert destinazione == "bb"
        return {
            "menus": [{"id": 1, "n": "Bar"}, {"id": 2, "n": "Altro"}],
            "cats": [{"id": 10, "m": 1}, {"id": 11, "m": 2}],
            "items": [{"id": 20, "c": 10, "p": 100}, {"id": 21, "c": 11, "p": 300}],
        }

    monkeypatch.setattr(colazioni, "_rpc_bb", rpc)
    monkeypatch.setattr(carta_menu, "carta_pubblica", carta)
    risposta = asyncio.run(colazioni.catalogo_menu_ospite(
        colazioni.MenuOspiteRequest(codice="ABCD", giorno="2026-10-03")
    ))

    assert risposta["items"] == [{"id": 20, "c": 10, "p": 250, "fp": 250}]
    assert risposta["cats"] == [{"id": 10, "m": 1}]
    assert risposta["menus"] == [{"id": 1, "n": "Bar"}]


def test_rpc_bb_cambiano_solo_il_filtro_visibilita_non_i_controlli_o_i_dati():
    import re

    migrations = ROOT / "supabase" / "migrations"
    vecchio = (migrations / "20261002150500_convenzioni_menu_unico_carrello.sql").read_text(encoding="utf-8")
    nuovo = (migrations / "20261002172407_ricette_visibilita_bb.sql").read_text(encoding="utf-8")
    for nome in ("bb_menu_prodotti_struttura_json", "bb_tit_menu_prodotti_salva", "bb_ospite_menu_salva"):
        pattern = rf"create or replace function public\.{nome}\(.*?\$\$;"
        prima = re.search(pattern, vecchio, re.S).group()
        dopo = re.search(pattern, nuovo, re.S).group()
        atteso = prima.replace("mp.visible is not false", "mp.menu_bb is not false and (mp.origine='lotti' or mp.visible is not false)")
        if nome == "bb_tit_menu_prodotti_salva":
            atteso = prima.replace("visible is not false", "menu_bb is not false and (origine='lotti' or visible is not false)")
        assert re.sub(r"\s+", "", dopo) == re.sub(r"\s+", "", atteso)
    # Nessun nuovo permesso, nessuna esecuzione delle RPC, nessuna riga riscritta.
    fuori_funzioni = re.sub(r"create or replace function.*?\$\$;", "", nuovo, flags=re.S)
    assert not re.search(r"\b(grant|revoke|insert|update|delete)\b", fuori_funzioni, re.I)
