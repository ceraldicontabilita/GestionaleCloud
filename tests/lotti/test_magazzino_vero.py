"""Blocco 6 dell'audit Lotti: il magazzino delle materie prime dice il vero.

- un ingrediente senza dose non si salta in silenzio: la produzione lo dichiara
  e il costo del lotto resta da verificare (mai un costo parziale);
- le intestazioni del vecchio ricettario non sono ingredienti;
- le ricette da completare si elencano per reparto;
- la merce ferma si vede per mese e si chiude solo su richiesta esplicita,
  senza cancellare niente e con la possibilita' di riaprire.
"""
import asyncio
from datetime import date

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient


def run(coro):
    return asyncio.run(coro)


RICETTA = {
    "id": "r1", "nome": "Babà", "reparto": "pasticceria",
    "ingredienti_dettaglio": [
        {"nome": "FARINA 00", "quantita": "500", "unita_misura": "g"},
        {"nome": "Uova", "quantita": None, "unita_misura": "g"},
        {"nome": "zucchero", "quantita": "0", "unita_misura": "g"},
        {"nome": "Peso impasto totale (g)", "quantita": "0", "unita_misura": "g"},
        {"nome": "Pezzi prodotti (n)", "quantita": None, "unita_misura": "g"},
    ],
}


def test_dosi_e_intestazioni():
    from app.lotti.servizi import ingredienti_ricetta as ir

    assert [i["nome"] for i in ir.righe_ingredienti(RICETTA)] == ["FARINA 00", "Uova", "zucchero"]
    assert ir.ingredienti_senza_dose(RICETTA) == ["Uova", "zucchero"]
    assert ir.dose({"quantita": "12,5"}) == 12.5 and ir.dose({"quantita": "tq"}) is None
    completa = {"id": "r2", "nome": "Crema", "reparto": "pasticceria",
                "ingredienti_dettaglio": [{"nome": "latte", "quantita": 1000}]}
    vuota = {"id": "r3", "nome": "Casatiello", "reparto": "rosticceria", "ingredienti_dettaglio": []}
    elenco = ir.ricette_da_completare([RICETTA, completa, vuota])
    assert [r["id"] for r in elenco] == ["r1", "r3"]
    assert [r["id"] for r in ir.ricette_da_completare([RICETTA, completa, vuota], "rosticceria")] == ["r3"]


def test_produzione_dichiara_gli_ingredienti_senza_dose(monkeypatch):
    import app.lotti.routers.lotti_produzione as lp

    database = AsyncMongoMockClient()["magazzino_vero"]
    monkeypatch.setattr(lp, "db", database)
    lotto = {"id": "lf1", "prodotto_nome": "FARINA 00 KG 25", "fornitore": "Molino",
             "quantita_disponibile": 25, "unita_misura": "KG", "prezzo_unitario": 0.8}
    run(database.lotti_fornitori.insert_one(dict(lotto)))

    async def candidati(ing):
        return ([dict(lotto)] if ing["nome"] == "FARINA 00" else []), []

    async def peso(_nome):
        return 0

    monkeypatch.setattr(lp, "_candidati_lotti_fifo", candidati)
    monkeypatch.setattr(lp, "_peso_pezzo_g_per_ing", peso)

    info = run(lp.scala_lotti_fornitori_per_ricetta(RICETTA, 1.0, "L-1"))
    assert info["ingredienti_senza_dose"] == ["Uova", "zucchero"]
    assert [s["ingrediente"] for s in info["lotti_scalati"]] == ["FARINA 00"]
    assert "Peso impasto totale (g)" not in info["ingredienti_non_trovati"]
    costo, motivo = lp.costo_da_consumo(info)
    assert costo is None and "senza dose" in motivo  # niente costo parziale spacciato per intero


def _lotto(i, data_fattura, **extra):
    return {"id": f"lf{i}", "prodotto_nome": f"Prodotto {i}", "fornitore": "F", "data_fattura": data_fattura,
            "quantita_disponibile": 10, "unita_misura": "KG", "prezzo_unitario": 2, "esaurito": False, **extra}


def test_riepilogo_merce_ferma():
    from app.lotti.servizi import merce_ferma

    lotti = [
        _lotto(1, "03/04/2026"), _lotto(2, "20/04/2026", prezzo_unitario=None),
        _lotto(3, "10/05/2026", storico_utilizzi=[{"quantita_usata": 1}]),  # scaricata: non e' ferma
        _lotto(4, "15/09/2026"),  # recente
        _lotto(5, "01/04/2026", esaurito=True),
    ]
    esito = merce_ferma.riepilogo(lotti, date(2026, 8, 1))
    assert esito["righe"] == 2 and esito["valore"] == "20.00" and esito["senza_prezzo"] == 1
    assert [m["mese"] for m in esito["mesi"]] == ["2026-04"]
    assert esito["ids"] == ["lf1", "lf2"]


@pytest.fixture()
def router(monkeypatch):
    import app.lotti.routers.lotti_fornitori as lf

    database = AsyncMongoMockClient()["merce_ferma"]
    monkeypatch.setattr(lf, "db", database)
    run(database.lotti_fornitori.insert_many([
        _lotto(1, "03/04/2026"), _lotto(2, "20/04/2026"), _lotto(3, "15/09/2026"),
    ]))
    return lf, database


class _Richiesta:
    class state:  # noqa: N801 - imita request.state
        user = {"nome": "Titolare"}


def test_chiusura_merce_ferma_simula_conferma_e_si_riapre(router):
    lf, database = router

    simulata = run(lf.chiudi_merce_ferma(lf.ChiusuraMerceFerma(prima_del="2026-08-01"), _Richiesta()))
    assert simulata["dry_run"] is True and simulata["righe"] == 2 and simulata["chiusi"] == 0
    assert run(database.lotti_fornitori.count_documents({"esaurito": True})) == 0

    with pytest.raises(HTTPException):
        run(lf.chiudi_merce_ferma(lf.ChiusuraMerceFerma(prima_del="2026-08-01", dry_run=False), _Richiesta()))

    fatta = run(lf.chiudi_merce_ferma(lf.ChiusuraMerceFerma(
        prima_del="2026-08-01", dry_run=False, conferma="chiudi merce ferma"), _Richiesta()))
    assert fatta["chiusi"] == 2
    chiuso = run(database.lotti_fornitori.find_one({"id": "lf1"}))
    assert chiuso["esaurito"] is True and chiuso["chiuso_senza_scarico"] is True
    assert chiuso["quantita_alla_chiusura"] == 10 and chiuso["quantita_disponibile"] == 0
    assert chiuso["chiuso_da"] == "Titolare"
    assert run(database.lotti_fornitori.count_documents({})) == 3  # niente cancellato
    assert run(database.lotti_fornitori.find_one({"id": "lf3"}))["esaurito"] is False

    assert run(lf.riapri_merce_ferma(fatta["chiuso_il"]))["riaperti"] == 2
    riaperto = run(database.lotti_fornitori.find_one({"id": "lf1"}))
    assert riaperto["esaurito"] is False and riaperto["quantita_disponibile"] == 10


def test_non_esiste_piu_la_cancellazione_dei_lotti_scaduti():
    import app.lotti.routers.lotti_fornitori as lf

    percorsi = {getattr(r, "path", "") for r in lf.router.routes}
    assert "/lotti-fornitori/pulizia-scaduti" not in percorsi
