import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.lotti.routers import irca as mod
from app.lotti.routers.irca import (
    DistintaPayload,
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
    assert r["prodotti_irca"][0]["slug"] == "trial-thermotech"
    assert r["pdf_url"].endswith("/it/pdf/recipe/42")


def test_associazione_mepa_richiede_marchio_irca_esplicito():
    assert _candidati_nome_mepa("IRCA TRIAL THERMOTECH") == ["TRIAL THERMOTECH"]
    assert _candidati_nome_mepa("IRCA MIX BISCUIMIX") == ["MIX BISCUIMIX", "BISCUIMIX"]
    assert _candidati_nome_mepa("TRIAL THERMOTECH") == []


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
    assert stati == {"COMPRATO": "gia_acquistato", "MANCANTE": "da_acquistare"}
    assert distinta["totali"]["gia_acquistati"] == 1
    assert distinta["totali"]["da_acquistare"] == 1
    assert carrello["aggiunti"] == 1
    assert carrello["gia_acquistati"] == 1
    assert carrello["righe"][0]["codici"] == ["MANCANTE"]
