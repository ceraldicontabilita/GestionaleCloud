"""Alert allergeni mancanti e associazione da una ricetta di Lotti
(app/menu/routes/allergeni_routes.py).

18/09/2026: l'abbinamento automatico per somiglianza di nome tra prodotti del
Menu e ricette di Lotti e' stato scartato (produce accoppiamenti sbagliati,
es. spritz diversi finiti sulla stessa ricetta). Qui si prova che l'unica
associazione automatica ammessa e' per id, dopo una scelta umana: /associa
collega e copia gli allergeni tradotti; /risincronizza li riallinea in seguito
senza rifare la scelta. Client Supabase e client Lotti sostituiti da finti in
memoria, nessuna rete.
"""
import asyncio

import pytest
from fastapi import HTTPException

from app.menu.routes import allergeni_routes as ar


def _run(coro):
    return asyncio.run(coro)


class _Res:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, tabelle, nome):
        self.tabelle, self.nome = tabelle, nome
        self.op, self.filtri, self.payload = "select", [], None

    def select(self, *_):
        return self

    def eq(self, colonna, valore):
        self.filtri.append((colonna, valore))
        return self

    def update(self, row):
        self.op, self.payload = "update", row
        return self

    def execute(self):
        righe = self.tabelle.get(self.nome, [])
        trovate = [r for r in righe if all(r.get(c) == v for c, v in self.filtri)]
        if self.op == "update":
            for r in trovate:
                r.update(self.payload)
            return _Res([dict(r) for r in trovate])
        return _Res([dict(r) for r in trovate])


class _FakeSupabase:
    def __init__(self, tabelle):
        self.tabelle = tabelle

    def table(self, nome):
        return _Query(self.tabelle, nome)


class _ClienteLottiFinto:
    def __init__(self, ricette):
        self._ricette = ricette
        self.configurato = True

    async def ricette(self):
        return self._ricette


def _prodotto(id_, nome, allergens=None, lotti_ref=None):
    return {
        "id": id_, "name_it": nome, "description_it": None,
        "allergens": allergens or [], "lotti_ref": lotti_ref, "visible": True,
    }


@pytest.fixture
def finto(monkeypatch):
    tabelle = {
        "menu_products": [
            _prodotto(1, "Brioche"),
            _prodotto(2, "Cappuccino", allergens=["milk"]),
            _prodotto(3, "Babà", lotti_ref="r-baba", allergens=["gluten"]),  # da riallineare
        ],
    }
    client = _FakeSupabase(tabelle)
    monkeypatch.setattr(ar, "supabase", client)
    ricette = [
        {"doc_id": "r-brioche", "nome": "brioche", "allergeni": ["gluten", "milk", "eggs"], "verificato": True},
        {"doc_id": "r-baba", "nome": "babà", "allergeni": ["gluten", "milk", "eggs"], "verificato": True},
    ]
    monkeypatch.setattr(ar, "_cliente_lotti", _ClienteLottiFinto(ricette))
    return tabelle


def test_traduzione_nomi_italiani_in_id_canonici():
    assert ar._traduci_allergeni(["Glutine", "Latte", "Uova"]) == ["eggs", "gluten", "milk"]
    assert ar._traduci_allergeni(["Ingrediente sconosciuto"]) == []
    assert ar._traduci_allergeni(None) == []


def test_mancanti_elenca_solo_prodotti_senza_allergeni(finto):
    esito = _run(ar.prodotti_senza_allergeni(_username="admin"))
    assert esito["totale_prodotti"] == 3
    assert esito["senza_allergeni"] == 1
    assert [p["name_it"] for p in esito["prodotti"]] == ["Brioche"]
    assert esito["senza_ricetta_collegata"] == 1


def test_ricette_lotti_richiede_configurazione(monkeypatch):
    monkeypatch.setattr(ar, "_cliente_lotti", ar._ClienteRicetteLotti())
    with pytest.raises(HTTPException) as err:
        _run(ar.ricette_lotti(_username="admin"))
    assert err.value.status_code == 503


def test_associa_collega_e_copia_gli_allergeni_tradotti(finto):
    payload = ar.AssociaRicetta(product_id=1, ricetta_doc_id="r-brioche")
    esito = _run(ar.associa_ricetta(payload, username="admin"))
    assert esito["success"] is True
    assert esito["prodotto"]["lotti_ref"] == "r-brioche"
    assert sorted(esito["prodotto"]["allergens"]) == ["eggs", "gluten", "milk"]
    assert esito["ricetta_verificata"] is True


def test_associa_ricetta_inesistente_da_404(finto):
    payload = ar.AssociaRicetta(product_id=1, ricetta_doc_id="non-esiste")
    with pytest.raises(HTTPException) as err:
        _run(ar.associa_ricetta(payload, username="admin"))
    assert err.value.status_code == 404


def test_risincronizza_riallinea_solo_chi_e_cambiato(finto):
    esito = _run(ar.risincronizza(_username="admin"))
    assert [a["id"] for a in esito["aggiornati"]] == [3]
    assert sorted(esito["aggiornati"][0]["allergens"]) == ["eggs", "gluten", "milk"]
    # Cappuccino non e' collegato a nessuna ricetta: non tocco i suoi allergeni manuali
    cappuccino = next(p for p in finto["menu_products"] if p["id"] == 2)
    assert cappuccino["allergens"] == ["milk"]
