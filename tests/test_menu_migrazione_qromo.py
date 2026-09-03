"""Sincronizzazione del catalogo da Qromo (app/menu/migrazione_qromo.py).

Copre l'estrazione delle costanti JavaScript incorporate nella pagina, i
filtri (listino interno "BANCO" escluso, prodotti non disponibili esclusi,
categorie/sottocategorie senza prodotti reali potate, come "Comunicazioni"),
la riduzione dei 39 tag Qromo ai 14 allergeni UE e la formattazione del
prezzo. Nessuna rete reale: la sorgente e' sostituita con dati sintetici.
"""
import asyncio

import pytest

from app.menu import migrazione_qromo as mq
from app.services.sheets_document_store import SheetDatabase


def _run(coro):
    return asyncio.run(coro)


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


def test_estrai_costanti_javascript_isola_ogni_const():
    costanti = mq._estrai_costanti_javascript(HTML_QROMO)
    assert costanti["TEST"] == "false"
    assert mq._costante_json(costanti, "business", {}) == {"business_id": 1}
    assert len(mq._costante_json(costanti, "menus", [])) == 3
    assert mq._costante_json(costanti, "assente", "fallback") == "fallback"


def test_estrai_costanti_javascript_senza_script_solleva_errore():
    with pytest.raises(ValueError):
        mq._estrai_costanti_javascript("<html><body>niente</body></html>")


@pytest.mark.parametrize("centesimi,atteso", [(120, "€ 1,20"), (350, "€ 3,50"), (0, "€ 0,00"), (None, "€ 0,00"), (5, "€ 0,05")])
def test_prezzo_formatta_in_euro_con_virgola(centesimi, atteso):
    assert mq._prezzo(centesimi) == atteso


class _SorgenteFinta:
    """Stessa interfaccia di SorgenteQromo, senza rete: le immagini sono
    contenuti finti derivati dall'URL, cosi' la dedup per contenuto resta
    verificabile (stesso URL -> stesso contenuto -> un solo blob)."""

    def __init__(self, _sottodominio):
        self.chiamate_immagine = []

    async def chiudi(self):
        pass

    async def catalogo(self):
        costanti = mq._estrai_costanti_javascript(HTML_QROMO)
        return {
            "menus": mq._costante_json(costanti, "menus", []),
            "menusCategories": mq._costante_json(costanti, "menusCategories", []),
            "menusItems": mq._costante_json(costanti, "menusItems", []),
            "menusItemsAllergens": mq._costante_json(costanti, "menusItemsAllergens", []),
            "allergens": mq._costante_json(costanti, "allergens", []),
        }

    async def scarica_immagine(self, url):
        self.chiamate_immagine.append(url)
        return (f"contenuto-di-{url}".encode(), "image/jpeg")


@pytest.fixture
def store(monkeypatch):
    from app import database as gestionale_database
    from app.menu import storage

    db = SheetDatabase("test")
    monkeypatch.setattr(gestionale_database.Database, "db", db)
    monkeypatch.setattr(gestionale_database.Database, "client", db)
    storage._blob_cache.clear()
    yield db
    storage._blob_cache.clear()


def test_sincronizza_filtra_banco_non_disponibili_e_categorie_vuote(store, monkeypatch):
    finta = _SorgenteFinta("test")
    monkeypatch.setattr(mq, "SorgenteQromo", lambda sottodominio: finta)

    esito = _run(mq.sincronizza(sottodominio="test", dry_run=False, con_immagini=True))

    assert esito["coincide"] is True
    assert esito["tabelle"]["menu"] == {"sorgente": 1, "destinazione": 1, "collezione": "menu_categories"}
    assert esito["tabelle"]["sottocategorie"] == {"sorgente": 1, "destinazione": 1, "collezione": "menu_subcategories"}
    assert esito["tabelle"]["prodotti"] == {"sorgente": 1, "destinazione": 1, "collezione": "menu_products"}

    categorie = _run(store["menu_categories"].find({}).to_list(None))
    assert [c["id"] for c in categorie] == [1]  # "BANCO - Bar" (2) e "Comunicazioni" (3, senza prodotti) escluse

    sottocategorie = _run(store["menu_subcategories"].find({}).to_list(None))
    assert [c["id"] for c in sottocategorie] == [10]

    prodotti = _run(store["menu_products"].find({}).to_list(None))
    assert len(prodotti) == 1
    prodotto = prodotti[0]
    assert prodotto["id"] == 100
    assert prodotto["price"] == "€ 1,20"
    assert prodotto["descriptionIT"] == "Ottimo caffè"
    # gluten (diretto) e barley (mappato su gluten) si fondono in un solo tag; vegan non e' un allergene e viene scartato.
    assert prodotto["allergens"] == ["gluten"]
    assert prodotto["image"].startswith("/api/menu/pubblico/immagini/")

    # Le immagini sono state scaricate una sola volta per URL distinto (categoria, sottocategoria, prodotto).
    assert sorted(finta.chiamate_immagine) == sorted([
        "https://img.qromo.io/cat1.jpg", "https://img.qromo.io/sub1.jpg", "https://img.qromo.io/p1.jpg",
    ])


def test_sincronizza_dry_run_non_scrive_nulla(store, monkeypatch):
    finta = _SorgenteFinta("test")
    monkeypatch.setattr(mq, "SorgenteQromo", lambda sottodominio: finta)

    esito = _run(mq.sincronizza(sottodominio="test", dry_run=True, con_immagini=True))

    assert esito["dry_run"] is True
    assert esito["tabelle"]["prodotti"]["sorgente"] == 1
    assert _run(store["menu_products"].count_documents({})) == 0
    assert finta.chiamate_immagine == []  # in prova non si scarica nulla


def test_sincronizza_e_idempotente(store, monkeypatch):
    finta = _SorgenteFinta("test")
    monkeypatch.setattr(mq, "SorgenteQromo", lambda sottodominio: finta)

    _run(mq.sincronizza(sottodominio="test", dry_run=False, con_immagini=False))
    _run(mq.sincronizza(sottodominio="test", dry_run=False, con_immagini=False))

    assert _run(store["menu_products"].count_documents({})) == 1
    assert _run(store["menu_categories"].count_documents({})) == 1
