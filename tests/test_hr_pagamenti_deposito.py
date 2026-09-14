"""Ponte gestionale -> HR per i pagamenti stipendio (14/09/2026).

Entrambi i database sono finti (mongomock): il gestionale (bonifici_transfers,
estratto_conto_movimenti, documents_inbox) e l'HR (dipendenti, pagamenti_esiti,
paghe_mensili, bonifici_da_associare). Nessuna rete, nessun PDF vero.
"""
import asyncio
import base64

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.services import hr_pagamenti_deposito as ponte

VESPA = {"id": "dip-vespa", "nome": "Vincenzo", "cognome": "Vespa",
         "nome_completo": "Vespa Vincenzo", "codice_fiscale": "VSPVCN80A01F839X", "attivo": True}
TAIANO = {"id": "dip-taiano", "nome": "Luigi", "cognome": "Taiano",
          "nome_completo": "Taiano Luigi", "codice_fiscale": "TNALGU85B02F839Y", "attivo": True}
RUSSO_C = {"id": "dip-russo-c", "nome": "Carmine", "cognome": "Russo",
           "nome_completo": "Russo Carmine", "codice_fiscale": "RSSCMN90C03F839Z", "attivo": True}
RUSSO_A = {"id": "dip-russo-a", "nome": "Anna", "cognome": "Russo",
           "nome_completo": "Russo Anna", "codice_fiscale": "RSSNNA91D44F839W", "attivo": True}

PDF = base64.b64encode(b"%PDF-1.4 finto").decode()


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def basi(monkeypatch):
    from app.hr.database import Database as DatabaseHR

    db = AsyncMongoMockClient()["gestionale_test"]
    hr = AsyncMongoMockClient()["hr_test"]
    monkeypatch.setattr(DatabaseHR, "get_db", classmethod(lambda cls: hr))
    _run(hr.dipendenti.insert_many([dict(VESPA), dict(TAIANO), dict(RUSSO_C), dict(RUSSO_A)]))
    return db, hr


def _transfer(**extra):
    base = {
        "id": "tr-1", "source": "drive_bonifico",
        "source_file": "Bonifico - ricevuta per ordinante_03-02-2026_1000,00.pdf",
        "source_path": "VESPA VINCENZO/BONIFICI/DA ELABORARE/Bonifico - ricevuta per ordinante_03-02-2026_1000,00.pdf",
        "data": "2026-02-03T00:00:00+00:00", "importo": 1000.0,
        "beneficiario": {"nome": "Vespa Vincenzo", "iban": None},
        "causale": "AGGIUNTIVA", "cro_trn": "5034903683956034480340003400IT",
        "periodo_mese": None, "periodo_anno": None,
        "document_hash": "a" * 64, "pdf_data": PDF, "riconciliato": False,
    }
    base.update(extra)
    return base


def _movimento(**extra):
    base = {
        "id": "2026-08-06_-1377.00_VOSTRA_DISPOSIZIONE_-_VSDISP", "data": "2026-08-06",
        "importo": -1377.0, "tipo": "uscita",
        "descrizione": "VOSTRA DISPOSIZIONE - VS.DISP. RIF. MB0B00923006/90679785 FAVORE Vespa Vincenzo - ADD.TOT - Vespa Vincenzo stip luglio 2026",
        "riconciliato": False,
    }
    base.update(extra)
    return base


# ── regole pure ──────────────────────────────────────────────────────────────

def test_fascicolo_persona_dal_percorso_drive():
    assert ponte.fascicolo_persona("VESPA VINCENZO/BONIFICI/DA ELABORARE/x.pdf") == "VESPA VINCENZO"
    assert ponte.fascicolo_persona("DA ELABORARE/x.pdf") is None
    assert ponte.fascicolo_persona("BONIFICI/DA ELABORARE/x.pdf") is None
    assert ponte.fascicolo_persona(None) is None


def test_periodo_bonifico_regola_del_giorno_25_e_causale():
    # saldo di gennaio pagato il 3 febbraio
    assert ponte.periodo_bonifico("AGGIUNTIVA", "2026-02-03") == (1, 2026)
    # dal 25 in poi e' il mese corrente
    assert ponte.periodo_bonifico("AGGIUNTIVA", "2026-03-30") == (3, 2026)
    # la causale vince sulla data
    assert ponte.periodo_bonifico("stip luglio 2026", "2026-08-06") == (7, 2026)
    # mese dichiarato dal parser senza anno: anno del bonifico (dicembre -> anno prima)
    assert ponte.periodo_bonifico("x", "2026-01-07", mese_dichiarato=12) == (12, 2025)
    assert ponte.periodo_bonifico("x", "2026-04-02", mese_dichiarato=3) == (3, 2026)


def test_risolvi_dipendente_cf_nome_cognome_ambiguo(basi):
    _, hr = basi
    from app.hr.routers.dipendenti_cloud import _indici_dipendenti

    indici = _run(_indici_dipendenti(hr))
    assert ponte.risolvi_dipendente(indici, "ADD.TOT - tnalgu85b02f839y stipendio")[0]["id"] == "dip-taiano"
    assert ponte.risolvi_dipendente(indici, "FAVORE Vespa Vincenzo - ADD.TOT")[0]["id"] == "dip-vespa"
    assert ponte.risolvi_dipendente(indici, "bonifico taiano marzo")[0]["id"] == "dip-taiano"
    assert ponte.risolvi_dipendente(indici, "bonifico russo marzo") == (None, "ambiguo")
    assert ponte.risolvi_dipendente(indici, "FAVORE Edenred Italia") == (None, "nessuno")


def test_movimento_candidato_solo_uscite_con_favore():
    assert ponte.movimento_candidato_stipendio(_movimento())
    assert not ponte.movimento_candidato_stipendio(_movimento(tipo="entrata", importo=6000,
        descrizione="BONIF. VS. FAVORE - BON.DA CERALDI MICHELE - Finanziamento soci"))
    assert not ponte.movimento_candidato_stipendio(_movimento(importo=-1.1,
        descrizione="COMM.SU BONIFICI - VS.DISP. RIF. MB0B01767911 FAVORE Moscato Emanuele - ADD.SPE"))
    assert not ponte.movimento_candidato_stipendio(_movimento(descrizione="PAGAMENTO POS 1234"))


# ── ingresso 1: PDF bonifico ─────────────────────────────────────────────────

def test_bonifico_del_fascicolo_entra_in_hr_con_pdf_e_stato_paga(basi):
    db, hr = basi
    _run(db.bonifici_transfers.insert_one(_transfer()))
    _run(hr.paghe_mensili.insert_one({"dipendente_id": "dip-vespa", "anno": 2026, "mese": 1,
                                      "importo_busta": 1000.0, "stato_pagamento": "in_attesa_pagamento"}))

    marca = _run(ponte.deposita_bonifico_transfer_in_hr(db, _transfer()))

    assert marca["esito"] == "depositato"
    assert marca["key"] == "gc:" + "a" * 24
    assert (marca["mese"], marca["anno"]) == (1, 2026)
    esito = _run(hr.pagamenti_esiti.find_one({"key": marca["key"]}, {"_id": 0}))
    assert esito["dipendente_id"] == "dip-vespa"
    assert esito["importo"] == 1000.0 and esito["data"] == "2026-02-03"
    assert esito["cro"] == "5034903683956034480340003400IT"
    assert esito["pdf_data"] == PDF and esito["ha_pdf"] is True
    assert esito["origine"] == ponte.ORIGINE_PDF
    assert esito["gestionale_transfer_id"] == "tr-1"
    paga = _run(hr.paghe_mensili.find_one({"dipendente_id": "dip-vespa", "anno": 2026, "mese": 1}))
    assert paga["stato_pagamento"] == "pagato"
    assert paga["bonifico_importo"] == 1000.0
    sorgente = _run(db.bonifici_transfers.find_one({"id": "tr-1"}))
    assert sorgente["hr_deposito"]["esito"] == "depositato"
    assert sorgente["hr_deposito"]["dipendente_id"] == "dip-vespa"


def test_bonifico_senza_fascicolo_e_senza_parola_stipendio_va_in_coda(basi):
    db, hr = basi
    transfer = _transfer(source="upload_manuale", source_path=None)
    _run(db.bonifici_transfers.insert_one(transfer))

    marca = _run(ponte.deposita_bonifico_transfer_in_hr(db, transfer))

    assert marca["esito"] == "in_coda"
    assert marca["motivo"] == "senza_segnale_stipendio"
    coda = _run(hr.bonifici_da_associare.find_one({"id": marca["coda_id"]}, {"_id": 0}))
    assert coda["stato"] == "da_associare" and coda["importo"] == 1000.0
    assert coda["pdf_data"] == PDF and coda["hash"] == "a" * 64
    assert coda["fonte"] == ponte.ORIGINE_PDF
    assert _run(hr.pagamenti_esiti.count_documents({})) == 0


def test_bonifico_con_causale_stipendio_ma_cognome_ambiguo_va_in_coda(basi):
    db, hr = basi
    transfer = _transfer(source="upload_manuale", source_path=None,
                         beneficiario={"nome": "ricevuta per ordinante"},
                         causale="Russo stipendio marzo 2026", source_file="bonifico.pdf")
    marca = _run(ponte.deposita_bonifico_transfer_in_hr(db, transfer))
    assert marca["esito"] == "in_coda" and marca["motivo"] == "ambiguo"
    assert _run(hr.bonifici_da_associare.count_documents({"stato": "da_associare"})) == 1


def test_bonifico_gia_importato_dal_drive_hr_non_viene_duplicato(basi):
    db, hr = basi
    _run(hr.pagamenti_esiti.insert_one({"key": "drive:" + "a" * 24, "hash": "a" * 64,
                                        "dipendente_id": "dip-vespa", "data": "2026-02-03",
                                        "importo": 1000.0, "mese": 1, "anno": 2026, "origine": "drive-pdf"}))
    marca = _run(ponte.deposita_bonifico_transfer_in_hr(db, _transfer()))
    assert marca["esito"] == "duplicato" and marca["motivo"] == "hash"
    assert _run(hr.pagamenti_esiti.count_documents({})) == 1


def test_bonifico_tfr_o_fattura_non_entra_mai(basi):
    db, hr = basi
    marca = _run(ponte.deposita_bonifico_transfer_in_hr(
        db, _transfer(causale="Vespa Vincenzo TFR", source_path=None)))
    assert marca["esito"] == "non_stipendio"
    marca = _run(ponte.deposita_bonifico_transfer_in_hr(db, _transfer(fattura_associata=True)))
    assert marca["esito"] == "non_stipendio" and marca["motivo"] == "fattura_fornitore"
    assert _run(hr.pagamenti_esiti.count_documents({})) == 0
    assert _run(hr.bonifici_da_associare.count_documents({})) == 0


def test_transfer_storico_recupera_il_fascicolo_da_import_documenti(basi):
    db, hr = basi
    transfer = _transfer(source_path=None)
    _run(db.bonifici_transfers.insert_one(transfer))
    _run(db.documents_inbox.insert_one({"id": "inbox-1", "category": "bonifico",
                                        "bonifico_transfer_id": "tr-1",
                                        "source_path": "VESPA VINCENZO/BONIFICI/DA ELABORARE/x.pdf"}))
    marca = _run(ponte.deposita_bonifico_transfer_in_hr(db, transfer))
    assert marca["esito"] == "depositato" and marca["dipendente_id"] == "dip-vespa"


def test_hr_non_configurato_e_un_no_op(basi, monkeypatch):
    from app.hr.database import Database as DatabaseHR, DatabaseNonConfigurato

    db, _ = basi
    monkeypatch.setattr(DatabaseHR, "get_db", classmethod(lambda cls: DatabaseNonConfigurato()))
    _run(db.bonifici_transfers.insert_one(_transfer()))
    marca = _run(ponte.deposita_bonifico_transfer_in_hr(db, _transfer()))
    assert marca["esito"] == "hr_non_configurato"
    assert "hr_deposito" not in _run(db.bonifici_transfers.find_one({"id": "tr-1"}))


# ── ingresso 2: riga di estratto conto ───────────────────────────────────────

def test_uscita_bancaria_favore_dipendente_con_stip_entra_in_hr(basi):
    db, hr = basi
    mov = _movimento()
    _run(db.estratto_conto_movimenti.insert_one(mov))
    _run(hr.paghe_mensili.insert_one({"dipendente_id": "dip-vespa", "anno": 2026, "mese": 7,
                                      "importo_busta": 1377.0}))

    marca = _run(ponte.deposita_movimento_banca_in_hr(db, mov))

    assert marca["esito"] == "depositato"
    assert (marca["mese"], marca["anno"]) == (7, 2026)
    esito = _run(hr.pagamenti_esiti.find_one({"key": "ecm:" + mov["id"]}, {"_id": 0}))
    assert esito["importo"] == 1377.0 and esito["data"] == "2026-08-06"
    assert esito["cro"] == "MB0B00923006/90679785"
    assert esito["ha_pdf"] is False and esito["origine"] == ponte.ORIGINE_BANCA
    paga = _run(hr.paghe_mensili.find_one({"dipendente_id": "dip-vespa", "anno": 2026, "mese": 7}))
    assert paga["stato_pagamento"] == "pagato"
    assert _run(db.estratto_conto_movimenti.find_one({"id": mov["id"]}))["hr_deposito"]["esito"] == "depositato"


def test_uscita_bancaria_con_cf_e_senza_mese_usa_la_regola_del_25(basi):
    db, hr = basi
    mov = _movimento(id="m-2", data="2026-08-07", importo=-1400,
                     descrizione="VOSTRA DISPOSIZIONE - VS.DISP. RIF. MB0B01752723/90731633 FAVORE Ceraldi Valerio - ADD.TOT - tnalgu85b02f839y stipendio")
    marca = _run(ponte.deposita_movimento_banca_in_hr(db, mov))
    assert marca["esito"] == "depositato" and marca["dipendente_id"] == "dip-taiano"
    assert (marca["mese"], marca["anno"]) == (7, 2026)


def test_stessa_paga_vista_da_pdf_e_da_banca_arricchisce_senza_duplicare(basi):
    db, hr = basi
    # 1) il PDF del fascicolo entra per primo (con PDF, senza riferimento banca)
    transfer = _transfer(data="2026-08-06T00:00:00+00:00", importo=1377.0, cro_trn=None)
    _run(ponte.deposita_bonifico_transfer_in_hr(db, transfer))
    # 2) poi arriva la riga dell'estratto conto: stesso dipendente, importo, data
    marca = _run(ponte.deposita_movimento_banca_in_hr(db, _movimento()))
    assert marca["esito"] == "arricchito" and marca["motivo"] == "vicino"
    assert "cro" in marca["campi"] and "gestionale_movimento_id" in marca["campi"]
    esiti = _run(hr.pagamenti_esiti.find({}, {"_id": 0}).to_list(None))
    assert len(esiti) == 1
    assert esiti[0]["key"].startswith("gc:") and esiti[0]["cro"] == "MB0B00923006/90679785"
    assert esiti[0]["pdf_data"] == PDF


def test_uscita_a_dipendente_senza_parola_stipendio_va_in_coda(basi):
    db, hr = basi
    mov = _movimento(id="m-3", importo=-1500,
                     descrizione="VOSTRA DISPOSIZIONE - VS.DISP. RIF. MB0B01411410/90509783 FAVORE Taiano Luigi - ADD.TOT - TAIANO LUIGI")
    marca = _run(ponte.deposita_movimento_banca_in_hr(db, mov))
    assert marca["esito"] == "in_coda" and marca["motivo"] == "senza_segnale_stipendio"
    coda = _run(hr.bonifici_da_associare.find_one({"id": marca["coda_id"]}, {"_id": 0}))
    assert coda["fonte"] == ponte.ORIGINE_BANCA and coda["gestionale_movimento_id"] == "m-3"


def test_uscite_a_fornitori_tfr_e_commissioni_non_entrano(basi):
    db, hr = basi
    casi = [
        _movimento(id="m-f", importo=-1656.64,
                   descrizione="VOSTRA DISPOSIZIONE - RIF. MBVT40187878 FAVORE Rosaria Marotta NOTPROVIDE - Rosaria Marotta fattura FPR 31/26"),
        _movimento(id="m-tfr", importo=-15000,
                   descrizione="VOSTRA DISPOSIZIONE - RIF. MB0B01767911 FAVORE Taiano Luigi - ADD.TOT - tnalgu85b02f839y TFR"),
        _movimento(id="m-srl", importo=-2752.98,
                   descrizione="VOSTRA DISPOSIZIONE - RIF. MBVT40188610 FAVORE Edenred Italia S.r.l. NOTPROVIDE - edenred"),
    ]
    esiti = [_run(ponte.deposita_movimento_banca_in_hr(db, m))["esito"] for m in casi]
    assert esiti == ["non_stipendio", "non_stipendio", "non_stipendio"]
    assert _run(hr.pagamenti_esiti.count_documents({})) == 0
    assert _run(hr.bonifici_da_associare.count_documents({})) == 0


# ── giro periodico / backfill ────────────────────────────────────────────────

def test_giro_riprende_solo_i_documenti_senza_marcatore_ed_e_idempotente(basi):
    db, hr = basi
    _run(db.bonifici_transfers.insert_many([
        _transfer(),
        _transfer(id="tr-fatto", document_hash="b" * 64, hr_deposito={"esito": "depositato"}),
    ]))
    _run(db.estratto_conto_movimenti.insert_many([
        _movimento(),
        _movimento(id="m-pos", tipo="uscita", importo=-12.5, descrizione="PAGAMENTO POS 1234"),
        _movimento(id="m-entrata", tipo="entrata", importo=59.9, descrizione="BONIF. VS. FAVORE - BON.DA AMAZON"),
    ]))

    prova = _run(ponte.deposita_pagamenti_in_hr(db, dry_run=True))
    assert prova["dry_run"] is True
    assert prova["bonifici_pdf"] == {"depositato": 1}
    assert prova["estratto_conto"] == {"depositato": 1, "non_stipendio": 2}
    assert _run(hr.pagamenti_esiti.count_documents({})) == 0
    assert "hr_deposito" not in _run(db.bonifici_transfers.find_one({"id": "tr-1"}))

    vero = _run(ponte.deposita_pagamenti_in_hr(db))
    assert vero["bonifici_pdf"] == {"depositato": 1}
    assert vero["estratto_conto"] == {"depositato": 1, "non_stipendio": 2}
    assert vero["letti"] == {"bonifici_pdf": 1, "estratto_conto": 3, "estratto_conto_riesame": 0}
    assert _run(hr.pagamenti_esiti.count_documents({})) == 2
    assert [d["sezione"] for d in vero["dettaglio"]] == ["bonifici_pdf", "estratto_conto"]

    ancora = _run(ponte.deposita_pagamenti_in_hr(db))
    assert ancora["letti"] == {"bonifici_pdf": 0, "estratto_conto": 0, "estratto_conto_riesame": 0}
    assert _run(hr.pagamenti_esiti.count_documents({})) == 2


def test_importa_pdf_bonifico_deposita_in_hr_senza_bloccare_l_ingest(basi, monkeypatch):
    from app.services import bonifici_pdf_ingest as ingest

    db, hr = basi
    monkeypatch.setattr(ingest, "read_pdf_bytes", lambda content: "Data esecuzione: 03/02/2026\nImporto bonifico: EUR 1.000,00\nCausale: AGGIUNTIVA\n")
    contenuto = b"%PDF-1.4 bonifico finto vespa"
    esito = _run(ingest.importa_pdf_bonifico(
        db, contenuto, "Bonifico - ricevuta per ordinante_03-02-2026_1000,00.pdf",
        source="drive_bonifico", auto_associa=False,
        source_path="VESPA VINCENZO/BONIFICI/DA ELABORARE/Bonifico - ricevuta per ordinante_03-02-2026_1000,00.pdf",
    ))
    assert esito["status"] == "saved"
    assert esito["deposito_hr"] == "depositato"
    transfer = _run(db.bonifici_transfers.find_one({"id": esito["transfer_id"]}, {"_id": 0}))
    assert transfer["source_path"].startswith("VESPA VINCENZO/BONIFICI/")
    assert transfer["hr_deposito"]["esito"] == "depositato"
    hr_esito = _run(hr.pagamenti_esiti.find_one({"dipendente_id": "dip-vespa"}, {"_id": 0}))
    assert hr_esito["importo"] == 1000.0 and hr_esito["hash"] == transfer["document_hash"]
    assert (hr_esito["mese"], hr_esito["anno"]) == (1, 2026)


def test_lotto_paghe_stesso_giorno_entra_senza_parola_stipendio(basi):
    """Estratto conto reale gen-apr 2026: 'FAVORE <dipendente> - ADD.TOT' senza
    causale, ma 3+ dipendenti lo stesso giorno = lotto paghe."""
    db, hr = basi
    _run(hr.dipendenti.insert_one({"id": "dip-lesina", "nome": "Angela", "cognome": "Lesina",
                                   "nome_completo": "Lesina Angela", "codice_fiscale": "LSNNGL92E45F839Q"}))
    righe = [
        _movimento(id="l-1", data="2026-02-03", importo=-1000,
                   descrizione="VS.DISP. RIF. MB0B10284028/90368396 FAVORE VESPA VINCENZO - ADD.TOT"),
        _movimento(id="l-2", data="2026-02-03", importo=-1000,
                   descrizione="VS.DISP. RIF. MB0B10283922/90368225 FAVORE TAIANO LUIGI - ADD.TOT"),
        _movimento(id="l-3", data="2026-02-03", importo=-1000,
                   descrizione="VS.DISP. RIF. MB0B10283457/90367437 FAVORE LESINA ANGELA - ADD.TOT"),
        # giorno diverso, un solo dipendente: resta in coda
        _movimento(id="l-4", data="2026-02-13", importo=-800,
                   descrizione="VS.DISP. RIF. MB0B16277669/90292976 FAVORE TAIANO LUIGI - ADD.TOT"),
        # cumulativo senza nomi: coda (mai scartato)
        _movimento(id="l-5", data="2026-03-16", importo=-1147,
                   descrizione="VS.DISP. RIF. MB0B30867928/90433783 FAVORE BENEFICIARI VARI DISTINTA - ADD.TOT"),
    ]
    _run(db.estratto_conto_movimenti.insert_many(righe))

    report = _run(ponte.deposita_pagamenti_in_hr(db))

    assert report["estratto_conto"] == {"depositato": 3, "in_coda": 2}
    marche = {m["id"]: m for m in _run(db.estratto_conto_movimenti.find({}, {"_id": 0}).to_list(None))}
    assert marche["l-1"]["hr_deposito"]["segnale"] == "lotto_paghe"
    assert (marche["l-1"]["hr_deposito"]["mese"], marche["l-1"]["hr_deposito"]["anno"]) == (1, 2026)
    assert marche["l-4"]["hr_deposito"]["motivo"] == "senza_segnale_stipendio"
    assert marche["l-5"]["hr_deposito"]["motivo"] == "beneficiari_diversi"
    assert _run(hr.pagamenti_esiti.count_documents({"origine": ponte.ORIGINE_BANCA})) == 3
    assert _run(hr.bonifici_da_associare.count_documents({"stato": "da_associare"})) == 2


def test_riesame_righe_in_coda_che_ora_formano_un_lotto_paghe(basi):
    """Primo giro reale (14/09/2026): 73 righe 'FAVORE X - ADD.TOT' in coda.
    Col giro successivo, se il giorno e' un lotto, escono dalla coda HR ed
    entrano nei pagamenti."""
    db, hr = basi
    _run(hr.dipendenti.insert_one({"id": "dip-lesina", "nome": "Angela", "cognome": "Lesina",
                                   "nome_completo": "Lesina Angela", "codice_fiscale": "LSNNGL92E45F839Q"}))
    marca_vecchia = {"esito": "in_coda", "motivo": "senza_segnale_stipendio", "coda_id": "q-1", "at": "x"}
    righe = [
        _movimento(id="r-1", data="2026-02-03", importo=-1000, hr_deposito=dict(marca_vecchia),
                   descrizione="VS.DISP. RIF. MB0B10284028/90368396 FAVORE VESPA VINCENZO - ADD.TOT"),
        _movimento(id="r-2", data="2026-02-03", importo=-1000, hr_deposito=dict(marca_vecchia, coda_id="q-2"),
                   descrizione="VS.DISP. RIF. MB0B10283922/90368225 FAVORE TAIANO LUIGI - ADD.TOT"),
        # la terza riga del lotto arriva solo ora (senza marcatore)
        _movimento(id="r-3", data="2026-02-03", importo=-1000,
                   descrizione="VS.DISP. RIF. MB0B10283457/90367437 FAVORE LESINA ANGELA - ADD.TOT"),
        # in coda, ma giorno con un solo dipendente: resta in coda
        _movimento(id="r-4", data="2026-02-13", importo=-800, hr_deposito=dict(marca_vecchia, coda_id="q-4"),
                   descrizione="VS.DISP. RIF. MB0B16277669/90292976 FAVORE TAIANO LUIGI - ADD.TOT"),
    ]
    _run(db.estratto_conto_movimenti.insert_many(righe))
    _run(hr.bonifici_da_associare.insert_many([
        {"id": "q-1", "stato": "da_associare", "gestionale_movimento_id": "r-1", "importo": 1000},
        {"id": "q-2", "stato": "da_associare", "gestionale_movimento_id": "r-2", "importo": 1000},
        {"id": "q-4", "stato": "da_associare", "gestionale_movimento_id": "r-4", "importo": 800},
    ]))

    report = _run(ponte.deposita_pagamenti_in_hr(db))

    assert report["estratto_conto"] == {"depositato": 1}
    assert report["estratto_conto_riesame"] == {"depositato": 2}
    assert report["letti"]["estratto_conto_riesame"] == 3
    stati = {q["id"]: q["stato"] for q in _run(hr.bonifici_da_associare.find({}, {"_id": 0}).to_list(None))}
    assert stati == {"q-1": "ritirato", "q-2": "ritirato", "q-4": "da_associare"}
    assert _run(hr.pagamenti_esiti.count_documents({"origine": ponte.ORIGINE_BANCA})) == 3
    r4 = _run(db.estratto_conto_movimenti.find_one({"id": "r-4"}, {"_id": 0}))
    assert r4["hr_deposito"]["esito"] == "in_coda"
    # secondo giro: niente da rifare
    ancora = _run(ponte.deposita_pagamenti_in_hr(db))
    assert ancora["estratto_conto_riesame"] == {} and ancora["letti"]["estratto_conto"] == 0


def test_riesame_beneficiari_vari_toglie_l_esito_sbagliato_e_mette_in_coda(basi):
    """Riga reale del 10/07/2026: 'FAVORE BENEFICIARI VARI DISTINTA - ADD.TOT -
    Vincenzo ceraldi stipendi' (4.600 EUR, piu' persone) era stata attribuita
    a Vespa/Ceraldi. Un cumulativo va sempre in coda."""
    db, hr = basi
    mov = _movimento(id="c-1", data="2026-07-10", importo=-4600,
                     descrizione="VOSTRA DISPOSIZIONE - VS.DISP. RIF. MB0B87387468/90385606 FAVORE BENEFICIARI VARI DISTINTA - ADD.TOT - Vespa Vincenzo stipendi",
                     hr_deposito={"esito": "depositato", "key": "ecm:c-1", "dipendente_id": "dip-vespa",
                                  "mese": 6, "anno": 2026, "at": "x"})
    vecchio = _movimento(id="c-2", data="2026-03-16", importo=-1147,
                         descrizione="VS.DISP. RIF. MB0B30867928/90433783 FAVORE BENEFICIARI VARI DISTINTA - ADD.TOT",
                         hr_deposito={"esito": "non_dipendente", "at": "x"})
    _run(db.estratto_conto_movimenti.insert_many([mov, vecchio]))
    _run(hr.pagamenti_esiti.insert_one({"key": "ecm:c-1", "dipendente_id": "dip-vespa", "data": "2026-07-10",
                                        "importo": 4600.0, "mese": 6, "anno": 2026, "origine": ponte.ORIGINE_BANCA}))
    _run(hr.paghe_mensili.insert_one({"dipendente_id": "dip-vespa", "anno": 2026, "mese": 6,
                                      "importo_busta": 1300.0, "bonifico_importo": 4600.0, "stato_pagamento": "pagato"}))

    report = _run(ponte.deposita_pagamenti_in_hr(db))

    assert report["estratto_conto_riesame"] == {"in_coda": 2}
    assert _run(hr.pagamenti_esiti.count_documents({})) == 0
    paga = _run(hr.paghe_mensili.find_one({"dipendente_id": "dip-vespa", "anno": 2026, "mese": 6}))
    assert paga["stato_pagamento"] == "in_attesa_pagamento"
    marche = {m["id"]: m["hr_deposito"] for m in _run(db.estratto_conto_movimenti.find({}, {"_id": 0}).to_list(None))}
    assert marche["c-1"]["esito"] == "in_coda" and marche["c-1"]["motivo"] == "beneficiari_diversi"
    assert marche["c-2"]["esito"] == "in_coda"
    assert _run(hr.bonifici_da_associare.count_documents({"stato": "da_associare"})) == 2
    # idempotente
    ancora = _run(ponte.deposita_pagamenti_in_hr(db))
    assert ancora["estratto_conto_riesame"] == {}
