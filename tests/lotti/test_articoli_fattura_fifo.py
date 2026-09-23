"""Nome commerciale in fattura → ingrediente di ricetta, senza equivoci.

Misurato sui dati veri il 23/09/2026: il FIFO agganciava per pezzo di parola.
«sale» trovava per primi i lotti di OLIVE «in acqua e SALE», «uova» trovava
«NUOVA BIANCALIEVE crema da montare», «margarina» non trovava mai OLVA.
Una conferma di una persona (o una proposta web sicura) ora decide.
"""
import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def dbmock(monkeypatch):
    import importlib
    import pkgutil

    import app.lotti.routers as routers  # noqa: F401
    from app.lotti.servizi import articoli_fattura

    db = AsyncMongoMockClient()["Gestionale_Test"]
    for m in pkgutil.iter_modules(routers.__path__):
        try:
            mod = importlib.import_module(f"app.lotti.routers.{m.name}")
        except Exception:
            continue
        if hasattr(mod, "db"):
            monkeypatch.setattr(mod, "db", db, raising=False)
    import app.lotti.db as dbmod

    monkeypatch.setattr(dbmod, "database", db, raising=False)
    articoli_fattura.invalida_cache()
    yield db
    articoli_fattura.invalida_cache()


def _lotto(id_, nome, fornitore, data, qta=10, um="KG"):
    return {
        "id": id_, "lotto_id_fornitore": f"L-{id_}", "fornitore": fornitore,
        "prodotto_nome": nome, "prodotto_nome_norm": nome.lower(), "nome_canonico": "",
        "quantita_disponibile": qta, "unita_misura": um, "data_fattura": data,
        "data_scadenza": "", "fattura_ref": f"F-{id_}", "esaurito": False,
    }


async def _semina(db):
    await db.lotti_fornitori.insert_many([
        _lotto("olive", "OLIVE VERDI TONDE 0000 MSM IN ACQUA E SALE", "Miraglia", "01/01/2026"),
        _lotto("sale-fior", "SALE FINO IODATO KG.1", "F.lli Fiorentino Srl", "10/02/2026"),
        _lotto("sale-mepa", "MEPA SALE FINO CF 1 KG", "Mepa", "20/03/2026"),
        _lotto("bianca", "NUOVA BIANCALIEVE CREMA DA MONTARE", "SAIMA S.p.A.", "05/01/2026", um="L"),
        _lotto("uova", "UOVA CAT.PESO L DA 180", "EUROUOVA SRL", "06/01/2026", qta=180, um="PZ"),
        _lotto("olva", "OLVA THERMO CREMA GATEAUX", "RONDINELLA MARKET S.R.L.", "03/01/2026"),
    ])


def test_ripiego_per_nome_usa_la_parola_intera(dbmock):
    from app.lotti.routers.lotti_produzione import _candidati_lotti_fifo
    run(_semina(dbmock))
    utilizzabili, _ = run(_candidati_lotti_fifo({"nome": "uova"}))
    assert [l["id"] for l in utilizzabili] == ["uova"]  # mai «nUOVA Biancalieve»
    assert utilizzabili[0]["abbinamento"] == "da_confermare"


def test_proposta_web_sicura_toglie_le_olive_dal_sale(dbmock):
    from app.lotti.routers.lotti_produzione import _candidati_lotti_fifo
    run(_semina(dbmock))
    run(dbmock.nome_mapping.insert_one({
        "descrizione_key": "olive verdi tonde 0000 msm in acqua e sale",
        "nome_canc": "Olive verdi in salamoia", "ingredienti_ricetta": ["olive verdi"],
        "fonte": "web", "confidenza": "alta", "confermato": False, "alimentare": True,
    }))
    utilizzabili, _ = run(_candidati_lotti_fifo({"nome": "sale"}))
    assert "olive" not in [l["id"] for l in utilizzabili]


def test_conferma_aggancia_margarina_e_passa_da_un_fornitore_all_altro(dbmock):
    from app.lotti.routers.lotti_produzione import _candidati_lotti_fifo
    from app.lotti.routers.normalizzazione import conferma_articolo
    run(_semina(dbmock))
    # prima della conferma «margarina» non trova OLVA
    assert run(_candidati_lotti_fifo({"nome": "margarina"}))[0] == []
    esito = run(conferma_articolo({"descrizione": "OLVA THERMO CREMA GATEAUX", "nome_canc": "Margarina"}))
    assert esito["lotti_aggiornati"] == 1
    utilizzabili, _ = run(_candidati_lotti_fifo({"nome": "margarina"}))
    assert [(l["id"], l["abbinamento"]) for l in utilizzabili] == [("olva", "confermato")]
    # sale: due fornitori confermati sullo stesso articolo, FIFO dal più vecchio
    for descr in ("SALE FINO IODATO KG.1", "MEPA SALE FINO CF 1 KG"):
        run(conferma_articolo({"descrizione": descr, "nome_canc": "Sale fino", "ingredienti_ricetta": ["sale"]}))
    utilizzabili, _ = run(_candidati_lotti_fifo({"nome": "sale"}))
    assert [l["id"] for l in utilizzabili] == ["sale-fior", "sale-mepa"]
    assert all(l["abbinamento"] == "confermato" for l in utilizzabili)


def test_non_alimentare_confermato_non_scarica_mai(dbmock):
    from app.lotti.routers.lotti_produzione import _candidati_lotti_fifo
    from app.lotti.routers.normalizzazione import conferma_articolo
    run(_semina(dbmock))
    run(conferma_articolo({"descrizione": "NUOVA BIANCALIEVE CREMA DA MONTARE", "alimentare": False}))
    utilizzabili, _ = run(_candidati_lotti_fifo({"nome": "biancalieve"}))
    assert utilizzabili == []


def test_proposte_web_non_toccano_una_conferma(dbmock):
    from app.lotti.routers.normalizzazione import conferma_articolo, importa_proposte_web, lista_proposte_articoli
    run(conferma_articolo({"descrizione": "OLVA THERMO QUICK", "nome_canc": "Margarina"}))
    esito = run(importa_proposte_web({"voci": [
        {"descrizione": "OLVA THERMO QUICK", "nome_usuale": "Grasso vegetale", "confidenza": "alta"},
        {"descrizione": "GLOB SFOGLIA Kg2x5", "nome_usuale": "Margarina da sfoglia",
         "ingredienti_ricetta": ["Margarina"], "confidenza": "media", "fonte_url": "https://esempio.it"},
        {"descrizione": "", "nome_usuale": "x"},
    ]}, _admin=None))
    assert esito == {"ricevute": 3, "inserite": 1, "aggiornate": 0, "confermate_intatte": 1, "scartate": 1}
    olva = run(dbmock.nome_mapping.find_one({"descrizione_key": "olva thermo quick"}))
    assert olva["nome_canc"] == "Margarina" and olva["confermato"] is True
    proposte = run(lista_proposte_articoli(stato="da_confermare", limit=100))
    assert [v["descrizione_key"] for v in proposte["voci"]] == ["glob sfoglia kg2x5"]
    assert proposte["voci"][0]["ingredienti_ricetta"] == ["margarina"]
    # reimport identico: nessuna nuova riga
    esito2 = run(importa_proposte_web({"voci": [
        {"descrizione": "GLOB SFOGLIA Kg2x5", "nome_usuale": "Margarina da sfoglia"}]}, _admin=None))
    assert esito2["inserite"] == 0 and esito2["aggiornate"] == 1


def test_ingrediente_senza_nome_non_rompe_lo_scarico(dbmock):
    from app.lotti.routers.lotti_produzione import _candidati_lotti_fifo
    assert run(_candidati_lotti_fifo({"nome": ""})) == ([], [])
