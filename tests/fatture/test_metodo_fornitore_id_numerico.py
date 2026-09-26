"""Cambio metodo di pagamento dalla pagina Fornitori.

180 anagrafiche su 188 hanno l'`id` salvato come numero, e la pagina lo manda
come testo: la ricerca testo contro numero non trovava nulla e ogni cambio
metodo rispondeva 404 «Fornitore non trovato». La Prima Nota, poi, deve
riconoscere il metodo del fornitore da qualunque campo P.IVA, con o senza «IT».
"""
import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def db(monkeypatch):
    database = AsyncMongoMockClient()["metodo_fornitore"]
    from app.database import Database

    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: database))
    return database


def test_filtro_trova_l_id_numerico_mandato_come_testo(db):
    from app.routers.suppliers_module.base import _filtro_fornitore

    run(db["fornitori"].insert_one({"id": 61, "partita_iva": "07679350632", "ragione_sociale": "ABC"}))
    trovato = run(db["fornitori"].find_one(_filtro_fornitore("61"), {"_id": 0}))
    assert trovato and trovato["ragione_sociale"] == "ABC"


def test_cambio_metodo_con_id_numerico_non_da_404(db, monkeypatch):
    from app.routers.suppliers_module import base

    async def niente(*_a, **_k):
        return True

    monkeypatch.setattr("app.utils.iva_calculator.save_supplier_payment_method", niente)
    monkeypatch.setattr(base.asyncio if hasattr(base, "asyncio") else asyncio, "create_task", lambda c: c.close())
    run(db["fornitori"].insert_one({"id": 61, "partita_iva": "07679350632", "ragione_sociale": "ABC",
                                    "metodo_pagamento": ""}))
    esito = run(base.update_supplier("61", {"metodo_pagamento": "banca"}))
    assert esito["supplier"]["metodo_pagamento"] == "banca"
    salvato = run(db["fornitori"].find_one({"id": 61}, {"_id": 0}))
    assert salvato["metodo_pagamento"] == "banca"


def test_mappa_unica_legge_ogni_campo_piva_normalizzato(db):
    from app.routers.prima_nota_module.sync import classifica_metodo_fornitore, mappa_fornitori_per_piva

    run(db["fornitori"].insert_many([
        {"id": 1, "partita_iva": "07679350632", "metodo_pagamento": "banca"},
        {"id": 2, "vat": "IT01234567890", "metodo_pagamento": "contanti"},
        # doppione della prima senza metodo: non cancella il metodo buono
        {"id": 3, "piva": "IT07679350632", "metodo_pagamento": ""},
        {"id": 4, "partita_iva": "11111111111", "metodo_pagamento": "banca", "cessato": True},
    ]))
    metodi, esclusi = run(mappa_fornitori_per_piva(db))
    assert classifica_metodo_fornitore(metodi.get("07679350632", "")) == "banca"
    assert classifica_metodo_fornitore(metodi.get("IT07679350632", "")) == "banca"
    assert classifica_metodo_fornitore(metodi.get("01234567890", "")) == "cassa"
    assert classifica_metodo_fornitore(metodi.get("99999999999", "")) == "sospesa"
    assert "IT11111111111" in esclusi and "07679350632" not in esclusi


def test_ogni_fattura_ha_la_sua_anagrafica(db, monkeypatch):
    from app.services.handlers import fattura_handlers

    chiamate = []

    async def finto_ensure(_db, fattura, **_k):
        chiamate.append(fattura["supplier_vat"])
        return {"supplier_created": True, "supplier_id": "nuovo"}

    monkeypatch.setattr("app.routers.invoices.fatture_upload.ensure_supplier_exists", finto_ensure)
    run(db["invoices"].insert_one({"id": "f1", "supplier_vat": "03617950633", "supplier_name": "COFRUT"}))
    esito = run(fattura_handlers.on_fattura_created_garantisci_fornitore(
        {"fattura_id": "f1", "fornitore_piva": "03617950633"}, db))
    assert chiamate == ["03617950633"] and esito["fornitore_creato"] is True
    # senza P.IVA non c'e' niente da garantire
    assert run(fattura_handlers.on_fattura_created_garantisci_fornitore({"fattura_id": "f1"}, db)) is None


def test_handler_registrato_prima_degli_altri():
    from app.services import event_bus

    sorgente = open(event_bus.__file__, encoding="utf-8").read()
    assert sorgente.index("register_handler(EventTypes.FATTURA_CREATED, on_fattura_created_garantisci_fornitore)") \
        < sorgente.index("register_handler(EventTypes.FATTURA_CREATED, on_fattura_created_crea_partita)")
