import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.lotti.routers import cataloghi_arricchimento
from app.lotti.routers.cataloghi_arricchimento import _normalizza_dettaglio
from app.lotti.routers.catalogo_forno import descrizione_catalogo_precaricato
from app.lotti.routers.mepa import _parse_dettaglio_mepa, _url_mepa_sicuro


def run(coro):
    return asyncio.run(coro)


def test_parser_mepa_usa_solo_codice_confezione_categoria_e_foto_ufficiali():
    html = """
    <html><head><meta property="og:image" content="https://www.mepaalimentari.com/p.jpg"></head>
    <body>
      <nav class="woocommerce-breadcrumb">Home / PASTICCERIA / SFOGLIE</nav>
      <h1 class="product_title">Conky crema</h1>
      <p class="elementor-heading-title">CT 6 PZ</p>
      <p class="elementor-heading-title">COD: CH0012</p>
    </body></html>
    """
    dettaglio = _parse_dettaglio_mepa(html)
    assert dettaglio["codice_articolo"] == "CH0012"
    assert dettaglio["unita_confezione"] == "CT 6 PZ"
    assert dettaglio["categoria_dettaglio"] == "PASTICCERIA / SFOGLIE"
    assert dettaglio["descrizione"] == "Categoria: PASTICCERIA / SFOGLIE · Confezione: CT 6 PZ"
    assert dettaglio["immagine_prodotto"].endswith("/p.jpg")
    assert _url_mepa_sicuro("https://www.mepaalimentari.com/prodotto/x/")
    assert not _url_mepa_sicuro("https://example.com/prodotto/x/")


def test_descrizione_pdf_non_inventa_testo_commerciale():
    descrizione = descrizione_catalogo_precaricato({
        "categoria": "Elite",
        "grammi": "75 g.",
        "pezzi_cartone": "50 pz.",
    })
    assert descrizione == "Linea: Elite · Peso unitario: 75 g. · Confezione: 50 pz."


def test_normalizzazione_rende_la_descrizione_visibile_nella_card():
    aggiornamento = _normalizza_dettaglio(
        "saima",
        {"nome": "Crema", "categoria": "Pasticceria", "descrizione": "Confezione: 3 KG"},
        {"descrizione_lunga": "Crema da farcitura.", "unita_confezione": "3 KG"},
    )
    assert aggiornamento["descrizione"] == "Crema da farcitura."
    assert aggiornamento["descrizione_lunga"] == "Crema da farcitura."
    assert aggiornamento["arricchimento_esito"] == "completo"


def test_risposta_vuota_non_blocca_un_futuro_tentativo():
    aggiornamento = _normalizza_dettaglio(
        "mepa",
        {"nome": "Prodotto senza dettaglio", "descrizione": ""},
        {},
    )
    assert aggiornamento["arricchimento_esito"] == "verificato_senza_dettagli"
    assert "arricchimento_version" not in aggiornamento


def test_salvataggio_batch_ritenta_un_timeout_transitorio(monkeypatch):
    class Collection:
        def __init__(self):
            self.chiamate = 0

        async def update_documents_by_id(self, updates):
            self.chiamate += 1
            if self.chiamate == 1:
                raise cataloghi_arricchimento.httpx.ConnectTimeout("")

    async def nessuna_attesa(_):
        return None

    monkeypatch.setattr(cataloghi_arricchimento.asyncio, "sleep", nessuna_attesa)
    collection = Collection()
    run(cataloghi_arricchimento._salva_aggiornamenti(collection, [("1", {"a": 1})]))
    assert collection.chiamate == 2


def test_descrizione_base_usa_solo_la_categoria_ufficiale(monkeypatch):
    class Collection:
        def __init__(self):
            self.salvati = []

        async def update_documents_by_id(self, updates):
            self.salvati.extend(updates)

    prodotti = [
        {"_id": "1", "categoria": "PASTICCERIA SURGELATA", "descrizione": ""},
        {"_id": "2", "categoria": "GELATERIA", "descrizione": "Testo esistente"},
    ]
    collection = Collection()
    aggiunte = run(cataloghi_arricchimento._assicura_descrizioni_base(
        collection, "saima", prodotti
    ))

    assert aggiunte == 1
    assert collection.salvati[0][1]["descrizione"] == "Categoria: PASTICCERIA SURGELATA"
    assert prodotti[0]["descrizione"] == "Categoria: PASTICCERIA SURGELATA"


def test_worker_e_idempotente_e_riprende_solo_schede_non_verificate(monkeypatch):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(cataloghi_arricchimento, "db", database)
    run(database.dizionario_ingredienti.insert_one({
        "_id": "mepa-1",
        "fonte": "mepa",
        "nome": "Conky crema",
        "categoria": "Sfoglie",
        "link_prodotto": "https://www.mepaalimentari.com/prodotto/conky/",
        "descrizione": "",
    }))

    chiamate = []

    async def dettaglio_finto(url, client=None):
        chiamate.append(url)
        return {
            "codice_articolo": "CH0012",
            "descrizione": "Categoria: Sfoglie · Confezione: CT 6 PZ",
        }

    monkeypatch.setattr(cataloghi_arricchimento, "scrape_dettaglio_mepa", dettaglio_finto)
    primo = run(cataloghi_arricchimento._arricchisci_catalogo("mepa"))
    secondo = run(cataloghi_arricchimento._arricchisci_catalogo("mepa"))

    doc = run(database.dizionario_ingredienti.find_one({"_id": "mepa-1"}))
    assert primo["elaborati"] == 1
    assert secondo["elaborati"] == 0
    assert len(chiamate) == 1
    assert doc["codice_articolo"] == "CH0012"
    assert doc["descrizione"].startswith("Categoria:")
    assert doc["arricchimento_version"] == cataloghi_arricchimento.VERSIONE_ARRICCHIMENTO
