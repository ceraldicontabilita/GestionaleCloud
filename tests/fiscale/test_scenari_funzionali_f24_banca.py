"""Scenari funzionali F24 ↔ quietanza ↔ banca, end-to-end sui servizi reali (archivio in memoria).

Atteso secondo CLAUDE.md («F24, tributi, dichiarazioni»): un solo motore a livelli
(CERTO / PROBABILE / PARZIALE / NESSUN_MATCH / MOVIMENTO_ORFANO); solo il CERTO scrive il
pagamento, gli altri una relazione `pending`; l'abbinamento parte all'arrivo del secondo
pezzo in qualunque ordine; il secondo ingest dà nuovi=0.
"""
import pytest

from app.db_collections import COLL_ENTITY_RELATIONS, COLL_ESTRATTO_CONTO, COLL_F24, COLL_QUIETANZE_F24
from app.parsers import estratto_conto_bpm_parser as parser_bpm
from app.routers.bank import estratto_conto as modulo_estratto
from app.services import event_bus, f24_canonico, quietanze_import as qi
from app.services import f24_controllo_incrociato as reg
from app.services import reconciliation_orchestrator as orch
from tests.fiscale.scenari_f24_comuni import (
    CF, causale_i24, collezione, db_nuovo, modello_parsed, quietanza_parsed, run,
)

RITENUTE_07 = [("sezione_erario", "1001", "07/2026", "654.33", "0")]
PROTOCOLLO = "26081811065626134/000001"
PDF_MODELLO, PDF_QUIETANZA = b"%PDF-modello-ritenute-07-2026", b"%PDF-quietanza-ritenute-07-2026"
ESTRATTO = "Estratto conto corrente_30-09-2026.pdf"  # nome da estratto UFFICIALE della banca


class _File:
    skip_duplicate_repairs = True

    def __init__(self, contenuto, filename):
        self.filename, self._contenuto = filename, contenuto

    async def read(self):
        return self._contenuto


@pytest.fixture
def ambiente(monkeypatch):
    """DB in memoria, parser (solo la lettura dei PDF) sostituiti, bus con gli handler veri."""
    db = db_nuovo("scenari_f24_banca")
    letti = {}
    import app.services.f24_parser as f24_parser
    import app.services.parser_f24 as parser_f24

    monkeypatch.setattr(parser_f24, "parse_f24_commercialista", lambda pdf_content: letti[pdf_content])
    monkeypatch.setattr(f24_parser, "parse_quietanza_f24", lambda pdf_content: letti[pdf_content])
    monkeypatch.setattr(modulo_estratto.Database, "get_db", staticmethod(lambda: db))
    salvati = {k: list(v) for k, v in event_bus._handlers.items()}
    event_bus._handlers.clear()
    event_bus.register_all_handlers()
    orch._IN_ATTESA.clear()
    orch._RIPASSO.clear()
    yield db, letti, monkeypatch
    event_bus._handlers.clear()
    event_bus._handlers.update(salvati)


def _importa_modello(db, letti, righe=RITENUTE_07, data="2026-08-20", pdf=PDF_MODELLO):
    letti[pdf] = modello_parsed(righe, data)
    return run(f24_canonico.importa_modello_bytes(db, pdf, "F24 ritenute luglio.pdf", source="test"))


def _importa_quietanza(db, letti, righe=RITENUTE_07, data="2026-08-20", protocollo=PROTOCOLLO, pdf=PDF_QUIETANZA):
    letti[pdf] = quietanza_parsed(righe, data, protocollo)
    return run(qi.importa_quietanza_bytes(db, pdf, "quietanza.pdf", fonte="test"))


def _importa_estratto(db, monkeypatch, movimenti, contenuto=b"%PDF-estratto"):
    transazioni = [{
        "data": m["data"], "data_valuta": m["data"], "descrizione": m["descrizione"],
        "importo": m["importo"], "tipo": "uscita" if m["importo"] < 0 else "entrata",
        "banca": "Banco BPM", "divisa": "EUR",
    } for m in movimenti]
    monkeypatch.setattr(parser_bpm, "parse_estratto_conto_bpm", lambda _c: {
        "success": True, "tipo_documento": "estratto_conto_banco_bpm",
        "totale_transazioni": len(transazioni), "transazioni": transazioni})
    esito = run(modulo_estratto.import_estratto_conto(_File(contenuto, ESTRATTO)))
    run(orch.attendi_riconciliazione_estratti())
    return esito


ADDEBITO = {"data": "2026-08-20", "importo": -654.33, "descrizione": causale_i24("20/08/2026")}


def _stato(db):
    quietanze = collezione(db, COLL_QUIETANZE_F24)
    modelli = collezione(db, COLL_F24)
    movimenti = collezione(db, COLL_ESTRATTO_CONTO)
    return quietanze, modelli, movimenti


def _impronta(db):
    return {c: collezione(db, c) for c in (COLL_QUIETANZE_F24, COLL_F24, COLL_ESTRATTO_CONTO, COLL_ENTITY_RELATIONS)}


def _senza_provenienze(impronta):
    return {c: [{k: v for k, v in r.items() if k != "source_occurrences"} for r in righe]
            for c, righe in impronta.items()}


def _verifica_certo(db):
    quietanze, modelli, movimenti = _stato(db)
    assert len(quietanze) == 1 and len(modelli) == 1 and len(movimenti) == 1
    q, f, m = quietanze[0], modelli[0], movimenti[0]
    assert q["riscontro_banca"]["livello"] == reg.LIVELLO_CERTO
    assert q["movimento_bancario_id"] == m["id"]
    assert q["f24_associati"] == [f["id"]]
    # il pagamento e' scritto sul modello, con la data d'incasso e l'addebito
    assert f["pagato"] is True and f["movimento_bancario_id"] == m["id"]
    assert f["data_pagamento_effettivo"] == "2026-08-20"
    assert m["riconciliato"] is True and m["f24_ids"] == [f["id"]]
    assert m["quietanze_f24_ids"] == [q["id"]]
    relazioni = {(r["source"]["id"], r["target"]["id"], r["status"]) for r in collezione(db, COLL_ENTITY_RELATIONS)
                 if r["relation_type"] in ("settles_f24_receipt", "settles_f24_model")}
    assert (m["id"], q["id"], "confirmed") in relazioni and (m["id"], f["id"], "confirmed") in relazioni


def test_ordine_modello_quietanza_banca(ambiente):
    db, letti, mp = ambiente
    m = _importa_modello(db, letti)
    assert m["success"] and not m["duplicate"]
    q = _importa_quietanza(db, letti)
    assert q["success"] and len(q["f24_matchati"]) == 1
    _importa_estratto(db, mp, [ADDEBITO])
    _verifica_certo(db)


def test_ordine_banca_modello_quietanza(ambiente):
    db, letti, mp = ambiente
    _importa_estratto(db, mp, [ADDEBITO])
    _importa_modello(db, letti)
    _importa_quietanza(db, letti)
    _verifica_certo(db)


def test_ordine_banca_quietanza_modello(ambiente):
    db, letti, mp = ambiente
    _importa_estratto(db, mp, [ADDEBITO])
    q = _importa_quietanza(db, letti)
    assert q["warning"].startswith("F24 mancante")      # prova senza modello: mai ricostruito
    bloccanti = collezione(db, "f24_riconciliazione_alerts")
    assert [a["status"] for a in bloccanti] == ["pending"] and bloccanti[0]["bloccante"] is True
    _importa_modello(db, letti)
    _verifica_certo(db)
    # arrivato il modello, l'alert bloccante «F24 mancante» non e' piu' vero e si chiude
    assert [a["status"] for a in collezione(db, "f24_riconciliazione_alerts")] == ["risolto"]
    [qz] = collezione(db, COLL_QUIETANZE_F24)
    assert qz["stato_associazione"] == "associata" and qz["calcolo_fiscale_sospeso"] is False


def test_ordine_quietanza_modello_banca(ambiente):
    db, letti, mp = ambiente
    _importa_quietanza(db, letti)
    _importa_modello(db, letti)
    _importa_estratto(db, mp, [ADDEBITO])
    _verifica_certo(db)


def test_secondo_ingest_di_ogni_pezzo_da_nuovi_zero_e_non_cambia_niente(ambiente):
    db, letti, mp = ambiente
    _importa_modello(db, letti)
    _importa_quietanza(db, letti)
    primo = _importa_estratto(db, mp, [ADDEBITO])
    assert primo["stats"]["nuovi"] == 1
    _verifica_certo(db)
    prima = _impronta(db)

    secondo = _importa_estratto(db, mp, [ADDEBITO])
    assert secondo["stats"]["nuovi"] == 0
    m2 = _importa_modello(db, letti)
    q2 = _importa_quietanza(db, letti)
    assert m2["duplicate"] is True and q2["duplicate"] is True
    giro = run(reg.riconcilia_f24_banca(db))
    assert giro["scritti"] == {"quietanze": 0, "addebiti": 0, "relazioni": 0, "alert_aperti": 0,
                               "alert_chiusi": 0, "modelli": {"modelli": 0, "relazioni": 0}}
    # La copia vista una seconda volta si annota fra le provenienze (non e' un documento nuovo):
    # tutto il resto, compreso lo stato di pagamento del modello, resta com'era.
    assert _senza_provenienze(_impronta(db)) == _senza_provenienze(prima)


# ── 2. i casi non certi: dichiarati, mai scritti come pagamento ─────────────────────────

def _alert_aperti(db, codice):
    return run(db["alerts"].find({"codice": codice, "stato": "aperto"}, {"_id": 0}).to_list(50))


def _relazioni_f24(db):
    return [(r["source"]["id"], r["target"]["id"], r["status"], r["rule"]) for r in collezione(db, COLL_ENTITY_RELATIONS)
            if r["relation_type"] in ("settles_f24_receipt", "settles_f24_model")]


def _nessun_pagamento_scritto(db):
    quietanze, modelli, movimenti = _stato(db)
    for q in quietanze:
        assert "riscontro_banca" not in q and not q.get("movimento_bancario_id")
    for f in modelli:
        assert f["pagato"] is False and f["status"] == "da_pagare" and not f.get("movimento_bancario_id")
    for m in movimenti:
        assert not m.get("riconciliato") and not m.get("quietanze_f24_ids") and not m.get("f24_ids")


def test_causale_senza_data_incasso_e_probabile_senza_scrivere_il_pagamento(ambiente):
    db, letti, mp = ambiente
    _importa_modello(db, letti)
    _importa_quietanza(db, letti)
    _importa_estratto(db, mp, [{**ADDEBITO, "descrizione": causale_i24()}])
    esito = run(reg.riconcilia_f24_banca(db))

    [r] = esito["da_verificare"]
    assert r["livello"] == reg.LIVELLO_PROBABILE and r["addebito"]["importo"] == 654.33
    assert "la causale non riporta la data d'incasso" in r["motivazione"]
    assert esito["riscontrati"] == []
    _nessun_pagamento_scritto(db)
    [(mov, _q, stato, regola)] = [x for x in _relazioni_f24(db) if x[1] == collezione(db, COLL_QUIETANZE_F24)[0]["id"]]
    assert (stato, regola) == ("pending", "f24_banca:PROBABILE")
    assert mov == collezione(db, COLL_ESTRATTO_CONTO)[0]["id"]


def test_due_addebiti_candidati_si_mostrano_tutti_e_nessuno_si_sceglie(ambiente):
    db, letti, mp = ambiente
    _importa_modello(db, letti)
    _importa_quietanza(db, letti)
    gemello = {**ADDEBITO, "data": "2026-08-21", "descrizione": causale_i24("20/08/2026", "2026-08-21-09.00.00.000000000001")}
    _importa_estratto(db, mp, [ADDEBITO, gemello])
    esito = run(reg.riconcilia_f24_banca(db))

    [r] = esito["da_verificare"]
    assert r["livello"] == reg.LIVELLO_PROBABILE and len(r["candidati"]) == 2
    assert {c["data"] for c in r["candidati"]} == {"2026-08-20", "2026-08-21"}
    assert esito["riscontrati"] == []
    _nessun_pagamento_scritto(db)
    assert sorted(s for *_x, s, _r in _relazioni_f24(db)) == ["pending", "pending"]


def test_differenza_sotto_cinque_euro_e_parziale_con_la_differenza(ambiente):
    db, letti, mp = ambiente
    _importa_modello(db, letti)
    _importa_quietanza(db, letti)
    _importa_estratto(db, mp, [{**ADDEBITO, "importo": -656.33}])
    esito = run(reg.riconcilia_f24_banca(db))

    [r] = esito["da_verificare"]
    assert r["livello"] == reg.LIVELLO_PARZIALE and r["differenza"] == 2.0
    assert "differenza +2.00 EUR" in r["motivazione"] and "da verificare con il commercialista" in r["motivazione"]
    _nessun_pagamento_scritto(db)
    assert all(s == "pending" and regola == "f24_banca:PARZIALE" for *_x, s, regola in _relazioni_f24(db))
    # il limite e' inclusivo: 5,00 EUR e' ancora parziale, 5,01 no (addebito orfano + nessun match)
    db2 = db_nuovo("scenari_f24_banca_soglia")
    for importo, atteso in ((-659.33, reg.LIVELLO_PARZIALE), (-659.34, None)):
        esito = reg.riscontri_quietanze_banca(
            [reg._quietanza_legacy({"id": "q", "data_pagamento": "2026-08-20", "saldo": 654.33,
                                    "protocollo_telematico": PROTOCOLLO, "f24_associati": []})],
            [{"id": "m", "data": "2026-08-20", "importo": importo, "tipo": "uscita",
              "descrizione": causale_i24("20/08/2026")}])
        assert (esito["da_verificare"][0]["livello"] if esito["da_verificare"] else None) == atteso
    assert db2 is not None


def test_nessun_addebito_dice_se_l_estratto_del_periodo_c_e_ed_e_un_alert_solo_se_c_e(ambiente):
    db, letti, mp = ambiente
    _importa_quietanza(db, letti)
    # estratto del periodo presente: altri movimenti prima e dopo il 20/08, nessun addebito I24 di 654,33
    _importa_estratto(db, mp, [
        {"data": "2026-08-03", "importo": -10.0, "descrizione": causale_i24("03/08/2026")},
        {"data": "2026-09-10", "importo": -20.0, "descrizione": causale_i24("10/09/2026", "2026-09-10-09.00.00.000000000009")},
    ])
    esito = run(reg.riconcilia_f24_banca(db))
    [n] = esito["quietanze_senza_addebito"]
    assert n["livello"] == reg.LIVELLO_NESSUN_MATCH and n["estratto_periodo_presente"] is True
    assert "estratto del periodo presente: si'" in n["motivazione"]
    assert len(_alert_aperti(db, reg.ALERT_QUIETANZA_SENZA_ADDEBITO)) == 1

    # estratto del periodo assente: non si dice che il pagamento manca, e nessun alert
    db2 = db_nuovo("scenari_f24_banca_senza_estratto")
    run(db2[COLL_QUIETANZE_F24].insert_one({
        "id": "q1", "data_pagamento": "2026-08-20", "saldo": 654.33, "protocollo_telematico": PROTOCOLLO,
        "filename": "q.pdf", "f24_associati": []}))
    run(db2[COLL_ESTRATTO_CONTO].insert_one({
        "id": "m0", "data": "2026-01-16", "importo": -10.0, "tipo": "uscita", "descrizione": causale_i24("16/01/2026")}))
    esito2 = run(reg.riconcilia_f24_banca(db2))
    [s] = esito2["quietanze_senza_estratto"]
    assert s["estratto_periodo_presente"] is False and "non si puo' dire se il pagamento manchi" in s["motivazione"]
    assert esito2["quietanze_senza_addebito"] == []
    assert run(db2["alerts"].find({"codice": reg.ALERT_QUIETANZA_SENZA_ADDEBITO}).to_list(10)) == []


def test_addebito_senza_quietanza_e_orfano_con_alert_che_si_chiude_all_arrivo_della_quietanza(ambiente):
    db, letti, mp = ambiente
    _importa_estratto(db, mp, [ADDEBITO])
    esito = run(reg.riconcilia_f24_banca(db))
    [o] = esito["addebiti_senza_quietanza"]
    assert o["livello"] == reg.LIVELLO_MOVIMENTO_ORFANO and "probabile quietanza da riscaricare" in o["motivazione"]
    [alert] = _alert_aperti(db, reg.ALERT_ADDEBITO_SENZA_QUIETANZA)
    assert alert["extra"]["record"][0]["importo"] == 654.33 and alert["entita_collection"] == COLL_ESTRATTO_CONTO

    # arriva la quietanza: il collegamento nasce subito e l'alert, che ora e' falso, si chiude subito
    _importa_quietanza(db, letti)
    q = collezione(db, COLL_QUIETANZE_F24)[0]
    assert q["riscontro_banca"]["livello"] == reg.LIVELLO_CERTO
    assert _alert_aperti(db, reg.ALERT_ADDEBITO_SENZA_QUIETANZA) == []


# ── identita' e finestre: cio' che NON deve agganciarsi ──────────────────────────────────

def test_un_cbill_all_agenzia_con_lo_stesso_importo_non_e_un_addebito_di_delega(ambiente):
    db, letti, mp = ambiente
    _importa_quietanza(db, letti)
    _importa_estratto(db, mp, [{"data": "2026-08-20", "importo": -654.33,
                                "descrizione": "PAGAMENTO CBILL AGENZIA ENTRATE RISCOSSIONE DATA INCASSO 20/08/2026"}])
    esito = run(reg.riconcilia_f24_banca(db))
    assert esito["riscontrati"] == [] and esito["addebiti_senza_quietanza"] == []
    assert "riscontro_banca" not in collezione(db, COLL_QUIETANZE_F24)[0]


def test_quietanza_di_un_altro_contribuente_non_si_aggancia_al_modello_nemmeno_con_righe_uguali(ambiente):
    db, letti, _mp = ambiente
    _importa_modello(db, letti)
    letti[b"%PDF-altro-cf"] = quietanza_parsed(RITENUTE_07, "2026-08-20", PROTOCOLLO, cf="12345678901")
    q = run(qi.importa_quietanza_bytes(db, b"%PDF-altro-cf", "altro.pdf", fonte="test"))
    assert q["f24_matchati"] == [] and q["stato_quietanza"] == "QUIETANZA_PRESENTE_F24_MANCANTE"
    [f] = collezione(db, COLL_F24)
    assert not f.get("quietanza_id") and f["pagato"] is False


def test_addebito_oltre_due_giorni_lavorativi_non_e_lo_stesso_pagamento(ambiente):
    db, letti, mp = ambiente
    _importa_quietanza(db, letti)                                   # giovedi' 20/08/2026
    _importa_estratto(db, mp, [{**ADDEBITO, "data": "2026-08-25"}])  # martedi': 3 giorni lavorativi dopo
    esito = run(reg.riconcilia_f24_banca(db))
    assert esito["riscontrati"] == [] and esito["da_verificare"] == []
    assert [o["livello"] for o in esito["addebiti_senza_quietanza"]] == [reg.LIVELLO_MOVIMENTO_ORFANO]
    # entro 2 giorni lavorativi (lunedi' 24) con la stessa DATA INCASSO e' lo stesso pagamento
    db2 = db_nuovo("scenari_f24_banca_finestra")
    run(db2[COLL_QUIETANZE_F24].insert_one({
        "id": "q", "data_pagamento": "2026-08-20", "saldo": 654.33, "protocollo_telematico": PROTOCOLLO,
        "filename": "q.pdf", "f24_associati": []}))
    run(db2[COLL_ESTRATTO_CONTO].insert_one({**ADDEBITO, "id": "m", "data": "2026-08-24", "tipo": "uscita"}))
    assert run(reg.riconcilia_f24_banca(db2))["riscontrati"][0]["livello"] == reg.LIVELLO_CERTO


def test_la_quietanza_sceglie_il_modello_giusto_fra_piu_modelli_simili(ambiente):
    db, letti, mp = ambiente
    giusto = _importa_modello(db, letti)["f24_id"]
    # stesso codice e periodo ma importo diverso; stesso importo ma altro periodo; stesso tutto ma altro contribuente
    altro_importo = _importa_modello(db, letti, [("sezione_erario", "1001", "07/2026", "654.34", "0")], pdf=b"%PDF-m2")["f24_id"]
    altro_periodo = _importa_modello(db, letti, [("sezione_erario", "1001", "06/2026", "654.33", "0")],
                                     data="2026-07-16", pdf=b"%PDF-m3")["f24_id"]
    letti[b"%PDF-m4"] = modello_parsed(RITENUTE_07, "2026-08-20", cf="12345678901")
    altro_cf = run(f24_canonico.importa_modello_bytes(db, b"%PDF-m4", "F24 altro contribuente.pdf", source="test"))["f24_id"]
    assert len({giusto, altro_importo, altro_periodo, altro_cf}) == 4

    q = _importa_quietanza(db, letti)
    assert [m["f24_id"] for m in q["f24_matchati"]] == [giusto]
    modelli = {f["id"]: f for f in collezione(db, COLL_F24)}
    assert modelli[giusto]["quietanza_id"] == q["quietanza_id"]
    assert not any(modelli[i].get("quietanza_id") for i in (altro_importo, altro_periodo, altro_cf))
    _importa_estratto(db, mp, [ADDEBITO])
    modelli = {f["id"]: f for f in collezione(db, COLL_F24)}
    assert modelli[giusto]["pagato"] is True
    assert not any(modelli[i]["pagato"] for i in (altro_importo, altro_periodo, altro_cf))
