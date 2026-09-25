import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.lotti.routers import food_cost


def run(coro):
    return asyncio.run(coro)


def test_dizionario_esclude_fornitori_senza_expr_non_supportato(monkeypatch):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(food_cost, "db", database)

    run(database.fornitori.insert_one({"nome": "Fornitore Escluso", "escluso": True}))
    run(database.dizionario_prodotti.insert_many([
        {
            "id": "escluso",
            "nome_originale": "Prodotto da nascondere",
            "nome_normalizzato": "prodotto da nascondere",
            "fornitore": "  FORNITORE ESCLUSO  ",
            "ultima_fattura_data": "2026-08-29",
        },
        {
            "id": "visibile",
            "nome_originale": "Prodotto valido",
            "nome_normalizzato": "prodotto valido",
            "fornitore": "Fornitore Attivo",
            "ultima_fattura_data": "2026-08-29",
        },
    ]))

    risultato = run(food_cost.get_dizionario(
        search=None,
        escludi_fornitori=True,
        senza_canonico=False,
        solo_completi=False,
        solo_esclusi=False,
        proponi_canonici=False,
        skip=0,
        limit=2000,
    ))

    assert risultato["totale"] == 1
    assert [p["id"] for p in risultato["prodotti"]] == ["visibile"]


def _riga(i, nome, **extra):
    return {"id": i, "nome_originale": nome, "nome_normalizzato": nome.lower(),
            "fornitore": "Fornitore Attivo", "ultima_fattura_data": "2026-09-01", **extra}


def _elenco(solo_esclusi=False):
    return run(food_cost.get_dizionario(
        search=None, escludi_fornitori=True, senza_canonico=False, solo_completi=False,
        solo_esclusi=solo_esclusi, proponi_canonici=False, skip=0, limit=2000,
    ))


def test_le_voci_non_pertinenti_escono_da_sole(monkeypatch):
    """Servizi, bolli, monouso: fuori dalla coda senza che nessuno le escluda."""
    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(food_cost, "db", database)
    run(database.dizionario_prodotti.insert_many([
        _riga("farina", "FARINA 00 CAPUTO RINFORZ.KG.25"),
        _riga("lamponi", "Lamponi orig.it-F.691/A-L.20"),          # prima: «.it» = dominio web
        _riga("miele", "MIELE MILLEFIORI CONTENITORE KG 10"),     # parola di cibo: decide una persona
        _riga("patate", ".PATATA FORNO VASSOIO X4"),
        _riga("consulenza", "Onorario per consulenza II trimestre 2026"),
        _riga("bollo", "Bollo su importi esenti"),
        _riga("tovaglioli", "TOVAGLIOLI 25X25 EXTRA 1 SCELTA 9KG"),
        _riga("piastrella", "120X120 Balance Mud"),
        _riga("ripristinata", "SHOPPERS SOLE 365 BIOCOMP.", escluso_ricette=False),  # scelta a mano
        _riga("a_mano", "ACQUA FERRARELLE CL.50 CTX24", escluso_ricette=True, escluso_motivo="famiglia:bevande"),
    ]))
    dentro = {p["id"] for p in _elenco()["prodotti"]}
    assert dentro == {"farina", "lamponi", "miele", "patate", "ripristinata"}

    fuori = {p["id"]: p for p in _elenco(solo_esclusi=True)["prodotti"]}
    assert set(fuori) == {"consulenza", "bollo", "tovaglioli", "piastrella", "a_mano"}
    assert fuori["bollo"]["escluso_automatico"] is True
    assert fuori["bollo"]["escluso_motivo"] == "automatico: servizio o voce contabile"
    assert fuori["tovaglioli"]["escluso_motivo"].startswith("automatico: non alimentare")
    assert "escluso_automatico" not in fuori["a_mano"]
    # niente e' stato scritto: l'esclusione automatica e' una lettura
    doc = run(database.dizionario_prodotti.find_one({"id": "bollo"}))
    assert "escluso_ricette" not in doc


def test_associa_non_rinomina_le_descrizioni_simili(monkeypatch):
    """Confermare «PASTA DE CECCO SPAGHETTI» non tocca le PENNE (stessi 15 caratteri)."""
    from app.lotti.routers import normalizzazione

    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(normalizzazione, "db", database)
    run(database.dizionario_prodotti.insert_many([
        _riga("spaghetti", "PASTA DE CECCO SPAGHETTI"),
        _riga("penne", "PASTA DE CECCO PENNE LISCE"),
    ]))
    esito = run(normalizzazione.correggi_mapping(
        {"descrizione_key": "pasta de cecco spaghetti", "nome_canc": "Spaghetti", "categoria": "Farine e Cereali"}))
    assert esito["prodotti_aggiornati"] == 1
    penne = run(database.dizionario_prodotti.find_one({"id": "penne"}))
    assert "ingrediente_canonico" not in penne
    spaghetti = run(database.dizionario_prodotti.find_one({"id": "spaghetti"}))
    assert spaghetti["ingrediente_canonico"] == "Spaghetti"
