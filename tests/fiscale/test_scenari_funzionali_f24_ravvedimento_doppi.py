"""Scenari funzionali: F24 ravveduto, RC01 ↔ DM10, saldo zero, doppi, doppio pagamento, avviso bonario.

Tutto passa dai servizi di import veri (`importa_modello_bytes`, `importa_quietanza_bytes`), con l'archivio
in memoria; si sostituisce solo la lettura dei PDF.
"""
import itertools

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db_collections import COLL_F24, COLL_QUIETANZE_F24
from app.services import f24_anomalie as fa
from app.services import f24_canonico, quietanze_import as qi
from app.services import f24_controllo_incrociato as reg
from tests.fiscale.scenari_f24_comuni import (
    causale_i24, collezione, db_nuovo, modello_parsed, quietanza_parsed, run,
)
from tests.fiscale.test_scenari_funzionali_f24_banca import ambiente, _importa_estratto  # noqa: F401  (fixture)

E, INPS = "sezione_erario", "sezione_inps"

# Il commercialista manda l'F24 delle ritenute di marzo (1.000,00); il titolare non lo paga il 16/04 e lo rifa'
# con il ravvedimento il 30/04: tributo + interessi cumulati (1.000,61) e sanzione 8947 (11,66).
ORIGINALE = [(E, "1001", "03/2026", "1000.00", "0")]
RAVVEDIMENTO = [(E, "1001", "03/2026", "1000.61", "0"), (E, "8947", "03/2026", "11.66", "0")]
PROTO_RAVV = "26043012000000001/000001"


def _modello(db, letti, nome, righe, data, pdf):
    letti[pdf] = modello_parsed(righe, data)
    esito = run(f24_canonico.importa_modello_bytes(db, pdf, nome, source="test"))
    assert esito["success"], esito
    return esito["f24_id"]


def _quietanza(db, letti, nome, righe, data, protocollo, pdf):
    letti[pdf] = quietanza_parsed(righe, data, protocollo)
    esito = run(qi.importa_quietanza_bytes(db, pdf, nome, fonte="test"))
    assert esito["success"], esito
    return esito["quietanza_id"]


PEZZI = ("originale", "modello_ravvedimento", "quietanza_ravvedimento")


def _arriva(db, letti, pezzo):
    if pezzo == "originale":
        return _modello(db, letti, "F24 marzo originale.pdf", ORIGINALE, "2026-04-16", b"%PDF-originale")
    if pezzo == "modello_ravvedimento":
        return _modello(db, letti, "F24 marzo ravveduto.pdf", RAVVEDIMENTO, "2026-04-30", b"%PDF-ravv-modello")
    return _quietanza(db, letti, "quietanza ravvedimento.pdf", RAVVEDIMENTO, "2026-04-30", PROTO_RAVV, b"%PDF-ravv-quietanza")


@pytest.mark.parametrize("ordine", list(itertools.permutations(PEZZI)), ids=lambda o: "-".join(p[:4] for p in o))
def test_il_ravvedimento_si_lega_all_originale_in_qualunque_ordine_d_arrivo(ambiente, ordine):
    db, letti, _mp = ambiente
    for pezzo in ordine:
        _arriva(db, letti, pezzo)

    modelli = {m["file_name"]: m for m in collezione(db, COLL_F24)}
    originale, ravv = modelli["F24 marzo originale.pdf"], modelli["F24 marzo ravveduto.pdf"]
    [quietanza] = collezione(db, COLL_QUIETANZE_F24)

    # l'originale resta il documento del commercialista (stato suo, nessuna riga toccata), con il legame accanto
    assert originale["status"] == "da_pagare" and originale["pagato"] is False and "etichetta" not in originale
    legame = originale["ravvedimento"]
    assert legame["stato"] == "RAVVEDUTO" and legame["f24_ravvedimento_id"] == ravv["id"]
    assert legame["quietanza_ids"] == [quietanza["id"]] and legame["protocollo"] == PROTO_RAVV
    assert legame["data_pagamento"] == "2026-04-30" and legame["importo_ravvedimento"] == 1012.27
    assert legame["interessi_cumulati"] == 0.61 and legame["sanzioni_totale"] == 11.66
    assert [(r["codice"], r["periodo"], r["originale"], r["versato"]) for r in legame["righe"]] == [
        ("1001", "03/2026", 1000.0, 1000.61)]
    # il ravvedimento e' un modello a se', etichettato; la quietanza e' sua, non dell'originale
    assert ravv["etichetta"] == "RAVVEDIMENTO" and ravv["ravvedimento_di"] == [originale["id"]]
    assert quietanza["ravvedimento_di"] == [originale["id"]] and quietanza["f24_associati"] == [ravv["id"]]
    assert ravv["quietanza_id"] == quietanza["id"] and not originale.get("quietanza_id")


def test_ravvedimento_scadenzario_e_banca_sullo_stesso_pagamento(ambiente):
    db, letti, mp = ambiente
    for pezzo in PEZZI:
        _arriva(db, letti, pezzo)
    _importa_estratto(db, mp, [{"data": "2026-04-30", "importo": -1012.27, "descrizione": causale_i24("30/04/2026")}])

    modelli = {m["file_name"]: m for m in collezione(db, COLL_F24)}
    ravv = modelli["F24 marzo ravveduto.pdf"]
    [q] = collezione(db, COLL_QUIETANZE_F24)
    # la banca addebita l'importo del ravvedimento (non quello del commercialista): CERTO sulla quietanza e sul suo modello
    assert q["riscontro_banca"]["livello"] == reg.LIVELLO_CERTO and q["riscontro_banca"]["importo"] == 1012.27
    assert ravv["pagato"] is True and ravv["movimento_bancario_id"] == q["movimento_bancario_id"]
    assert modelli["F24 marzo originale.pdf"]["pagato"] is False       # l'originale non e' mai stato versato
    # lo scadenzario giudica il pagamento: scadenza dal modello del commercialista, 14 giorni, ravveduto
    [voce] = [v for v in collezione(db, "scadenzario_tributi") if v["codice"] == "1001"]
    p = voce["pagamenti"][0]
    assert voce["stato"] == "RAVVEDUTO" and voce["scadenza"] == "2026-04-16" and p["giorni_ritardo"] == 14
    assert p["sanzioni_periodo_cents"] == 1166 and p["interessi_periodo_attesi_cents"] == 61
    # secondo giro di tutto: nessuna scrittura
    giro = run(reg.riconcilia_f24_banca(db))
    assert giro["scritti"]["quietanze"] == giro["scritti"]["addebiti"] == giro["scritti"]["relazioni"] == 0
    assert giro["scritti"]["modelli"] == {"modelli": 0, "relazioni": 0}


def test_un_ravvedimento_che_non_torna_riga_per_riga_non_si_lega_all_originale(ambiente):
    db, letti, _mp = ambiente
    _arriva(db, letti, "originale")
    # importo del tributo piu' basso dell'originale e codice/periodo diversi: nessun legame, mai per importo vicino
    _modello(db, letti, "altro ravvedimento.pdf",
             [(E, "1001", "03/2026", "900.00", "0"), (E, "8947", "03/2026", "10.00", "0")],
             "2026-04-30", b"%PDF-altro")
    originale = [m for m in collezione(db, COLL_F24) if m["file_name"] == "F24 marzo originale.pdf"][0]
    assert "ravvedimento" not in originale


# ── RC01: regolarizzazione di un periodo precedente ────────────────────────────────────────

def test_rc01_non_e_costo_del_mese_in_cui_si_paga_e_si_collega_al_dm10_del_periodo(ambiente):
    db, letti, _mp = ambiente
    from app.services import fascicolo_f24

    dm10 = [(E, "1001", "11/2022", "1382.12", "0"), (INPS, "DM10", "11/2022", "2840.00", "0")]
    rc01 = [(INPS, "RC01", "11/2022", "2840.00", "0")]
    id_dm10 = _modello(db, letti, "DM10 novembre 2022.pdf", dm10, "2022-12-16", b"%PDF-dm10")
    # pagata nel 2026: e' la regolarizzazione del 11/2022, non l'INPS di agosto 2026
    id_rc01 = _modello(db, letti, "RC01 novembre 2022.pdf", rc01, "2026-08-20", b"%PDF-rc01")
    qid = _quietanza(db, letti, "quietanza RC01.pdf", rc01, "2026-08-20", "26081811065626134/000009", b"%PDF-q-rc01")

    # la scadenza di agosto 2026 del calendario INPS non si segna come pagata dall'RC01 (periodo precedente)
    assert qi._tipo_scadenza_da_codice("RC01") == ""
    # il tipo di versamento dice «regolarizzazione», non ordinario
    [pag] = reg.pagamenti_da_quietanze([reg._quietanza_legacy(q) for q in collezione(db, COLL_QUIETANZE_F24)
                                        if q["id"] == qid])
    assert pag["tipo_versamento"] == "regolarizzazione"
    # il fascicolo del periodo 11/2022 lega l'RC01 al DM10 senza sommare due volte i tributi
    fascicolo = run(fascicolo_f24.costruisci_fascicolo(db, "01879020517", (11, 2022)))
    assert fascicolo["f24_ordinari_ids"] == [id_dm10] and fascicolo["f24_rc01_ids"] == [id_rc01]
    [rel] = fascicolo["relazioni_dm10_rc01"]
    assert rel["f24_ordinario_id"] == id_dm10 and rel["f24_rc01_id"] == id_rc01
    assert fascicolo["totali"]["regolarizzazione"] == 2840.0 and fascicolo["totali"]["debito_originario"] == 4222.12
    # nessuna scadenza del mese di pagamento (08/2026) risulta onorata dallo scadenzario: e' il periodo 2022
    assert all(v["anno"] != 2026 or v["codice"] != "RC01" for v in collezione(db, "scadenzario_tributi"))
    # e in Tributi la riga vive nel periodo regolarizzato (11/2022), mai nel mese di pagamento
    from app.services import tributi_per_codice as tributi

    voci_rc01 = [v for v in run(tributi.carica_voci(db))["voci"] if v["codice"] == "RC01"]
    assert [(v["anno"], v["mese"]) for v in voci_rc01] == [(2022, 11)]


# ── F24 a saldo zero: pagato tutto in compensazione ──────────────────────────────────────────

SALDO_ZERO = [(E, "1001", "07/2026", "395.73", "0"), (E, "1631", "2025", "0", "395.73")]


def test_f24_a_saldo_zero_e_compensato_senza_addebito_atteso_e_senza_alert_bloccanti(ambiente):
    db, letti, mp = ambiente
    letti[b"%PDF-zero"] = quietanza_parsed(SALDO_ZERO, "2026-08-20", "26081811065626134/000003")
    esito_q = run(qi.importa_quietanza_bytes(db, b"%PDF-zero", "zero.pdf", fonte="test"))
    assert esito_q["stato_quietanza"] == "QUIETANZA_COMPENSAZIONE_TOTALE"
    assert "nessun addebito in banca atteso" in esito_q["warning"]
    assert collezione(db, "f24_alerts") == [] and "compensazione" in esito_q["riscontro_banca"]["saltato"]
    # c'e' un estratto del periodo (altri addebiti) ma nessuno da 0: niente «quietanza senza addebito»
    _importa_estratto(db, mp, [{"data": "2026-08-03", "importo": -10.0, "descrizione": causale_i24("03/08/2026")},
                               {"data": "2026-09-10", "importo": -20.0,
                                "descrizione": causale_i24("10/09/2026", "2026-09-10-09.00.00.000000000009")}])
    giro = run(reg.riconcilia_f24_banca(db))
    assert [c["protocollo"] for c in giro["compensate_saldo_zero"]] == ["26081811065626134/000003"]
    assert giro["quietanze_senza_addebito"] == [] and giro["quietanze_senza_estratto"] == []
    assert giro["compensate_saldo_zero"][0]["stato"] == "COMPENSATA"
    aperti = run(db["alerts"].find({"stato": "aperto", "codice": {"$regex": "F24"}}).to_list(10))
    # gli unici alert F24 sono i due addebiti di riempimento senza quietanza; nessuno parla della delega a zero
    assert sorted(a["codice"] for a in aperti) == [reg.ALERT_ADDEBITO_SENZA_QUIETANZA] * 2
    assert not any(a["entita_id"] == "26081811065626134/000003" for a in aperti)
    # Tributi: la riga e' pagata in compensazione (COMPENSATO), non da pagare
    from app.services import tributi_per_codice as tributi

    voci = run(tributi.carica_voci(db))["voci"]
    [v] = [x for x in voci if x["codice"] == "1001"]
    assert v["stato"] == tributi.COMPENSATO and v["compensazione_cents"] == 39573
    # Scadenzario: puntuale (20/08, Ferragosto) anche a saldo zero
    [s] = [x for x in collezione(db, "scadenzario_tributi") if x["codice"] == "1001"]
    assert s["stato"] == "PUNTUALE" and s["pagamenti"][0]["compensazione_totale"] is True


def test_modello_a_saldo_zero_non_cerca_un_addebito_e_lo_dichiara(ambiente):
    db, letti, _mp = ambiente
    _modello(db, letti, "F24 zero.pdf", SALDO_ZERO, "2026-08-20", b"%PDF-modello-zero")
    esito = run(reg.riconcilia_f24_banca(db))["modelli"]
    [v] = esito["non_riscontrabili"]
    assert v["esito"] == reg.ESITO_SALDO_ASSENTE and "nessun addebito da cercare" in v["motivazione"]


# ── 6. doppi: stessa quietanza, saldo diverso, doppio pagamento ───────────────────────────

def _quiet_raw(db, letti, pdf, righe, data, protocollo, nome="q.pdf"):
    letti[pdf] = quietanza_parsed(righe, data, protocollo)
    return run(qi.importa_quietanza_bytes(db, pdf, nome, fonte="test"))


R_1001 = [(E, "1001", "07/2026", "654.33", "0")]


def test_stessa_quietanza_da_due_pdf_diversi_e_una_sola(ambiente):
    db, letti, _mp = ambiente
    prima = _quiet_raw(db, letti, b"%PDF-copia-1", R_1001, "2026-08-20", "26081811065626134/000001", "q (1).pdf")
    seconda = _quiet_raw(db, letti, b"%PDF-copia-2", R_1001, "2026-08-20", "26081811065626134/000001", "q (2).pdf")
    stesso_pdf = _quiet_raw(db, letti, b"%PDF-copia-1", R_1001, "2026-08-20", "26081811065626134/000001", "q (1).pdf")
    assert prima["duplicate"] is False
    assert seconda["duplicate"] is True and seconda["quietanza_id"] == prima["quietanza_id"]
    assert seconda["motivo"] == "stesso protocollo telematico e stesso saldo"
    assert stesso_pdf["duplicate"] is True and stesso_pdf["quietanza_id"] == prima["quietanza_id"]
    [q] = collezione(db, COLL_QUIETANZE_F24)
    assert len(q["source_occurrences"]) == 2          # la copia in piu' si annota, non si crea
    assert "protocollo_condiviso_con" not in q


def test_stesso_protocollo_con_saldo_diverso_e_un_altra_delega_con_il_suo_addebito(ambiente):
    db, letti, mp = ambiente
    # 21/08/2023 reale: dallo stesso PDF escono due deleghe, 5.959,18 e 12,95 EUR, stesso protocollo
    grande = [(E, "1001", "07/2023", "5959.18", "0")]
    piccola = [(E, "1040", "07/2023", "12.95", "0")]
    a = _quiet_raw(db, letti, b"%PDF-grande", grande, "2026-08-20", "26081811065626134/000001", "grande.pdf")
    b = _quiet_raw(db, letti, b"%PDF-piccola", piccola, "2026-08-20", "26081811065626134/000001", "piccola.pdf")
    assert b["duplicate"] is False and b["quietanza_id"] != a["quietanza_id"]
    quietanze = {q["id"]: q for q in collezione(db, COLL_QUIETANZE_F24)}
    assert quietanze[b["quietanza_id"]]["protocollo_condiviso_con"] == [a["quietanza_id"]]
    _importa_estratto(db, mp, [
        {"data": "2026-08-20", "importo": -5959.18, "descrizione": causale_i24("20/08/2026")},
        {"data": "2026-08-20", "importo": -12.95, "descrizione": causale_i24("20/08/2026", "2026-08-20-10.00.00.000000000002")},
    ])
    quietanze = {q["id"]: q for q in collezione(db, COLL_QUIETANZE_F24)}
    assert quietanze[a["quietanza_id"]]["riscontro_banca"]["importo"] == 5959.18
    assert quietanze[b["quietanza_id"]]["riscontro_banca"]["importo"] == 12.95
    assert quietanze[a["quietanza_id"]]["movimento_bancario_id"] != quietanze[b["quietanza_id"]]["movimento_bancario_id"]


def test_lo_stesso_tributo_in_due_deleghe_dello_stesso_giorno_apre_un_alert_con_le_due_deleghe(ambiente):
    db, letti, mp = ambiente
    _quiet_raw(db, letti, b"%PDF-prog", R_1001, "2026-08-20", "26081211000000001/000001", "programmata.pdf")
    _quiet_raw(db, letti, b"%PDF-stesso-giorno", R_1001, "2026-08-20", "26082011000000002/000001", "stesso giorno.pdf")
    _importa_estratto(db, mp, [
        {"data": "2026-08-20", "importo": -654.33, "descrizione": causale_i24("20/08/2026")},
        {"data": "2026-08-20", "importo": -654.33, "descrizione": causale_i24("20/08/2026", "2026-08-20-10.00.00.000000000002")},
    ])
    run(reg.riconcilia_f24_banca(db))
    [alert] = run(db["alerts"].find({"codice": reg.ALERT_TRIBUTO_DUE_VOLTE, "stato": "aperto"}).to_list(5))
    assert "1001 07/2026 654.33" in alert["dettaglio"] and len(alert["extra"]["record"]) == 2
    assert {r["protocollo"] for r in alert["extra"]["record"]} == {
        "26081211000000001/000001", "26082011000000002/000001"}


DM10_ORDINARIO = [(E, "1001", "11/2022", "1382.12", "0"), (INPS, "DM10", "11/2022", "2840.00", "0")]
RC01 = [(INPS, "RC01", "11/2022", "2840.00", "0")]


def _api_analisi(db, monkeypatch):
    from app.database import Database
    from app.routers import f24_analisi
    from app.utils.dependencies import get_current_admin_user

    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    app = FastAPI()
    app.include_router(f24_analisi.router, prefix="/api/f24-analisi")
    app.dependency_overrides[get_current_admin_user] = lambda: {"sub": "titolare", "email": "titolare@example.test", "role": "admin"}
    return TestClient(app)


def test_doppio_pagamento_dm10_rc01_anomalia_alert_decisione_e_nessuna_riapertura(ambiente):
    db, letti, mp = ambiente
    _modello(db, letti, "DM10 novembre 2022.pdf", DM10_ORDINARIO, "2022-12-16", b"%PDF-dm10")
    _quietanza(db, letti, "q dm10.pdf", DM10_ORDINARIO, "2022-12-16", "22121612000000001/000001", b"%PDF-q-dm10")
    _modello(db, letti, "RC01 novembre 2022.pdf", RC01, "2026-08-20", b"%PDF-rc01")
    _quietanza(db, letti, "q rc01.pdf", RC01, "2026-08-20", "26081811065626134/000009", b"%PDF-q-rc01")
    client = _api_analisi(db, mp)

    # anteprima (dry_run per difetto): non scrive niente
    anteprima = client.post("/api/f24-analisi/doppi-pagamenti/rileva").json()
    assert anteprima["dry_run"] is True and anteprima["nuove"] == 1
    assert collezione(db, fa.COLL_ANOMALIE_DOPPIO) == []

    primo = client.post("/api/f24-analisi/doppi-pagamenti/rileva", params={"dry_run": "false"}).json()
    assert primo["nuove"] == 1 and primo["gia_presenti"] == 0
    [anomalia] = collezione(db, fa.COLL_ANOMALIE_DOPPIO)
    assert anomalia["stato"] == "da_verificare" and anomalia["quota_duplicata_cents"] == 284000
    aperti = run(db["alerts"].find({"codice": fa.ALERT_DOPPIO_PAGAMENTO, "stato": "aperto"}).to_list(5))
    assert [a["entita_id"] for a in aperti] == [anomalia["id"]]

    # secondo giro: nessuna anomalia nuova, nessun secondo alert
    secondo = client.post("/api/f24-analisi/doppi-pagamenti/rileva", params={"dry_run": "false"}).json()
    assert secondo["nuove"] == 0 and secondo["gia_presenti"] == 1
    assert len(run(db["alerts"].find({"codice": fa.ALERT_DOPPIO_PAGAMENTO}).to_list(10))) == 1

    # il titolare decide: serve il motivo (422 senza), poi l'alert si chiude
    senza_motivo = client.put(f"/api/f24-analisi/doppi-pagamenti/{anomalia['id']}/stato", json={"stato": "non_duplicato"})
    assert senza_motivo.status_code == 422 and senza_motivo.json()["detail"]["code"] == "STATO_ANOMALIA_NON_VALIDO"
    assert len(run(db["alerts"].find({"codice": fa.ALERT_DOPPIO_PAGAMENTO, "stato": "aperto"}).to_list(5))) == 1
    ok = client.put(f"/api/f24-analisi/doppi-pagamenti/{anomalia['id']}/stato",
                    json={"stato": "non_duplicato", "motivo": "RC01 a regolarizzazione di una quota diversa"})
    assert ok.status_code == 200 and ok.json()["stato"] == "non_duplicato"
    assert run(db["alerts"].find({"codice": fa.ALERT_DOPPIO_PAGAMENTO, "stato": "aperto"}).to_list(5)) == []
    assert ok.json()["storico"][-1]["da"] == "titolare@example.test"

    # una coppia decisa non si riapre ne' si duplica, e l'elenco porta lo stato scelto
    dopo = client.post("/api/f24-analisi/doppi-pagamenti/rileva", params={"dry_run": "false"}).json()
    assert dopo["nuove"] == 0
    assert run(db["alerts"].find({"codice": fa.ALERT_DOPPIO_PAGAMENTO, "stato": "aperto"}).to_list(5)) == []
    elenco = client.get("/api/f24-analisi/doppi-pagamenti").json()
    assert elenco["da_verificare"] == 0 and elenco["anomalie"][0]["stato"] == "non_duplicato"
    # riportarla a «da verificare» riapre l'alert
    client.put(f"/api/f24-analisi/doppi-pagamenti/{anomalia['id']}/stato", json={"stato": "da_verificare"})
    assert len(run(db["alerts"].find({"codice": fa.ALERT_DOPPIO_PAGAMENTO, "stato": "aperto"}).to_list(5))) == 1


def test_solo_accessori_o_un_solo_pagato_non_e_doppio_pagamento(ambiente):
    db, letti, mp = ambiente
    _modello(db, letti, "DM10 novembre 2022.pdf", DM10_ORDINARIO, "2022-12-16", b"%PDF-dm10")
    _quietanza(db, letti, "q dm10.pdf", DM10_ORDINARIO, "2022-12-16", "22121612000000001/000001", b"%PDF-q-dm10")
    # l'RC01 e' caricato ma non pagato (nessuna quietanza, nessun addebito): non risultano entrambi pagati
    _modello(db, letti, "RC01 novembre 2022.pdf", RC01, "2026-08-20", b"%PDF-rc01")
    esito = run(fa.rileva_doppi_pagamenti(db, dry_run=False))
    assert esito["rilevate"] == 0 and esito["nuove"] == 0
    assert run(db["alerts"].find({"codice": fa.ALERT_DOPPIO_PAGAMENTO}).to_list(5)) == []


# ── 8. avviso bonario: dovuto o no, con la prova ─────────────────────────────────────────

def _api_avviso(db, monkeypatch):
    from app.database import Database
    from app.routers.f24 import avviso_bonario
    from app.utils.dependencies import get_current_user

    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    app = FastAPI()
    app.include_router(avviso_bonario.router, prefix="/api/f24")
    app.dependency_overrides[get_current_user] = lambda: {"sub": "titolare", "role": "admin"}
    return TestClient(app)


def _avviso(client, righe, **kw):
    corpo = client.post("/api/f24/avviso-bonario/controllo", json={
        "numero_avviso": "0123456789", "data_avviso": "2026-09-01", "includi_cedolini_hr": False,
        "righe": righe, **kw})
    assert corpo.status_code == 200, corpo.text
    return corpo.json()


def test_avviso_non_dovuto_con_la_prova_per_le_righe_pagate_nei_termini_o_ravvedute(ambiente):
    db, letti, mp = ambiente
    # 1001 di marzo: puntuale (16/04). 1040 di marzo: ravveduto il 30/04 (14 gg: sanzione 8948 di 2,45 su 210,00)
    _quiet_raw(db, letti, b"%PDF-1001", [(E, "1001", "03/2026", "1000.00", "0")], "2026-04-16",
               "26041611000000001/000001", "q1001.pdf")
    _quiet_raw(db, letti, b"%PDF-1040", [(E, "1040", "03/2026", "210.13", "0"), (E, "8948", "03/2026", "2.45", "0")],
               "2026-04-30", "26043011000000002/000001", "q1040.pdf")
    prima = {c: collezione(db, c) for c in (COLL_QUIETANZE_F24, COLL_F24, "scadenzario_tributi", "alerts")}
    esito = _avviso(_api_avviso(db, mp), [
        {"codice_tributo": "1001", "periodo": "03/2026", "importo": 1000.00},
        {"codice_tributo": "1040", "periodo": "03/2026", "importo": 210.00,
         "importo_sanzioni": 100.00, "importo_interessi": 5.00},
    ])
    r1001, r1040 = [r["scadenzario"] for r in esito["righe"]]
    assert r1001["verdetto"] == "NON_DOVUTO" and r1001["differenza_cents"] == 0
    assert "pagato nei termini" in r1001["motivazione"] and "26041611000000001/000001" in r1001["motivazione"]
    assert r1001["prove"][0]["importo_cents"] == 100000 and r1001["prove"][0]["data"] == "2026-04-16"
    assert r1040["verdetto"] == "NON_DOVUTO"
    assert "pagato in ritardo e ravveduto con sanzioni e interessi" in r1040["motivazione"]
    assert r1040["prove"][0]["stato"] == "RAVVEDUTO" and r1040["prove"][0]["protocollo"] == "26043011000000002/000001"
    assert r1040["sanzioni_richieste_cents"] == 10000 and r1040["interessi_richiesti_cents"] == 500
    # l'avviso nel suo insieme
    assert esito["verdetto"]["esito"] == "NON_DOVUTO" and esito["verdetto"]["da_pagare_cents"] == 0
    assert esito["verdetto"]["testo"].startswith(
        "Avviso n. 0123456789 non dovuto: F24 pagati regolarmente con sanzioni e interessi da ravvedimento")
    assert esito["verdetto"]["non_dovuto_cents"] == 121000
    assert esito["sola_lettura"] is True
    # sola lettura: l'avviso non scrive niente
    assert {c: collezione(db, c) for c in prima} == prima


def test_avviso_dovuto_se_in_ritardo_senza_ravvedimento_o_senza_quietanza_o_con_differenza(ambiente):
    db, letti, mp = ambiente
    _quiet_raw(db, letti, b"%PDF-tardi", [(E, "1001", "03/2026", "1000.00", "0")], "2026-05-20",
               "26052011000000003/000001", "tardi.pdf")                       # 34 giorni dopo, nessuna sanzione
    _quiet_raw(db, letti, b"%PDF-meno", [(E, "1012", "03/2026", "900.00", "0")], "2026-04-16",
               "26041611000000004/000001", "meno.pdf")                        # puntuale ma 100,00 in meno
    esito = _avviso(_api_avviso(db, mp), [
        {"codice_tributo": "1001", "periodo": "03/2026", "importo": 1000.00, "importo_sanzioni": 20.00,
         "importo_interessi": 3.00},
        {"codice_tributo": "1012", "periodo": "03/2026", "importo": 1000.00, "data_versamento_ade": "2026-04-20"},
        {"codice_tributo": "6031", "periodo": "2026", "importo": 500.00},
    ])
    tardi, meno, senza = [r["scadenzario"] for r in esito["righe"]]
    assert tardi["verdetto"] == "DOVUTO_DIFFERENZA" and tardi["differenza_cents"] == 2300     # solo sanzione + interessi
    assert "senza ravvedimento sufficiente" in tardi["motivazione"]
    assert meno["verdetto"] == "DOVUTO_DIFFERENZA" and meno["differenza_cents"] == 10000
    assert "chiedere lo sgravio" in meno["note"][0]                         # l'AdE data il versamento al 20/04, la quietanza al 16
    assert senza["verdetto"] == "DOVUTO" and senza["differenza_cents"] == 50000 and senza["prove"] == []
    assert esito["verdetto"]["esito"] == "DOVUTO_DIFFERENZA"
    assert esito["verdetto"]["da_pagare_cents"] == 2300 + 10000 + 50000


@pytest.mark.parametrize("ordine", list(itertools.permutations(PEZZI + ("banca",))),
                         ids=lambda o: "-".join(p[:4] for p in o))
def test_ravvedimento_e_banca_stesso_risultato_in_tutti_i_24_ordini(ambiente, ordine):
    db, letti, mp = ambiente
    for pezzo in ordine:
        if pezzo == "banca":
            _importa_estratto(db, mp, [{"data": "2026-04-30", "importo": -1012.27,
                                        "descrizione": causale_i24("30/04/2026")}])
        else:
            _arriva(db, letti, pezzo)

    modelli = {m["file_name"]: m for m in collezione(db, COLL_F24)}
    originale, ravv = modelli["F24 marzo originale.pdf"], modelli["F24 marzo ravveduto.pdf"]
    [q] = collezione(db, COLL_QUIETANZE_F24)
    [m] = collezione(db, "estratto_conto_movimenti")
    assert originale["ravvedimento"]["f24_ravvedimento_id"] == ravv["id"] and originale["pagato"] is False
    assert q["riscontro_banca"]["livello"] == reg.LIVELLO_CERTO and q["movimento_bancario_id"] == m["id"]
    assert ravv["pagato"] is True and ravv["status"] == "pagato" and ravv["movimento_bancario_id"] == m["id"]
    assert m["riconciliato"] is True and m["f24_ids"] == [ravv["id"]] and m["quietanze_f24_ids"] == [q["id"]]
    assert run(reg.riconcilia_f24_banca(db))["scritti"]["modelli"] == {"modelli": 0, "relazioni": 0}


def test_ravvedimento_senza_originale_non_nasconde_il_ritardo_nello_scadenzario(ambiente):
    """Il modello di ravvedimento ha la data del versamento (30/04), non una scadenza: senza l'originale
    del commercialista la scadenza e' quella del codice (16/04) e il pagamento resta «ravveduto, 14 giorni»."""
    db, letti, _mp = ambiente
    _arriva(db, letti, "modello_ravvedimento")
    assert collezione(db, "scadenzario_tributi") == []          # un modello senza quietanza non e' un pagamento
    _arriva(db, letti, "quietanza_ravvedimento")
    [voce] = [v for v in collezione(db, "scadenzario_tributi") if v["codice"] == "1001"]
    assert voce["stato"] == "RAVVEDUTO" and voce["scadenza"] == "2026-04-16"
    assert voce["scadenza_fonte"] == "regola 16 del mese dopo" and voce["pagamenti"][0]["giorni_ritardo"] == 14
    # e in Tributi la riga non e' maggiorata dagli interessi del modello di ravvedimento
    from app.services import tributi_per_codice as tributi

    [t] = [v for v in run(tributi.carica_voci(db))["voci"] if v["codice"] == "1001"]
    assert t["inviato_cents"] == 0 and t["pagato_cents"] == 100061 and t["stato"] == tributi.RAVVEDUTO


def test_avviso_su_un_tributo_ravveduto_dice_ravveduto_non_nei_termini(ambiente):
    db, letti, mp = ambiente
    _arriva(db, letti, "modello_ravvedimento")       # il modello rifatto dal titolare, senza l'originale
    _arriva(db, letti, "quietanza_ravvedimento")
    esito = _avviso(_api_avviso(db, mp), [{"codice_tributo": "1001", "periodo": "03/2026", "importo": 1000.00}])
    riga = esito["righe"][0]["scadenzario"]
    assert riga["verdetto"] == "NON_DOVUTO" and riga["prove"][0]["stato"] == "RAVVEDUTO"
    assert "pagato in ritardo e ravveduto con sanzioni e interessi" in riga["motivazione"]
    assert "nei termini" not in esito["verdetto"]["testo"]
