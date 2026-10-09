"""PagoPA, cartelle e TARI: un documento si lega solo al SUO movimento.

Prima si prendeva il primo movimento con una parola generica («pagopa») e lo si
legava a ogni documento, senza guardare l'importo e riusandolo per tutti.
"""
import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.services import riconciliazione_completa as rc


def run(c):
    return asyncio.run(c)


def _db():
    db = AsyncMongoMockClient()["Test"]
    run(db.estratto_conto_movimenti.insert_many([
        {"id": "m1", "tipo": "uscita", "descrizione": "PAGOPA COMUNE DI NAPOLI 301000000000123456", "importo": -120.00, "data_contabile": "2026-05-02"},
        {"id": "m2", "tipo": "uscita", "descrizione": "PAGOPA PARTENOPAY", "importo": -45.50, "data_contabile": "2026-05-10"},
        {"id": "m3", "tipo": "uscita", "descrizione": "PAGOPA PARTENOPAY", "importo": -45.50, "data_contabile": "2026-06-10"},
    ]))
    return db


def test_per_iuv_per_importo_e_mai_due_volte_lo_stesso():
    db = _db()
    run(db.documenti_non_associati.insert_many([
        {"id": "d1", "categoria_mittente": "Comune di Napoli", "filename": "avviso_301000000000123456.pdf"},
        {"id": "d2", "categoria_mittente": "Comune di Napoli", "filename": "avviso.pdf", "email_subject": "Verbale 99,00"},
        {"id": "d3", "categoria_mittente": "Comune di Napoli", "filename": "senza_nulla.pdf"},
        {"id": "d4", "categoria_mittente": "Comune di Napoli", "filename": "rata.pdf", "email_subject": "Importo 45,50"},
    ]))
    stats = run(rc.riconcilia_pagopa_con_banca(db))
    docs = {d["id"]: d for d in run(db.documenti_non_associati.find({}, {"_id": 0}).to_list(10))}
    assert docs["d1"]["movimento_banca_id"] == "m1"          # IUV
    assert not docs["d2"].get("riconciliato")                # importo che non c'e'
    assert not docs["d3"].get("riconciliato")                # nessun riferimento
    assert not docs["d4"].get("riconciliato")                # due movimenti da 45,50: ambiguo
    assert stats == {"analizzati": 4, "riconciliati": 1, "non_trovati": 1, "ambigui": 1, "senza_riferimenti": 1}


def test_un_movimento_gia_usato_non_si_riusa():
    db = _db()
    run(db.documenti_non_associati.insert_many([
        {"id": "gia", "riconciliato": True, "movimento_banca_id": "m2"},
        {"id": "d5", "categoria_mittente": "Comune di Napoli", "filename": "x.pdf", "importo": 45.5},
    ]))
    run(rc.riconcilia_pagopa_con_banca(db))
    d5 = run(db.documenti_non_associati.find_one({"id": "d5"}))
    assert d5["movimento_banca_id"] == "m3"


def test_tari_non_prende_il_primo_movimento_per_tutti():
    db = AsyncMongoMockClient()["Test"]
    run(db.estratto_conto_movimenti.insert_one(
        {"id": "t1", "tipo": "uscita", "descrizione": "F24 TARI", "importo": -300.0}))
    run(db.documenti_non_associati.insert_many([
        {"id": "a", "filename": "TARI_2026_rata1.pdf", "importo": 300.0},
        {"id": "b", "filename": "TARI_2026_rata2.pdf", "importo": 300.0},
    ]))
    stats = run(rc.riconcilia_tari_con_banca(db))
    assert stats["riconciliati"] == 1
