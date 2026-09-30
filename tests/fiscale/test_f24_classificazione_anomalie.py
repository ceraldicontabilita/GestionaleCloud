"""F24: riga INPS letta al suo posto, motore che legge la vista canonica, doppio pagamento
persistito con alert e controlli §18 («da verificare», mai indovinati).

Il modello del 16/01/2023 (saldo 50,61) era in archivio con la riga INPS
«5100 RC01 5124776507 11 2022 11 2022» in Erario col codice «2022». Il PDF originale non
si scarica da qui (Drive senza id nei metadati): il testo della riga e' quello salvato in
produzione (`testo_sorgente`), e il layout e' ricostruito parola per parola.
"""
import asyncio

import fitz
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Database
from app.engines import tributi_engine as te
from app.routers import f24_analisi
from app.services import f24_anomalie as fa
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.f24_fiscal_evidence import normalize_f24_evidence_rows
from app.services.parser_f24 import parse_f24_commercialista
from app.utils.dependencies import get_current_admin_user


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _pdf(righe):
    doc = fitz.open()
    pagina = doc.new_page(width=595, height=842)
    for x, y, testo in righe:
        pagina.insert_text((x, y), testo, fontsize=8)
    return doc.tobytes()


ERARIO = [
    (100, 240, "1001"), (140, 240, "11"), (170, 240, "2022"), (350, 240, "1.382,12"), (470, 240, "0,00"),
]

# La riga com'e' nel PDF del 16/01/2023: virgole staccate e due volte il periodo.
RIGA_RC01 = [
    (60, 352, "5100"), (100, 352, "RC01"), (150, 352, "5124776507"),
    (230, 352, "11"), (250, 352, "2022"), (280, 352, "11"), (300, 352, "2022"),
    (350, 352, "2.840,00"), (400, 352, ","), (470, 352, "0,00"), (500, 352, ","),
]

TESTO_RC01 = "5100 RC01 5124776507 11 2022 11 2022 2.840,00 , 0,00 ,"


# ── 1. Parser ─────────────────────────────────────────────────────────────

def test_rc01_del_16_01_2023_va_in_inps_con_periodo_da_a_e_mai_in_erario_con_codice_anno():
    parsed = parse_f24_commercialista(pdf_content=_pdf(ERARIO + RIGA_RC01))

    assert [r["codice_tributo"] for r in parsed["sezione_erario"]] == ["1001"]
    [riga] = parsed["sezione_inps"]
    assert (riga["codice_sede"], riga["causale"], riga["matricola"]) == ("5100", "RC01", "5124776507")
    assert (riga["periodo_da"], riga["periodo_a"]) == ("11/2022", "11/2022")
    assert riga["importo_debito_cents"] == 284000


def test_periodo_a_diverso_dal_periodo_da_si_conserva():
    parsed = parse_f24_commercialista(pdf_content=_pdf(ERARIO + [
        (60, 352, "5100"), (100, 352, "RC01"), (150, 352, "5124776507"),
        (230, 352, "3"), (250, 352, "2022"), (280, 352, "11"), (300, 352, "2022"),
        (350, 352, "2.840,00"), (470, 352, "0,00"),
    ]))
    [riga] = parsed["sezione_inps"]
    assert (riga["periodo_da"], riga["periodo_a"]) == ("03/2022", "11/2022")
    assert riga["periodo_riferimento"] == "03/2022" and riga["mese"] == "03"  # chiavi di sempre


def test_causale_inps_nuova_va_in_inps_e_non_in_erario():
    parsed = parse_f24_commercialista(pdf_content=_pdf(ERARIO + [
        (60, 352, "5100"), (100, 352, "DMRA"), (150, 352, "5124776507"),
        (230, 352, "11"), (250, 352, "2022"), (350, 352, "100,00"), (470, 352, "0,00"),
    ]))
    assert [r["codice_tributo"] for r in parsed["sezione_erario"]] == ["1001"]
    assert [r["causale"] for r in parsed["sezione_inps"]] == ["DMRA"]


def test_un_anno_dopo_mese_e_matricola_non_e_un_codice_tributo_ma_il_2003_ires_si():
    solo_anno = parse_f24_commercialista(pdf_content=_pdf(ERARIO + [
        (100, 300, "5124776507"), (150, 300, "11"), (170, 300, "2022"), (200, 300, "11"), (250, 300, "2022"),
        (350, 300, "10,00"), (470, 300, "0,00"),
    ]))
    assert [r["codice_tributo"] for r in solo_anno["sezione_erario"]] == ["1001"]

    ires = parse_f24_commercialista(pdf_content=_pdf([
        (100, 240, "2003"), (140, 240, "0101"), (170, 240, "2022"), (350, 240, "500,00"), (470, 240, "0,00"),
    ]))
    assert [r["codice_tributo"] for r in ires["sezione_erario"]] == ["2003"]


def test_riga_inail_incompleta_resta_col_suo_elenco_di_campi_mancanti():
    parsed = parse_f24_commercialista(pdf_content=_pdf(ERARIO + [
        (30, 400, "33400"), (90, 400, "13882560"), (350, 400, "12,00"), (400, 400, ","), (470, 400, "0,00"),
    ]))
    [riga] = parsed["sezione_inail"]
    assert riga["incompleta"] is True
    assert set(riga["campi_mancanti"]) == {"cc", "numero_riferimento", "causale"}
    assert riga["importo_debito_cents"] == 1200


def test_riga_inail_senza_importo_non_e_persa_ne_entra_fra_i_pagamenti():
    parsed = parse_f24_commercialista(pdf_content=_pdf(ERARIO + [
        (30, 400, "33400"), (90, 400, "13882560"), (150, 400, "91"), (200, 400, "902025"), (250, 400, "P"),
    ]))
    assert parsed["sezione_inail"] == []
    [riga] = parsed["righe_inail_incomplete"]
    assert riga["campi_mancanti"] == ["importo"]


# ── 2. Il motore legge la vista canonica ──────────────────────────────────

def _modello_vecchio_con_riga_inps_in_erario(**altro):
    """Il modello com'e' in produzione: RC01 finita in Erario col codice = anno."""
    return {
        "id": "023cbbae", "file_name": "CassettoFiscaleServlet (2).pdf",
        "dati_generali": {"codice_fiscale": "04523831214", "saldo_delega": 50.61},
        "sezione_erario": [
            {"codice_tributo": "1001", "periodo_riferimento": "11/2022", "importo_debito": 1382.12},
            {"codice_tributo": "2022", "periodo_riferimento": "11/2022", "importo_debito": 2840.0,
             "testo_sorgente": TESTO_RC01, "riga_y": 352},
        ],
        "sezione_inps": [],
        "status": "pagato", "quietanza_id": "q1",
        **altro,
    }


def test_la_vista_canonica_rimette_la_riga_in_inps_con_matricola_e_periodo():
    [_, rc01] = normalize_f24_evidence_rows(_modello_vecchio_con_riga_inps_in_erario())
    assert (rc01["section"], rc01["tax_code"], rc01["entity_code"]) == ("INPS", "RC01", "5100")
    assert (rc01["matricola"], rc01["periodo_da"], rc01["periodo_a"]) == ("5124776507", "11/2022", "11/2022")


def test_il_motore_riconosce_rc01_su_un_modello_gia_in_archivio():
    f24 = _modello_vecchio_con_riga_inps_in_erario()
    assert te.causali_inps(f24) == ["RC01"]
    assert te.tipo_versamento(f24) == "regolarizzazione"
    analisi = te.classifica_f24(f24)
    assert analisi["causali_inps"] == ["RC01"]
    assert analisi["totali_per_natura"]["regolarizzazione"] == 2840.0


def test_associazione_ai_cedolini_di_maggio_2026_rifiutata_con_spiegazione_leggibile():
    esito = te.valuta_associazione_cedolini(_modello_vecchio_con_riga_inps_in_erario(), 5, 2026)
    assert esito["associabile"] is False
    assert any("RC01" in m and "vietata" in m for m in esito["motivi"])
    assert "Associazione NON consentita" in esito["spiegazione"]


def test_dm10_rc01_vede_la_regolarizzazione_del_modello_vecchio():
    ordinario = {
        "dati_generali": {"codice_fiscale": "04523831214"},
        "sezione_erario": [{"codice_tributo": "1001", "periodo_riferimento": "11/2022", "importo_debito": 1382.12}],
        "sezione_inps": [{"causale": "DM10", "matricola": "5124776507", "periodo_riferimento": "11/2022",
                          "importo_debito": 2840.0}],
    }
    legame = te.confronta_dm10_rc01(ordinario, _modello_vecchio_con_riga_inps_in_erario())
    assert legame["collegati"] is True
    assert "RC01" in legame["tributi_comuni"]


# ── 4. Controlli §18 ──────────────────────────────────────────────────────

def _tipi(f24):
    return {c["tipo"]: c for c in te.controlli_f24(f24)}


def test_regione_e_comune_fuori_tabella_sono_da_verificare_col_codice_mostrato():
    controlli = _tipi({
        "sezione_regioni": [
            {"codice_tributo": "3802", "codice_regione": "07", "importo_debito": 10.0},
            {"codice_tributo": "3802", "importo_debito": 5.0},
        ],
        "sezione_tributi_locali": [
            {"codice_tributo": "3847", "codice_comune": "A662", "importo_debito": 10.0},
            {"codice_tributo": "3848", "importo_debito": 4.0},
        ],
    })
    assert controlli["regione_non_in_tabella"]["codice"] == "07"
    assert "Regione 07 non in tabella" in controlli["regione_non_in_tabella"]["motivo"]
    assert controlli["comune_non_in_tabella"]["codice"] == "A662"
    assert {"regione_assente", "comune_assente"} <= set(controlli)
    assert all(c["natura"] == "da_verificare" for c in controlli.values())


def test_regione_e_comuni_noti_non_generano_controlli():
    assert te.controlli_f24({
        "sezione_regioni": [{"codice_tributo": "3802", "codice_regione": "05", "importo_debito": 10.0}],
        "sezione_tributi_locali": [
            {"codice_tributo": "3847", "codice_comune": "F839", "importo_debito": 10.0},
            {"codice_tributo": "3848", "codice_comune": "B990", "importo_debito": 4.0},
        ],
        "sezione_inps": [{"causale": "DM10", "importo_debito": 1.0}],
    }) == []


def test_inail_incompleta_e_causale_inps_sconosciuta_sono_controlli():
    controlli = _tipi({
        "sezione_inail": [{"codice_sede": "33400", "codice_ditta": "13882560", "causale": "",
                           "incompleta": True, "campi_mancanti": ["causale"], "importo_debito": 12.0}],
        "righe_inail_incomplete": [{"campi_mancanti": ["importo"]}],
        "sezione_inps": [{"causale": "ZZ99", "importo_debito": 1.0}],
    })
    motivi = [c["motivo"] for c in te.controlli_f24({"sezione_inail": [
        {"codice_sede": "33400", "causale": "", "incompleta": True, "campi_mancanti": ["causale"]}]})]
    assert motivi == ["Riga INAIL incompleta: mancano causale"]
    assert "mancano importo" in controlli["inail_incompleta"]["motivo"]
    assert controlli["causale_inps_sconosciuta"]["codice"] == "ZZ99"
    analisi = te.classifica_f24({"sezione_inps": [{"causale": "ZZ99", "importo_debito": 1.0}]})
    assert analisi["controlli_da_verificare"] == 1


def test_il_6869_e_nel_registro_unico():
    from app.services.codici_tributo_f24 import get_descrizione_tributo

    assert get_descrizione_tributo("6869") == "Credito investimenti Mezzogiorno"


def test_alert_controllo_da_verificare_si_apre_una_volta_e_si_chiude_da_solo():
    db = ClientArchivioMemoria()["gestionale_test"]
    f24 = {"id": "m1", "file_name": "m1.pdf", "sezione_inps": [{"causale": "ZZ99", "importo_debito": 1.0}]}
    _run(db[fa.COLL_F24].insert_one(dict(f24)))

    primo = _run(fa.controlla_f24_da_verificare(db))
    secondo = _run(fa.controlla_f24_da_verificare(db))
    assert (primo["alert_aperti"], secondo["alert_aperti"]) == (1, 0)
    [alert] = _run(db["alerts"].find({"codice": fa.ALERT_CONTROLLO}).to_list(10))
    assert (alert["entita_collection"], alert["entita_id"]) == ("f24_unificato", "m1")
    assert "ZZ99" in alert["dettaglio"] and alert["stato"] == "aperto"

    _run(db[fa.COLL_F24].update_one({"id": "m1"}, {"$set": {"sezione_inps": [{"causale": "DM10"}]}}))
    chiuso = _run(fa.controlla_f24_da_verificare(db))
    assert chiuso["alert_chiusi"] == 1
    assert _run(db["alerts"].find_one({"codice": fa.ALERT_CONTROLLO}))["stato"] == "risolto"


# ── 3. Doppio pagamento persistito ────────────────────────────────────────

def _coppia():
    ordinario = {
        "id": "ord-1", "file_name": "ordinario.pdf",
        "dati_generali": {"codice_fiscale": "04523831214"},
        "sezione_erario": [{"codice_tributo": "1001", "periodo_riferimento": "11/2022", "importo_debito": 1382.12}],
        "sezione_inps": [{"causale": "DM10", "matricola": "5124776507", "periodo_riferimento": "11/2022",
                          "importo_debito": 2840.0}],
        "status": "pagato",
    }
    rc01 = {
        "id": "rc-1", "file_name": "rc01.pdf",
        "dati_generali": {"codice_fiscale": "04523831214"},
        "sezione_erario": [{"codice_tributo": "1001", "periodo_riferimento": "11/2022", "importo_debito": 1382.12},
                           {"codice_tributo": "8906", "periodo_riferimento": "11/2022", "importo_debito": 36.56}],
        "sezione_inps": [{"causale": "RC01", "matricola": "5124776507", "periodo_riferimento": "11/2022",
                          "importo_debito": 2840.0}],
        "status": "pagato",
    }
    return ordinario, rc01


def _db_con_coppia():
    db = ClientArchivioMemoria()["gestionale_test"]
    for d in _coppia():
        _run(db[fa.COLL_F24].insert_one(dict(d)))
    return db


def _alert(db):
    return _run(db["alerts"].find({"codice": fa.ALERT_DOPPIO_PAGAMENTO}).to_list(10))


def test_dry_run_non_scrive_niente():
    db = _db_con_coppia()
    esito = _run(fa.rileva_doppi_pagamenti(db, dry_run=True))
    assert (esito["dry_run"], esito["nuove"]) == (True, 1)
    assert _run(db[fa.COLL_ANOMALIE_DOPPIO].find({}).to_list(10)) == [] and _alert(db) == []


def test_la_rilevazione_crea_una_anomalia_per_coppia_e_un_alert_una_volta_sola():
    db = _db_con_coppia()
    primo = _run(fa.rileva_doppi_pagamenti(db, dry_run=False))
    secondo = _run(fa.rileva_doppi_pagamenti(db, dry_run=False))
    assert (primo["nuove"], secondo["nuove"], secondo["gia_presenti"]) == (1, 0, 1)

    [anomalia] = _run(db[fa.COLL_ANOMALIE_DOPPIO].find({}).to_list(10))
    assert anomalia["id"] == fa.id_anomalia("ord-1", "rc-1") == fa.id_anomalia("rc-1", "ord-1")
    assert anomalia["stato"] == "da_verificare"
    assert anomalia["quota_duplicata_cents"] == 138212 + 284000
    assert anomalia["quota_sanzioni_interessi_cents"] == 3656
    assert [s["stato"] for s in anomalia["storico"]] == ["da_verificare"]
    [alert] = _alert(db)
    assert (alert["entita_collection"], alert["entita_id"]) == (fa.COLL_ANOMALIE_DOPPIO, anomalia["id"])


def test_lo_stato_richiede_il_motivo_e_chiude_l_alert_senza_riaprirsi():
    db = _db_con_coppia()
    _run(fa.rileva_doppi_pagamenti(db, dry_run=False))
    anomalia_id = fa.id_anomalia("ord-1", "rc-1")

    with pytest.raises(fa.StatoNonValido) as senza_motivo:
        _run(fa.imposta_stato(db, anomalia_id, "non_duplicato", "  ", "titolare"))
    assert "stati_con_motivo" in senza_motivo.value.dettagli
    with pytest.raises(fa.StatoNonValido) as fuori_lista:
        _run(fa.imposta_stato(db, anomalia_id, "boh", "x", "titolare"))
    assert "non_duplicato" in fuori_lista.value.dettagli["stati_ammessi"]

    doc = _run(fa.imposta_stato(db, anomalia_id, "non_duplicato", "Capitale versato una volta sola", "titolare"))
    assert doc["storico"][-1]["da"] == "titolare" and doc["storico"][-1]["motivo"].startswith("Capitale")
    assert _alert(db)[0]["stato"] == "risolto"

    # Il giro dopo non la riapre e non la duplica.
    ripasso = _run(fa.rileva_doppi_pagamenti(db, dry_run=False))
    assert ripasso["nuove"] == 0
    assert _run(db[fa.COLL_ANOMALIE_DOPPIO].find_one({"id": anomalia_id}))["stato"] == "non_duplicato"
    assert [a["stato"] for a in _alert(db)] == ["risolto"]
    assert _run(fa.imposta_stato(db, "inesistente", "non_duplicato", "x", "t")) is None


def _client(db):
    app = FastAPI()
    app.include_router(f24_analisi.router, prefix="/api/f24-analisi")
    app.dependency_overrides[get_current_admin_user] = lambda: {"email": "titolare@example.test"}
    return TestClient(app)


def test_api_get_unisce_lo_stato_e_put_valida(monkeypatch):
    db = _db_con_coppia()
    monkeypatch.setattr(Database, "get_db", classmethod(lambda cls: db))
    client = _client(db)

    anteprima = client.post("/api/f24-analisi/doppi-pagamenti/rileva").json()
    assert (anteprima["dry_run"], anteprima["nuove"]) == (True, 1)
    assert client.post("/api/f24-analisi/doppi-pagamenti/rileva?dry_run=false").json()["nuove"] == 1

    elenco = client.get("/api/f24-analisi/doppi-pagamenti").json()
    [anomalia] = elenco["anomalie"]
    assert anomalia["stato"] == "da_verificare" and elenco["da_verificare"] == 1

    url = f"/api/f24-analisi/doppi-pagamenti/{anomalia['id']}/stato"
    rifiuto = client.put(url, json={"stato": "boh"})
    assert rifiuto.status_code == 422 and "non_duplicato" in rifiuto.json()["detail"]["details"]["stati_ammessi"]
    assert client.put(url, json={"stato": "confermato_doppio_pagamento"}).status_code == 422
    assert client.put("/api/f24-analisi/doppi-pagamenti/nessuna/stato",
                      json={"stato": "non_duplicato", "motivo": "x"}).status_code == 404

    ok = client.put(url, json={"stato": "rimborsato_compensato", "motivo": "Compensato nel F24 di febbraio"})
    assert ok.status_code == 200 and ok.json()["storico"][-1]["da"] == "titolare@example.test"
    elenco = client.get("/api/f24-analisi/doppi-pagamenti").json()
    assert elenco["anomalie"][0]["stato"] == "rimborsato_compensato" and elenco["da_verificare"] == 0


def test_giro_unico_del_job_f24():
    db = _db_con_coppia()
    esito = _run(fa.giro_anomalie_f24(db))
    assert esito["doppi_pagamenti"]["nuove"] == 1
    assert "controlli" in esito


# ── Colonne allineate a destra: un credito a 4 cifre parte piu' a sinistra ──

def test_credito_a_quattro_cifre_non_finisce_nel_debito_ne_perde_le_migliaia():
    """F24 del 20/12/2022, pagina 2: «5.024» a x=438 e «76» a x=473 erano letti 0,76."""
    parsed = parse_f24_commercialista(pdf_content=_pdf([
        (60, 240, "1001"), (150, 240, "0011"), (200, 240, "2022"),
        (355, 240, "1.378"), (382, 240, ","), (391, 240, "58"),
        (60, 256, "6869"), (200, 256, "2022"),
        (438, 256, "5.024"), (466, 256, ","), (473, 256, "76"),
    ]))
    per_codice = {r["codice_tributo"]: r for r in parsed["sezione_erario"]}
    assert (per_codice["1001"]["importo_debito_cents"], per_codice["1001"]["importo_credito_cents"]) == (137858, 0)
    assert (per_codice["6869"]["importo_debito_cents"], per_codice["6869"]["importo_credito_cents"]) == (0, 502476)


def test_credito_a_tre_cifre_e_debiti_di_sempre_restano_al_loro_posto():
    parsed = parse_f24_commercialista(pdf_content=_pdf([
        (60, 240, "1001"), (150, 240, "0011"), (200, 240, "2022"),
        (367, 240, "204"), (391, 240, "43"),
        (60, 256, "6869"), (200, 256, "2022"), (450, 256, "667"), (473, 256, "40"),
    ]))
    per_codice = {r["codice_tributo"]: r for r in parsed["sezione_erario"]}
    assert per_codice["1001"]["importo_debito_cents"] == 20443
    assert per_codice["6869"]["importo_credito_cents"] == 66740
