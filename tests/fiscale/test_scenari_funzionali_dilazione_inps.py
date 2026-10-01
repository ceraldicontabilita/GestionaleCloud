"""Collaudo funzionale Dilazione INPS: il piano crea le rate, la quietanza giusta le paga.

ATTESO (CLAUDE.md, «Dilazione INPS»): il piano apre una rata per scadenza; la paga la quietanza con
sede, causale, matricola, periodo e importo al centesimo, dopo la domanda, in ordine; l'addebito e'
quello della quietanza; rata scaduta senza quietanza -> alert, che si chiude quando arriva.
"""
import asyncio

import pytest

from app.db_collections import COLL_QUIETANZE_F24
from app.services import dilazioni_inps as di
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from tests.fiscale.test_dilazioni_inps import PIANO, QUIETANZE, TESTO, _q


def _run(coro):
    return asyncio.run(coro)


def _db(quietanze=()):
    db = ClientArchivioMemoria()["inps-scenari"]

    async def carica():
        for q in quietanze:
            await db[COLL_QUIETANZE_F24].insert_one(dict(q))
        await di.deposita_piano(db, PIANO, documento_id="doc-1", filename="piano.pdf", sha256="abc")

    _run(carica())
    return db


def _stati(esito):
    return [(r["numero"], r["stato"]) for r in esito["rate"]]


def _con(q, **riga):
    """La stessa quietanza con una riga INPS modificata."""
    return {**q, "sezione_inps": [{**q["sezione_inps"][0], **riga}]}


@pytest.mark.parametrize("campo,valore", [
    ("codice_sede", "5101"),             # un'altra sede
    ("causale", "DM10"),                 # un'altra causale
    ("matricola", "5124776999"),         # un'altra matricola
    ("periodo_riferimento", "10/2025"),  # un altro periodo
])
def test_una_sola_coordinata_diversa_e_il_versamento_non_e_della_dilazione(campo, valore):
    q = _con(QUIETANZE[0], **{campo: valore})
    if campo == "periodo_riferimento":
        q = _con(QUIETANZE[0], periodo_riferimento=valore, periodo_raw="10 2025 10 2025")
    esito = di.abbina_rate(PIANO, [q], oggi="2026-03-07")
    assert esito["rate"][0]["stato"] == di.RATA_DA_PAGARE
    assert esito["rate"][0]["quietanza_ids"] == []
    assert esito["pagamenti_non_previsti"] == []        # non e' nemmeno un versamento «in piu'» della dilazione


def test_importo_al_centesimo_e_in_ordine_di_scadenza():
    """Rate 2, 3 e 4 sono tutte da 1.294,00: i tre versamenti le pagano nell'ordine delle date."""
    q = [QUIETANZE[3], QUIETANZE[1], QUIETANZE[2]]          # arrivati in disordine
    esito = di.abbina_rate(PIANO, q, oggi="2026-06-10")
    assert [(r["numero"], r["quietanza_ids"]) for r in esito["rate"][1:]] == [
        (2, ["q2"]), (3, ["q3"]), (4, ["q4"])]
    assert esito["rate"][0]["stato"] == di.RATA_SCADUTA


def test_una_quietanza_eliminata_non_paga_la_rata():
    esito = di.abbina_rate(PIANO, [{**QUIETANZE[0], "status": "eliminato"}], oggi="2026-03-10")
    assert esito["rate"][0]["stato"] == di.RATA_SCADUTA


def test_l_addebito_in_banca_e_quello_riscontrato_sulla_quietanza_non_uno_cercato_per_importo():
    senza_riscontro = {k: v for k, v in QUIETANZE[0].items() if k != "riscontro_banca"}
    esito = di.abbina_rate(PIANO, [senza_riscontro], oggi="2026-03-07")
    assert esito["rate"][0]["stato"] == di.RATA_PAGATA and esito["rate"][0]["movimento_id"] is None
    esito = di.abbina_rate(PIANO, [QUIETANZE[0]], oggi="2026-03-07")
    assert esito["rate"][0]["movimento_id"] == "m-0309"


def test_alert_per_la_rata_scaduta_e_non_per_quelle_future_e_si_chiude_con_la_quietanza():
    db = _db(QUIETANZE[:1])                                  # versata solo la prima rata
    esito = _run(di.collega_dilazioni(db, oggi="2026-04-20"))
    # scadute: rata 2 (08/04); non scadute: rata 3 (08/05), rata 4 (08/06)
    assert esito["scritti"]["alert_aperti"] == 1
    aperti = _run(db["alerts"].find({"codice": di.ALERT_RATA_NON_PAGATA}).to_list(10))
    assert len(aperti) == 1 and "rata 2/4" in aperti[0]["dettaglio"] and aperti[0]["entita_id"].endswith("#2")
    # nessun doppione ripassando
    assert _run(di.collega_dilazioni(db, oggi="2026-04-20"))["scritti"]["alert_aperti"] == 0
    assert len(_run(db["alerts"].find({"codice": di.ALERT_RATA_NON_PAGATA}).to_list(10))) == 1
    # arriva la quietanza della rata 2
    _run(db[COLL_QUIETANZE_F24].insert_one(dict(QUIETANZE[1])))
    chiuso = _run(di.collega_dilazioni(db, oggi="2026-04-20"))
    assert chiuso["scritti"]["alert_chiusi"] == 1
    dil = _run(db[di.COLL_DILAZIONI_INPS].find_one({"id": di.id_dilazione(PIANO)}))
    assert dil["rate_pagate"] == 2 and dil["residuo_cents"] == 1294_00 * 2


def test_la_rata_pagata_in_ritardo_e_pagata_e_non_apre_alert():
    db = _db([_q("t", "2026-03-20", 1293.0, "26032011002055014/000001")])
    esito = _run(di.collega_dilazioni(db, oggi="2026-03-21"))
    assert esito["scritti"]["alert_aperti"] == 0
    assert _run(db["alerts"].count_documents({"codice": di.ALERT_RATA_NON_PAGATA})) == 0
    assert esito["esiti"][0]["rate"][0]["oltre_scadenza"] is True


def test_il_versamento_con_importo_diverso_apre_l_alert_con_il_versamento_accanto_e_non_paga():
    db = _db([_q("x", "2026-04-08", 1294.01, "26030611002055014/000001")])
    _run(di.collega_dilazioni(db, oggi="2026-04-20"))
    dil = _run(db[di.COLL_DILAZIONI_INPS].find_one({"id": di.id_dilazione(PIANO)}))
    assert dil["rate_pagate"] == 0 and dil["rate"][0]["stato"] == di.RATA_IMPORTO_DIVERSO
    aperti = _run(db["alerts"].find({"codice": di.ALERT_RATA_NON_PAGATA}).to_list(10))
    assert any("1294.01" in a["dettaglio"] for a in aperti)
    q = _run(db[COLL_QUIETANZE_F24].find_one({"id": "x"}))
    assert q["dilazione_inps"]["importo_diverso"] is True


def test_un_piano_che_non_quadra_non_abbina_nulla_e_non_si_deposita():
    testo = TESTO.replace("1.294,00\n08/06/2026", "1.200,00\n08/06/2026")
    piano = di.leggi_piano(testo)
    assert piano["quadra"] is False
    db = ClientArchivioMemoria()["inps-non-quadra"]
    assert _run(di.deposita_piano(db, piano, documento_id="d", filename="p.pdf", sha256="x")) is None
    assert _run(db[di.COLL_DILAZIONI_INPS].count_documents({})) == 0
