"""Modello F24 senza protocollo → quietanza per stesso codice e periodo, importo diverso, conferma del titolare."""
import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.services import f24_proposte_quietanza as prop


def run(coro):
    return asyncio.run(coro)


def _riga(sezione_codice, mese, anno, debito):
    return {"codice_tributo": sezione_codice, "anno": str(anno), "mese": f"{mese:02d}",
            "importo_debito_cents": debito, "importo_credito_cents": 0}


def _db():
    db = AsyncMongoMockClient()["prop"]
    run(db["f24_unificato"].insert_one({
        "id": "m1", "status": "da_pagare", "file_name": "modello agosto 2025.pdf",
        "dati_generali": {"data_versamento": "2025-08-20", "saldo_delega_cents": 704360},
        "sezione_erario": [_riga("1001", 7, 2025, 167601)],
        "sezione_inps": [{"causale": "CXX", "anno": "2025", "mese": "07", "importo_debito_cents": 175200,
                          "importo_credito_cents": 0},
                         {"causale": "DM10", "anno": "2025", "mese": "07", "importo_debito_cents": 580400,
                          "importo_credito_cents": 0}],
    }))
    # Ravvedimento: stessi tributi e periodi, importi con interessi, data diversa.
    run(db["quietanze_f24"].insert_one({
        "id": "q1", "filename": "Quietanza_ravvedimento.pdf", "protocollo_telematico": "25092200000000001",
        "dati_generali": {"data_pagamento": "2025-09-22"}, "saldo_delega": "7100.00",
        "sezione_erario": [_riga("1001", 7, 2025, 168000)],
        "sezione_inps": [{"causale": "CXX", "anno": "2025", "mese": "07", "importo_debito_cents": 175600,
                          "importo_credito_cents": 0},
                         {"causale": "DM10", "anno": "2025", "mese": "07", "importo_debito_cents": 581000,
                          "importo_credito_cents": 0}],
    }))
    # Un'altra quietanza con una sola riga in comune: rumore, non un candidato.
    run(db["quietanze_f24"].insert_one({
        "id": "q2", "filename": "altra.pdf", "dati_generali": {"data_pagamento": "2025-08-20"},
        "saldo_delega": "100.00", "sezione_erario": [_riga("1001", 7, 2025, 10000)],
    }))
    return db


def test_propone_per_tributo_e_periodo_con_la_differenza():
    esito = run(prop.proposte_per_modello(_db(), "m1"))
    ids = [c["quietanza_id"] for c in esito["candidati"]]
    assert ids == ["q1"]                                   # q2 ha una sola riga in comune: scartata
    c = esito["candidati"][0]
    assert c["copertura"] == "3/3" and c["tutte_identiche"] is False
    per_codice = {r["codice"]: r for r in c["righe_corrispondenti"]}
    assert per_codice["1001"]["differenza_cents"] == 399
    assert per_codice["CXX"]["differenza_cents"] == 400
    assert c["differenza_totale_cents"] == 399 + 400 + 600
    assert c["pdf_url"]                                    # l'originale della quietanza si apre


def test_la_conferma_scrive_il_collegamento_ma_non_prova_la_banca():
    db = _db()
    with pytest.raises(prop.CollegamentoNonAmmesso) as e:   # fuori dai candidati: 409
        run(prop.conferma_collegamento_quietanza(db, f24_id="m1", quietanza_id="q2", motivo="altro",
                                                 motivo_testo="prova"))
    assert e.value.code == "QUIETANZA_NON_CANDIDATA"
    with pytest.raises(prop.CollegamentoNonAmmesso) as e:   # motivo fuori elenco: 422
        run(prop.conferma_collegamento_quietanza(db, f24_id="m1", quietanza_id="q1", motivo="boh"))
    assert e.value.stato == 422
    esito = run(prop.conferma_collegamento_quietanza(
        db, f24_id="m1", quietanza_id="q1", motivo="ravvedimento_stesso_tributo", utente="titolare"))
    assert esito["collegato"] and esito["protocollo"] == "25092200000000001"
    m = run(db["f24_unificato"].find_one({"id": "m1"}))
    assert m["quietanza_id"] == "q1" and m["pagamento_verificato_banca"] is False and m["pagato"] is False
    assert m["collegamento_quietanza_titolare"]["differenza_totale_cents"] == 1399
    assert "m1" in run(db["quietanze_f24"].find_one({"id": "q1"}))["f24_associati"]
    # Un secondo collegamento sullo stesso modello e' rifiutato.
    with pytest.raises(prop.CollegamentoNonAmmesso) as e:
        run(prop.conferma_collegamento_quietanza(db, f24_id="m1", quietanza_id="q1",
                                                 motivo="ravvedimento_stesso_tributo"))
    assert e.value.code == "MODELLO_GIA_COLLEGATO"
