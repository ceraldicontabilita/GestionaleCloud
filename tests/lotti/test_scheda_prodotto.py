"""Scheda prodotto: la catena del piatto sotto un solo ID (PRD-000123)."""
import asyncio

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

from app.lotti.routers import ricette as ricette_router
from app.lotti.routers import scheda_prodotto
from app.lotti.servizi import menu_bridge
from app.menu import carta_qromo
from app.menu.qr_prodotto import url_prodotto
from app.menu.routes import menu_routes


def _run(coro):
    return asyncio.run(coro)


# ---------- scheda vendita sulla ricetta ----------

def test_la_ricetta_senza_scheda_vende_ovunque_ed_e_disponibile():
    assert menu_bridge.scheda_vendita_da_ricetta({}) == {
        "vendita_sala": True, "vendita_delivery": True, "disponibile": True, "aggiunte": [], "rimozioni": [],
    }


def test_la_scheda_vendita_porta_canali_esaurito_aggiunte_e_rimozioni():
    s = menu_bridge.scheda_vendita_da_ricetta({
        "vendita_delivery": False, "esaurito": True,
        "aggiunte": [{"nome": "Panna", "prezzo_centesimi": 50}, {"nome": "", "prezzo_centesimi": 10}, {"nome": "X", "prezzo_centesimi": -1}],
        "rimozioni": ["Rum", " "],
    })
    assert s["vendita_sala"] is True and s["vendita_delivery"] is False and s["disponibile"] is False
    assert s["aggiunte"] == [{"nome": "Panna", "prezzo_centesimi": 50}]
    assert s["rimozioni"] == ["Rum"]


@pytest.fixture
def archivio(monkeypatch):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(ricette_router, "db", database)

    async def _sync(_id):
        return {"esito": "finto"}

    monkeypatch.setattr(ricette_router, "_sincronizza_menu", _sync)
    _run(database.ricette.insert_one({"id": "r1", "nome": "Babà", "ingredienti_dettaglio": [{"nome": "Rum"}, {"nome": "Farina"}]}))
    return database


def _salva(**campi):
    return _run(ricette_router.set_scheda_vendita("r1", ricette_router.SchedaVendita(**campi), _admin=None))


def test_si_salvano_canali_esaurito_aggiunte_e_rimozioni_con_prezzo_in_centesimi(archivio):
    esito = _salva(vendita_delivery=False, esaurito=True,
                   aggiunte=[{"nome": "Panna", "prezzo": 0.5}, {"nome": "Crema", "prezzo": 1.1}], rimozioni=["rum"])
    assert esito["aggiunte"] == [{"nome": "Panna", "prezzo_centesimi": 50}, {"nome": "Crema", "prezzo_centesimi": 110}]
    assert esito["rimozioni"] == ["Rum"]
    salvata = _run(archivio.ricette.find_one({"id": "r1"}))
    assert salvata["vendita_delivery"] is False and salvata["esaurito"] is True and "vendita_sala" not in salvata


def test_una_rimozione_deve_essere_un_ingrediente_della_ricetta(archivio):
    with pytest.raises(HTTPException) as e:
        _salva(rimozioni=["Cioccolato"])
    assert e.value.status_code == 400


def test_aggiunta_ripetuta_o_scheda_vuota_sono_rifiutate(archivio):
    with pytest.raises(HTTPException):
        _salva(aggiunte=[{"nome": "Panna", "prezzo": 1}, {"nome": "panna", "prezzo": 2}])
    with pytest.raises(HTTPException):
        _salva()


def test_prezzo_aggiunta_non_finito_e_rifiutato():
    with pytest.raises(ValueError):
        ricette_router.AggiuntaProdotto(nome="Panna", prezzo=float("nan"))
    with pytest.raises(ValueError):
        ricette_router.AggiuntaProdotto(nome="Panna", prezzo=-1)


# ---------- costo e food cost ----------

def test_food_cost_dagli_stessi_campi_del_motore_prezzi():
    f = scheda_prodotto.costo_e_food_cost({"costo_totale": 12, "porzioni": 4, "prezzo_vendita": 6})
    assert (f["costo_porzione"], f["food_cost_percentuale"], f["motivo"]) == ("3.00", "50.0", None)


def test_senza_costo_o_prezzo_il_food_cost_e_non_disponibile_non_zero():
    f = scheda_prodotto.costo_e_food_cost({"porzioni": 4, "prezzo_vendita": 6})
    assert f["food_cost_percentuale"] is None and f["costo_totale"] is None and f["motivo"]


# ---------- QR del prodotto ----------

def test_url_prodotto_dal_menu_pubblico():
    assert url_prodotto("https://x.it/menu/", "PRD-000123") == "https://x.it/menu/carta/?p=PRD-000123"
    assert url_prodotto("https://x.it/menu/", "PRD-000123", "delivery") == "https://x.it/menu/carta/?p=PRD-000123&canale=delivery"
    assert url_prodotto(None, "PRD-000123") is None
    assert url_prodotto("https://x.it/menu/", "abc") is None
    with pytest.raises(ValueError):
        url_prodotto("https://x.it/menu/", "PRD-000123", "tavolo")


# ---------- il Menu riceve la scheda; senza la migrazione la ricetta arriva lo stesso ----------

class _Tab:
    def __init__(self, scrittore):
        self.s = scrittore

    def update(self, riga):
        self.riga = riga
        return self

    def eq(self, *_):
        return self

    def execute(self):
        return self.s(self.riga)


def test_senza_colonne_di_vendita_il_ponte_riprova_senza(monkeypatch):
    scritture = []

    def scrittore(riga):
        scritture.append(set(riga))
        if "vendita_sala" in riga:
            raise RuntimeError("Could not find the 'vendita_sala' column of 'menu_products' in the schema cache")
        return None

    class _Sb:
        def table(self, _):
            return _Tab(scrittore)

    monkeypatch.setattr(menu_bridge, "supabase", _Sb())
    monkeypatch.setattr(menu_bridge, "_riga_esistente", lambda ref: {"id": 1000001})
    monkeypatch.setattr(menu_bridge, "_destinazione_menu", lambda r: (1, 2, "automatica"))
    monkeypatch.setattr(menu_bridge, "_immagine_per_prodotto", lambda *a: None)
    esito = menu_bridge._pubblica_sync({"id": "r1", "nome": "Babà", "prezzo_vendita": 3.5, "vendita_delivery": False}, None, True)
    assert esito["esito"] == "aggiornato"
    assert "vendita_sala" in scritture[0] and "vendita_sala" not in scritture[1]


def test_un_errore_diverso_dalle_colonne_non_si_nasconde(monkeypatch):
    def scrittore(riga):
        raise RuntimeError("connessione persa")

    class _Sb:
        def table(self, _):
            return _Tab(scrittore)

    monkeypatch.setattr(menu_bridge, "supabase", _Sb())
    monkeypatch.setattr(menu_bridge, "_riga_esistente", lambda ref: {"id": 1000001})
    monkeypatch.setattr(menu_bridge, "_destinazione_menu", lambda r: (1, 2, "automatica"))
    monkeypatch.setattr(menu_bridge, "_immagine_per_prodotto", lambda *a: None)
    with pytest.raises(RuntimeError):
        menu_bridge._pubblica_sync({"id": "r1", "nome": "Babà"}, None, True)


# ---------- carta: campi e canali ----------

def _prodotto(id_, **extra):
    riga = {"id": id_, "category_id": 1, "subcategory_id": 2, "name": f"P{id_}", "name_it": f"P{id_}", "price": "3.50€",
            "allergens": [], "visible": True, "origine": "lotti", "lotti_ref": f"ricetta:{id_}", "codice_prodotto": f"PRD-{id_:06d}"}
    riga.update(extra)
    return menu_routes.prod_out(riga)


def test_la_carta_porta_codice_canali_disponibilita_aggiunte_e_rimozioni():
    prodotti = [_prodotto(1), _prodotto(2, vendita_delivery=False, disponibile=False,
                                         aggiunte=[{"nome": "Panna", "prezzo_centesimi": 50}], rimozioni=["Rum"])]
    sub = [{"id": 2, "category_id": 1, "name": "Pastry", "nameIT": "Pasticceria"}]
    cat = [{"id": 1, "name": "Produzione Ceraldi", "nameIT": "Produzione Ceraldi"}]
    carta = carta_qromo.carta_da_menu(cat, sub, prodotti, {"menus": [], "cats": [], "items": []}, {})
    a, b = carta["items"]
    assert (a["sala"], a["dlv"], a["disp"], a["ag"], a["rm"]) == (1, 1, 1, [], [])
    assert (b["sala"], b["dlv"], b["disp"]) == (1, 0, 0)
    assert b["ag"] == [{"n": "Panna", "p": 50}] and b["rm"] == ["Rum"] and b["cod"] == "PRD-000002"


def test_il_canale_delivery_toglie_i_prodotti_non_venduti(monkeypatch):
    items = [{"id": 1, "c": 2, "dlv": 1, "sala": 1}, {"id": 2, "c": 3, "dlv": 0, "sala": 1}]
    carta = {"menus": [{"id": 9}], "cats": [{"id": 2, "m": 9}, {"id": 3, "m": 9}], "items": items}

    async def _dati():
        return {"pub": {}, "extras": {}}

    async def _carta(dati, destinazione="pubblico"):
        return {k: list(v) for k, v in carta.items()}

    monkeypatch.setattr(carta_qromo, "_dataset", _dati)
    monkeypatch.setattr(carta_qromo, "_carta_dai_dati", _carta)
    d = _run(carta_qromo.carta_pubblica(canale="delivery"))
    assert [i["id"] for i in d["items"]] == [1] and [c["id"] for c in d["cats"]] == [2]
    s = _run(carta_qromo.carta_pubblica(canale="sala"))
    assert len(s["items"]) == 2
    with pytest.raises(HTTPException):
        _run(carta_qromo.carta_pubblica(canale="tavolo"))


# ---------- la scheda intera ----------

def test_la_scheda_riunisce_la_catena_sotto_un_solo_codice(monkeypatch, archivio):
    _run(archivio.ricette.update_one({"id": "r1"}, {"$set": {
        "prezzo_vendita": 3.5, "prezzo_tavolo": 4, "reparto": "pasticceria", "costo_totale": 7, "porzioni": 7,
        "allergeni": ["Glutine"], "vendita_sala": False, "aggiunte": [{"nome": "Panna", "prezzo_centesimi": 50}],
        "rimozioni": ["Rum"]}}))
    _run(archivio.ricette.insert_one({"id": "r2", "nome": "Babà senza rum", "ricetta_base_id": "r1"}))
    monkeypatch.setattr(scheda_prodotto, "db", archivio)

    async def _codici():
        return {"r1": "PRD-000007", "r2": "PRD-000008"}

    async def _url():
        return "https://x.it/menu/"

    async def _disp(rid, esaurito):
        return {"esaurito": esaurito, "ingredienti_in_giacenza": True, "ingredienti_mancanti": [], "motivo": None}

    async def _nutri(rid):
        return {"per_porzione": {"kcal": 300}, "per_100g": None, "motivo": None}

    monkeypatch.setattr(menu_bridge, "codici_prodotti_ricette", _codici)
    monkeypatch.setattr(menu_bridge, "url_menu_pubblico", _url)
    monkeypatch.setattr(scheda_prodotto, "_disponibilita", _disp)
    monkeypatch.setattr(scheda_prodotto, "_nutrizionali", _nutri)
    ricetta = _run(archivio.ricette.find_one({"id": "r1"}, {"_id": 0}))
    s = _run(scheda_prodotto.costruisci_scheda(ricetta))
    assert s["codice_prodotto"] == "PRD-000007"
    assert s["prezzo"] == {"banco": "3.50", "tavolo": "4.00"}
    assert s["costo_ingredienti_e_food_cost"]["food_cost_percentuale"] == "28.6"
    assert s["varianti"] == [{"id": "r2", "nome": "Babà senza rum", "codice_prodotto": "PRD-000008"}]
    assert s["vendita"] == {"sala": False, "delivery": True}
    assert s["aggiunte"] == [{"nome": "Panna", "prezzo": "0.50"}] and s["rimozioni"] == ["Rum"]
    assert s["qr"]["delivery"] == "https://x.it/menu/carta/?p=PRD-000007&canale=delivery"
    assert s["valori_nutrizionali"]["per_porzione"]["kcal"] == 300


def test_scheda_senza_menu_raggiungibile_non_inventa_il_qr(monkeypatch, archivio):
    monkeypatch.setattr(scheda_prodotto, "db", archivio)

    async def _giu():
        raise RuntimeError("Menu giu'")

    async def _disp(rid, esaurito):
        return {"esaurito": esaurito, "ingredienti_in_giacenza": None, "ingredienti_mancanti": [], "motivo": "x"}

    async def _nutri(rid):
        return {"per_porzione": None, "per_100g": None, "motivo": "x"}

    monkeypatch.setattr(menu_bridge, "codici_prodotti_ricette", _giu)
    monkeypatch.setattr(scheda_prodotto, "_disponibilita", _disp)
    monkeypatch.setattr(scheda_prodotto, "_nutrizionali", _nutri)
    s = _run(scheda_prodotto.costruisci_scheda(_run(archivio.ricette.find_one({"id": "r1"}, {"_id": 0}))))
    assert s["codice_prodotto"] is None and s["qr"]["scheda"] is None and s["qr"]["motivo"] == "Menu non raggiungibile"
