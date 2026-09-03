from app.lotti.routers.acquaviva import (
    _parse_acquaviva_dettaglio,
    _parse_acquaviva_listing,
    _url_acquaviva_sicuro,
)
from app.lotti.routers.mepa import CATEGORIE_MEPA
from app.lotti.routers.prodotti_master import _CATALOGO_MAX_PRODOTTI, _categoria_merce
from app.lotti.routers.ricette import _categorizza_reparto, _reparto_finale_auto
from bs4 import BeautifulSoup
from app.lotti.routers.saima import build_saima_image_url, _immagine_saima_da_listing


def test_cartel1_non_sposta_piu_i_dolci_sconosciuti_in_rosticceria():
    assert _categorizza_reparto("Buondì") == "pasticceria"
    assert _categorizza_reparto("Via Col Vento") == "pasticceria"
    assert _categorizza_reparto("Treccia", ricetta_base_nome="brioche") == "pasticceria"
    assert _categorizza_reparto(
        "Crostone di ricotta", ingredienti=["ricotta", "prosciutto cotto", "pepe"]
    ) == "rosticceria"
    assert _categorizza_reparto("Nome realmente ambiguo") == "altro"


def test_classificazione_automatica_riconosce_il_reparto_bar():
    assert _categorizza_reparto("Crema di caffè") == "bar"
    assert _categorizza_reparto("Spritz") == "bar"
    assert _categorizza_reparto("Babà Napoletano al Rum") == "pasticceria"
    assert _reparto_finale_auto("bar", "bar") == "bar"
    assert _reparto_finale_auto("rosticceria", "pasticceria") == "pasticceria"


def test_cola_non_deve_confondersi_con_cioccolato():
    assert _categorizza_reparto("coda di aragosta al Cioccolato") == "pasticceria"
    assert _categorizza_reparto("crostatina Cioccolato") == "pasticceria"
    assert _categorizza_reparto("pizza parigina") == "rosticceria"
    assert _categorizza_reparto("Croccantini scozzesi") == "pasticceria"
    assert _categorizza_reparto("Grand Supreme — Nocciola e Caffè") == "pasticceria"
    assert _categorizza_reparto("Casatiello dolce") == "pasticceria"
    assert _categorizza_reparto("Cioccolato e lampone") == "pasticceria"


def test_preparazioni_base_storiche_hanno_un_reparto():
    assert _categorizza_reparto("panna") == "pasticceria"
    assert _categorizza_reparto("ragù di pomodoro") == "rosticceria"


def test_classificazione_bar_corregge_anche_un_reparto_errato():
    assert _reparto_finale_auto("rosticceria", _categorizza_reparto("Succo alla pera")) == "bar"


def test_categoria_ufficiale_fornitore_precede_le_parole_del_nome():
    assert _categoria_merce(
        "Mini Croissant Rustico", ["Snack", "Cornetti Salati"]
    ) == "Salato / Gastronomia"
    assert _categoria_merce(
        "Cornetto crema", ["Prelievitati", "Doramì"]
    ) == "Pasticceria"
    assert _categoria_merce("Pomodori pelati", ["POMODORI"]) == "Salato / Gastronomia"
    assert _categoria_merce("Stampo silicone", ["ATTREZZATURE"]) == "Attrezzature"


def test_catalogo_unificato_non_taglia_i_prodotti_oltre_cinquemila():
    assert _CATALOGO_MAX_PRODOTTI >= 10_000


def test_catalogo_mepa_include_tutte_le_categorie_ufficiali_mancanti():
    nomi = {categoria["nome"] for categoria in CATEGORIE_MEPA}
    assert {
        "ATTREZZATURE",
        "BAGNE",
        "CARTA & PLASTICA",
        "COADIUVANTI, EMULSIONANTI",
        "COLORANTI ALIMENTARI",
        "CRUNCH",
        "DETERGENZA",
        "PASTE DA DECORAZIONE",
        "POMODORI",
        "TOPPING",
    }.issubset(nomi)


def test_parser_acquaviva_conserva_foto_link_categorie_e_id_stabile():
    html = """
    <div class="jet-woo-products__item" data-product-id="13748">
      <div class="jet-woo-product-thumbnail">
        <a href="https://dolciariaacquaviva.com/prodotto/baby-calise-dritto/">
          <img src="https://dolciariaacquaviva.com/wp-content/uploads/2023/01/CS0030-1-1024x1024.jpg">
        </a>
      </div>
      <div class="jet-woo-product-categories">
        <a>Calise</a><a>Tipici</a><a>Baby &amp; Mini</a>
      </div>
      <h5 class="jet-woo-product-title">
        <a href="https://dolciariaacquaviva.com/prodotto/baby-calise-dritto/">Baby Calise Dritto</a>
      </h5>
    </div>
    """
    primo = _parse_acquaviva_listing(html)
    secondo = _parse_acquaviva_listing(html)
    assert len(primo) == 1
    assert primo[0]["id"] == secondo[0]["id"]
    assert primo[0]["codice_articolo"] == "CS0030"
    assert primo[0]["categoria"] == "Calise > Tipici > Baby & Mini"
    assert primo[0]["immagine_url"].endswith("/CS0030-1.jpg")


def test_parser_dettaglio_acquaviva_legge_codice_peso_e_confezione():
    html = """
      <h1>Baby croissant glassato Vuoto</h1>
      <div class="elementor-widget-woocommerce-product-content">
        Descrizione ufficiale.
        <table><tr><td><strong>CODICE</strong></td><td><strong>GRAMMI</strong></td>
        <td><strong>PZ CONF</strong></td></tr><tr><td>57198</td><td>40</td><td>100</td></tr></table>
      </div>
    """
    dettaglio = _parse_acquaviva_dettaglio(html)
    assert dettaglio["codice_articolo"] == "57198"
    assert dettaglio["peso_g"] == "40"
    assert dettaglio["pz_confezione"] == "100"
    assert dettaglio["unita_confezione"] == "100 pz"


def test_dettaglio_acquaviva_blocca_url_esterne_e_saima_codifica_spazi():
    assert _url_acquaviva_sicuro("https://dolciariaacquaviva.com/prodotto/test/")
    assert not _url_acquaviva_sicuro("https://example.com/prodotto/test/")
    assert "saima%201625.jpg" in build_saima_image_url("SAIMA 1625")


def test_saima_usa_la_foto_pubblicata_e_fallback_per_no_image():
    html = """
      <a href="prodottosito.php?cat=SAIMA 226"><img src="../public/prodotti/small/saima 226.jpg"></a>
      <a href="prodottosito.php?cat=SAIMA 1625"><img src="../public/prodotti/small/no-image.png"></a>
    """
    soup = BeautifulSoup(html, "html.parser")
    pagina = "https://www.saimaspa.com/app/site/categoriasito2.php?categoria=amidi"
    foto = _immagine_saima_da_listing(
        soup, "prodottosito.php?cat=SAIMA 226", pagina, "/saima/amidi.png"
    )
    mancante = _immagine_saima_da_listing(
        soup, "prodottosito.php?cat=SAIMA 1625", pagina, "/saima/amidi.png"
    )
    assert foto == "https://www.saimaspa.com/app/public/prodotti/small/saima 226.jpg"
    assert mancante == "/saima/amidi.png"
