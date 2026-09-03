"""
test_fonti_catalogo.py
───────────────────────
Regression test per il connettore "incolla il link" (richiesta Enzo
03/07/2026: pagina admin per collegare cataloghi fornitore senza scraper
scritto a mano per ogni sito). Verifica solo la parte pura — il parsing
di una pagina prodotto HTML già scaricata — senza rete/DB, dato che i
siti reali (ilpasticcere.it, sammontana.it, tremarie.sammontanaitalia.it)
non sono raggiungibili da questo ambiente di sviluppo.
"""
from app.lotti.routers.fonti_catalogo import _estrai_prodotto_da_html, _slugify

HTML_JSONLD_PRODUCT = """
<html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org/",
  "@type": "Product",
  "name": "Cornetto vuoto surgelato",
  "image": ["https://example.com/img/cornetto.jpg"],
  "description": "Cornetto pronto da farcire, confezione da 100 pezzi.",
  "sku": "COR-100",
  "offers": {"@type": "Offer", "price": "45.90", "priceCurrency": "EUR"}
}
</script>
</head><body></body></html>
"""

HTML_JSONLD_LISTA = """
<html><head>
<script type="application/ld+json">
[
  {"@type": "BreadcrumbList", "itemListElement": []},
  {"@type": "Product", "name": "Bignè al cioccolato", "sku": "BIG-01",
   "offers": {"price": 12.5}, "image": {"url": "https://example.com/bigne.jpg"}}
]
</script>
</head><body></body></html>
"""

HTML_SOLO_OG = """
<html><head>
<meta property="og:title" content="Torta Margherita 1kg" />
<meta property="og:description" content="Torta pronta da vendere al banco." />
<meta property="og:image" content="https://example.com/torta.jpg" />
</head><body></body></html>
"""

HTML_SENZA_DATI = "<html><head><title>Homepage</title></head><body><p>Benvenuti</p></body></html>"


def test_estrae_da_jsonld_product_singolo():
    p = _estrai_prodotto_da_html(HTML_JSONLD_PRODUCT, "https://example.com/p/cornetto")
    assert p["nome"] == "Cornetto vuoto surgelato"
    assert p["codice_articolo"] == "COR-100"
    assert p["prezzo"] == 45.90
    assert p["immagine_url"] == "https://example.com/img/cornetto.jpg"
    assert "farcire" in p["descrizione"]


def test_estrae_da_jsonld_lista_mista_ignora_non_product():
    p = _estrai_prodotto_da_html(HTML_JSONLD_LISTA, "https://example.com/p/bigne")
    assert p["nome"] == "Bignè al cioccolato"
    assert p["codice_articolo"] == "BIG-01"
    assert p["prezzo"] == 12.5
    assert p["immagine_url"] == "https://example.com/bigne.jpg"


def test_fallback_open_graph_se_niente_jsonld():
    p = _estrai_prodotto_da_html(HTML_SOLO_OG, "https://example.com/p/torta")
    assert p["nome"] == "Torta Margherita 1kg"
    assert p["immagine_url"] == "https://example.com/torta.jpg"
    assert p["prezzo"] == 0.0  # nessun prezzo strutturato: onestamente 0, non inventato


def test_nessun_dato_riconoscibile_ritorna_none():
    assert _estrai_prodotto_da_html(HTML_SENZA_DATI, "https://example.com/") is None


def test_slugify_nome_fornitore():
    assert _slugify("Il Pasticcere") == "ilpasticcere"
    assert _slugify("Tre Marie") == "tremarie"
    assert _slugify("  ") == "fonte"
