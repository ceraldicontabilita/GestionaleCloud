from app.services.mutui_document_import import (
    classify_mutuo_text,
    parse_estratto_annuale_text,
    parse_quietanza_text,
)


def test_classifica_le_tre_fonti_senza_confonderle():
    assert classify_mutuo_text("Piano di Ammortamento Numero delibera: 9") == "piano_ammortamento"
    assert classify_mutuo_text("MUTUI: QUIETANZA DI PAGAMENTO") == "quietanza"
    assert classify_mutuo_text(
        "CAPITALE EUR 4.558,42 Finanziamento n. 1788/0005217466 "
        "RATA N. 011 SCADENTE IL 17/01/2022"
    ) == "quietanza"
    assert classify_mutuo_text("capitale iniziale al 01/01/2022 capitale finale al 31/12/2022") == "estratto_annuale"


def test_quietanza_separa_capitale_interessi_spese_e_non_finge_riconciliazione():
    text = """
    1788/0005217466Finanziamento n.
    CAPITALE EUR 4.558,42
    INTERESSI EUR 427,86
    MUTUI: QUIETANZA DI PAGAMENTO
    DEBITO RESIDUO DOPO INCASSO EUR 223.363,46
    RATA N. 011 SCADENTE IL 17/01/2022
    SU QUESTA RATA SONO STATE CONTEGGIATE 2,75 EURO PER SPESE INCASSO RATA
    """
    parsed = parse_quietanza_text(text, "Mutui - Quietanza di pagamento_01-02-2022_4989,03.pdf")
    assert parsed["numero_finanziamento"] == "1788/0005217466"
    assert parsed["numero_rata"] == 11
    assert parsed["importo_totale"] == 4989.03
    assert parsed["quota_capitale"] == 4558.42
    assert parsed["quota_interessi"] == 427.86
    assert parsed["spese_incasso"] == 2.75
    assert parsed["data_pagamento"] == "2022-02-01"
    assert parsed["riconciliato_banca"] is False


def test_estratto_annuale_conserva_movimenti_e_capitali():
    text = """
    capitale iniziale al 01/01/2022: 30.000,00
    PAGAMENTO RATA 24/10/2022 24/10/2022 24/10/2022 512,17
    capitale finale al 31/12/2022: 28.500,00
    IMPORTO STIPULATO/RINEGOZIATO 30.000,00
    DATA SCADENZA 24/09/2027
    del Finanziamento n. 1788/045/000004851906
    """
    parsed = parse_estratto_annuale_text(text)
    assert parsed["anno"] == 2022
    assert parsed["capitale_iniziale"] == 30000.0
    assert parsed["capitale_finale"] == 28500.0
    assert parsed["numero_finanziamento"] == "1788/045/000004851906"
    assert parsed["pagamenti"][0]["importo"] == 512.17
