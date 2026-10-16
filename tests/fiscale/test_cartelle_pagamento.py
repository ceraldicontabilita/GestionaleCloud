"""Cartella di pagamento: lettura, attesa «da pagare», verbale e ricevuta con lo stesso IUV (dati inventati)."""
import asyncio
import fitz
import pytest
from mongomock_motor import AsyncMongoMockClient

from app.services import cartelle_pagamento as cp

IUV = "80070000000000123"
NUMERO = "071 2026 00000001 11/000"

RIGHE = [
    "Spett. AZIENDA TEST SRL",
    f"CARTELLA DI PAGAMENTO N. {NUMERO}",
    "Agenzia delle entrate-Riscossione",
    "Totale da pagare entro 60 giorni dalla data di notifica",
    "euro 118,88",
    "113,00",
    "5,88",
    "118,88",
    "RUOLO EMESSO DA",
    "Comune di Prova Polizia Urbana",
    "RUOLO N. 2026/000001",
    "1", "2025", "5242 Contrav.cod.strada l.689/81", "100,00",
    "VER. 111/V/2025 31/03/2025 NOT. IL 02/06/2025 TG. AB123CD ART. 7",
    "2", "2025", "5243 Contrav.cod.strada mag.", "13,00",
    "VER. 111/V/2025 31/03/2025 NOT. IL 02/06/2025 TG. AB123CD ART. 7",
    "Destinatario Cod. Fiscale 00000000000",
    "AJZ8Z",
    "1" + IUV,
]

def _pdf(righe=RIGHE) -> bytes:
    doc = fitz.open()
    pagina = doc.new_page()
    y = 30
    for riga in righe:
        pagina.insert_text((30, y), riga, fontsize=8, fontname="helv")
        y += 12
    contenuto = doc.tobytes()
    doc.close()
    return contenuto


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _azienda_di_prova(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "FISCAL_COMPANY_ID", "00000000000")


def test_legge_numero_ente_righe_verbale_e_iuv_e_i_conti_tornano():
    dati = cp.leggi_cartella(cp._testo(_pdf()))

    assert dati["numero_cartella"] == NUMERO and dati["ente_creditore"].startswith("Comune di Prova")
    assert (dati["importo_ente"], dati["diritti_notifica"], dati["totale"]) == ("113.00", "5.88", "118.88")
    assert dati["importi_quadrano"] is True
    assert dati["iuv"] == IUV and dati["codice_avviso"] == "1" + IUV
    assert [r["codice_tributo"] for r in dati["righe"]] == ["5242", "5243"]
    assert dati["verbali"] == [{"numero_verbale": "111/V/2025", "targa": "AB123CD"}]


def test_somme_che_non_tornano_lasciano_la_cartella_da_verificare():
    righe = [r.replace("13,00", "14,00") for r in RIGHE]

    dati = cp.leggi_cartella(cp._testo(_pdf(righe)))

    assert dati["importi_quadrano"] is False


def test_riepilogo_con_oneri_non_scambia_notifica_per_totale():
    testo = "\n".join(RIGHE[:5] + [
        "100,00", "13,00", "5,88", "Spett.", "SOMME DA PAGARE",
        "100,00", "13,00", "5,88", "118,88", "-",
        "100,00", "26,00", "5,88", "131,88",
    ])
    dati = cp.leggi_cartella(testo)
    assert dati["importo_ente"] == "100.00"
    assert dati["oneri_riscossione"] == "13.00"
    assert dati["diritti_notifica"] == "5.88"
    assert dati["totale"] == "118.88"
    assert dati["importi_quadrano"] is True


def test_piu_enti_prende_somme_da_pagare_non_primi_tre_importi():
    testo = "\n".join(RIGHE[:5] + [
        "70,00", "43,00", "5,88", "Spett.", "SOMME DA PAGARE",
        "113,00", "5,88", "118,88", "Modalita di pagamento",
    ])
    dati = cp.leggi_cartella(testo)
    assert dati["importo_ente"] == "113.00"
    assert dati["diritti_notifica"] == "5.88"
    assert dati["totale"] == "118.88"
    assert dati["importi_quadrano"] is True


def test_senza_totale_etichettato_non_usa_cifre_casuali():
    testo = "\n".join(RIGHE[:3] + ["113,00", "5,88", "118,88"])
    dati = cp.leggi_cartella(testo)
    assert dati["totale"] is None
    assert dati["importi_quadrano"] is False


def test_riepilogo_incoerente_conserva_totale_ma_richiede_verifica():
    testo = "\n".join(RIGHE[:5] + ["SOMME DA PAGARE", "113,00", "6,88", "118,88"])
    dati = cp.leggi_cartella(testo)
    assert dati["totale"] == "118.88"
    assert dati["diritti_notifica"] is None
    assert dati["importi_quadrano"] is False


def test_interessi_mora_espliciti_chiudono_senza_alterare_il_dovuto_originale():
    db = AsyncMongoMockClient()["cartelle"]
    cartella = _run(cp.registra_cartella(db, "a.pdf", _pdf()))
    ricevuta = {"id": "r-mora", "importi_quadrano": True, "importo": 121.38,
                "documenti": [{"numero": "07120260000000111000", "totale": 121.38,
                                "quadra": True, "interessi_mora": 2.50}]}
    for _ in range(2):
        assert _run(cp.chiudi_da_ricevuta(db, ricevuta)) == "SODDISFATTO"
    doc = _run(db[cp.COLL].find_one({"id": cartella["id"]}))
    assert doc["totale"] == "118.88"
    assert doc["importo_pagato_documentale"] == "121.38"
    assert doc["interessi_mora_documentati"] == "2.5"
    assert len(doc["pagamenti_documentati"]) == 1


def test_importo_maggiore_senza_prova_interessi_resta_da_verificare():
    db = AsyncMongoMockClient()["cartelle"]
    _run(cp.registra_cartella(db, "a.pdf", _pdf()))
    for extra in ({}, {"interessi_mora": 1.00}):
        ricevuta = {"id": "r-mora", "importi_quadrano": True,
                    "documenti": [{"numero": "07120260000000111000", "totale": 121.38,
                                    "quadra": True, **extra}]}
        assert _run(cp.chiudi_da_ricevuta(db, ricevuta)) == "DA_VERIFICARE"


def test_registra_apre_l_attesa_senza_scadenza_e_il_secondo_file_non_duplica():
    db = AsyncMongoMockClient()["cartelle"]

    primo = _run(cp.registra_cartella(db, "a.pdf", _pdf()))
    secondo = _run(cp.registra_cartella(db, "b.pdf", _pdf()))
    doc = _run(db[cp.COLL].find_one({"id": primo["id"]}))

    assert primo["success"] and primo["duplicate"] is False and secondo["duplicate"] is True
    assert _run(db[cp.COLL].count_documents({})) == 1
    assert doc["expectation_status"] == "ATTESO" and doc["expectation_type"] == cp.TIPO_ATTESA
    assert doc["source_fact_id"] == primo["id"]
    # La notifica non e' nel PDF: nessuna scadenza inventata.
    assert doc["data_notifica"] is None and doc["scadenza"] is None


def test_snapshot_ader_a_residuo_zero_supera_l_attesa_senza_inventare_pagamento(monkeypatch):
    from app.config import settings
    from app.db_collections import COLL_TAX_COLLECTION_CLAIMS
    from app.services.fiscal_evidence import stable_id

    monkeypatch.setattr(settings, "FISCAL_COMPANY_ID", "00000000000")
    db = AsyncMongoMockClient()["cartelle-snapshot-zero"]
    numero = "07120260000000111000"
    claim_id = stable_id("taxclaim", "00000000000", numero)
    _run(db[COLL_TAX_COLLECTION_CLAIMS].insert_one({
        "id": claim_id, "company_id": "00000000000", "collection_number": numero,
        "business_status": "PORTAL_CLOSED_PENDING_EVIDENCE", "residual_cents": 0,
    }))

    result = _run(cp.registra_cartella(db, "cartella.pdf", _pdf()))
    doc = _run(db[cp.COLL].find_one({"id": result["id"]}, {"_id": 0}))
    claim = _run(db[COLL_TAX_COLLECTION_CLAIMS].find_one({"id": claim_id}, {"_id": 0}))

    assert doc["expectation_status"] == "SUPERATO"
    assert doc["expectation_resolution"] == "ADER_CURRENT_RESIDUAL_ZERO_WITHOUT_PAYMENT_EVIDENCE"
    assert not doc.get("expectation_evidence_ids") and not doc.get("data_pagamento")
    assert claim["business_status"] == "PORTAL_CLOSED_PENDING_EVIDENCE" and claim["residual_cents"] == 0
    assert claim["original_document_id"] == result["fiscal"]["document_id"]
    assert claim["original_total_cents"] == 11888


def test_la_notifica_dice_il_termine_di_60_giorni_e_salta_il_fine_settimana():
    db = AsyncMongoMockClient()["cartelle"]
    cartella = _run(cp.registra_cartella(db, "a.pdf", _pdf()))

    esito = _run(cp.imposta_notifica(db, cartella["id"], "2026-07-25"))

    # 25/07 + 60 giorni = 23/09/2026 (mercoledi')
    assert esito["scadenza"] == "2026-09-23"
    # 28/07 + 60 giorni = sabato 26/09: passa a lunedi' 28/09.
    assert cp.scadenza_da_notifica("2026-07-28") == "2026-09-28"
    assert _run(cp.imposta_notifica(db, cartella["id"], "31/13/2026"))["success"] is False


def test_rilettura_stesso_originale_corregge_importi_e_riconcilia_senza_duplicare():
    db = AsyncMongoMockClient()["cartelle"]
    primo = _run(cp.registra_cartella(db, "a.pdf", _pdf()))
    # Rappresenta una scheda storica generata dal vecchio parser.
    _run(db[cp.COLL].update_one({"id": primo["id"]}, {
        "$unset": {"parser_version": ""},
        "$set": {"totale": "5.88", "data_notifica": "2026-07-01"},
    }))
    _run(db["ricevute_pagopa"].insert_one({
        "id": "r-storica", "identificativo_bolletta": IUV, "importo": 118.88,
    }))
    # Usa gli stessi byte, non una nuova stampa con metadati PDF differenti.
    import base64
    vecchio = _run(db[cp.COLL].find_one({"id": primo["id"]}))
    result = _run(cp.registra_cartella(db, "altra-copia.pdf", base64.b64decode(vecchio["contenuto_b64"])))
    doc = _run(db[cp.COLL].find_one({"id": primo["id"]}))
    assert result["duplicate"] and result["metadati_aggiornati"]
    assert doc["totale"] == "118.88" and doc["parser_precedente"]["totale"] == "5.88"
    assert doc["data_notifica"] == "2026-07-01"
    assert doc["expectation_status"] == "SODDISFATTO"
    assert _run(db[cp.COLL].count_documents({})) == 1


def test_ricevuta_con_lo_stesso_iuv_e_importo_chiude_l_attesa():
    db = AsyncMongoMockClient()["cartelle"]
    cartella = _run(cp.registra_cartella(db, "a.pdf", _pdf()))
    _run(db["ricevute_pagopa"].insert_one({
        "id": "ric-1", "identificativo_bolletta": IUV, "operation_amount": 118.88,
        "data_pagamento": "2026-09-20", "stato": "non_associata",
    }))

    stato = _run(cp.chiudi_da_ricevuta(db, {
        "id": "ric-1", "identificativo_bolletta": IUV, "operation_amount": 118.88,
        "data_pagamento": "2026-09-20",
    }))
    doc = _run(db[cp.COLL].find_one({"id": cartella["id"]}))
    ricevuta = _run(db["ricevute_pagopa"].find_one({"id": "ric-1"}))

    assert stato == "SODDISFATTO" and doc["expectation_evidence_ids"] == ["ric-1"]
    assert ricevuta["stato"] == "associata"
    assert ricevuta["cartelle_collegate"] == [cartella["id"]]


def test_ricevuta_con_lo_stesso_iuv_e_importo_diverso_resta_da_verificare():
    db = AsyncMongoMockClient()["cartelle"]
    cartella = _run(cp.registra_cartella(db, "a.pdf", _pdf()))

    stato = _run(cp.chiudi_da_ricevuta(db, {
        "id": "ric-2", "identificativo_bolletta": IUV, "operation_amount": 113.00,
    }))

    assert stato == "DA_VERIFICARE"
    assert _run(db[cp.COLL].find_one({"id": cartella["id"]}))["expectation_status"] == "DA_VERIFICARE"


def test_ricevuta_arrivata_prima_della_cartella_la_chiude_subito():
    db = AsyncMongoMockClient()["cartelle"]
    _run(db["ricevute_pagopa"].insert_one({
        "id": "ric-3", "identificativo_bolletta": IUV, "operation_amount": 118.88,
    }))

    cartella = _run(cp.registra_cartella(db, "a.pdf", _pdf()))

    assert cartella["ricevuta"] == "SODDISFATTO"


def test_verbale_si_aggancia_solo_se_unico_e_con_la_stessa_targa():
    db = AsyncMongoMockClient()["cartelle"]
    _run(db["verbali_noleggio"].insert_many([
        {"id": "v1", "numero_verbale": "111/V/2025", "targa": "AB123CD"},
        {"id": "v2", "numero_verbale": "222/V/2025", "targa": "AB123CD"},
    ]))

    cartella = _run(cp.registra_cartella(db, "a.pdf", _pdf()))
    doc = _run(db[cp.COLL].find_one({"id": cartella["id"]}))

    assert [v["id"] for v in doc["verbali_collegati"]] == ["v1"]

    # Due verbali con lo stesso numero e targa: ambiguo, nessun collegamento.
    _run(db["verbali_noleggio_completi"].insert_one(
        {"id": "v3", "numero_verbale": "111/V/2025", "targa": "AB123CD"}))
    _run(cp.collega_verbali(db, cartella["id"]))
    doc = _run(db[cp.COLL].find_one({"id": cartella["id"]}))
    assert doc["verbali_collegati"] == [] and len(doc["verbali_candidati"]["111/V/2025"]) == 2


def test_documenti_import_riconosce_la_cartella_di_pagamento():
    from app.routers.documenti import detect_document_type

    assert detect_document_type("cartella.pdf", _pdf()) == "cartella_pagamento"


def test_feedback_import_non_dichiara_da_pagare_se_ader_ha_residuo_zero():
    """Il riepilogo di upload deve rispettare lo snapshot AdeR gia' presente."""
    from app.routers.documenti import _stato_cartella_importata

    stato = _stato_cartella_importata({"fiscal": {"residual_cents": 0}})
    assert "posizione corrente AdeR ha residuo 0,00 EUR" in stato
    assert "pagamento non e' provato" in stato
    assert "da pagare entro" not in stato


def test_feedback_import_cartella_distingue_duplicato_e_dovuto():
    from app.routers.documenti import _stato_cartella_importata

    assert _stato_cartella_importata({"duplicate": True}) == " già presente"
    assert "da pagare entro 60 giorni" in _stato_cartella_importata({"fiscal": {"residual_cents": 1711}})


def test_lipe_che_cita_versamenti_auto_f24_non_e_un_modello_f24():
    """Il campo VP «VERSAMENTI AUTO F24» faceva classificare la LIPE come F24 (import bloccato)."""
    from app.routers.documenti import detect_document_type

    contenuto = _pdf([
        "COMUNICAZIONE DEI DATI DELLE LIQUIDAZIONI PERIODICHE IVA",
        "VP7 DEBITO PERIODO PRECEDENTE NON SUPERIORE A 100 EURO",
        "VERSAMENTI AUTO F24 ELEMENTI IDENTIFICATIVI",
    ])

    assert detect_document_type("LIPE_2026_123456789.pdf", contenuto) == "dichiarazione_fiscale"


def test_dichiarazioni_che_citano_f24_non_finiscono_nel_lettore_dei_modelli():
    """770, IRAP e Redditi SC citano «F24»: erano lette come modelli e bloccate «non quadrato»."""
    from app.routers.documenti import detect_document_type

    contenuto = _pdf([
        "MODELLO 770 SEMPLIFICATO 2021 REDDITI 2020",
        "VERSAMENTI CON MODELLO F24 E COMPENSAZIONI",
        "QUADRO ST RITENUTE OPERATE",
    ])

    assert detect_document_type("770_2021_imposta_2020_T211025164220380377.pdf", contenuto) == "dichiarazione_fiscale"
    assert detect_document_type("IRAP_2021_imposta_2020_T210930200114276161.pdf", contenuto) == "dichiarazione_fiscale"
    assert detect_document_type("760_2021_imposta_2020_T210930200158679371.pdf", contenuto) == "dichiarazione_fiscale"


def test_un_vero_modello_f24_resta_f24_anche_con_un_nome_da_dichiarazione():
    from app.routers.documenti import detect_document_type

    contenuto = _pdf([
        "MODELLO DI PAGAMENTO UNIFICATO",
        "DELEGA IRREVOCABILE A",
        "SEZIONE ERARIO CODICE TRIBUTO 1001",
    ])

    assert detect_document_type("770_ritenute_2021.pdf", contenuto) == "f24"
    assert detect_document_type("documento.pdf", contenuto) == "f24"


def test_irap_ira_t_con_riga_f24_nel_testo_e_dichiarazione():
    from app.routers.documenti import _tipo_dichiarazione

    testo = "QUADRO IR Ripartizione della base imponibile e dell'imposta Versato in F24"
    assert _tipo_dichiarazione("IRA_T210930200114276161_00000000000.pdf", testo) == "dichiarazione_fiscale"
    assert _tipo_dichiarazione("UNICO_SC_2019.pdf", "") == "dichiarazione_fiscale"
