"""Sincronizzazione da Qromo nelle tabelle originali del Menu
(app/menu/qromo_sync.py).

Copre la trasformazione pura costanti JavaScript -> righe snake_case delle
tabelle menu_categories / menu_subcategories / menu_products (filtri BANCO /
non disponibili / categorie vuote, riduzione allergeni, prezzo nel formato
del seed, immagini come URL esterni) e il contratto di scrittura (ordine
FK-safe, lotti, dry run che non tocca il client). Nessuna rete e nessun
client Supabase reale: la sorgente e il client sono sostituiti da finti.
"""
import asyncio

import pytest

from app.menu import qromo_sync as qs

# Stessa pagina sintetica di tests/test_menu_migrazione_qromo.py
HTML_QROMO = """<!DOCTYPE html>
<html><head><script>const TEST = false;const business = {"business_id":1};const menus = [
{"menu_id":1,"name":"Bar","picture":"https://img.qromo.io/cat1.jpg","available":1,"order_number":0},
{"menu_id":2,"name":"BANCO - Bar","picture":null,"available":0,"order_number":1},
{"menu_id":3,"name":"Comunicazioni","picture":null,"available":1,"order_number":2}
];const menusCategories = [
{"menu_category_id":10,"menu_id":1,"name":"Caffetteria","picture":"https://img.qromo.io/sub1.jpg","active":1},
{"menu_category_id":11,"menu_id":2,"name":"Caffetteria","picture":null,"active":1},
{"menu_category_id":12,"menu_id":3,"name":"Comunicazioni ","picture":null,"active":1}
];const menusItems = [
{"menu_item_id":100,"category_id":10,"name":"Espresso","ingredients":"Ottimo caff\\u00e8","price":120,"picture":"https://img.qromo.io/p1.jpg","available":1},
{"menu_item_id":101,"category_id":10,"name":"Nascosto","ingredients":null,"price":100,"picture":null,"available":0},
{"menu_item_id":102,"category_id":11,"name":"Espresso","ingredients":null,"price":80,"picture":null,"available":1},
{"menu_item_id":103,"category_id":12,"name":"Q","ingredients":null,"price":0,"picture":null,"available":0}
];const menusItemsAllergens = [
{"menu_item_id":100,"allergen_id":6},
{"menu_item_id":100,"allergen_id":16},
{"menu_item_id":100,"allergen_id":32},
{"menu_item_id":102,"allergen_id":6}
];const allergens = [
{"allergen_id":6,"category":"grains","name_key":"allergens_gluten"},
{"allergen_id":16,"category":"grains","name_key":"allergens_barley"},
{"allergen_id":32,"category":"dietary","name_key":"allergens_vegan"}
];</script></head><body></body></html>"""


def _run(coro):
    return asyncio.run(coro)


# ---------- trasformazione pura ----------

def test_estrai_costanti_javascript_isola_ogni_const():
    costanti = qs._estrai_costanti_javascript(HTML_QROMO)
    assert costanti["TEST"] == "false"
    assert qs._costante_json(costanti, "business", {}) == {"business_id": 1}
    assert len(qs._costante_json(costanti, "menus", [])) == 3
    assert qs._costante_json(costanti, "assente", "fallback") == "fallback"


def test_estrai_costanti_javascript_senza_script_solleva_errore():
    with pytest.raises(ValueError):
        qs._estrai_costanti_javascript("<html><body>niente</body></html>")


@pytest.mark.parametrize("centesimi,atteso", [(120, "1.20€"), (350, "3.50€"), (0, "0.00€"), (None, "0.00€"), (5, "0.05€")])
def test_prezzo_nel_formato_del_seed_originale(centesimi, atteso):
    assert qs._prezzo(centesimi) == atteso


def test_trasforma_catalogo_produce_righe_snake_case_filtrate():
    righe = qs.trasforma_catalogo(qs.catalogo_da_html(HTML_QROMO))

    # "BANCO - Bar" (2) e "Comunicazioni" (3, senza prodotti) escluse
    assert righe["categories"] == [
        {"id": 1, "name": "Bar", "name_it": "Bar", "image": "https://img.qromo.io/cat1.jpg"},
    ]
    assert righe["subcategories"] == [
        {"id": 10, "category_id": 1, "name": "Caffetteria", "name_it": "Caffetteria", "image": "https://img.qromo.io/sub1.jpg"},
    ]
    assert righe["products"] == [{
        "id": 100, "category_id": 1, "subcategory_id": 10,
        "name": "Espresso", "name_it": "Espresso", "price": "1.20€",
        "description": "Ottimo caffè", "description_it": "Ottimo caffè",
        # gluten (diretto) + barley (mappato su gluten) si fondono; vegan non e' un allergene
        "allergens": ["gluten"],
        # URL Qromo lasciato com'e': nessun download
        "image": "https://img.qromo.io/p1.jpg",
    }]


def test_trasforma_catalogo_colonne_uguali_al_seed_originale():
    """Le chiavi delle righe devono coincidere con quelle usate da routes/seed_routes.py."""
    from app.menu.routes import seed_routes

    righe = qs.trasforma_catalogo(qs.catalogo_da_html(HTML_QROMO))
    cat_seed = seed_routes._to_db_category({"id": 1, "name": "n", "nameIT": "n"})
    sub_seed = seed_routes._to_db_subcategory({"id": 1, "category_id": 1, "name": "n", "nameIT": "n"})
    prod_seed = seed_routes._to_db_product({"id": 1, "category_id": 1, "subcategory_id": 1, "name": "n", "nameIT": "n", "price": "1.00€"})
    assert set(righe["categories"][0]) == set(cat_seed)
    assert set(righe["subcategories"][0]) == set(sub_seed)
    assert set(righe["products"][0]) == set(prod_seed)


# ---------- scrittura: client Supabase finto ----------

class _Query:
    def __init__(self, registro, tabella):
        self.registro, self.tabella, self.op, self.payload = registro, tabella, None, None

    def delete(self):
        self.op = "delete"
        return self

    def neq(self, *_):
        return self

    def insert(self, rows):
        self.op, self.payload = "insert", list(rows)
        return self

    def execute(self):
        self.registro.append((self.op, self.tabella, self.payload))
        return self


class _FakeSupabase:
    def __init__(self):
        self.chiamate = []

    def table(self, nome):
        return _Query(self.chiamate, nome)


class _SorgenteFinta:
    def __init__(self, _sottodominio):
        pass

    async def chiudi(self):
        pass

    async def catalogo(self):
        return qs.catalogo_da_html(HTML_QROMO)


@pytest.fixture
def finto(monkeypatch):
    client = _FakeSupabase()
    monkeypatch.setattr(qs, "supabase", client)
    monkeypatch.setattr(qs, "SorgenteQromo", _SorgenteFinta)
    return client


def test_sincronizza_dry_run_non_chiama_il_client(finto):
    esito = _run(qs.sincronizza(sottodominio="test", dry_run=True))
    assert esito == {"ok": True, "dry_run": True, "sottodominio": "test", "categories": 1, "subcategories": 1, "products": 1}
    assert finto.chiamate == []


def test_sincronizza_cancella_in_ordine_fk_safe_e_reinserisce(finto):
    esito = _run(qs.sincronizza(sottodominio="test", dry_run=False))
    assert esito["products"] == 1

    ops = [(op, tab) for op, tab, _ in finto.chiamate]
    assert ops == [
        ("delete", "menu_products"), ("delete", "menu_subcategories"), ("delete", "menu_categories"),
        ("insert", "menu_categories"), ("insert", "menu_subcategories"), ("insert", "menu_products"),
    ]
    inseriti = {tab: rows for op, tab, rows in finto.chiamate if op == "insert"}
    assert [r["id"] for r in inseriti["menu_products"]] == [100]
    assert inseriti["menu_products"][0]["price"] == "1.20€"
    # menu_allergens mai toccata
    assert all(tab != "menu_allergens" for _, tab, _ in finto.chiamate)


def test_inserimento_a_lotti(finto, monkeypatch):
    monkeypatch.setattr(qs, "DIMENSIONE_LOTTO", 2)
    righe = {"categories": [], "subcategories": [], "products": [{"id": i} for i in range(5)]}
    qs._sostituisci_tabelle(righe)
    lotti = [len(rows) for op, tab, rows in finto.chiamate if op == "insert" and tab == "menu_products"]
    assert lotti == [2, 2, 1]
