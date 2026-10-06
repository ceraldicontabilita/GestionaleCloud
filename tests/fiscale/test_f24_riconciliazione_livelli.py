"""RST-F24B: un solo motore F24 ↔ banca, a livelli.

CERTO scrive il pagamento; PROBABILE, PARZIALE, NESSUN_MATCH e
MOVIMENTO_ORFANO lo dichiarano soltanto (relazione ``pending``), mai un
pagamento. Due candidati non si scelgono. Un estratto che non c'e' non e' un
pagamento che manca.
"""
import asyncio
import importlib.util
from datetime import date

from app.db_collections import COLL_ENTITY_RELATIONS, COLL_ESTRATTO_CONTO, COLL_F24, COLL_QUIETANZE_F24
from app.services import calendario_lavorativo as cal
from app.services import f24_controllo_incrociato as reg
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _q(id_, data, saldo, protocollo="26082011065626134/000001"):
    return {"id": id_, "data_pagamento": data, "saldo": saldo,
            "protocollo_telematico": protocollo, "filename": f"{id_}.pdf", "f24_associati": []}


def _m(id_, data, importo, incasso=None):
    causale = "I24 AGENZIA ENTRATE - PAG.TO TELEMATICO"
    if incasso:
        causale += f" - DATA INCASSO {incasso} 2026-08-19-22.35.33.939744076309"
    return {"id": id_, "data": data, "importo": importo, "descrizione": causale, "tipo": "uscita"}


def _modello(id_, data, saldo, **extra):
    return {"id": id_, "status": "da_pagare", "pagato": False, "file_name": f"{id_}.pdf",
            "dati_generali": {"data_versamento": data}, "totali": {"saldo_netto": saldo},
            "sezione_erario": [{"codice_tributo": "1001", "periodo_riferimento": "12/2025",
                                "importo_debito": saldo}], **extra}


def _riscontri(quietanze, movimenti, **kw):
    return reg.riscontri_quietanze_banca(
        [reg._quietanza_legacy(q) for q in quietanze], movimenti, **kw)


def _db(quietanze=(), movimenti=(), modelli=()):
    db = ClientArchivioMemoria()["f24_livelli"]

    async def _carica():
        for q in quietanze:
            await db[COLL_QUIETANZE_F24].insert_one(dict(q))
        for m in movimenti:
            await db[COLL_ESTRATTO_CONTO].insert_one(dict(m))
        for f in modelli:
            await db[COLL_F24].insert_one(dict(f))
    _run(_carica())
    return db


# ── il calendario ──────────────────────────────────────────────────────────

def test_giorni_lavorativi_con_weekend_e_festivi():
    assert cal.giorni_lavorativi_tra(date(2026, 1, 16), date(2026, 1, 16)) == 0
    assert cal.giorni_lavorativi_tra(date(2026, 1, 16), date(2026, 1, 19)) == 1  # ven → lun
    # Pasquetta 06/04/2026: gio 02/04 → mar 07/04 sono 2 giorni lavorativi (ven, mar)
    assert cal.giorni_lavorativi_tra(date(2026, 4, 2), date(2026, 4, 7)) == 2
    assert cal.giorni_lavorativi_tra(date(2026, 1, 19), date(2026, 1, 16)) == -1


# ── i livelli sulle quietanze ─────────────────────────────────────────────

def test_certo_scrive_e_porta_livello_e_motivazione():
    esito = _riscontri([_q("q1", "2026-08-20", 654.33)],
                       [_m("m1", "2026-08-20", -654.33, "20/08/2026")])
    [r] = esito["riscontrati"]
    assert r["livello"] == reg.LIVELLO_CERTO
    assert "654.33 EUR uguale al centesimo" in r["motivazione"]
    assert esito["conteggi"]["per_livello"][reg.LIVELLO_CERTO] == 1


def test_i_festivi_allargano_la_finestra_di_calendario_non_quella_lavorativa():
    dentro = _riscontri([_q("q1", "2026-04-02", 900.00)], [_m("m1", "2026-04-07", -900.00, "02/04/2026")])
    fuori = _riscontri([_q("q1", "2026-04-02", 900.00)], [_m("m1", "2026-04-08", -900.00, "02/04/2026")])
    assert len(dentro["riscontrati"]) == 1
    assert fuori["riscontrati"] == [] and fuori["da_verificare"] == []


def test_probabile_importo_e_data_uguali_ma_causale_generica():
    esito = _riscontri([_q("q1", "2026-06-16", 8139.63)], [_m("m1", "2026-06-17", -8139.63)])
    assert esito["riscontrati"] == []
    [r] = esito["da_verificare"]
    assert r["livello"] == reg.LIVELLO_PROBABILE and r["stato"] == reg.RISCONTRO_DA_VERIFICARE


def test_parziale_sotto_soglia_con_la_differenza_sopra_no():
    sotto = _riscontri([_q("q1", "2026-08-20", 1000.00)], [_m("m1", "2026-08-20", -1004.99, "20/08/2026")])
    [r] = sotto["da_verificare"]
    assert r["livello"] == reg.LIVELLO_PARZIALE and r["differenza"] == 4.99
    sopra = _riscontri([_q("q1", "2026-08-20", 1000.00)], [_m("m1", "2026-08-20", -1005.01, "20/08/2026")])
    assert sopra["da_verificare"] == [] and len(sopra["addebiti_senza_quietanza"]) == 1
    piu_larga = _riscontri([_q("q1", "2026-08-20", 1000.00)], [_m("m1", "2026-08-20", -1005.01, "20/08/2026")],
                           soglia_parziale_cents=600)
    assert piu_larga["da_verificare"][0]["livello"] == reg.LIVELLO_PARZIALE


def test_due_candidati_non_si_scelgono_e_si_mostrano_entrambi():
    esito = _riscontri([_q("q1", "2026-06-16", 915.00)],
                       [_m("m1", "2026-06-17", -915.00), _m("m2", "2026-06-18", -915.00)])
    [r] = esito["da_verificare"]
    assert {c["movimento_id"] for c in r["candidati"]} == {"m1", "m2"}
    assert esito["riscontrati"] == []


def test_nessun_match_dice_se_l_estratto_del_periodo_c_e():
    movimenti = [_m("m0", "2026-01-16", -535.70, "16/01/2026"), _m("m9", "2026-09-17", -104.54, "16/09/2026")]
    con_estratto = _riscontri([_q("q1", "2026-05-18", 777.00)], movimenti)
    senza_estratto = _riscontri([_q("q1", "2025-05-16", 777.00)], movimenti)

    [c] = con_estratto["quietanze_senza_addebito"]
    assert c["livello"] == reg.LIVELLO_NESSUN_MATCH and c["estratto_periodo_presente"] is True
    assert "estratto del periodo presente: si'" in c["motivazione"]
    assert senza_estratto["quietanze_senza_addebito"] == []
    [s] = senza_estratto["quietanze_senza_estratto"]
    assert s["estratto_periodo_presente"] is False
    assert "manca solo l'estratto conto del periodo" in s["motivazione"]


def test_movimento_orfano_e_probabile_quietanza_da_riscaricare():
    [a] = _riscontri([], [_m("m1", "2026-09-17", 9421.15, "16/09/2026")])["addebiti_senza_quietanza"]
    assert a["livello"] == reg.LIVELLO_MOVIMENTO_ORFANO
    assert "probabile quietanza da riscaricare" in a["motivazione"]


def test_saldo_zero_in_compensazione_non_cerca_un_addebito():
    q = {"id": "q0", "data_pagamento": "2026-05-18", "saldo": 0, "protocollo_telematico": "P/000001",
         "filename": "q0.pdf", "f24_associati": [],
         "righe": [{"sezione": "erario", "codice": "1001", "importo_debito_cents": 5000,
                    "importo_credito_cents": 5000}]}
    esito = _riscontri([q], [_m("m1", "2026-05-18", -50.00)])
    assert esito["quietanze_senza_addebito"] == [] and esito["quietanze_senza_estratto"] == []


# ── cosa scrivono i livelli ───────────────────────────────────────────────

def _relazioni(db):
    return _run(db[COLL_ENTITY_RELATIONS].find({}, {"_id": 0}).to_list(50))


def test_solo_il_certo_scrive_il_pagamento_gli_altri_una_relazione_pending():
    db = _db([_q("q1", "2026-08-20", 654.33), _q("q2", "2026-06-16", 1000.00, "26061611002055014/000001")],
             [_m("m1", "2026-08-20", -654.33, "20/08/2026"), _m("m2", "2026-06-16", -1003.00, "16/06/2026")])
    esito = _run(reg.riconcilia_f24_banca(db))

    q1 = _run(db[COLL_QUIETANZE_F24].find_one({"id": "q1"}))
    q2 = _run(db[COLL_QUIETANZE_F24].find_one({"id": "q2"}))
    assert q1["riscontro_banca"]["livello"] == reg.LIVELLO_CERTO
    assert "riscontro_banca" not in q2 and "movimento_bancario_id" not in q2
    stati = {(r["source"]["id"], r["target"]["id"]): r["status"] for r in _relazioni(db)}
    assert stati == {("m1", "q1"): "confirmed", ("m2", "q2"): "pending"}
    assert esito["scritti"]["relazioni"] == 2
    m2 = _run(db[COLL_ESTRATTO_CONTO].find_one({"id": "m2"}))
    assert not m2.get("riconciliato") and not m2.get("quietanze_f24_ids")


def test_il_secondo_giro_scrive_zero_righe():
    db = _db([_q("q1", "2026-08-20", 654.33), _q("q2", "2026-06-16", 1000.00, "26061611002055014/000001")],
             [_m("m1", "2026-08-20", -654.33, "20/08/2026"), _m("m2", "2026-06-16", -1003.00, "16/06/2026")],
             [_modello("f1", "2026-01-16", 500.00)])
    _run(reg.riconcilia_f24_banca(db))
    secondo = _run(reg.riconcilia_f24_banca(db))
    assert secondo["scritti"] == {"quietanze": 0, "addebiti": 0, "relazioni": 0, "alert_aperti": 0,
                                  "alert_chiusi": 0, "modelli": {"modelli": 0, "relazioni": 0}}


# ── i modelli, con lo stesso motore ───────────────────────────────────────

def test_un_modello_senza_quietanza_e_provato_dall_addebito_certo():
    db = _db(movimenti=[_m("m1", "2026-01-16", -5600.93)],
             modelli=[_modello("f-a", "2026-01-16", 5600.93)])
    esito = _run(reg.riconcilia_f24_banca(db))

    assert esito["modelli"]["riscontrati"][0]["livello"] == reg.LIVELLO_CERTO
    f = _run(db[COLL_F24].find_one({"id": "f-a"}))
    assert f["pagato"] is True and f["movimento_bancario_id"] == "m1"
    assert f["data_pagamento_effettivo"] == "2026-01-16"
    m = _run(db[COLL_ESTRATTO_CONTO].find_one({"id": "m1"}))
    assert m["riconciliato"] is True and m["f24_ids"] == ["f-a"] and m["tipo_riconciliazione"] == "f24_tributi"
    assert _run(reg.riconcilia_f24_banca(db))["scritti"]["modelli"] == {"modelli": 0, "relazioni": 0}
    assert {(r["source"]["id"], r["relation_type"], r["status"]) for r in _relazioni(db)
            if r["target"]["id"] == "f-a"} == {("m1", "settles_f24_model", "confirmed")}


def test_un_modello_con_quietanza_di_altro_importo_non_si_aggancia_da_solo_alla_banca():
    db = _db([_q("q1", "2026-08-20", 700.00)], [_m("m1", "2026-08-20", -654.33)],
             [_modello("f-q", "2026-08-20", 654.33, quietanza_id="q1")])
    assert _run(reg.riconcilia_f24_banca(db))["modelli"]["riscontrati"] == []
    assert _run(reg.riconcilia_f24_arrivato(db, 654.33))["modelli"]["riscontrati"] == 0


def test_la_data_incasso_diversa_dalla_data_programmata_del_modello_non_lo_esclude():
    db = _db(movimenti=[_m("m1", "2026-01-17", -500.00, "17/01/2026")],
             modelli=[_modello("f-p", "2026-01-16", 500.00)])
    [r] = _run(reg.riconcilia_f24_banca(db))["modelli"]["riscontrati"]
    assert r["movimento_id"] == "m1"


def test_due_modelli_stesso_importo_e_data_non_si_scelgono():
    db = _db(movimenti=[_m("m1", "2026-03-16", -781.60)],
             modelli=[_modello("f-x", "2026-03-16", 781.60), _modello("f-y", "2026-03-16", 781.60)])
    esito = _run(reg.riconcilia_f24_banca(db))
    assert esito["modelli"]["riscontrati"] == []
    assert len(esito["modelli"]["da_verificare"]) == 2
    for fid in ("f-x", "f-y"):
        assert _run(db[COLL_F24].find_one({"id": fid}))["pagato"] is False
    assert not _run(db[COLL_ESTRATTO_CONTO].find_one({"id": "m1"})).get("riconciliato")


def test_un_modello_lontano_dalla_data_non_si_aggancia_per_solo_importo():
    db = _db(movimenti=[_m("m1", "2026-02-05", -535.70)], modelli=[_modello("f-l", "2026-01-16", 535.70)])
    esito = _run(reg.riconcilia_f24_banca(db))
    assert esito["modelli"]["riscontrati"] == [] and esito["modelli"]["da_verificare"] == []
    assert _run(db[COLL_F24].find_one({"id": "f-l"}))["pagato"] is False


def test_un_modello_senza_data_di_versamento_si_dichiara_e_non_si_abbina():
    """Prima era saltato in silenzio: ora l'esito dice quale dato manca, le regole non cambiano."""
    senza_data = _modello("f-sd", None, 400.00)
    senza_data["dati_generali"] = {}
    senza_saldo = _modello("f-ss", "2026-03-16", 0)
    senza_saldo["totali"] = {}
    senza_saldo["sezione_erario"] = []
    db = _db(movimenti=[_m("m1", "2026-03-16", -400.00)],
             modelli=[senza_data, senza_saldo, _modello("f-ok", "2026-05-18", 99.00)])
    esito = _run(reg.riconcilia_f24_banca(db))["modelli"]

    voci = {v["f24_id"]: v for v in esito["non_riscontrabili"]}
    assert voci["f-sd"]["esito"] == reg.ESITO_DATA_VERSAMENTO_ASSENTE
    assert voci["f-ss"]["esito"] == reg.ESITO_SALDO_ASSENTE
    assert "f-ok" not in voci            # ha data e saldo: solo nessun addebito
    assert esito["conteggi"]["data_versamento_assente"] == 1 and esito["conteggi"]["saldo_assente"] == 1
    # lo stesso importo in banca NON lo aggancia: la regola d'abbinamento e' quella di sempre
    assert esito["riscontrati"] == [] and esito["da_verificare"] == []
    assert not _run(db[COLL_F24].find_one({"id": "f-sd"}))["pagato"]
    # secondo giro: stesso esito, nessuna scrittura
    assert _run(reg.riconcilia_f24_banca(db))["scritti"]["modelli"] == {"modelli": 0, "relazioni": 0}


def test_un_modello_con_quietanza_e_provato_dall_addebito_della_quietanza():
    quietanza = _q("q1", "2026-08-20", 654.33)
    db = _db([quietanza], [_m("m1", "2026-08-20", -654.33, "20/08/2026")],
             [_modello("f-q", "2026-08-20", 654.33, quietanza_id="q1")])
    esito = _run(reg.riconcilia_f24_banca(db))

    [r] = esito["modelli"]["riscontrati"]
    assert r["criterio"] == "via_quietanza" and r["movimento_id"] == "m1"
    assert _run(db[COLL_F24].find_one({"id": "f-q"}))["movimento_bancario_id"] == "m1"


def test_un_modello_con_saldo_diverso_dalla_quietanza_non_e_provato_dall_addebito():
    quietanza = _q("q1", "2026-08-20", 654.33)
    db = _db([quietanza], [_m("m1", "2026-08-20", -654.33, "20/08/2026")],
             [_modello("f-q", "2026-08-20", 700.00, quietanza_id="q1")])
    esito = _run(reg.riconcilia_f24_banca(db))
    assert esito["modelli"]["riscontrati"] == []
    assert _run(db[COLL_F24].find_one({"id": "f-q"}))["pagato"] is False


# ── il vecchio motore non esiste piu' ─────────────────────────────────────

def test_i_motori_paralleli_non_esistono_piu():
    from app.services import estratto_conto_bpm_parser as parser

    assert importlib.util.find_spec("app.services.f24_bank_reconciliation") is None
    assert importlib.util.find_spec("app.services.f24_tributi_saldo") is None
    assert not hasattr(parser, "riconcilia_f24_con_estratto")
    assert not hasattr(reg, "riconcilia_addebiti") and not hasattr(reg, "proposte_aggancio")
    assert not hasattr(reg, "riscontra_quietanze_banca")
