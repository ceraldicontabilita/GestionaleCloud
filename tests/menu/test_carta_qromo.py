"""La carta del menu: tre livelli come nella replica Qromo, dati dal repository o dall'admin."""
import asyncio
import json
from copy import deepcopy

import pytest

from app.menu import carta_qromo as carta
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def _run(coro):
    return asyncio.run(coro)


def test_card_dolci_unifica_sorgenti_conservando_id_prezzi_e_allergeni():
    dati = {
        "menus": [{"id": 1, "n": "Bar & Dolci"}, {"id": 2, "n": "Food"}, {"id": 3, "n": "Produzione Ceraldi", "pic": "salato.jpg"}],
        "cats": [{"id": 10, "m": 1, "n": "Dolci"}, {"id": 11, "m": 1, "n": "Colazione"}, {"id": 12, "m": 1, "n": "Caffè"},
                 {"id": 20, "m": 2, "n": "Piatti"}, {"id": 30, "m": 3, "n": "Pasticceria"}, {"id": 31, "m": 3, "n": "Rosticceria"}, {"id": 32, "m": 3, "n": "Altro"}],
        "items": [{"id": c["id"] * 10, "c": c["id"], "p": None if c["id"] == 30 else 250, "a": ["milk"], "pic": f"foto-{c['id']}.jpg"} for c in
                  [{"id": i} for i in (10, 11, 12, 20, 30, 31, 32)]],
    }
    originale = deepcopy(dati)
    risultato = carta._raggruppa_carta(dati)
    assert {m["n"] for m in risultato["menus"]} == {"Bar", "Food", "Dolci", "Altri prodotti"}
    cats = {c["id"]: c for c in risultato["cats"]}
    assert cats[10]["m"] == cats[11]["m"] == 3 and 30 not in cats
    assert cats[12]["m"] == 1 and cats[31]["m"] == 2 and cats[32]["m"] == "altri_prodotti"
    assert next(i for i in risultato["items"] if i["id"] == 300)["c"] == 10
    assert next(m for m in risultato["menus"] if m["n"] == "Dolci")["pic"] != "salato.jpg"
    for campo in ("id", "p", "a", "pic"):
        assert [i[campo] for i in risultato["items"]] == [i[campo] for i in originale["items"]]
    assert carta._raggruppa_carta(deepcopy(risultato)) == risultato


def test_card_dolci_senza_produzione_e_food_non_perde_prodotti():
    dati = {"menus": [{"id": 1, "n": "Bar & Dolci"}], "cats": [{"id": 10, "m": 1, "n": "Dolci"}],
            "items": [{"id": 100, "c": 10, "pic": None}]}
    risultato = carta._raggruppa_carta(dati)
    assert [m["n"] for m in risultato["menus"]] == ["Dolci"]
    assert risultato["cats"][0]["m"] == "dolci"
    risultato = carta._raggruppa_carta({"menus": [{"id": 2, "n": "Produzione Ceraldi"}],
        "cats": [{"id": 20, "m": 2, "n": "Rosticceria"}], "items": [{"id": 200, "c": 20}]})
    assert [m["n"] for m in risultato["menus"]] == ["Food"]
    assert risultato["cats"][0]["m"] == "food_lotti"


@pytest.fixture
def db(monkeypatch):
    finto = ClientArchivioMemoria()["carta_test"]

    async def _finto():
        return finto

    monkeypatch.setattr(carta, "_db", _finto)
    from app.menu.qromo_sync import trasforma_catalogo
    from tests.menu.test_menu_public_visible import _FakeSupabase
    righe = trasforma_catalogo(carta._seme()["pub"])
    client = _FakeSupabase({"menu_categories": righe["categories"],
                            "menu_subcategories": righe["subcategories"],
                            "menu_products": righe["products"]})
    monkeypatch.setattr(carta.menu_routes, "supabase", client)
    return finto


def test_il_seme_ha_la_carta_completa(db):
    seme = carta._seme()
    dati = carta.costruisci_carta(seme["pub"], seme["extras"], seme["imgmap"])
    assert len(dati["menus"]) == 11 and len(dati["cats"]) == 68 and len(dati["items"]) == 769
    prodotto = next(i for i in dati["items"] if i["id"] == 152788)
    assert prodotto["p"] == 250 and "gluten" in prodotto["a"] and prodotto["mat"]
    # le foto sono file serviti dal menu, non indirizzi esterni
    foto = [x["pic"] for x in dati["items"] + dati["cats"] + dati["menus"] if x["pic"]]
    assert foto and all(f.startswith("/menu/carta/img/") for f in foto)


def test_ogni_foto_indicata_esiste_nei_file_statici(db):
    from pathlib import Path
    radice = Path(__file__).resolve().parents[2] / "frontend_menu" / "public"
    seme = carta._seme()
    dati = carta.costruisci_carta(seme["pub"], seme["extras"], seme["imgmap"])
    mancanti = {x["pic"] for x in dati["items"] + dati["cats"] + dati["menus"]
                if x["pic"] and not (radice / x["pic"].removeprefix("/menu/")).exists()}
    assert not mancanti


def test_la_scelta_dell_admin_cambia_prezzo_e_disponibilita_e_sopravvive_all_import(db):
    _run(carta.imposta_prodotto(152788, carta.SceltaProdotto(prezzo_centesimi=300), "admin"))
    dati = _run(carta.carta_pubblica())
    p = next(i for i in dati["items"] if i["id"] == 152788)
    assert p["p"] == 300 and p["on"] == 1
    seme = carta._seme()
    _run(carta.importa(carta.Importa(**seme), "admin"))
    p = next(i for i in _run(carta.carta_pubblica())["items"] if i["id"] == 152788)
    assert p["p"] == 300 and p["on"] == 1, "un nuovo import non cancella le scelte"
    _run(carta.imposta_prodotto(152788, carta.SceltaProdotto(disponibile=False), "admin"))
    assert not any(i["id"] == 152788 for i in _run(carta.carta_pubblica())["items"])


def test_il_vecchio_reset_non_cancella_dati_e_indica_la_modifica_canonica(db):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        _run(carta.toglie_override(152788, "admin"))
    assert e.value.status_code == 410


def test_import_dettagli_dichiara_che_non_cambia_catalogo(db):
    from copy import deepcopy
    dati = deepcopy(carta._seme())
    p = next(p for p in dati["pub"]["menusItems"] if p["menu_item_id"] == 152788)
    p.update(name="Nome importato di prova", price=666)
    risposta = _run(carta.importa(carta.Importa(**dati), "admin"))
    assert risposta["ok"] is True
    assert risposta["ambito"] == "dettagli_carta" and risposta["catalogo_aggiornato"] is False
    prodotto = next(p for p in _run(carta.carta_pubblica())["items"] if p["id"] == 152788)
    assert prodotto["p"] == 250 and prodotto["n"] != "Nome importato di prova"


def test_salvataggio_admin_compare_nella_carta_usata_dai_clienti(db):
    from app.menu.models.menu_models import ProductUpdate
    _run(carta.menu_routes.update_product(152788, ProductUpdate(
        nameIT="Prodotto di prova", price="3,75€", allergens=["milk", "nuts"],
        descriptionIT="Ingredienti confermati", image="/menu/foto-prova.jpg"), "admin"))
    prodotto = next(i for i in _run(carta.carta_pubblica())["items"] if i["id"] == 152788)
    assert prodotto["n"] == "Prodotto di prova" and prodotto["p"] == 375
    assert prodotto["a"] == ["milk", "wot"] and prodotto["pic"] == "/menu/foto-prova.jpg"
    assert prodotto["d"] == "Ingredienti confermati" and prodotto["mat"] is None


def test_carta_include_lotti_senza_prezzo_ma_non_li_rende_ordinabili(db):
    client = carta.menu_routes.supabase
    tabelle = client.tabelle
    tabelle["menu_categories"].append({"id": 1000000, "name": "Produzione", "name_it": "Produzione"})
    tabelle["menu_subcategories"].extend([
        {"id": 1000000, "category_id": 1000000, "name": "Ricette", "name_it": "Ricette"},
        {"id": 1000001, "category_id": 1000000, "name": "Vuota", "name_it": "Vuota"},
    ])
    base = {"category_id": 1000000, "subcategory_id": 1000000, "name": "Ricetta",
            "name_it": "Ricetta", "origine": "lotti", "allergens": ["eggs"], "visible": True}
    for indice, prezzo in enumerate(["4.50€", "", "nan", "0.00€", "-1.00€", "1.001€"]):
        tabelle["menu_products"].append({**base, "id": 1000000 + indice, "price": prezzo})
    risultato = _run(carta.carta_pubblica())
    ricette = [i for i in risultato["items"] if i["id"] >= 1000000]
    assert [i["id"] for i in ricette] == list(range(1000000, 1000006))
    assert all(i["p"] is None for i in ricette[1:])
    assert ricette[0]["p"] == 450 and ricette[0]["a"] == ["egg"]
    assert [c["id"] for c in risultato["cats"] if c["m"] == 1000000] == [1000000]
    from fastapi import HTTPException
    for id_ in range(1000001, 1000006):
        with pytest.raises(HTTPException) as errore:
            _run(carta.menu_routes.get_product(id_))
        assert errore.value.status_code == 404
    with pytest.raises(HTTPException) as e:
        _run(carta.imposta_prodotto(1000000, carta.SceltaProdotto(prezzo_centesimi=500), "admin"))
    assert e.value.status_code == 409


def test_prodotto_inesistente_e_import_incompleto_sono_rifiutati(db):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        _run(carta.imposta_prodotto(1, carta.SceltaProdotto(disponibile=True), "admin"))
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:
        _run(carta.importa(carta.Importa(pub={"menus": []}), "admin"))
    assert e.value.status_code == 422
    assert _run(carta.stato("admin"))["fonte"] == "seme"


def test_carta_non_espone_listini_banco_o_prodotti_qromo_non_attivi(db):
    pub = carta._seme()["pub"]
    menus = {m["menu_id"]: m for m in pub["menus"]}
    categorie = {c["menu_category_id"]: c for c in pub["menusCategories"]}
    attesi = {
        p["menu_item_id"] for p in pub["menusItems"]
        if p["available"] == 1 and p["price"] and p["price"] > 0
        and categorie[p["category_id"]]["active"] == 1
        and menus[categorie[p["category_id"]]["menu_id"]]["available"] == 1
        and not menus[categorie[p["category_id"]]["menu_id"]]["name"].startswith("BANCO - ")
    }
    risultato = _run(carta.carta_pubblica())
    assert {i["id"] for i in risultato["items"]} == attesi
    stato = _run(carta.stato("admin"))
    assert stato["prodotti"] == len(attesi)
    assert stato["catalogo"] == "menu_products"


def test_tutti_i_quattordici_allergeni_ue_arrivano_ai_filtri_della_carta():
    canonici = ["celery", "molluscs", "sulphites", "eggs", "fish", "gluten", "lupin",
                "milk", "mustard", "peanuts", "sesame", "crustaceans", "soy", "nuts"]
    risultato = carta.carta_da_menu(
        [{"id": 1, "name": "Test", "nameIT": "Test"}],
        [{"id": 10, "category_id": 1, "name": "Test", "nameIT": "Test"}],
        [{"id": 100, "category_id": 1, "subcategory_id": 10, "name": "Test", "nameIT": "Test",
          "price": "1.00€", "allergens": canonici}],
        {"menus": [], "cats": [], "items": []}, {},
    )
    assert set(risultato["items"][0]["a"]) == {
        "celery", "clams", "dioxide", "egg", "fish", "gluten", "lupins", "milk",
        "mustard", "peanuts", "sesame", "shellfish", "soia", "wot",
    }
