"""Dizionario ingredienti: bibite fuori lista, categorie, associazione automatica."""
import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.lotti.servizi import dizionario_ingredienti as di


def run(coro):
    return asyncio.run(coro)


def test_categorie_richieste():
    for c in ("Salumi", "Pasta", "Olio", "Latticini", "Burro o margarina", "Zuccheri", "Bagne e Aromi"):
        assert c in di.CATEGORIE
    assert "Aromi" not in di.CATEGORIE and "Latticini e Grassi" not in di.CATEGORIE
    assert len(di.CATEGORIE) == len(set(di.CATEGORIE))


def test_bibite_fuori_ma_ingredienti_dentro():
    assert di.e_bevanda({"nome_originale": "CHINOTTO NERI VAP 33CL X 24", "categoria_canonica": "Bevande"})
    assert di.e_bevanda({"nome_originale": "TOURTEL CL.33X3"})
    assert di.e_bevanda({"nome_originale": "ACQUA PERRIER CL33X24 NATURALE VAP", "categoria_canonica": "Varie Alimentari"})
    assert di.e_bevanda({"nome_originale": "APEROL BARBIERI CL 100"})
    # ingredienti che contengono una parola da bibita
    assert not di.e_bevanda({"nome_originale": "CACAO AMARO IN POLVERE x 1kg"})
    assert not di.e_bevanda({"nome_originale": "CHEF PANNA DA CUCINA ML.200", "categoria_canonica": "Latticini"})
    assert not di.e_bevanda({"nome_originale": "sciroppo di glucosio kg 7"})
    # una categoria alimentare decisa vince sulla parola nel nome
    assert not di.e_bevanda({"nome_originale": "OLIVE IN ACQUA E SALE", "categoria_canonica": "Conserve e Condimenti"})


def test_categoria_dal_nome():
    casi = {
        "AMADORI COTOLETTA CROCANT. AST. GR 300X9": "Carni e Salumi",
        "TULIP.BACON/PANCETTA AFFUM.KG.1": "Salumi",
        "CHEF PANNA DA CUCINA ML.200": "Latticini",
        "DE CECCO PAS.GR.500 117MEZ.ZITA TA": "Pasta",
        "OLIO SEMI GIRASOLE SORRENTO L.25": "Olio",
        "ZUCCHERO DI CANNA BUSTINE KG.5": "Zuccheri",
        "PASTA NOCCIOLA 5kg": "Semilavorati Pasticceria",
        "NUPPY PISTACCHIO PIU' 6Kg": "Semilavorati Pasticceria",
        "MARGARINA OLVA THERMO": "Burro o margarina",
        "TOVAGLIOLI 15X15": None,
    }
    for nome, atteso in casi.items():
        assert di.categoria_da_testo(nome) == atteso, nome


def test_fonti_discordi_non_assegnano():
    riga = {"nome_originale": "CREMA PISTACCHIO", "nome_canonico": "Panna"}
    assert di.categoria_proposta(riga) is None


def _doc(i, nome, cat=None, **extra):
    d = {"id": i, "nome_originale": nome, "nome_canonico": nome}
    if cat is not None:
        d["categoria_canonica"] = cat
    d.update(extra)
    return d


def test_giro_idempotente_e_rispetta_manuale():
    db = AsyncMongoMockClient()["T"]

    async def prepara():
        await db.dizionario_prodotti.insert_many([
            _doc("1", "CHEF PANNA DA CUCINA", "Latticini e Grassi"),
            _doc("2", "ILARIA AROMA", "Aromi"),
            _doc("3", "DE CECCO PAS.GR.500 SPAGHETTI"),
            _doc("4", "TULIP BACON", "Varie Alimentari"),
            _doc("5", "DE CECCO PAS.GR.500 PENNE", "Varie Alimentari", categoria_fonte="manuale"),
            _doc("6", "TOURTEL CL.33X3"),
        ])
        await db.nome_mapping.insert_one({"descrizione_key": "panna", "categoria": "Latticini e Grassi"})

    run(prepara())
    r1 = run(di.giro_dizionario(db))
    assert r1["rinomine"] == {"dizionario": 2, "mapping": 1}
    assert r1["categorie"]["assegnate"] == 2 and r1["categorie"]["bevande"] == 1

    async def leggi():
        return {d["id"]: d async for d in db.dizionario_prodotti.find({}, {"_id": 0})}

    d = run(leggi())
    assert d["1"]["categoria_canonica"] == "Latticini"
    assert d["2"]["categoria_canonica"] == "Bagne e Aromi"
    assert d["3"]["categoria_canonica"] == "Pasta" and d["3"]["categoria_fonte"] == "auto"
    assert d["4"]["categoria_canonica"] == "Salumi"
    assert d["5"]["categoria_canonica"] == "Varie Alimentari"  # scelta di una persona: intatta
    assert "categoria_canonica" not in d["6"]  # bibita: non si classifica ne' si cancella
    r2 = run(di.giro_dizionario(db))
    assert r2["rinomine"] == {"dizionario": 0, "mapping": 0}
    assert r2["categorie"]["assegnate"] == 0
