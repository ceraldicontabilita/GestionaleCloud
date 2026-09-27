"""Quietanza F24 ↔ addebito I24: due prove dello stesso pagamento, collegate.

Al 27/09/2026 il motore canonico abbinava la banca ai soli modelli F24, e 242
pagamenti su 328 avevano la sola quietanza: i loro addebiti restavano orfani.
Qui si provano le regole del riscontro, sui formati veri delle causali BPM:

- certo solo con importo uguale al centesimo e la «DATA INCASSO» della causale
  uguale alla data della quietanza; senza quella data e' da verificare;
- mai una tolleranza sull'importo, mai un candidato scelto fra due;
- due copie della stessa quietanza sono un pagamento solo, ma lo stesso
  protocollo con importi diversi sono due pagamenti;
- l'addebito non diventa «riconciliato» e il modello F24 non si ricostruisce.
"""
import asyncio

from app.db_collections import COLL_ESTRATTO_CONTO, COLL_QUIETANZE_F24
from app.services import f24_controllo_incrociato as reg
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def _run(coroutine):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


def _q(id_, data, saldo, protocollo="26082011065626134/000001"):
    """Una quietanza come la salva quietanze_import."""
    return {"id": id_, "data_pagamento": data, "saldo": saldo,
            "protocollo_telematico": protocollo, "filename": f"{id_}.pdf", "f24_associati": []}


def _m(id_, data, importo, incasso=None, rif="2026-08-19-22.35.33.939744076309"):
    causale = "I24 AGENZIA ENTRATE - PAG.TO TELEMATICO"
    if incasso:
        causale += f" - DATA INCASSO {incasso} {rif}"
    return {"id": id_, "data": data, "importo": importo, "descrizione": causale, "tipo": "uscita"}


def _riscontri(quietanze, movimenti):
    return reg.riscontri_quietanze_banca([reg._quietanza_legacy(q) for q in quietanze], movimenti)


# ── le regole dell'abbinamento ─────────────────────────────────────────────

def test_importo_e_data_incasso_uguali_fanno_un_riscontro_certo():
    esito = _riscontri([_q("q1", "2026-08-20", 654.33)],
                       [_m("m1", "2026-08-20", -654.33, "20/08/2026")])

    [r] = esito["riscontrati"]
    assert r["stato"] == reg.RISCONTRO_CERTO
    assert r["addebito"]["movimento_id"] == "m1"
    assert "654.33 EUR uguale al centesimo" in r["motivazione"]
    assert "DATA INCASSO nella causale: 20/08/2026" in r["motivazione"]


def test_l_addebito_del_lunedi_paga_la_quietanza_del_venerdi():
    esito = _riscontri([_q("q1", "2026-01-16", 5600.93)],
                       [_m("m1", "2026-01-19", -5600.93, "16/01/2026")])
    assert len(esito["riscontrati"]) == 1


def test_senza_data_incasso_nella_causale_e_solo_da_verificare():
    esito = _riscontri([_q("q1", "2026-06-16", 8139.63)],
                       [_m("m1", "2026-06-17", -8139.63)])

    assert esito["riscontrati"] == []
    [r] = esito["da_verificare"]
    assert "non riporta la data d'incasso" in r["motivazione"]


def test_un_centesimo_di_differenza_non_abbina():
    esito = _riscontri([_q("q1", "2026-08-20", 654.33)],
                       [_m("m1", "2026-08-20", -654.34, "20/08/2026")])
    assert esito["riscontrati"] == [] and esito["da_verificare"] == []
    assert len(esito["addebiti_senza_quietanza"]) == 1


def test_una_data_incasso_diversa_e_un_altro_versamento():
    esito = _riscontri([_q("q1", "2026-04-08", 1294.00)],
                       [_m("m1", "2026-04-09", -1294.00, "09/04/2026")])
    assert esito["riscontrati"] == []


def test_oltre_quattro_giorni_non_e_lo_stesso_pagamento():
    esito = _riscontri([_q("q1", "2026-03-06", 1293.00)],
                       [_m("m1", "2026-03-11", -1293.00)])
    assert esito["riscontrati"] == [] and esito["da_verificare"] == []


def test_due_addebiti_compatibili_restano_candidati():
    esito = _riscontri([_q("q1", "2026-06-16", 915.00)],
                       [_m("m1", "2026-06-17", -915.00), _m("m2", "2026-06-18", -915.00)])

    [r] = esito["da_verificare"]
    assert {c["movimento_id"] for c in r["candidati"]} == {"m1", "m2"}
    assert esito["riscontrati"] == []


def test_due_copie_della_stessa_quietanza_sono_un_pagamento():
    esito = _riscontri(
        [_q("q1", "2026-04-08", 1294.00, "26030611002055014/000001"),
         _q("q2", "2026-04-08", 1294.00, "26030611002055014/000001")],
        [_m("m1", "2026-04-08", -1294.00, "08/04/2026")],
    )
    [r] = esito["riscontrati"]
    assert {q["id"] for q in r["quietanze"]} == {"q1", "q2"}


def test_stesso_protocollo_importi_diversi_sono_due_pagamenti():
    """Dallo stesso PDF escono deleghe diverse con lo stesso protocollo."""
    esito = _riscontri(
        [_q("q1", "2023-08-21", 5959.18, "23081114592059905/000001"),
         _q("q2", "2023-08-21", 12.95, "23081114592059905/000001")],
        [],
    )
    assert esito["conteggi"]["pagamenti"] == 2


def test_un_bollettino_cbill_non_e_una_delega_f24():
    cbill = {"id": "m1", "data": "2026-03-16", "importo": -781.60, "tipo": "uscita",
             "descrizione": "BOLL.CBILL AGENZIA DELLE ENTRATE - R CBILL 180071115977917838"}
    esito = _riscontri([], [cbill])
    assert esito["addebiti_senza_quietanza"] == []


def test_un_addebito_i24_senza_quietanza_va_riscaricato():
    esito = _riscontri([], [_m("m1", "2026-09-17", 9421.15, "16/09/2026")])
    [a] = esito["addebiti_senza_quietanza"]
    assert "riscaricare dal Cassetto Fiscale" in a["motivazione"]


def test_quietanza_senza_addebito_solo_se_l_estratto_copre_quei_giorni():
    movimenti = [_m("m0", "2026-01-16", -535.70, "16/01/2026"),
                 _m("m9", "2026-09-17", -104.54, "16/09/2026")]
    dentro = _riscontri([_q("q1", "2026-05-18", 777.00)], movimenti)
    fuori = _riscontri([_q("q1", "2025-05-16", 777.00)], movimenti)

    assert len(dentro["quietanze_senza_addebito"]) == 1
    assert fuori["quietanze_senza_addebito"] == []
    assert fuori["conteggi"]["fuori_periodo_estratto"] == 1


def test_una_quietanza_senza_saldo_letto_si_dichiara_incompleta():
    esito = _riscontri([_q("q1", "2026-05-18", 0)], [])
    [q] = esito["quietanze_incomplete"]
    assert q["motivo"] == "saldo non letto"


# ── la scrittura ───────────────────────────────────────────────────────────

def _db(quietanze, movimenti):
    db = ClientArchivioMemoria()["gestionale_test"]

    async def _carica():
        for q in quietanze:
            await db[COLL_QUIETANZE_F24].insert_one(dict(q))
        for m in movimenti:
            await db[COLL_ESTRATTO_CONTO].insert_one(dict(m))
    _run(_carica())
    return db


def test_il_riscontro_si_scrive_su_quietanze_e_addebito_senza_riconciliare():
    db = _db([_q("q1", "2026-08-20", 654.33), _q("q2", "2026-08-20", 654.33)],
             [_m("m1", "2026-08-20", -654.33, "20/08/2026")])

    esito = _run(reg.riscontra_quietanze_banca(db))
    assert esito["scritti"]["quietanze"] == 2

    q = _run(db[COLL_QUIETANZE_F24].find_one({"id": "q1"}))
    assert q["riscontro_banca"]["stato"] == reg.RISCONTRO_CERTO
    assert q["movimento_bancario_id"] == "m1"
    m = _run(db[COLL_ESTRATTO_CONTO].find_one({"id": "m1"}))
    assert m["quietanze_f24_ids"] == ["q1", "q2"]
    assert not m.get("riconciliato")  # il modello F24 resta da caricare
    assert q["f24_associati"] == []   # e non si ricostruisce dalla quietanza


def test_il_secondo_giro_non_riscrive_niente():
    db = _db([_q("q1", "2026-08-20", 654.33)], [_m("m1", "2026-08-20", -654.33, "20/08/2026")])
    _run(reg.riscontra_quietanze_banca(db))

    secondo = _run(reg.riscontra_quietanze_banca(db))
    assert secondo["scritti"]["quietanze"] == 0
    assert secondo["scritti"]["addebiti"] == 0


def test_in_simulazione_non_si_scrive():
    db = _db([_q("q1", "2026-08-20", 654.33)], [_m("m1", "2026-08-20", -654.33, "20/08/2026")])
    esito = _run(reg.riscontra_quietanze_banca(db, dry_run=True))

    assert esito["conteggi"]["riscontrati"] == 1
    assert "riscontro_banca" not in _run(db[COLL_QUIETANZE_F24].find_one({"id": "q1"}))


def test_l_addebito_orfano_apre_un_alert_che_si_chiude_all_arrivo_della_quietanza():
    db = _db([], [_m("m1", "2026-09-17", -9421.15, "16/09/2026")])
    _run(reg.riscontra_quietanze_banca(db))
    aperti = _run(db["alerts"].find({"codice": reg.ALERT_ADDEBITO_SENZA_QUIETANZA,
                                     "stato": "aperto"}).to_list(10))
    assert [a["entita_id"] for a in aperti] == ["m1"]
    assert aperti[0]["extra"]["record"][0]["importo"] == 9421.15

    _run(db[COLL_QUIETANZE_F24].insert_one(_q("q1", "2026-09-16", 9421.15)))
    _run(reg.riscontra_quietanze_banca(db))
    aperti = _run(db["alerts"].find({"codice": reg.ALERT_ADDEBITO_SENZA_QUIETANZA,
                                     "stato": "aperto"}).to_list(10))
    assert aperti == []


def test_all_arrivo_della_quietanza_si_guarda_solo_il_suo_importo():
    db = _db([_q("q1", "2026-08-20", 654.33)],
             [_m("m1", "2026-08-20", -654.33, "20/08/2026"),
              _m("m2", "2026-08-21", -111.11, "21/08/2026")])

    esito = _run(reg.riscontra_quietanza_arrivata(db, 654.33))

    assert esito["riscontrati"] == 1
    assert esito["addebiti_senza_quietanza"] == 0  # m2 non e' stato nemmeno letto
    assert _run(db[COLL_QUIETANZE_F24].find_one({"id": "q1"}))["movimento_bancario_id"] == "m1"
    assert _run(db["alerts"].find({}).to_list(10)) == []  # gli alert li apre solo il giro
