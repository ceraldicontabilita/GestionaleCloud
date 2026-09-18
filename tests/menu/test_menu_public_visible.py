"""Menu pubblico e colonna ``visible`` (app/menu/routes/menu_routes.py).

I prodotti creati da Lotti (origine "lotti") nascono con ``visible`` = scelta
del titolare: il menu per i clienti (``GET /api/menu/``, sottocategoria,
prodotto, ricerca) li esclude quando visible=false, l'area admin li vede
sempre e puo' cambiare il flag. Righe senza la chiave = visibili.
Client Supabase sostituito da un finto in memoria, nessuna rete.
"""
import asyncio

import pytest
from fastapi import HTTPException

from app.menu.routes import menu_routes as mr
from app.menu.models.menu_models import ProductCreate, ProductUpdate


def _run(coro):
    return asyncio.run(coro)


class _Res:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, tabelle, registro, nome):
        self.tabelle, self.registro, self.nome = tabelle, registro, nome
        self.op, self.filtri, self.payload, self._limit = "select", [], None, None
        self._order = None

    def select(self, *_):
        return self

    def order(self, colonna, desc=False):
        self._order = (colonna, desc)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def eq(self, colonna, valore):
        self.filtri.append((colonna, valore))
        return self

    def or_(self, *_):
        return self

    def insert(self, row):
        self.op, self.payload = "insert", row
        return self

    def update(self, row):
        self.op, self.payload = "update", row
        return self

    def execute(self):
        righe = self.tabelle.get(self.nome, [])
        trovate = [r for r in righe if all(r.get(c) == v for c, v in self.filtri)]
        if self.op == "insert":
            self.registro.append(("insert", self.nome, self.payload))
            righe.append(dict(self.payload))
            return _Res([self.payload])
        if self.op == "update":
            self.registro.append(("update", self.nome, self.payload, list(self.filtri)))
            for r in trovate:
                r.update(self.payload)
            return _Res([dict(r) for r in trovate])
        if self._order:
            trovate.sort(key=lambda r: r[self._order[0]], reverse=self._order[1])
        if self._limit:
            trovate = trovate[: self._limit]
        return _Res([dict(r) for r in trovate])


class _FakeSupabase:
    def __init__(self, tabelle):
        self.tabelle = tabelle
        self.chiamate = []

    def table(self, nome):
        return _Query(self.tabelle, self.chiamate, nome)


def _prodotto(id_, sub, nome, **extra):
    riga = {
        "id": id_, "category_id": 1, "subcategory_id": sub, "name": nome, "name_it": nome,
        "price": "1.00€", "description": None, "description_it": None, "allergens": [], "image": None,
    }
    riga.update(extra)
    return riga


@pytest.fixture
def finto(monkeypatch):
    tabelle = {
        "menu_categories": [{"id": 1, "name": "Bar", "name_it": "Bar", "image": None}],
        "menu_subcategories": [{"id": 10, "category_id": 1, "name": "Caffetteria", "name_it": "Caffetteria", "image": None}],
        "menu_products": [
            _prodotto(100, 10, "Espresso"),                                   # senza chiave = visibile
            _prodotto(101, 10, "Cappuccino", visible=True, origine=None),
            _prodotto(1000000, 10, "Babà", visible=False, origine="lotti", lotti_ref="ricetta:r1"),
        ],
        "menu_allergens": [],
    }
    client = _FakeSupabase(tabelle)
    monkeypatch.setattr(mr, "supabase", client)
    return client


def test_menu_pubblico_esclude_visible_false(finto):
    menu = _run(mr.get_full_menu())
    voci = menu["categories"][0]["subcategories"][0]["items"]
    assert [p["nameIT"] for p in voci] == ["Espresso", "Cappuccino"]
    assert all(p["visible"] is True for p in voci)

    sotto = _run(mr.get_subcategory(10))
    assert [p["id"] for p in sotto["items"]] == [100, 101]

    categoria = _run(mr.get_category(1))
    assert [p["id"] for p in categoria["subcategories"][0]["items"]] == [100, 101]

    ricerca = _run(mr.search_products("ba"))
    assert ricerca["count"] == 2
    assert 1000000 not in [p["id"] for p in ricerca["results"]]


def test_prodotto_nascosto_404_nel_pubblico_ma_visibile_in_admin(finto):
    assert _run(mr.get_product(100))["id"] == 100
    with pytest.raises(HTTPException) as err:
        _run(mr.get_product(1000000))
    assert err.value.status_code == 404

    tutti = _run(mr.get_all_products_flat(username="admin"))
    assert tutti["total"] == 3
    nascosto = next(p for p in tutti["products"] if p["id"] == 1000000)
    assert nascosto["visible"] is False
    assert nascosto["origine"] == "lotti"


def test_prod_in_e_prod_out_gestiscono_visible():
    assert mr.prod_out(_prodotto(1, 10, "x"))["visible"] is True
    assert mr.prod_out(_prodotto(1, 10, "x", visible=None))["visible"] is True
    assert mr.prod_out(_prodotto(1, 10, "x", visible=False))["visible"] is False

    base = {"name": "n", "nameIT": "n", "price": "1.00€"}
    assert mr.prod_in(base)["visible"] is True
    assert mr.prod_in({**base, "visible": False})["visible"] is False
    assert ProductCreate(category_id=1, subcategory_id=10, **base).visible is True


def test_admin_create_e_update_accettano_visible(finto):
    creato = _run(mr.create_product(
        ProductCreate(category_id=1, subcategory_id=10, name="Nuovo", nameIT="Nuovo", price="2.00€", visible=False),
        username="admin",
    ))
    assert creato["success"] is True
    inserito = next(p for op, tab, p in finto.chiamate if op == "insert" and tab == "menu_products")
    assert inserito["visible"] is False
    assert inserito["id"] == 1000001

    _run(mr.update_product(1000000, ProductUpdate(visible=True), username="admin"))
    aggiornamento = next(c for c in finto.chiamate if c[0] == "update")
    assert aggiornamento[2] == {"visible": True}
    assert _run(mr.get_product(1000000))["nameIT"] == "Babà"
