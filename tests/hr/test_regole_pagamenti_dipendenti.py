import asyncio

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

from app.hr.services.regole_pagamenti_dipendenti import (
    bonifica_storico, filtra_acconti_contanti, valuta_contanti,
)


def run(coro):
    return asyncio.run(coro)


def test_contanti_post_2018_solo_dopo_cessazione_con_data():
    attivo = {"id": "d1", "stato": "attivo", "attivo": True}
    cessato = {"id": "d1", "stato": "cessato", "attivo": False,
               "data_fine_rapporto": "2026-07-15"}

    assert valuta_contanti(attivo, "2018-06-30")[0] is True
    assert valuta_contanti(attivo, "2018-07-01")[:2] == (False, "rapporto_in_corso")
    assert valuta_contanti(cessato, "2026-07-14")[:2] == (
        False, "pagamento_anteriore_alla_cessazione")
    assert valuta_contanti(cessato, "2026-07-15") == (
        True, "pagamento_post_cessazione", "2026-07-15")


def test_filtro_non_fa_entrare_nel_saldo_i_contanti_di_un_attivo():
    validi, scartati = filtra_acconti_contanti(
        {"stato": "attivo", "attivo": True},
        [{"data": "2026-08-01", "importo": 108.0}],
    )
    assert validi == []
    assert scartati[0]["dettaglio_motivo"] == "rapporto_in_corso"


def test_bonifica_storico_e_reversibile_e_promuove_la_prova_con_nome_univoco():
    db = AsyncMongoMockClient()["hr_regole_pagamenti"]
    run(db.dipendenti.insert_one({
        "id": "dip-vespa", "nome": "Vincenzo", "cognome": "Vespa",
        "nome_completo": "Vespa Vincenzo", "codice_fiscale": "VSPVCN67T26F839P",
        "stato": "attivo", "attivo": True,
    }))
    run(db.paghe_mensili.insert_one({
        "dipendente_id": "dip-vespa", "anno": 2026, "mese": 7,
        "importo_busta": 1377.0, "bonifico_importo": 1377.0,
        "acconti": [{"data": "2026-07-20", "importo": 108.0}],
        "stato_pagamento": "pagato", "saldo": -108.0,
    }))
    run(db.pagamenti_esiti.insert_one({
        "key": "ecm:m-1", "dipendente_id": "dip-vespa", "anno": 2026, "mese": 7,
        "data": "2026-08-06", "importo": 1377.0,
        "beneficiario": "Vespa Vincenzo",
        "causale": "VS.DISP. RIF. MB0B00923006 FAVORE Vespa Vincenzo",
        "origine": "gestionale-estratto-conto",
    }))

    anteprima = run(bonifica_storico(db, dry_run=True))
    assert anteprima["movimenti_contanti_scartati"] == 1
    assert anteprima["prove_promosse_certe"] == 1
    assert run(db.paghe_mensili.find_one({}))["saldo"] == -108.0

    esito = run(bonifica_storico(db, dry_run=False))
    assert esito["mesi_con_contanti_corretti"] == 1
    paga = run(db.paghe_mensili.find_one({}, {"_id": 0}))
    assert paga["acconti"] == []
    assert paga["acconti_scartati_regola_2018"][0]["importo"] == 108.0
    assert paga["saldo"] == 0.0
    assert paga["bonifico_riconciliato_auto"] is True
    prova = run(db.pagamenti_esiti.find_one({}, {"_id": 0}))
    assert prova["associazione_certa"] is True
    assert prova["associazione_certa_motivo"] == "nome"

    ancora = run(bonifica_storico(db, dry_run=False))
    assert ancora["gia_completato"] is True


def test_endpoint_acconti_blocca_attivo_e_salva_la_cessazione(monkeypatch):
    from app.hr.routers import dipendenti_cloud as router

    db = AsyncMongoMockClient()["hr_endpoint_contanti"]
    run(db.dipendenti.insert_one({"id": "d1", "stato": "attivo", "attivo": True}))
    monkeypatch.setattr(router, "get_db", lambda: db)
    payload = router.AccontiCloud(
        dipendente_id="d1", anno=2026, mese=7,
        acconti=[{"data": "2026-07-31", "importo": 100}],
    )
    with pytest.raises(HTTPException) as exc:
        run(router.imposta_acconti(payload))
    assert exc.value.status_code == 422

    run(db.dipendenti.update_one(
        {"id": "d1"},
        {"$set": {"stato": "cessato", "attivo": False,
                  "in_carico": False, "data_fine_rapporto": "2026-07-15"}},
    ))
    esito = run(router.imposta_acconti(payload))
    assert esito["ok"] is True
    paga = run(db.paghe_mensili.find_one({}, {"_id": 0}))
    assert paga["acconti"] == [{"data": "2026-07-31", "importo": 100.0,
                                "data_cessazione_rapporto": "2026-07-15"}]
