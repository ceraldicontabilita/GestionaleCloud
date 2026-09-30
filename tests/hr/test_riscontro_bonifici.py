"""Riscontro bonifico <-> busta: stati, confidenza, fonte, sola lettura.

Stessa forma del ``riscontro`` del minisito (``cedolini_canonici.json``):
confermato / da_verificare / differenza / nessun_bonifico_trovato /
non_riscontrabile, con la priorita' manuale > ricevuta > estratto.
"""
import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.constants.stati_associazione_bonifico import (
    CONFIDENZA_ALTA_CAUSALE,
    CONFIDENZA_MEDIA_IMPORTO,
    FONTE_ESTRATTO,
    FONTE_MANUALE,
    FONTE_RICEVUTA,
    STATI_RISCONTRO,
)
from app.services.riscontro_bonifici import riscontra_busta, riscontro_periodo


def _run(coro):
    return asyncio.run(coro)


def _paga(mese=1, anno=2025, netto=297.77, **extra):
    return {"dipendente_id": "d1", "anno": anno, "mese": mese, "importo_busta": netto, **extra}


def _esito(importo, key="gc:1", origine="gestionale-bonifico-pdf", causale="stipendio", **extra):
    return {"key": key, "dipendente_id": "d1", "mese": 1, "anno": 2025, "importo": importo,
            "data": "2025-02-19", "cro": "CRO1", "origine": origine, "causale": causale, **extra}


def test_un_solo_bonifico_d_importo_uguale_e_riconciliato_e_media_confidenza():
    r = riscontra_busta(_paga(bonifico_riconciliato=True), [_esito(297.77)])
    assert r["stato"] == "confermato" and r["confidenza"] == CONFIDENZA_MEDIA_IMPORTO
    assert r["fonte"] == FONTE_RICEVUTA
    assert r["totale_bonifici_cents"] == 29777 and r["differenza_cents"] == 0
    assert r["bonifici"][0]["id"] == "gc:1" and r["bonifici"][0]["cro"] == "CRO1"


def test_solo_importo_senza_riconciliazione_resta_da_verificare():
    """L'importo da solo non conferma: CLAUDE.md, nessuna entita' per solo importo."""
    r = riscontra_busta(_paga(), [_esito(297.77)])
    assert r["stato"] == "da_verificare" and r["confidenza"] is None


def test_causale_che_scrive_il_periodo_e_alta_confidenza():
    r = riscontra_busta(_paga(netto=549.0), [_esito(549.0, causale="stipendio gennaio 2025")])
    assert r["stato"] == "confermato" and r["confidenza"] == CONFIDENZA_ALTA_CAUSALE


def test_differenza_col_netto_e_con_segno():
    # pagato piu' del netto: differenza negativa come nel golden (2 - 564 = -562)
    r = riscontra_busta(_paga(netto=2.0), [_esito(564.0, causale="stipendio gennaio 2025")])
    assert r["stato"] == "differenza" and r["differenza_cents"] == 200 - 56400
    # pagato meno del netto
    r = riscontra_busta(_paga(netto=600.0), [_esito(500.0, causale="stipendio gennaio 2025")])
    assert r["stato"] == "differenza" and r["differenza_cents"] == 10000


def test_piu_bonifici_senza_prova_sono_da_verificare_e_si_elencano():
    r = riscontra_busta(_paga(netto=15.0, mese=12, anno=2024),
                        [_esito(952.03, key="a"), _esito(297.77, key="b")])
    assert r["stato"] == "da_verificare" and [b["id"] for b in r["bonifici"]] == ["a", "b"]


def test_priorita_delle_fonti_manuale_poi_ricevuta_poi_estratto():
    est = _esito(100.0, key="ecm:1", origine="gestionale-estratto-conto")
    ric = _esito(100.0, key="gc:2")
    man = _esito(100.0, key="beneficiari-diversi:q1", origine=None, confermato_manuale=True)
    assert riscontra_busta(_paga(netto=100.0), [est])["fonte"] == FONTE_ESTRATTO
    assert riscontra_busta(_paga(netto=100.0), [est, ric])["fonte"] == FONTE_RICEVUTA
    r = riscontra_busta(_paga(netto=100.0), [est, ric, man])
    assert r["fonte"] == FONTE_MANUALE
    assert r["stato"] == "differenza"  # tre pagamenti da 100 su un netto da 100: c'e' prova, non quadra
    # la conferma del titolare e' la prova: confermato, confidenza vuota (la dice la fonte)
    assert riscontra_busta(_paga(netto=100.0), [man])["stato"] == "confermato"
    assert riscontra_busta(_paga(netto=100.0), [man])["confidenza"] is None


def test_nessun_bonifico_e_non_riscontrabile_prima_dei_dati_bancari():
    assert riscontra_busta(_paga(mese=8, anno=2024), [])["stato"] == "nessun_bonifico_trovato"
    # giugno 2024 finisce prima del 26/07/2024: non e' «senza bonifico», non si puo' dire
    r = riscontra_busta(_paga(mese=6, anno=2024), [])
    assert r["stato"] == "non_riscontrabile" and r["differenza_cents"] is None
    # ma un bonifico depositato vale anche prima
    assert riscontra_busta(_paga(mese=6, anno=2024), [_esito(297.77)])["stato"] != "non_riscontrabile"


def test_gli_stati_sono_solo_quelli_dichiarati():
    for paga, esiti in ((_paga(), []), (_paga(mese=1, anno=2020), []), (_paga(), [_esito(1.0)])):
        assert riscontra_busta(paga, esiti)["stato"] in STATI_RISCONTRO


def test_riscontro_periodo_e_di_sola_lettura_e_senza_pdf():
    db = AsyncMongoMockClient()["hr_riscontro"]
    _run(db.dipendenti.insert_one({"id": "d1", "nome": "Luigi", "cognome": "Taiano", "nome_completo": "Taiano Luigi"}))
    _run(db.paghe_mensili.insert_many([
        _paga(mese=1, bonifico_riconciliato=True, stato_pagamento="pagato"),
        _paga(mese=2, netto=500.0, stato_pagamento="in_attesa_pagamento"),
        _paga(mese=1, anno=2024, netto=100.0),
    ]))
    _run(db.pagamenti_esiti.insert_one({**_esito(297.77), "pdf_data": "QUJD"}))
    prima = {n: _run(db[n].find({}, {"_id": 0}).to_list(None))
             for n in ("paghe_mensili", "pagamenti_esiti", "dipendenti")}

    out = _run(riscontro_periodo(db, anno=2025))

    assert out["count"] == 2 and out["conteggi"] == {"nessun_bonifico_trovato": 1, "confermato": 1}
    assert [r["mese"] for r in out["righe"]] == [2, 1]  # il piu' recente per primo
    assert out["righe"][1]["dipendente"] == "Taiano Luigi"
    assert "pdf_data" not in str(out)
    dopo = {n: _run(db[n].find({}, {"_id": 0}).to_list(None)) for n in prima}
    assert dopo == prima  # nessuna scrittura
    # 2024: senza dati bancari
    assert _run(riscontro_periodo(db, anno=2024))["righe"][0]["stato"] == "non_riscontrabile"
