"""Lotti spinge nel Menu: descrizione, prezzo al tavolo, categoria, backfill.

Richiesta del titolare (19/09/2026): «il sistema deve prendere la ricetta della
sfogliatella e inserirla in menu dopo aver spuntato "inserisci in menu", quindi
visualizzo immagine, breve descrizione, prezzo tavolo, allergeni se presenti
evidenziati, e la categoria dove inserirla, che recuperi da Menu o si creano in
Lotti».

Il client Supabase finto (tabelle + Storage in memoria) e i payload di ricetta
sono quelli gia' usati dai test del ponte in ``app/lotti/tests/test_menu_bridge.py``:
qui si importano invece di riscriverli, cosi' il finto resta uno solo.
"""
import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.lotti.servizi import menu_backfill, menu_bridge
from app.lotti.tests.test_menu_bridge import _FakeSupabase, _payload


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def ambiente(monkeypatch):
    import app.lotti.routers.ricette as ricette

    monkeypatch.setenv("MENU_SUPABASE_URL", "https://menu.test.supabase.co")
    finto = _FakeSupabase()
    monkeypatch.setattr(menu_bridge, "supabase", finto)
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(ricette, "db", database)
    return ricette, database, finto


def _riga_menu(finto, indice=0):
    return finto.tabelle["menu_products"][indice]


# ─────────────────────────────────────────────────────────────────────────────
# 1) Descrizione breve: prima campo fantasma, ora campo vero della ricetta
# ─────────────────────────────────────────────────────────────────────────────

def test_descrizione_breve_e_un_campo_dichiarato_della_ricetta(ambiente):
    """Prima: ``menu_bridge._descrizione`` leggeva ``descrizione``, che non
    esisteva ne' nel modello ne' nella whitelist della PATCH — nessuna pagina
    poteva valorizzarlo e tutte le righe del Menu avevano descrizione vuota."""
    ricette, _, _ = ambiente
    assert "descrizione" in ricette.RicettaCreate.model_fields
    assert "descrizione" in ricette.Ricetta.model_fields
    # Resta distinta dal procedimento interno
    assert "note" in ricette.RicettaCreate.model_fields


def test_descrizione_arriva_nel_menu_e_le_note_no(ambiente):
    ricette, _, finto = ambiente
    senza = run(ricette.create_ricetta(ricette.RicettaCreate(
        **_payload(nome="Sfogliatella", descrizione=None, note="Sfogliare a 2 mm, forno 210°"))))
    assert _riga_menu(finto)["description_it"] is None
    assert _riga_menu(finto)["description"] is None

    run(ricette.aggiorna_campo_ricetta(
        senza["id"], {"descrizione": "Riccia, ricotta e canditi, calda al mattino"}))
    riga = _riga_menu(finto)
    assert riga["description_it"] == "Riccia, ricotta e canditi, calda al mattino"
    assert riga["description"] == riga["description_it"]
    # Il procedimento non esce mai verso i clienti
    assert "forno 210" not in (riga["description_it"] or "")


def test_put_senza_descrizione_non_cancella_quella_salvata(ambiente):
    ricette, database, finto = ambiente
    creata = run(ricette.create_ricetta(ricette.RicettaCreate(
        **_payload(descrizione="Babà bagnato al rum"))))
    run(ricette.update_ricetta(
        creata["id"], ricette.RicettaCreate(**_payload(descrizione=None)),
        _admin={"nome": "Admin"}))
    assert _riga_menu(finto)["description_it"] == "Babà bagnato al rum"
    assert run(database.ricette.find_one({"id": creata["id"]}))["descrizione"] == "Babà bagnato al rum"


# ─────────────────────────────────────────────────────────────────────────────
# 2) Due prezzi: il Menu mostra quello al tavolo
# ─────────────────────────────────────────────────────────────────────────────

def test_il_menu_riceve_il_prezzo_al_tavolo_non_quello_al_banco(ambiente):
    ricette, _, finto = ambiente
    run(ricette.create_ricetta(ricette.RicettaCreate(
        **_payload(prezzo_vendita=1.50, prezzo_tavolo=2.50))))
    assert _riga_menu(finto)["price"] == "2.50€"


def test_senza_prezzo_tavolo_il_menu_non_perde_il_prezzo(ambiente):
    """Le centinaia di ricette gia' in archivio non hanno un prezzo al tavolo:
    il Menu continua a esporre quello al banco, che e' il prezzo che stanno
    gia' mostrando. Il ripiego resta dichiarato in ``prezzo_origine``."""
    ricette, _, finto = ambiente
    creata = run(ricette.create_ricetta(ricette.RicettaCreate(
        **_payload(prezzo_vendita=1.50, prezzo_tavolo=None))))
    assert _riga_menu(finto)["price"] == "1.50€"
    assert creata["menu_sync"]["prezzo_origine"] == "banco"

    esito = run(ricette.set_prezzo_tavolo(creata["id"], 2.80))
    assert esito["prezzo_tavolo"] == 2.80
    assert esito["menu_sync"]["prezzo_origine"] == "tavolo"
    assert _riga_menu(finto)["price"] == "2.80€"


def test_prezzo_vendita_resta_il_prezzo_al_banco_del_food_cost(ambiente):
    """Il food cost non deve accorgersi di nulla: ``prezzo_vendita`` non
    cambia nome ne' significato, e il prezzo al tavolo non lo tocca."""
    ricette, database, _ = ambiente
    creata = run(ricette.create_ricetta(ricette.RicettaCreate(
        **_payload(prezzo_vendita=1.50, prezzo_tavolo=2.50))))
    salvata = run(database.ricette.find_one({"id": creata["id"]}))
    assert salvata["prezzo_vendita"] == 1.50
    assert salvata["prezzo_tavolo"] == 2.50

    run(ricette.set_prezzo_vendita(creata["id"], 1.80))
    salvata = run(database.ricette.find_one({"id": creata["id"]}))
    assert salvata["prezzo_vendita"] == 1.80
    assert salvata["prezzo_tavolo"] == 2.50


def test_prezzi_e_margini_mostra_chi_non_ha_deciso_il_prezzo_tavolo(ambiente):
    """Il ripiego sul prezzo al banco non deve restare invisibile."""
    ricette, _, _ = ambiente
    run(ricette.create_ricetta(ricette.RicettaCreate(
        **_payload(nome="Con tavolo", prezzo_vendita=1.5, prezzo_tavolo=2.5))))
    run(ricette.create_ricetta(ricette.RicettaCreate(
        **_payload(nome="Senza tavolo", prezzo_vendita=1.5))))

    righe = {r["nome"]: r for r in run(ricette.get_ricette_prezzi())}
    assert righe["Con tavolo"]["prezzo_tavolo"] == 2.5
    assert righe["Con tavolo"]["prezzo_tavolo_impostato"] is True
    assert righe["Senza tavolo"]["prezzo_tavolo"] is None
    assert righe["Senza tavolo"]["prezzo_tavolo_impostato"] is False


# ─────────────────────────────────────────────────────────────────────────────
# 3) Categoria scelta da Lotti
# ─────────────────────────────────────────────────────────────────────────────

def test_senza_scelta_resta_il_comportamento_di_oggi(ambiente):
    ricette, _, finto = ambiente
    run(ricette.create_ricetta(ricette.RicettaCreate(**_payload(reparto="rosticceria"))))
    categorie = finto.tabelle["menu_categories"]
    assert [c["name_it"] for c in categorie] == ["Produzione Ceraldi"]
    assert [s["name_it"] for s in finto.tabelle["menu_subcategories"]] == ["Rosticceria"]
    assert _riga_menu(finto)["category_id"] == categorie[0]["id"]


def test_la_categoria_scelta_viene_usata(ambiente):
    ricette, _, finto = ambiente
    creata_cat = run(menu_bridge.crea_categoria_menu("Colazioni"))
    categoria_id = creata_cat["categoria"]["id"]
    sotto = run(menu_bridge.crea_sottocategoria_menu(categoria_id, "Sfogliate"))
    sottocategoria_id = sotto["sottocategoria"]["id"]

    run(ricette.create_ricetta(ricette.RicettaCreate(**_payload(
        nome="Sfogliatella riccia", menu_category_id=categoria_id,
        menu_subcategory_id=sottocategoria_id))))

    riga = _riga_menu(finto)
    assert riga["category_id"] == categoria_id
    assert riga["subcategory_id"] == sottocategoria_id
    # Non e' nata nessuna "Produzione Ceraldi"
    assert [c["name_it"] for c in finto.tabelle["menu_categories"]] == ["Colazioni"]


def test_categoria_scelta_senza_sottocategoria_usa_il_reparto_dentro_quella_categoria(ambiente):
    ricette, _, finto = ambiente
    categoria_id = run(menu_bridge.crea_categoria_menu("Colazioni"))["categoria"]["id"]
    creata = run(ricette.create_ricetta(ricette.RicettaCreate(**_payload(
        nome="Cornetto", reparto="bar", menu_category_id=categoria_id))))

    assert creata["menu_sync"]["categoria_origine"] == "scelta_senza_sottocategoria"
    sottocategorie = finto.tabelle["menu_subcategories"]
    assert [s["name_it"] for s in sottocategorie] == ["Bar"]
    assert sottocategorie[0]["category_id"] == categoria_id
    assert _riga_menu(finto)["category_id"] == categoria_id


def test_categoria_di_qromo_non_e_agganciabile_e_si_ricade_sul_default(ambiente):
    """Una categoria senza ``origine`` viene cancellata e reinserita a ogni
    sync Qromo: appenderci un prodotto di Lotti farebbe fallire quella
    cancellazione per vincolo di chiave esterna."""
    ricette, _, finto = ambiente
    finto.tabelle["menu_categories"] = [
        {"id": 7, "name": "Bar", "name_it": "Bar", "image": None, "origine": None}]

    creata = run(ricette.create_ricetta(ricette.RicettaCreate(
        **_payload(menu_category_id=7))))
    assert creata["menu_sync"]["categoria_origine"] == "scelta_non_valida"
    nomi = [c["name_it"] for c in finto.tabelle["menu_categories"]]
    assert "Produzione Ceraldi" in nomi
    assert _riga_menu(finto)["category_id"] != 7

    # E l'elenco lo dice esplicitamente al frontend
    elenco = run(menu_bridge.elenco_categorie_menu())
    qromo = [c for c in elenco["categorie"] if c["id"] == 7][0]
    assert qromo["selezionabile"] is False and qromo["motivo"]
    lotti = [c for c in elenco["categorie"] if c["name_it"] == "Produzione Ceraldi"][0]
    assert lotti["selezionabile"] is True and lotti["motivo"] is None


def test_creazione_categoria_idempotente_e_sottocategoria_su_qromo_rifiutata(ambiente):
    _, _, finto = ambiente
    prima = run(menu_bridge.crea_categoria_menu("Colazioni"))
    seconda = run(menu_bridge.crea_categoria_menu("Colazioni"))
    assert prima["creata"] is True and seconda["creata"] is False
    assert prima["categoria"]["id"] == seconda["categoria"]["id"]
    assert len(finto.tabelle["menu_categories"]) == 1

    finto.tabelle["menu_categories"].append(
        {"id": 7, "name": "Bar", "name_it": "Bar", "image": None, "origine": None})
    with pytest.raises(menu_bridge.CategoriaMenuNonValida):
        run(menu_bridge.crea_sottocategoria_menu(7, "Caffetteria"))


def test_categoria_creata_da_lotti_sopravvive_alla_sync_qromo(ambiente, monkeypatch):
    """Simulazione della sostituzione integrale fatta da Qromo
    (``app/menu/qromo_sync.py::_sostituisci_tabelle``): cancella solo cio' che
    ha ``origine IS NULL``."""
    from app.menu import qromo_sync as qs

    ricette, _, finto = ambiente
    monkeypatch.setattr(qs, "supabase", finto)

    categoria_id = run(menu_bridge.crea_categoria_menu("Colazioni"))["categoria"]["id"]
    assert finto.tabelle["menu_categories"][0]["origine"] == "lotti"
    creata = run(ricette.create_ricetta(ricette.RicettaCreate(
        **_payload(nome="Sfogliatella riccia", menu_category_id=categoria_id))))

    # Righe di Qromo (senza origine), come le scriverebbe la sincronizzazione
    finto.tabelle["menu_categories"].append(
        {"id": 1, "name": "Bar", "name_it": "Bar", "image": None, "origine": None})
    finto.tabelle["menu_subcategories"].append(
        {"id": 10, "category_id": 1, "name": "Caffetteria", "name_it": "Caffetteria",
         "image": None, "origine": None})
    finto.tabelle["menu_products"].append(
        {"id": 100, "category_id": 1, "subcategory_id": 10, "name": "Espresso",
         "name_it": "Espresso", "price": "1.20€", "origine": None})

    qs._sostituisci_tabelle({
        "categories": [{"id": 1, "name": "Bar", "name_it": "Bar", "image": None}],
        "subcategories": [{"id": 10, "category_id": 1, "name": "Caffetteria",
                           "name_it": "Caffetteria", "image": None}],
        "products": [{"id": 100, "category_id": 1, "subcategory_id": 10,
                      "name": "Espresso", "name_it": "Espresso", "price": "1.20€"}],
    })

    categorie = {c["name_it"]: c for c in finto.tabelle["menu_categories"]}
    assert categorie["Colazioni"]["origine"] == "lotti"
    assert categorie["Colazioni"]["id"] == categoria_id
    nostri = [p for p in finto.tabelle["menu_products"]
              if p.get("lotti_ref") == f"ricetta:{creata['id']}"]
    assert len(nostri) == 1 and nostri[0]["category_id"] == categoria_id
    # La categoria di Qromo e' stata sostituita, non duplicata
    assert sum(1 for c in finto.tabelle["menu_categories"] if c["id"] == 1) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 4) Backfill delle ricette gia' in archivio
# ─────────────────────────────────────────────────────────────────────────────

def _semina(database, quante=3, **extra):
    for i in range(quante):
        run(database.ricette.insert_one({
            "id": f"vecchia-{i}", "nome": f"Ricetta storica {i}",
            "reparto": "pasticceria", "prezzo_vendita": 2.0, **extra,
        }))


def test_backfill_pubblica_le_ricette_mai_arrivate_nel_menu(ambiente):
    ricette, database, finto = ambiente
    _semina(database, 3)
    assert finto.tabelle.get("menu_products", []) == []

    esito = run(menu_backfill.ripubblica_menu(database))
    assert esito["ricette_totali"] == 3
    assert esito["pubblicate"] == 3 and esito["aggiornate"] == 0 and esito["errori"] == 0
    assert len(finto.tabelle["menu_products"]) == 3


def test_backfill_idempotente_nessuna_riga_duplicata(ambiente):
    _, database, finto = ambiente
    _semina(database, 3)
    run(menu_backfill.ripubblica_menu(database))
    secondo = run(menu_backfill.ripubblica_menu(database))

    assert secondo["pubblicate"] == 0 and secondo["aggiornate"] == 3
    assert len(finto.tabelle["menu_products"]) == 3
    riferimenti = [p["lotti_ref"] for p in finto.tabelle["menu_products"]]
    assert len(set(riferimenti)) == 3
    # Nemmeno categorie o sottocategorie si moltiplicano
    assert len(finto.tabelle["menu_categories"]) == 1
    assert len(finto.tabelle["menu_subcategories"]) == 1


def test_backfill_non_rende_visibile_chi_non_e_in_menu_pubblico(ambiente):
    _, database, finto = ambiente
    _semina(database, 2, menu_pubblico=False)
    run(database.ricette.insert_one({
        "id": "scelta", "nome": "Scelta dal titolare", "reparto": "bar",
        "prezzo_vendita": 1.2, "menu_pubblico": True}))

    esito = run(menu_backfill.ripubblica_menu(database))
    assert esito["visibili"] == 1 and esito["nascoste"] == 2
    visibili = {p["name_it"]: p["visible"] for p in finto.tabelle["menu_products"]}
    assert visibili == {"Ricetta storica 0": False, "Ricetta storica 1": False,
                        "Scelta dal titolare": True}


def test_backfill_dry_run_non_scrive_e_conta_i_prezzi_tavolo_mancanti(ambiente):
    _, database, finto = ambiente
    _semina(database, 2)
    run(database.ricette.insert_one({
        "id": "con-tavolo", "nome": "Con tavolo", "prezzo_vendita": 1.0,
        "prezzo_tavolo": 2.0, "menu_pubblico": True}))

    esito = run(menu_backfill.ripubblica_menu(database, dry_run=True))
    assert esito["dry_run"] is True
    assert esito["ricette_totali"] == 3
    assert esito["senza_prezzo_tavolo"] == 2
    assert {c["nome"] for c in esito["campioni_senza_prezzo_tavolo"]} == {
        "Ricetta storica 0", "Ricetta storica 1"}
    assert finto.tabelle.get("menu_products", []) == []


def test_stato_backfill_leggibile_dopo_il_giro(ambiente):
    _, database, _ = ambiente
    _semina(database, 1)

    async def giro():
        await menu_backfill._ripubblica_in_background(database)
        return await menu_backfill.stato_ripubblicazione_menu(database)

    stato = run(giro())
    assert stato["stato"] == "completato"
    assert stato["risultato"]["pubblicate"] == 1
    assert menu_backfill.ripubblicazione_in_corso() is False


# ─────────────────────────────────────────────────────────────────────────────
# 5) I due difetti collegati
# ─────────────────────────────────────────────────────────────────────────────

def test_put_foto_sincronizza_il_menu(ambiente):
    """Prima ``PUT /foto`` scriveva solo in Lotti: la stessa ricetta mostrava
    due immagini diverse nelle due app."""
    ricette, _, finto = ambiente
    creata = run(ricette.create_ricetta(ricette.RicettaCreate(**_payload())))
    assert _riga_menu(finto)["image"] is None

    esito = run(ricette.aggiorna_foto(creata["id"], "https://cdn.test/sfogliatella.jpg"))
    assert esito["success"] is True
    assert esito["menu_sync"]["esito"] == "aggiornato"
    assert _riga_menu(finto)["image"] == "https://cdn.test/sfogliatella.jpg"


def test_put_reparto_accetta_bar(ambiente):
    ricette, _, finto = ambiente
    creata = run(ricette.create_ricetta(ricette.RicettaCreate(**_payload())))

    aggiornata = run(ricette.aggiorna_reparto(creata["id"], "bar"))
    assert aggiornata["reparto"] == "bar"
    assert [s["name_it"] for s in finto.tabelle["menu_subcategories"]] == ["Pasticceria", "Bar"]
    assert _riga_menu(finto)["subcategory_id"] == finto.tabelle["menu_subcategories"][1]["id"]

    for reparto in ("pasticceria", "rosticceria", "altro"):
        assert run(ricette.aggiorna_reparto(creata["id"], reparto))["reparto"] == reparto

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as errore:
        run(ricette.aggiorna_reparto(creata["id"], "gelateria"))
    assert errore.value.status_code == 400
