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

from fastapi import HTTPException

from app.lotti.servizi import menu_backfill, menu_bridge
from tests.lotti.test_menu_bridge import _FakeSupabase, _Query, _payload


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
    assert _riga_menu(finto)["description_it"] == "Preparato con Farina, Latte, Uova, Rum."
    assert _riga_menu(finto)["description"] == _riga_menu(finto)["description_it"]

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
        _ruolo={"ruolo": "amministratore"}))
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


def test_i_vecchi_campi_categoria_non_creano_una_seconda_classificazione(ambiente):
    ricette, _, finto = ambiente
    creata_cat = run(menu_bridge.crea_categoria_menu("Colazioni"))
    categoria_id = creata_cat["categoria"]["id"]
    sotto = run(menu_bridge.crea_sottocategoria_menu(categoria_id, "Sfogliate"))
    sottocategoria_id = sotto["sottocategoria"]["id"]

    run(ricette.create_ricetta(ricette.RicettaCreate(**_payload(
        nome="Sfogliatella riccia", menu_category_id=categoria_id,
        menu_subcategory_id=sottocategoria_id))))

    riga = _riga_menu(finto)
    produzione = [c for c in finto.tabelle["menu_categories"] if c["name_it"] == "Produzione Ceraldi"][0]
    assert riga["category_id"] == produzione["id"]
    assert riga["subcategory_id"] != sottocategoria_id


def test_categoria_automatica_usa_il_reparto(ambiente):
    ricette, _, finto = ambiente
    categoria_id = run(menu_bridge.crea_categoria_menu("Colazioni"))["categoria"]["id"]
    creata = run(ricette.create_ricetta(ricette.RicettaCreate(**_payload(
        nome="Cornetto", reparto="bar", menu_category_id=categoria_id))))

    assert creata["menu_sync"]["categoria_origine"] == "automatica"
    sottocategorie = finto.tabelle["menu_subcategories"]
    assert [s["name_it"] for s in sottocategorie] == ["Bar"]
    produzione = [c for c in finto.tabelle["menu_categories"] if c["name_it"] == "Produzione Ceraldi"][0]
    assert sottocategorie[-1]["category_id"] == produzione["id"]
    assert _riga_menu(finto)["category_id"] == produzione["id"]


def _destinazione(ricette, ricetta_id, **campi):
    return run(ricette.set_destinazione_menu(
        ricetta_id, ricette.DestinazioneMenu(**campi), _admin=None))


def test_la_categoria_scelta_dal_titolare_decide_dove_compare_la_ricetta(ambiente):
    ricette, _, finto = ambiente
    categoria_id = run(menu_bridge.crea_categoria_menu("Colazioni"))["categoria"]["id"]
    sotto_id = run(menu_bridge.crea_sottocategoria_menu(categoria_id, "Sfogliate"))["sottocategoria"]["id"]
    creata = run(ricette.create_ricetta(ricette.RicettaCreate(**_payload(nome="Sfogliatella riccia"))))

    esito = _destinazione(ricette, creata["id"], categoria_id=categoria_id, sottocategoria_id=sotto_id)

    assert esito["menu_sync"]["categoria_origine"] == "scelta"
    riga = [p for p in finto.tabelle["menu_products"] if p.get("lotti_ref") == f"ricetta:{creata['id']}"][0]
    assert riga["category_id"] == categoria_id and riga["subcategory_id"] == sotto_id

    # Togliere la scelta riporta la ricetta alla destinazione del reparto
    esito = _destinazione(ricette, creata["id"], categoria_id=0, sottocategoria_id=0)
    assert esito["menu_sync"]["categoria_origine"] == "automatica"


def test_una_categoria_gia_nel_menu_si_puo_scegliere(ambiente):
    ricette, _, finto = ambiente
    finto.tabelle["menu_categories"] = [{"id": 7, "name": "Bar", "name_it": "Bar", "image": None, "origine": None}]
    finto.tabelle["menu_subcategories"] = [
        {"id": 70, "category_id": 7, "name": "Caffe", "name_it": "Caffe", "image": None, "origine": None}]
    creata = run(ricette.create_ricetta(ricette.RicettaCreate(**_payload(nome="Caffe speciale"))))

    esito = _destinazione(ricette, creata["id"], categoria_id=7, sottocategoria_id=70)

    assert esito["menu_sync"]["categoria_origine"] == "scelta"
    riga = [p for p in finto.tabelle["menu_products"] if p.get("lotti_ref") == f"ricetta:{creata['id']}"][0]
    assert (riga["category_id"], riga["subcategory_id"]) == (7, 70)


def test_scelta_incoerente_e_rifiutata(ambiente):
    ricette, _, finto = ambiente
    finto.tabelle["menu_categories"] = [
        {"id": 7, "name": "Bar", "name_it": "Bar", "origine": None},
        {"id": 8, "name": "Food", "name_it": "Food", "origine": None}]
    finto.tabelle["menu_subcategories"] = [
        {"id": 70, "category_id": 7, "name": "Caffe", "name_it": "Caffe", "origine": None}]
    creata = run(ricette.create_ricetta(ricette.RicettaCreate(**_payload(nome="Caffe speciale"))))

    for campi in ({"categoria_id": 8, "sottocategoria_id": 70},   # sottocategoria di un'altra categoria
                  {"categoria_id": 99, "sottocategoria_id": 70},  # categoria inesistente
                  {"categoria_id": 7},                           # una sola delle due
                  {"prodotto_id": 4242}):                        # prodotto inesistente
        with pytest.raises(HTTPException) as errore:
            _destinazione(ricette, creata["id"], **campi)
        assert errore.value.status_code == 400


def test_la_ricetta_si_unisce_a_un_prodotto_gia_nel_menu_senza_doppioni(ambiente):
    ricette, _, finto = ambiente
    finto.tabelle["menu_categories"] = [{"id": 1, "name": "Bar", "name_it": "Bar", "origine": None}]
    finto.tabelle["menu_subcategories"] = [
        {"id": 10, "category_id": 1, "name": "Dolci", "name_it": "Dolci", "origine": None}]
    finto.tabelle["menu_products"] = [
        {"id": 152788, "category_id": 1, "subcategory_id": 10, "name": "Sfogliatella", "name_it": "Sfogliatella",
         "price": "2.00€", "origine": None, "codice_prodotto": "PRD-000007"}]
    creata = run(ricette.create_ricetta(ricette.RicettaCreate(**_payload(nome="Sfogliatella riccia"))))
    assert len(finto.tabelle["menu_products"]) == 2  # la pubblicazione automatica ha creato la sua riga
    run(menu_bridge.rimuovi_prodotto_dal_menu(f"ricetta:{creata['id']}"))
    assert len(finto.tabelle["menu_products"]) == 1

    elenco = run(menu_bridge.prodotti_agganciabili(creata["id"], "sfoglia"))
    assert [p["id"] for p in elenco] == [152788] and elenco[0]["codice"] == "PRD-000007"

    esito = _destinazione(ricette, creata["id"], prodotto_id=152788)

    prodotti = finto.tabelle["menu_products"]
    assert len(prodotti) == 1, "nessun doppione: la ricetta prende il posto del prodotto"
    assert prodotti[0]["id"] == 152788 and prodotti[0]["lotti_ref"] == f"ricetta:{creata['id']}"
    assert prodotti[0]["origine"] == "lotti" and prodotti[0]["codice_prodotto"] == "PRD-000007"
    assert esito["menu_sync"]["menu_product_id"] == 152788
    # un prodotto gia' unito non e' piu' agganciabile da un'altra ricetta
    assert run(menu_bridge.prodotti_agganciabili("altra", "sfoglia")) == []
    altra = run(ricette.create_ricetta(ricette.RicettaCreate(**_payload(nome="Altra ricetta"))))
    with pytest.raises(HTTPException) as errore:
        _destinazione(ricette, altra["id"], prodotto_id=152788)
    assert errore.value.status_code in (400, 409)


def test_creazione_categoria_idempotente_e_sottocategoria_su_categoria_esistente(ambiente):
    _, _, finto = ambiente
    prima = run(menu_bridge.crea_categoria_menu("Colazioni"))
    seconda = run(menu_bridge.crea_categoria_menu("Colazioni"))
    assert prima["creata"] is True and seconda["creata"] is False
    assert prima["categoria"]["id"] == seconda["categoria"]["id"]
    assert len(finto.tabelle["menu_categories"]) == 1

    finto.tabelle["menu_categories"].append(
        {"id": 7, "name": "Bar", "name_it": "Bar", "image": None, "origine": None})
    assert run(menu_bridge.crea_sottocategoria_menu(7, "Caffetteria"))["creata"] is True
    with pytest.raises(menu_bridge.CategoriaMenuNonValida):
        run(menu_bridge.crea_sottocategoria_menu(999, "Inesistente"))


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


def test_pubblica_tutte_spunta_archivio_senza_doppioni_e_con_foto(ambiente):
    _, database, finto = ambiente
    _semina(database, 2, menu_pubblico=False, foto_url="https://foto.test/prodotto.jpg")
    anteprima = run(menu_backfill.ripubblica_menu(database, dry_run=True, pubblica_tutte=True))
    assert anteprima["visibili"] == 2 and anteprima["nascoste"] == 0
    assert run(database.ricette.count_documents({"menu_pubblico": False})) == 2
    assert finto.tabelle.get("menu_products", []) == []
    esito = run(menu_backfill.ripubblica_menu(database, pubblica_tutte=True))
    assert esito["pubblicate"] == 2 and esito["errori"] == 0
    assert run(database.ricette.count_documents({"menu_pubblico": True})) == 2
    assert all(p["visible"] and p["image"] == "https://foto.test/prodotto.jpg"
               for p in finto.tabelle["menu_products"])
    stato = run(menu_backfill.stato_ripubblicazione_menu(database))
    assert len(stato["visibilita_precedente"]) == 2
    secondo = run(menu_backfill.ripubblica_menu(database, pubblica_tutte=True))
    assert secondo["pubblicate"] == 0 and secondo["aggiornate"] == 2


def test_backfill_conserva_riferimento_foto_storage(ambiente, monkeypatch):
    _, database, finto = ambiente
    from app.lotti.servizi import supabase_foto_ricette
    monkeypatch.setattr(supabase_foto_ricette, "url_pubblico", lambda p: f"https://foto.test/{p}")
    _semina(database, 1, foto_storage_path="lotti/ricette/foto.jpg")
    run(menu_backfill.ripubblica_menu(database))
    assert _riga_menu(finto)["image"] == "https://foto.test/lotti/ricette/foto.jpg"


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

    with pytest.raises(HTTPException) as errore:
        run(ricette.aggiorna_reparto(creata["id"], "gelateria"))
    assert errore.value.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# 6) Una ricetta senza prezzo non diventa MAI visibile nel Menu
# ─────────────────────────────────────────────────────────────────────────────

def test_ricetta_senza_prezzo_visibile_nella_carta_senza_prezzo_inventato(ambiente):
    """Una riga con `price` vuoto entrerebbe nell'ordine contando 0 euro
    (`app/menu/models/order_models.py::compute_total` scarta il valore e
    continua): un prodotto ordinabile gratis. Si pubblica nascosta, e il
    motivo esce nell'esito del ponte."""
    ricette, _, finto = ambiente
    creata = run(ricette.create_ricetta(ricette.RicettaCreate(**_payload(
        nome="Senza prezzo", prezzo_vendita=None, menu_pubblico=True))))

    sync = creata["menu_sync"]
    assert sync["prezzo_mancante"] is True
    assert sync["visibile_richiesta"] is True
    assert sync["visible"] is True
    assert sync["motivo_nascosto"] is None
    riga = _riga_menu(finto)
    assert riga["price"] == "" and riga["visible"] is True
    # Pubblicata comunque: resta idempotente e recuperabile
    assert riga["lotti_ref"] == f"ricetta:{creata['id']}"


def test_appena_arriva_un_prezzo_la_ricetta_diventa_visibile(ambiente):
    ricette, _, finto = ambiente
    creata = run(ricette.create_ricetta(ricette.RicettaCreate(**_payload(
        nome="Senza prezzo", prezzo_vendita=None, menu_pubblico=True))))
    assert _riga_menu(finto)["visible"] is True

    esito = run(ricette.set_prezzo_tavolo(creata["id"], 2.50))
    assert esito["menu_sync"]["prezzo_mancante"] is False
    assert esito["menu_sync"]["motivo_nascosto"] is None
    riga = _riga_menu(finto)
    assert riga["price"] == "2.50€" and riga["visible"] is True
    # Nessuna riga in piu': e' sempre la stessa, aggiornata
    assert len(finto.tabelle["menu_products"]) == 1


def test_senza_prezzo_ma_gia_nascosta_nessun_motivo_da_segnalare(ambiente):
    """Chi non ha spuntato «inserisci in menu» resta nascosto per sua scelta:
    non e' il prezzo a nasconderla e il cruscotto non deve segnalarla."""
    ricette, _, _ = ambiente
    creata = run(ricette.create_ricetta(ricette.RicettaCreate(**_payload(
        nome="Bozza", prezzo_vendita=None, menu_pubblico=False))))
    assert creata["menu_sync"]["prezzo_mancante"] is True
    assert creata["menu_sync"]["motivo_nascosto"] is None


def test_backfill_conta_e_campiona_le_ricette_senza_prezzo(ambiente):
    _, database, finto = ambiente
    run(database.ricette.insert_one({
        "id": "con-prezzo", "nome": "Con prezzo", "reparto": "bar",
        "prezzo_vendita": 1.2, "menu_pubblico": True}))
    run(database.ricette.insert_one({
        "id": "seminata", "nome": "Seminata da _seed_lotto_nomi",
        "reparto": "pasticceria", "menu_pubblico": True}))
    run(database.ricette.insert_one({
        "id": "import-excel", "nome": "Import Excel", "reparto": "pasticceria"}))

    esito = run(menu_backfill.ripubblica_menu(database))
    assert esito["senza_prezzo"] == 2
    assert {c["nome"] for c in esito["campioni_senza_prezzo"]} == {
        "Seminata da _seed_lotto_nomi", "Import Excel"}
    assert esito["nascoste_per_prezzo"] == 0
    assert esito["campioni_nascoste_per_prezzo"] == []

    visibili = {p["name_it"]: p["visible"] for p in finto.tabelle["menu_products"]}
    assert visibili == {"Con prezzo": True, "Seminata da _seed_lotto_nomi": True,
                        "Import Excel": True}


# ─────────────────────────────────────────────────────────────────────────────
# 7) Prezzo al tavolo: validato all'ingresso, coerente col cruscotto
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("prezzo", [-2, -0.01, float("nan"), float("inf"), float("-inf")])
def test_prezzo_tavolo_negativo_o_non_finito_rifiutato(ambiente, prezzo):
    """`nan` finiva nella colonna `price` come "nan€" sotto gli occhi dei
    clienti (`nan <= 0` e' False, nessun filtro lo fermava)."""
    ricette, _, finto = ambiente
    creata = run(ricette.create_ricetta(ricette.RicettaCreate(
        **_payload(prezzo_vendita=1.50))))

    with pytest.raises(HTTPException) as errore:
        run(ricette.set_prezzo_tavolo(creata["id"], prezzo))
    assert errore.value.status_code == 400
    assert _riga_menu(finto)["price"] == "1.50€"


@pytest.mark.parametrize("prezzo", [-2, float("nan"), float("inf")])
def test_prezzo_vendita_ha_la_stessa_validazione(ambiente, prezzo):
    ricette, database, _ = ambiente
    creata = run(ricette.create_ricetta(ricette.RicettaCreate(
        **_payload(prezzo_vendita=1.50))))
    with pytest.raises(HTTPException) as errore:
        run(ricette.set_prezzo_vendita(creata["id"], prezzo))
    assert errore.value.status_code == 400
    assert run(database.ricette.find_one({"id": creata["id"]}))["prezzo_vendita"] == 1.50


def test_prezzo_zero_toglie_il_prezzo_tavolo_e_il_menu_torna_al_banco(ambiente):
    ricette, database, finto = ambiente
    creata = run(ricette.create_ricetta(ricette.RicettaCreate(
        **_payload(prezzo_vendita=1.50, prezzo_tavolo=2.50))))
    assert _riga_menu(finto)["price"] == "2.50€"

    esito = run(ricette.set_prezzo_tavolo(creata["id"], 0))
    assert esito["prezzo_tavolo"] is None and esito["prezzo_rimosso"] is True
    assert run(database.ricette.find_one({"id": creata["id"]}))["prezzo_tavolo"] is None
    assert _riga_menu(finto)["price"] == "1.50€"
    assert esito["menu_sync"]["prezzo_origine"] == "banco"


def test_prezzo_tavolo_non_valido_in_archivio_non_risulta_deciso(ambiente):
    """Con `prezzo_tavolo = -2` il ponte ripiegava sul banco ma il cruscotto
    diceva «prezzo deciso»: il titolare leggeva una cosa e il cliente ne vedeva
    un'altra. Ora le due nozioni di «prezzo valido» sono la stessa."""
    ricette, database, finto = ambiente
    run(database.ricette.insert_one({
        "id": "storica", "nome": "Storica", "reparto": "bar",
        "prezzo_vendita": 1.50, "prezzo_tavolo": -2}))

    righe = {r["nome"]: r for r in run(ricette.get_ricette_prezzi())}
    assert righe["Storica"]["prezzo_tavolo_impostato"] is False

    run(menu_backfill.ripubblica_menu(database))
    assert _riga_menu(finto)["price"] == "1.50€"


def test_prezzo_non_valido_rifiutato_anche_da_patch_e_dal_modello(ambiente):
    ricette, database, _ = ambiente
    creata = run(ricette.create_ricetta(ricette.RicettaCreate(
        **_payload(prezzo_vendita=1.50))))

    with pytest.raises(HTTPException) as errore:
        run(ricette.aggiorna_campo_ricetta(creata["id"], {"prezzo_tavolo": -3}))
    assert errore.value.status_code == 400

    # 0 dalla PATCH significa «togli il prezzo», non «gratis»
    run(ricette.aggiorna_campo_ricetta(creata["id"], {"prezzo_tavolo": 0}))
    assert run(database.ricette.find_one({"id": creata["id"]}))["prezzo_tavolo"] is None

    with pytest.raises(Exception):
        ricette.RicettaCreate(**_payload(prezzo_tavolo=-1))
    with pytest.raises(Exception):
        ricette.RicettaCreate(**_payload(prezzo_vendita=float("nan")))


# ─────────────────────────────────────────────────────────────────────────────
# 8) Assegnazione id: la decide il database (CLAUDE.md §5); il ripiego
#    max(id)+1 vale solo finche' la migrazione menu_id_dal_database non c'e'
# ─────────────────────────────────────────────────────────────────────────────

def test_id_dal_database_nessuna_lettura_del_massimo_nessun_id_calcolato(ambiente):
    """Con l'identity il ponte inserisce senza id e usa quello restituito: non
    legge mai max(id), non lo calcola, non ritenta. Vale per prodotto,
    categoria e sottocategoria."""
    ricette, _, finto = ambiente
    creata = run(ricette.create_ricetta(ricette.RicettaCreate(**_payload(nome="Babà"))))
    cat = run(menu_bridge.crea_categoria_menu("Colazioni"))["categoria"]
    sotto = run(menu_bridge.crea_sottocategoria_menu(cat["id"], "Sfogliate"))["sottocategoria"]

    assert creata["menu_sync"]["esito"] == "pubblicato"
    assert finto.letture_massimo == []
    generati = set(finto.id_assegnati)
    assert ("menu_products", creata["menu_sync"]["menu_product_id"]) in generati
    assert ("menu_categories", cat["id"]) in generati
    assert ("menu_subcategories", sotto["id"]) in generati
    # id del database, non la base alta dell'app
    assert creata["menu_sync"]["menu_product_id"] < menu_bridge.ID_MINIMO_LOTTI


def test_senza_identity_il_ponte_ripiega_su_max_id_e_lo_dice(ambiente, monkeypatch, caplog):
    """Migrazione non ancora applicata: l'insert senza id e' rifiutato senza
    scrivere nulla, il ponte ripiega sul vecchio percorso con base alta e la
    ricetta arriva nel Menu una volta sola. Il ripiego resta visibile nel log."""
    ricette, _, _ = ambiente
    finto = _FakeSupabase(identity=False)
    monkeypatch.setattr(menu_bridge, "supabase", finto)

    with caplog.at_level("WARNING", logger="uvicorn.error"):
        creata = run(ricette.create_ricetta(ricette.RicettaCreate(**_payload(nome="Babà"))))

    assert creata["menu_sync"]["esito"] == "pubblicato"
    prodotti = finto.tabelle["menu_products"]
    assert len(prodotti) == 1 and prodotti[0]["id"] >= menu_bridge.ID_MINIMO_LOTTI
    assert finto.id_assegnati == []
    assert "menu_products" in finto.letture_massimo
    assert any("menu_id_dal_database" in r.getMessage() for r in caplog.records)


def test_insert_riuscito_senza_id_in_risposta_non_viene_ripetuto():
    """Se la riga e' stata scritta ma la risposta non porta l'id, reinserire
    creerebbe un doppione: l'errore risale e il ripiego NON parte."""
    from app.menu.supabase_client import inserisci_con_id_del_database

    class _Muto:
        inserimenti = 0

        def table(self, _nome):
            return self

        def insert(self, riga):
            assert "id" not in riga
            return self

        def execute(self):
            _Muto.inserimenti += 1
            return type("R", (), {"data": [{"name": "x"}]})()

    with pytest.raises(RuntimeError, match="non ha restituito l'id"):
        inserisci_con_id_del_database(_Muto(), "menu_products", {"id": 5, "name": "x"})
    assert _Muto.inserimenti == 1


def test_un_errore_diverso_dal_default_mancante_non_attiva_il_ripiego(ambiente, monkeypatch):
    """Il ripiego scatta solo per la NOT NULL su ``id`` (23502): un'altra NOT
    NULL, o la collisione su ``lotti_ref``, risale come errore del ponte senza
    letture di max(id)."""
    from app.menu.supabase_client import _e_id_senza_default

    assert _e_id_senza_default(RuntimeError('null value in column "id" of relation "menu_products" violates not-null constraint')) is True
    assert _e_id_senza_default(RuntimeError('null value in column "name" of relation "menu_products" violates not-null constraint')) is False
    assert _e_id_senza_default(RuntimeError('duplicate key value violates unique constraint "menu_products_lotti_ref_uidx"')) is False
    assert _e_id_senza_default(RuntimeError("connessione persa")) is False

    ricette, _, finto = ambiente

    class _NomeNullo(_Query):
        def execute(self):
            if self.op == "insert" and self.nome == "menu_products":
                raise RuntimeError('null value in column "name" of relation "menu_products" violates not-null constraint (code 23502)')
            return super().execute()

    finto.table = lambda nome: _NomeNullo(finto.tabelle, nome, finto)
    creata = run(ricette.create_ricetta(ricette.RicettaCreate(**_payload(nome="Babà"))))
    assert creata["menu_sync"]["esito"] == "errore"
    assert finto.letture_massimo == []
    assert finto.tabelle["menu_products"] == []


class _QueryInCorsa(_Query):
    """Come il finto normale (senza identity: e' il ripiego), ma con la primary
    key applicata davvero e con un «altro thread» che si prende l'id appena
    letto da ``max(id)``."""

    def __init__(self, finto, nome):
        super().__init__(finto.tabelle, nome, finto)
        self.finto = finto

    def execute(self):
        finto = self.finto
        contesa = self.nome == finto.tabella_contesa
        if (self.op == "select" and contesa and self._order == ("id", True)
                and finto.intrusioni < finto.max_intrusioni):
            risultato = super().execute()
            massimo = int(risultato.data[0]["id"]) if risultato.data else 0
            preso = max(massimo + 1, menu_bridge.ID_MINIMO_LOTTI)
            # L'altro thread inserisce PRIMA di noi con lo stesso id
            self.tabelle.setdefault(self.nome, []).append(
                {"id": preso, "name_it": "riga di un altro thread"})
            finto.intrusioni += 1
            return risultato
        if self.op == "insert":
            righe = self.tabelle.setdefault(self.nome, [])
            nuove = self.payload if isinstance(self.payload, list) else [self.payload]
            if any(any(e.get("id") == n.get("id") for e in righe) for n in nuove):
                finto.collisioni += 1
                raise RuntimeError(
                    "duplicate key value violates unique constraint "
                    f'"{self.nome}_pkey" (code 23505)')
        return super().execute()


class _SupabaseInCorsa(_FakeSupabase):
    def __init__(self, tabella_contesa, max_intrusioni=1):
        super().__init__(identity=False)
        self.tabella_contesa = tabella_contesa
        self.max_intrusioni = max_intrusioni
        self.intrusioni = 0
        self.collisioni = 0

    def table(self, nome):
        return _QueryInCorsa(self, nome)


def test_collisione_di_id_ritentata_e_la_ricetta_arriva_nel_menu(ambiente, monkeypatch):
    """Solo nel ripiego (identity assente). Il backfill cicla per minuti mentre
    il form continua a salvare: le due `select max(id)` tornavano lo stesso
    valore e la seconda insert violava la primary key, con la ricetta appena
    salvata persa nel Menu."""
    ricette, _, _ = ambiente
    finto = _SupabaseInCorsa("menu_products", max_intrusioni=1)
    monkeypatch.setattr(menu_bridge, "supabase", finto)

    creata = run(ricette.create_ricetta(ricette.RicettaCreate(**_payload(nome="Babà"))))
    assert creata["menu_sync"]["esito"] == "pubblicato"
    assert finto.collisioni == 1

    nostre = [p for p in finto.tabelle["menu_products"] if p.get("lotti_ref")]
    assert len(nostre) == 1
    identificativi = [p["id"] for p in finto.tabelle["menu_products"]]
    assert len(identificativi) == len(set(identificativi)) == 2


def test_collisione_persistente_resta_un_errore_visibile(ambiente, monkeypatch):
    """Ripiego: il ciclo e' limitato, non gira all'infinito e il fallimento non sparisce."""
    ricette, database, _ = ambiente
    finto = _SupabaseInCorsa("menu_products", max_intrusioni=99)
    monkeypatch.setattr(menu_bridge, "supabase", finto)

    creata = run(ricette.create_ricetta(ricette.RicettaCreate(**_payload())))
    assert creata["menu_sync"]["esito"] == "errore"
    assert finto.collisioni == menu_bridge.TENTATIVI_ID

    esito = run(menu_backfill.ripubblica_menu(database))
    assert esito["errori"] == 1
    assert esito["campioni_errori"][0]["esito"] == "errore"


def test_la_collisione_su_lotti_ref_non_viene_ritentata():
    """L'unico altro indice unico di `menu_products`: li' ritentare non serve,
    l'errore deve uscire subito."""
    pkey = RuntimeError('duplicate key value violates unique constraint "menu_products_pkey"')
    ref = RuntimeError('duplicate key value violates unique constraint "menu_products_lotti_ref_uidx"')
    altro = RuntimeError("connessione persa")
    assert menu_bridge._e_collisione_di_id(pkey) is True
    assert menu_bridge._e_collisione_di_id(ref) is False
    assert menu_bridge._e_collisione_di_id(altro) is False


# ─────────────────────────────────────────────────────────────────────────────
# 9) Backfill: troncamento dichiarato, task non raccolto dal garbage collector
# ─────────────────────────────────────────────────────────────────────────────

def test_backfill_dichiara_il_troncamento(ambiente, monkeypatch):
    """Oltre il tetto il giro e' parziale: «completato» mentirebbe."""
    _, database, _ = ambiente
    monkeypatch.setattr(menu_backfill, "LIMITE_RICETTE", 2)
    _semina(database, 5)

    esito = run(menu_backfill.ripubblica_menu(database, dry_run=True))
    assert esito["troncato"] is True
    assert esito["ricette_totali"] == 2
    assert esito["limite_ricette"] == 2
    assert esito["ricette_ignorate"] == 3

    async def giro():
        await menu_backfill._ripubblica_in_background(database)
        return await menu_backfill.stato_ripubblicazione_menu(database)

    stato = run(giro())
    assert stato["stato"] == "completato_parziale"
    assert stato["risultato"]["troncato"] is True


def test_backfill_sotto_il_tetto_non_e_troncato(ambiente):
    _, database, _ = ambiente
    _semina(database, 2)
    esito = run(menu_backfill.ripubblica_menu(database, dry_run=True))
    assert esito["troncato"] is False and esito["ricette_ignorate"] == 0


def test_il_task_del_backfill_resta_referenziato(ambiente):
    """Senza riferimento il garbage collector puo' raccoglierlo a meta' giro:
    il `finally` che azzera `_in_corso` non gira e ogni avvio successivo
    risponde «Ripubblicazione gia' in corso» fino al riavvio del processo."""
    _, database, _ = ambiente
    _semina(database, 1)
    menu_backfill._task_in_corso = None

    async def giro():
        assert menu_backfill.avvia_ripubblicazione_in_background(database) is True
        task = menu_backfill._task_in_corso
        assert task is not None and not task.done()
        # Un secondo avvio non parte finche' il primo e' in volo
        assert menu_backfill.avvia_ripubblicazione_in_background(database) is False
        await task
        return task

    task = run(giro())
    assert menu_backfill._task_in_corso is task
    assert menu_backfill.ripubblicazione_in_corso() is False


# ─────────────────────────────────────────────────────────────────────────────
# 10) Categoria omonima di una gia' presente: avviso, non blocco
# ─────────────────────────────────────────────────────────────────────────────

def test_categoria_omonima_di_una_gia_presente_crea_ma_avvisa(ambiente):
    _, _, finto = ambiente
    finto.tabelle["menu_categories"] = [
        {"id": 7, "name": "Bar", "name_it": "Bar", "image": None, "origine": None}]

    creata = run(menu_bridge.crea_categoria_menu("Bar"))
    assert creata["creata"] is True
    assert creata["avviso"] and "Bar" in creata["avviso"] and "7" in creata["avviso"]
    # Non si blocca: il titolare potrebbe volerne davvero una sua
    assert len(finto.tabelle["menu_categories"]) == 2

    # L'avviso resta anche alla seconda chiamata (idempotente)
    ripetuta = run(menu_bridge.crea_categoria_menu("Bar"))
    assert ripetuta["creata"] is False and ripetuta["avviso"]
    assert len(finto.tabelle["menu_categories"]) == 2


def test_senza_omonimia_nessun_avviso(ambiente):
    _, _, _ = ambiente
    creata = run(menu_bridge.crea_categoria_menu("Colazioni"))
    assert creata["creata"] is True and creata["avviso"] is None
