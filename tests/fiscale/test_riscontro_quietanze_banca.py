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


def test_un_centesimo_di_differenza_e_solo_parziale_mai_certo():
    esito = _riscontri([_q("q1", "2026-08-20", 654.33)],
                       [_m("m1", "2026-08-20", -654.34, "20/08/2026")])
    assert esito["riscontrati"] == []
    [r] = esito["da_verificare"]
    assert r["livello"] == reg.LIVELLO_PARZIALE and r["differenza"] == 0.01
    assert "da verificare con il commercialista" in r["motivazione"]
    assert esito["addebiti_senza_quietanza"] == []


def test_una_data_incasso_diversa_e_un_altro_versamento():
    esito = _riscontri([_q("q1", "2026-04-08", 1294.00)],
                       [_m("m1", "2026-04-09", -1294.00, "09/04/2026")])
    assert esito["riscontrati"] == []


def test_oltre_due_giorni_lavorativi_non_e_lo_stesso_pagamento():
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

    esito = _run(reg.riconcilia_f24_banca(db))
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
    _run(reg.riconcilia_f24_banca(db))

    secondo = _run(reg.riconcilia_f24_banca(db))
    assert secondo["scritti"]["quietanze"] == 0
    assert secondo["scritti"]["addebiti"] == 0


def test_in_simulazione_non_si_scrive():
    db = _db([_q("q1", "2026-08-20", 654.33)], [_m("m1", "2026-08-20", -654.33, "20/08/2026")])
    esito = _run(reg.riconcilia_f24_banca(db, dry_run=True))

    assert esito["conteggi"]["riscontrati"] == 1
    assert "riscontro_banca" not in _run(db[COLL_QUIETANZE_F24].find_one({"id": "q1"}))


def test_l_addebito_orfano_apre_un_alert_che_si_chiude_all_arrivo_della_quietanza():
    db = _db([], [_m("m1", "2026-09-17", -9421.15, "16/09/2026")])
    _run(reg.riconcilia_f24_banca(db))
    aperti = _run(db["alerts"].find({"codice": reg.ALERT_ADDEBITO_SENZA_QUIETANZA,
                                     "stato": "aperto"}).to_list(10))
    assert [a["entita_id"] for a in aperti] == ["m1"]
    assert aperti[0]["extra"]["record"][0]["importo"] == 9421.15

    _run(db[COLL_QUIETANZE_F24].insert_one(_q("q1", "2026-09-16", 9421.15)))
    _run(reg.riconcilia_f24_banca(db))
    aperti = _run(db["alerts"].find({"codice": reg.ALERT_ADDEBITO_SENZA_QUIETANZA,
                                     "stato": "aperto"}).to_list(10))
    assert aperti == []


def test_all_arrivo_della_quietanza_si_guarda_solo_il_suo_importo():
    db = _db([_q("q1", "2026-08-20", 654.33)],
             [_m("m1", "2026-08-20", -654.33, "20/08/2026"),
              _m("m2", "2026-08-21", -111.11, "21/08/2026")])

    esito = _run(reg.riconcilia_f24_arrivato(db, 654.33))

    assert esito["riscontrati"] == 1
    assert esito["addebiti_senza_quietanza"] == 0  # m2 non e' stato nemmeno letto
    assert _run(db[COLL_QUIETANZE_F24].find_one({"id": "q1"}))["movimento_bancario_id"] == "m1"
    assert _run(db["alerts"].find({}).to_list(10)) == []  # gli alert li apre solo il giro


def test_la_causale_troncata_prende_la_data_incasso_dall_export_in_quarantena():
    """17/06/2026: resta la riga del vecchio archivio («I24 AGENZIA ENTRATE»),
    l'export ufficiale con «DATA INCASSO 16/06/2026» e' in quarantena come suo
    doppione. La data della banca vale lo stesso: il riscontro e' certo."""
    tenuta = {"id": "2026-06-17_-8139.63_I24_AGENZIA_ENTRATE", "data": "2026-06-17",
              "importo": -8139.63, "tipo": "uscita", "descrizione": "I24 AGENZIA ENTRATE",
              "causale": "I24 AGENZIA ENTRATE", "fonte": "legacy_staging_2026"}
    db = _db([_q("q1", "2026-06-16", 8139.63)], [tenuta])
    export = {"id": "EC-2026-06-17-8139.63-cee432330c22", "data": "2026-06-17", "importo": 8139.63,
              "tipo": "uscita", "duplicato_di": tenuta["id"],
              "descrizione": "I24 AGENZIA ENTRATE - PAG.TO TELEMATICO - DATA INCASSO 16/06/2026 "
                             "2026-06-16-22.34.20.770713000604"}
    _run(db["estratto_conto_movimenti_quarantena"].insert_one(export))

    esito = _run(reg.riconcilia_f24_banca(db))

    [r] = esito["riscontrati"]
    assert r["addebito"]["movimento_id"] == tenuta["id"]
    assert export["id"] in r["motivazione"]
    m = _run(db[COLL_ESTRATTO_CONTO].find_one({"id": tenuta["id"]}))
    assert m["descrizione"] == "I24 AGENZIA ENTRATE"  # la riga tenuta non si riscrive


def test_una_copia_in_quarantena_di_importo_diverso_non_presta_la_data():
    tenuta = _m("m1", "2026-06-17", -8139.63)
    db = _db([_q("q1", "2026-06-16", 8139.63)], [tenuta])
    _run(db["estratto_conto_movimenti_quarantena"].insert_one({
        "id": "x", "duplicato_di": "m1", "importo": 8139.64,
        "descrizione": "I24 AGENZIA ENTRATE - DATA INCASSO 16/06/2026"}))

    esito = _run(reg.riconcilia_f24_banca(db, dry_run=True))
    assert esito["riscontrati"] == [] and len(esito["da_verificare"]) == 1


# ── deleghe non programmate e tributi versati due volte ─────────────────────

def _q_righe(id_, data, saldo, protocollo, righe, **extra):
    return {**_q(id_, data, saldo, protocollo), "sezione_erario": [
        {"codice_tributo": c, "periodo_riferimento": p, "importo_debito": d, "importo_credito": cr}
        for c, p, d, cr in righe], **extra}


def test_il_protocollo_dice_quando_la_delega_e_stata_inviata():
    assert reg.data_invio_protocollo("26060212304532735/000001") == "2026-06-02"
    assert reg.data_invio_protocollo("26061631545528157/000001") == "2026-06-16"
    assert reg.data_invio_protocollo("") is None
    assert reg.data_invio_protocollo("99999999999/1") is None


def test_programmata_non_programmata_tipo_e_senza_modello():
    programmata = _q_righe("q1", "2026-06-16", 1969.10, "26060212304532735/000001",
                           [("3918", "2026", 3574.00, 0), ("6099", "01/2025", 0, 1604.90)])
    ravvedimento = _q_righe("q2", "2026-07-21", 286.00, "26072135472143961/000001",
                            [("1040", "06/2026", 284.00, 0), ("8948", "06/2026", 2.00, 0)])
    [p1, p2] = sorted(reg.pagamenti_da_quietanze(reg._quietanza_legacy(q) for q in (programmata, ravvedimento)),
                      key=lambda p: p["data"])
    assert (p1["inviato_il"], p1["programmato"], p1["tipo_versamento"], p1["senza_modello"]) == (
        "2026-06-02", True, "ordinario", True)
    assert (p2["programmato"], p2["tipo_versamento"]) == (False, "ravvedimento")


def test_lo_stesso_tributo_in_due_deleghe_dello_stesso_giorno_si_segnala():
    """16/06/2026: IMU 3918 e credito 6099 in una delega programmata e in una
    inviata il giorno stesso, entrambe addebitate."""
    righe = [("3918", "2026", 3574.00, 0), ("6099", "01/2025", 0, 1604.90)]
    q1 = _q_righe("q1", "2026-06-16", 1969.10, "26060212304532735/000001", righe)
    q2 = _q_righe("q2", "2026-06-16", 2179.10, "26061631545528157/000001",
                  righe + [("1040", "05/2026", 210.00, 0)])
    esito = _riscontri([q1, q2], [_m("m1", "2026-06-17", -1969.10, "16/06/2026"),
                                  _m("m2", "2026-06-17", -2179.10, "16/06/2026")])

    [t] = esito["tributi_ripetuti"]
    assert "3918 2026 3574.00" in t["righe"] and "1040" not in t["righe"]
    assert "inviata il 02/06/2026, addebitata il 17/06/2026" in t["motivazione"]
    assert "inviata il 16/06/2026" in t["motivazione"]
    assert {p["programmato"] for p in t["pagamenti"]} == {True, False}


def test_le_rate_mensili_non_sono_tributi_ripetuti():
    """RC01 09/2025 da 1.294,00 EUR pagato ogni mese: stessa riga, giorni diversi."""
    rate = [{**_q("q%d" % i, d, 1294.00, "2604081%d000000000/000001" % i), "sezione_inps": [
        {"causale": "RC01", "periodo_da": "09/2025", "importo_debito": 1294.00}]}
        for i, d in enumerate(("2026-04-08", "2026-05-08", "2026-06-08"))]
    assert _riscontri(rate, [])["tributi_ripetuti"] == []


def test_due_copie_della_stessa_delega_non_sono_un_tributo_ripetuto():
    righe = [("3918", "2026", 3574.00, 0)]
    copie = [_q_righe(i, "2026-06-16", 3574.00, "26060212304532735/000001", righe) for i in ("q1", "q2")]
    assert _riscontri(copie, [])["tributi_ripetuti"] == []


def test_il_tributo_ripetuto_apre_un_alert_con_le_due_deleghe():
    righe = [("3918", "2026", 3574.00, 0)]
    db = _db([_q_righe("q1", "2026-06-16", 3574.00, "26060212304532735/000001", righe),
              _q_righe("q2", "2026-06-16", 3784.00, "26061631545528157/000001",
                       righe + [("1040", "05/2026", 210.00, 0)])], [])
    _run(reg.riconcilia_f24_banca(db))
    [a] = _run(db["alerts"].find({"codice": reg.ALERT_TRIBUTO_DUE_VOLTE}).to_list(10))
    assert len(a["extra"]["record"]) == 2

    _run(reg.riconcilia_f24_banca(db))  # il secondo giro non ne apre un altro
    assert len(_run(db["alerts"].find({"codice": reg.ALERT_TRIBUTO_DUE_VOLTE}).to_list(10))) == 1
