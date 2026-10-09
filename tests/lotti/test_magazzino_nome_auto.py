"""Gestione prodotti magazzino: nome dell'ingrediente riconosciuto da solo,
e un salvataggio si rivede subito (non la copia di 2 minuti prima)."""
import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def mag(monkeypatch):
    import app.lotti.routers.magazzino_unificato as m
    db = AsyncMongoMockClient()["t"]
    monkeypatch.setattr(m, "db", db)
    m._GESTIONE_CACHE.update({"dati": None, "scade": 0.0})
    run(db.magazzino_bar_prodotti.insert_one({"id": "b1", "nome": "ACQUA", "categoria": "Bar"}))
    run(db.lotti_fornitori.insert_many([
        {"id": "l1", "prodotto_nome": "AIA. WUDY GR.300 WURSTEL POLLO", "prodotto_nome_norm": "wudy",
         "quantita_disponibile": 3, "unita_misura": "PZ", "fornitore": "BIG FOOD SRL"},
        {"id": "l2", "prodotto_nome": "Ananas L. 055-000857-0003014", "prodotto_nome_norm": "ananas l",
         "quantita_disponibile": 2, "unita_misura": "KG", "fornitore": "I COZZOLINO SRL"},
    ]))
    return m, db


def test_il_nome_dell_ingrediente_si_ricava_da_solo(mag):
    m, _db = mag
    righe = {p["key"]: p for p in run(m.gestione_prodotti())["prodotti"]}
    assert righe["wudy"]["nome_norm_auto"] == "Würstel"
    assert righe["ananas l"]["nome_norm_auto"] == "Ananas"
    assert righe["wudy"]["nome_originale"] == "AIA. WUDY GR.300 WURSTEL POLLO"
    # in magazzino si vede gia' il nome dell'ingrediente, e si trova anche col nome di fattura
    trovati = run(m.prodotti_unificati(search="wudy"))
    assert [p["nome"] for p in trovati] == ["Würstel"]


def test_salvataggio_visibile_subito(mag):
    m, _db = mag
    run(m.gestione_prodotti())  # riempie la copia in memoria
    run(m.salva_override(m.OverridePayload(key="ananas l", nome_norm="Ananas fresco", categoria="Frutta/Noci")))
    riga = next(p for p in run(m.gestione_prodotti())["prodotti"] if p["key"] == "ananas l")
    assert riga["nome_norm"] == "Ananas fresco" and riga["categoria"] == "Frutta/Noci"
