from app.parsers.estratto_conto_bpm_parser import (
    parse_bpm_card_movements_text,
    parse_bpm_text,
)


def test_parser_bpm_conserva_segno_beneficiario_e_pos():
    text = """
    DATA CONTABILE
    25/03/26
    25/03/26
    NUMIA-AMEX DEL 24/03/26 PDV 3757283/00011
    24,40
    25/03/26
    CERALDI CAFFE NA
    27/03/26
    27/03/26
    VS.DISP. RIF. MBVT0001/0001 FAVORE
    - 267,02
    27/03/26
    TOP SPINA S.R.L. UNIPERSONALE NOTPROVIDE 000000000001855/01
    """
    rows = parse_bpm_text(text)
    assert len(rows) == 2
    assert rows[0]["tipo"] == "entrata"
    assert rows[0]["importo"] == 24.40
    assert "NUMIA-AMEX" in rows[0]["descrizione"]
    assert rows[1]["tipo"] == "uscita"
    assert rows[1]["importo"] == -267.02
    assert "TOP SPINA" in rows[1]["descrizione"]
    assert "000000000001855/01" in rows[1]["descrizione"]


def test_parser_bpm_assegno_non_inventa_beneficiario():
    text = """
    20/03/26
    20/03/26
    VOSTRO ASSEGNO N. 0208770767
    - 646,72
    20/03/26
    21/03/26
    21/03/26
    NUMIA-INTER DEL 20/03/26
    100,00
    21/03/26
    """
    rows = parse_bpm_text(text)
    assert len(rows) == 2
    assert rows[0]["descrizione"] == "VOSTRO ASSEGNO N. 0208770767"
    assert "EUREKA" not in rows[0]["descrizione"]


def test_parser_movimenti_carta_debito_bpm_conserva_segno_e_descrizione():
    text = """Carta di debito
Circuito: MASTERCARD Conto Appoggio: 5462
Filtro
Data da: 12/05/2025 Data a: 12/06/2025
Data e ora Importo Descrizione Tipo operazione
03/06/2025 10:30:00 -716,72 EUR FORNITORE ESEMPIO SRL NAPOLI PAGAMENTO
Creato il 12/06/2025 alle ore 08.45.40 Pagina 1 di 1
"""

    rows = parse_bpm_card_movements_text(text)

    assert len(rows) == 1
    assert rows[0]["data"] == "2025-06-03"
    assert rows[0]["data_ora"] == "2025-06-03T10:30:00"
    assert rows[0]["importo"] == -716.72
    assert rows[0]["tipo"] == "uscita"
    assert rows[0]["tipo_operazione"] == "pagamento"
    assert rows[0]["descrizione"] == "FORNITORE ESEMPIO SRL NAPOLI"
    assert rows[0]["divisa"] == "EUR"


def test_parser_bpm_impaginazione_dal_30_06_2026():
    """Dal trimestre al 30/06/2026 PyMuPDF restituisce: entrata = tre date e
    poi «importo testo» sulla stessa riga; uscita = due date, importo da solo,
    descrizione dopo, data disponibile in coda (a volte assente). Un'uscita
    senza data disponibile seguita da un'entrata non deve mangiarsi la sua
    prima data."""
    text = """
    31/03/26
    11.391,75 SALDO INIZIALE A VOSTRO CREDITO
    01/04/26
    01/04/26
    01/04/26
    14,00 CIRCUITO-A  DEL 31/03/26 PDV 1/00011
    NEGOZIO PROVA                            NA
    01/04/26
    01/04/26
    - 850,34  
    SDD CORE: 0000000000000000000001
    FORNITORE UNO SRL
    01/04/26
    03/04/26
    03/04/26
    - 29,10  
    IMP.BOLLO CC LR EX ART.13
    DA 01/01/2026 A 31/03/2026
    03/04/26
    03/04/26
    03/04/26
    570,00 CIRCUITO-B  DEL 02/04/26 PDV 1/00011
    NEGOZIO PROVA                            NA
    """
    rows = parse_bpm_text(text)
    assert [(r["data"], r["importo"]) for r in rows] == [
        ("2026-04-01", 14.0), ("2026-04-01", -850.34),
        ("2026-04-03", -29.1), ("2026-04-03", 570.0),
    ]
    assert rows[0]["data_disponibile"] == "2026-04-01"
    assert rows[0]["descrizione"] == "CIRCUITO-A DEL 31/03/26 PDV 1/00011 NEGOZIO PROVA NA"
    assert rows[1]["descrizione"] == "SDD CORE: 0000000000000000000001 FORNITORE UNO SRL"
    assert rows[1]["data_disponibile"] == "2026-04-01"
    assert rows[2]["data_disponibile"] is None
    assert "DA 01/01/2026" in rows[2]["descrizione"]
    assert rows[3]["data_disponibile"] == "2026-04-03"
