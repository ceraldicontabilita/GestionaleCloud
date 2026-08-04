"""
Arricchimento IVA delle fatture (app/engines/iva_fatture.py): dai dati grezzi
di una fattura ricava periodo IVA attribuito, regola e stato di detrazione.
"""
from app.engines import iva_fatture as ivf


def test_fattura_immediata_stesso_mese():
    inv = {"invoice_date": "2026-03-10", "created_at": "2026-03-12T00:00:00", "iva": 220}
    c = ivf.campi_iva_da_fattura(inv)
    assert c["periodo_iva_attribuito"] == "2026-03"
    assert c["regola_iva_applicata"] == "STESSO_MESE"
    assert c["iva_documento"] == 220
    assert c["iva_detraibile"] == 0 and c["iva_utilizzata"] is False
    assert c["stato_detrazione_iva"] == "DA_VERIFICARE"


def test_fattura_classificata_preserva_iva_detraibile():
    inv = {
        "invoice_date": "2026-03-10", "iva": 220,
        "iva_detraibile": 88, "classificato_da": "learning_machine",
        "stato_classificazione": "classificata",
    }
    c = ivf.campi_iva_da_fattura(inv)
    assert c["iva_documento"] == 220
    assert c["iva_detraibile"] == 88
    assert c["stato_detrazione_iva"] == "DA_INSERIRE"


def test_classificazione_incerta_non_diventa_credito_disponibile():
    inv = {
        "invoice_date": "2026-03-10", "iva": 220,
        "iva_detraibile": 88, "classificato_da": "learning_machine",
        "stato_classificazione": "da_verificare",
    }
    c = ivf.campi_iva_da_fattura(inv)
    assert c["iva_detraibile"] == 88
    assert c["stato_detrazione_iva"] == "DA_VERIFICARE"


def test_ricevuta_entro_il_15_attribuita_mese_precedente():
    # operazione 31/01 (data documento), ricevuta/registrata l'8-10/02 → gennaio
    inv = {"invoice_date": "2026-01-31", "data_ricezione": "2026-02-08",
           "data_registrazione": "2026-02-10", "iva": 100}
    c = ivf.campi_iva_da_fattura(inv)
    assert c["periodo_iva_attribuito"] == "2026-01"
    assert c["regola_iva_applicata"] == "ENTRO_15_MESE_SUCCESSIVO"


def test_periodo_da_righe_operazione():
    # fattura periodica: l'operazione è la fine periodo indicata nella riga
    inv = {"invoice_date": "2026-03-05",
           "linee": [{"data_inizio_periodo": "2026-02-01", "data_fine_periodo": "2026-02-28"}],
           "data_ricezione": "2026-03-05", "iva": 50}
    c = ivf.campi_iva_da_fattura(inv)
    assert c["data_operazione"] == "2026-02-28"
    # operazione febbraio, ricezione 5/3 (entro il 15) → attribuita a febbraio
    assert c["periodo_iva_attribuito"] == "2026-02"


def test_cambio_anno_non_retroattribuisce():
    inv = {"invoice_date": "2025-12-31", "data_ricezione": "2026-01-08",
           "data_registrazione": "2026-01-08", "iva": 300}
    c = ivf.campi_iva_da_fattura(inv)
    assert c["periodo_iva_attribuito"] == "2026-01"
    assert c["regola_iva_applicata"] == "OPERAZIONE_ANNO_PRECEDENTE"


def test_iva_gia_utilizzata_non_viene_toccata():
    inv = {"invoice_date": "2026-01-31", "data_ricezione": "2026-02-08",
           "iva": 100, "iva_utilizzata": True,
           "stato_detrazione_iva": "INSERITA_IN_LIQUIDAZIONE",
           "periodo_iva_utilizzato": "2026-01"}
    c = ivf.campi_iva_da_fattura(inv)
    assert c["iva_utilizzata"] is True
    assert c["stato_detrazione_iva"] == "INSERITA_IN_LIQUIDAZIONE"
    assert c["periodo_iva_utilizzato"] == "2026-01"


def test_fallback_data_ricezione_su_data_documento():
    # P2-a (fix 13/07/2026): senza data_ricezione esplicita si usa la data del
    # DOCUMENTO, NON la data di importazione (created_at), che per le fatture
    # storiche importate in blocco mis-attribuirebbe il pregresso.
    inv = {"invoice_date": "2026-05-31", "created_at": "2026-06-10T09:00:00", "iva": 10}
    c = ivf.campi_iva_da_fattura(inv)
    assert c["data_ricezione"] == "2026-05-31"
    assert c["periodo_iva_attribuito"] == "2026-05"
