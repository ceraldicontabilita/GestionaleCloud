from app.engines.iva_fatture import campi_iva_da_fattura, motivo_detraibilita_in_dubbio


def test_condizioni_fiscali_incerte_non_scompaiono_con_cdc_classificato():
    fattura = {"invoice_date": "2026-09-30", "iva": 22,
               "iva_detraibile": 11, "stato_classificazione": "classificata",
               "valutazione_fiscale_iva": {"stato": "da_verificare", "motivo": "Uso telefono non documentato"}}
    assert motivo_detraibilita_in_dubbio(fattura) == "Uso telefono non documentato"
    assert campi_iva_da_fattura(fattura)["stato_detrazione_iva"] == "DA_VERIFICARE"


def test_decisione_iva_documentata_prevale_sul_vecchio_cdc_telefonia():
    fattura = {"iva_detraibile": 22, "percentuale_detraibilita_iva": 1,
               "centro_costo_id": "10.1_TELEFONIA", "stato_classificazione": "da_verificare",
               "classificazione_confidence": 0.2,
               "valutazione_fiscale_iva": {"stato": "valutata", "motivo": "Uso aziendale documentato"}}
    assert motivo_detraibilita_in_dubbio(fattura) is None
