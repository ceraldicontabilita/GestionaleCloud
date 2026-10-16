import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.lotti.routers import irca as mod
from app.lotti.routers.irca import (
    DistintaPayload,
    PreferitoRicettaPayload,
    RicettaSelezionata,
    _candidati_nome_mepa,
    _numero_dose,
    _proposta_catalogo_fallback,
    estrai_cataloghi_irca,
    estrai_prodotto_irca,
    estrai_ricetta_irca,
)


CATALOGHI = """
<article class="node--book--teaser">
  <span class="badge">Catalogo</span><div class="img-wrapper"><img src="/cover.jpg"></div>
  <h3>IRCA - Pasticceria 2024</h3><div class="actions"><a href="https://www.flipsnack.com/E89/test">Visualizza</a></div>
</article>
<article class="node--book--teaser">
  <span class="badge">Ricettario</span><div class="img-wrapper"><img src="/premium.jpg"></div>
  <h3>Ricettario Premium</h3><div class="book--premium-flag">PREMIUM</div>
</article>
"""


PRODOTTO = """
<div class="node--masterproduct--full">
  <section class="hero">
    <div class="main-slider"><img src="/img/trial.jpg"></div>
    <div class="hero--content"><h2>IRCA</h2><h3>PANIFICAZIONE</h3><h1>TRIAL THERMOTECH</h1>
      <div class="hero--content--intro">Miglioratore professionale.</div>
      <div class="copy-section">01090613 Copied!</div>
      <div class="tab-content-item">
        <div class="info--row"><div>Descrizione</div><div>Descrizione completa verificata.</div></div>
        <div class="info--row"><div>Modalità d'uso</div><div>1 kg per quintale.</div></div>
        <div class="allergen--note">Cereali</div>
        <div class="crosscontaminations--note">Soia</div>
      </div>
    </div>
  </section>
  <div class="block--views-block--recipes-recipes-product"><div class="views-row"><h3>Croissant</h3><a href="/it/ricette/croissant">Read more</a></div></div>
</div>
"""


RICETTA = """
<article class="node--recipe--full">
  <div class="variant--header"><h1>CROISSANT</h1><h5>Livello intermedio</h5><div><div><p>LIEVITATI</p></div></div></div>
  <div class="image-solo"><img src="/img/croissant.jpg"></div>
  <a href="/it/pdf/recipe/42">PDF</a>
  <section class="all-ingredients"><div class="paragraph--ingredients"><h4>Farina</h4><p class="dose">1000g</p></div></section>
  <section class="paragraph--steps"><h2>IMPASTO</h2><div class="paragraph--ingredients"><h4><a href="/it/prodotti/trial-thermotech">TRIAL THERMOTECH</a></h4><p class="dose">10g</p></div><div class="preparation--container"><p>Impastare bene.</p></div></section>
  <section class="paragraph--steps"><h2>Composizione finale</h2><div class="preparation--container"><p>Cuocere per 15 minuti.</p><p>AVVERTENZE: lasciare spazio tra i biscotti.</p></div></section>
  <div class="recipe-product-wrapper"><div class="views-row"><h4 class="badge">PANIFICAZIONE</h4><h3>TRIAL THERMOTECH</h3><a href="/it/prodotti/trial-thermotech">Read more</a></div></div>
</article>
"""


def test_estrae_prodotto_irca_con_provenienza_e_dettagli():
    p = estrai_prodotto_irca(PRODOTTO, "https://www.ircagroup.com/it/prodotti/trial-thermotech")
    assert p["nome"] == "TRIAL THERMOTECH"
    assert p["codici_irca"] == ["01090613"]
    assert p["descrizione"] == "Descrizione completa verificata."
    assert p["dettagli_irca"]["modalita_d_uso"] == "1 kg per quintale."
    assert p["allergeni"] == ["Cereali"]
    assert p["cross_contaminazioni"] == ["Soia"]
    assert p["ricette"][0]["slug"] == "croissant"


def test_estrae_ricetta_irca_senza_confonderla_con_ricetta_operativa():
    r = estrai_ricetta_irca(RICETTA, "https://www.ircagroup.com/it/ricette/croissant")
    assert r["nome"] == "CROISSANT"
    assert r["ingredienti"] == [{"nome": "Farina", "dose": "1000g", "prodotto_irca_url": ""}]
    assert r["fasi"][0]["preparazione"] == "Impastare bene."
    assert r["fasi"][1]["nome"] == "Composizione finale"
    assert "AVVERTENZE" in r["fasi"][1]["preparazione"]
    assert r["prodotti_irca"][0]["slug"] == "trial-thermotech"
    assert r["pdf_url"].endswith("/it/pdf/recipe/42")


def test_associazione_mepa_richiede_marchio_irca_esplicito():
    assert _candidati_nome_mepa("IRCA TRIAL THERMOTECH") == ["TRIAL TERMOTECH"]
    assert _candidati_nome_mepa("IRCA TRIAL TERMOTECH") == ["TRIAL TERMOTECH"]
    assert _candidati_nome_mepa("IRCA MIX BISCUIMIX") == ["MIX BISCUIMIX", "BISCUIMIX"]
    assert _candidati_nome_mepa("TRIAL THERMOTECH") == []


def test_associazione_mepa_accetta_variante_termotech_solo_se_univoca(monkeypatch):
    database = AsyncMongoMockClient()["Irca_Associazione_Test"]
    monkeypatch.setattr(mod, "db", database)

    async def scenario():
        await database.catalogo_forno_prodotti.insert_one({
            "fornitore": "irca", "slug": "trial-thermotech",
            "nome": "TRIAL THERMOTECH",
            "link_prodotto": "https://www.ircagroup.com/it/prodotti/trial-thermotech",
        })
        await database.dizionario_ingredienti.insert_one({
            "fonte": "mepa", "nome": "IRCA TRIAL TERMOTECH",
        })
        risultato = await mod.associa_prodotti_mepa()
        prodotto = await database.dizionario_ingredienti.find_one({"fonte": "mepa"})
        return risultato, prodotto

    risultato, prodotto = asyncio.run(scenario())
    assert risultato["associati"] == 1
    assert risultato["ambigui"] == 0
    assert prodotto["irca_slug"] == "trial-thermotech"
    assert prodotto["irca_associazione"] == "nome_esatto_univoco"


def test_cataloghi_pubblici_e_premium_restano_distinti():
    docs = estrai_cataloghi_irca(CATALOGHI, pagina=2)
    assert docs[0]["url"].startswith("https://www.flipsnack.com/")
    assert docs[0]["stato_accesso"] == "pubblico"
    assert docs[1]["premium"] is True
    assert docs[1]["stato_accesso"] == "accesso_riservato"
    assert docs[1]["url"] == ""


def test_quantita_irca_supporta_migliaia_intervalli_e_qb():
    assert _numero_dose("1.000g") == (1000, 1000, "g")
    assert _numero_dose("1300-1500g") == (1300, 1500, "g")
    assert _numero_dose("qb") == (None, None, "qb")


def test_fallback_concept_usa_solo_prodotti_irca_e_formula_1000g():
    prodotti = [
        {"slug": "biscuimix", "nome": "BISCUIMIX", "descrizione": "Mix per pan di Spagna soffice"},
        {"slug": "chococream", "nome": "CHOCOCREAM", "descrizione": "Crema al cioccolato per farcitura"},
        {"slug": "cover", "nome": "COVER", "descrizione": "Glassa di copertura al cioccolato"},
        {"slug": "emul", "nome": "EMUL", "descrizione": "Emulsionante per masse montate"},
    ]
    ricette = [{"slug": "pan-di-spagna", "nome": "PAN DI SPAGNA"}]
    proposta = _proposta_catalogo_fallback("Dolce soffice con crema, glassa e riso soffiato", ricette, prodotti)
    ingredienti = [i for c in proposta["componenti"] for i in c["ingredienti"]]
    assert sum(i["quantita_per_kg_lordo_g"] for i in ingredienti) == 1000
    assert {i["product_slug"] for i in ingredienti if i["product_slug"]} <= {p["slug"] for p in prodotti}
    assert proposta["emulsionanti_e_stabilizzanti"][0]["product_slug"] == "emul"
    assert proposta["origine_formula"] == "fallback_catalogo_irca"


def test_distinta_somma_quantita_e_ordina_solo_associazione_esatta(monkeypatch):
    database = AsyncMongoMockClient()["Irca_Test"]
    monkeypatch.setattr(mod, "db", database)

    async def scenario():
        await database.irca_ricette.insert_many([
            {"slug": "r1", "nome": "Uno", "ingredienti": [
                {"nome": "TRIAL", "dose": "100g", "prodotto_irca_url": "https://www.ircagroup.com/it/prodotti/trial"},
                {"nome": "Acqua", "dose": "200g", "prodotto_irca_url": ""},
            ]},
            {"slug": "r2", "nome": "Due", "ingredienti": [
                {"nome": "TRIAL", "dose": "50g", "prodotto_irca_url": "https://www.ircagroup.com/it/prodotti/trial"},
            ]},
        ])
        await database.catalogo_forno_prodotti.insert_one({
            "fornitore": "irca", "slug": "trial", "codici_irca": ["01090613"],
            "descrizione": "Miglioratore",
        })
        await database.dizionario_ingredienti.insert_one({
            "fonte": "mepa", "irca_slug": "trial", "nome": "IRCA TRIAL",
            "codice_articolo": "MEPA-1",
        })
        return await mod._genera_distinta(DistintaPayload(ricette=[
            RicettaSelezionata(slug="r1", moltiplicatore=2),
            RicettaSelezionata(slug="r2", moltiplicatore=1),
        ]))

    out = asyncio.run(scenario())
    trial = next(r for r in out["righe"] if r["ingrediente"] == "TRIAL")
    acqua = next(r for r in out["righe"] if r["ingrediente"] == "Acqua")
    assert trial["quantita_min"] == 250
    assert trial["fornitore"]["codice"] == "MEPA-1"
    assert trial["stato_associazione"] == "pronto"
    assert trial["stato"] == "da_acquistare"
    assert acqua["stato"] == "DA_VERIFICARE"


def test_distinta_distingue_acquistati_da_mancanti_usando_solo_fatture(monkeypatch):
    database = AsyncMongoMockClient()["Irca_Acquisti_Test"]
    monkeypatch.setattr(mod, "db", database)

    async def scenario():
        await database.irca_ricette.insert_one({
            "slug": "r1", "nome": "Ricetta", "ingredienti": [
                {"nome": "COMPRATO", "dose": "100g", "prodotto_irca_url": "https://www.ircagroup.com/it/prodotti/comprato"},
                {"nome": "MANCANTE", "dose": "50g", "prodotto_irca_url": "https://www.ircagroup.com/it/prodotti/mancante"},
                {"nome": "DA ASSOCIARE", "dose": "25g", "prodotto_irca_url": "https://www.ircagroup.com/it/prodotti/da-associare"},
            ],
        })
        await database.catalogo_forno_prodotti.insert_many([
            {"fornitore": "irca", "slug": "comprato"},
            {"fornitore": "irca", "slug": "mancante"},
        ])
        await database.dizionario_ingredienti.insert_many([
            {"fonte": "mepa", "irca_slug": "comprato", "nome": "IRCA COMPRATO", "codice_articolo": "COMPRATO",
             "gia_acquistato": True, "prezzo_fattura": 12.5, "prezzo_fattura_data": "2026-10-01", "iva_pct": 10},
            {"fonte": "mepa", "irca_slug": "mancante", "nome": "IRCA MANCANTE", "codice_articolo": "MANCANTE"},
        ])
        distinta = await mod._genera_distinta(DistintaPayload(ricette=[RicettaSelezionata(slug="r1")]))
        carrello = await mod.aggiungi_distinta_carrello(
            DistintaPayload(ricette=[RicettaSelezionata(slug="r1")]), _admin={}
        )
        return distinta, carrello

    distinta, carrello = asyncio.run(scenario())
    stati = {r["ingrediente"]: r["stato"] for r in distinta["righe"]}
    assert stati == {"COMPRATO": "gia_acquistato", "MANCANTE": "da_acquistare", "DA ASSOCIARE": "DA_VERIFICARE"}
    assert distinta["totali"]["gia_acquistati"] == 1
    assert distinta["totali"]["da_acquistare"] == 1
    assert carrello["aggiunti"] == 2
    assert carrello["gia_acquistati"] == 1
    assert carrello["da_verificare_aggiunti"] == 1
    assert {r["nome"]: r["richiede_associazione"] for r in carrello["righe"]} == {
        "IRCA MANCANTE": False, "DA ASSOCIARE": True,
    }


def test_reno_senza_link_irca_viene_riconosciuto_e_ordinato_da_nome_esatto(monkeypatch):
    database = AsyncMongoMockClient()["Irca_Reno_Test"]
    monkeypatch.setattr(mod, "db", database)

    async def scenario():
        await database.irca_ricette.insert_one({
            "slug": "cornetto-bicolore", "nome": "CORNETTO BICOLORE", "ingredienti": [
                {"nome": "RENO CONCERTO FONDENTE 72%", "dose": "75g", "prodotto_irca_url": ""},
                {"nome": "CACAO IN POLVERE", "dose": "15g", "prodotto_irca_url": ""},
            ],
        })
        await database.dizionario_ingredienti.insert_one({
            "fonte": "mepa",
            "nome": "IRCA RENO CONCERTO CIOCCOLATO EXTRA FONDENTE 72%",
            "nome_display": "IRCA RENO CONCERTO CIOCCOLATO EXTRA FONDENTE 72%",
            "codice_articolo": "01011792",
            "gia_acquistato": False,
        })
        distinta = await mod._genera_distinta(DistintaPayload(
            ricette=[RicettaSelezionata(slug="cornetto-bicolore")]
        ))
        carrello = await mod.aggiungi_distinta_carrello(
            DistintaPayload(ricette=[RicettaSelezionata(slug="cornetto-bicolore")]), _admin={}
        )
        return distinta, carrello

    distinta, carrello = asyncio.run(scenario())
    reno = next(r for r in distinta["righe"] if r["ingrediente"].startswith("RENO CONCERTO"))
    cacao = next(r for r in distinta["righe"] if r["ingrediente"] == "CACAO IN POLVERE")
    assert reno["prodotto_irca_slug"] == ""
    assert reno["fornitore"]["codice"] == "01011792"
    assert reno["fornitore"]["associazione"] == "nome_irca_esatto_univoco"
    assert reno["stato"] == "da_acquistare"
    assert cacao["stato"] == "DA_VERIFICARE"
    assert carrello["aggiunti"] == 2
    assert {r["nome"] for r in carrello["righe"]} == {
        "IRCA RENO CONCERTO CIOCCOLATO EXTRA FONDENTE 72%", "CACAO IN POLVERE",
    }


def test_preferito_ricetta_persiste_e_viene_ordinato_prima(monkeypatch):
    database = AsyncMongoMockClient()["Irca_Preferiti_Test"]
    monkeypatch.setattr(mod, "db", database)

    async def scenario():
        await database.irca_ricette.insert_many([
            {"id": "irca-ricetta:zeta", "slug": "zeta", "nome": "Zeta"},
            {"id": "irca-ricetta:alfa", "slug": "alfa", "nome": "Alfa"},
        ])
        await mod.imposta_ricetta_preferita(
            "zeta", PreferitoRicettaPayload(preferito=True), _admin={},
        )
        elenco = await mod.lista_ricette(q="", prodotto="", skip=0, limit=100)
        return elenco, await database.irca_ricette.find_one({"slug": "zeta"})

    elenco, salvata = asyncio.run(scenario())
    assert salvata["preferito"] is True
    assert [r["slug"] for r in elenco["ricette"]] == ["zeta", "alfa"]
