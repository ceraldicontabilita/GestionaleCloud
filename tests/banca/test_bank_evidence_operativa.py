from app.services.bank_evidence import (
    EVIDENZA_PROVVISORIA,
    EVIDENZA_UFFICIALE,
    STATO_ATTESA_UFFICIALE,
    campi_evidenza,
    filtro_solo_evidenza_ufficiale,
)
from app.services.estratto_conto_bpm_parser import parse_estratto_conto_bpm
from app.services.riconciliazione_operativa_banca import classifica_movimento_operativo


def test_csv_excel_sono_operativi_pdf_e_ufficiale():
    for filename in ("movimenti.csv", "movimenti.xlsx", "movimenti.xls"):
        campi = campi_evidenza(filename)
        assert campi["livello_evidenza"] == EVIDENZA_PROVVISORIA
        assert campi["evidenza_bancaria_ufficiale"] is False
        assert campi["in_attesa_estratto_ufficiale"] is True
        assert campi["stato_riconciliazione"] == STATO_ATTESA_UFFICIALE

    ufficiale = campi_evidenza("Estratto conto trimestrale.pdf")
    assert ufficiale["livello_evidenza"] == EVIDENZA_UFFICIALE
    assert ufficiale["evidenza_bancaria_ufficiale"] is True
    assert ufficiale["in_attesa_estratto_ufficiale"] is False


def test_filtro_ufficiale_mantiene_compatibilita_con_storico():
    filtro = filtro_solo_evidenza_ufficiale()
    assert {"livello_evidenza": {"$exists": False}} in filtro["$or"]
    assert {"livello_evidenza": "ufficiale"} in filtro["$or"]
    assert {"evidenza_bancaria_ufficiale": True} in filtro["$or"]


def test_parser_export_bpm_reale_con_formato_italiano():
    csv = (
        "Ragione Sociale;Data contabile;Data valuta;Banca;Rapporto;Importo;"
        "Divisa;Descrizione;Categoria/sottocategoria;Hashtag\n"
        "AZIENDA TEST;03/08/2026;04/08/2026;BANCA TEST;***1234;-1.234,56;"
        "EUR;BONIFICO FATTURA TEST 123/26;Fornitori;\n"
        "AZIENDA TEST;03/08/2026;04/08/2026;BANCA TEST;***1234;250,40;"
        "EUR;ACCREDITO POS NUMIA;POS;\n"
    )
    result = parse_estratto_conto_bpm(csv)
    assert result["stats"]["totale_movimenti"] == 2
    assert result["totale_uscite"] == 1234.56
    assert result["totale_entrate"] == 250.40
    assert result["saldo"] == -984.16


def test_classificazione_operativa_specializzata():
    assert classifica_movimento_operativo({
        "tipo": "uscita", "descrizione": "VOSTRO ASSEGNO N. 1234567890"
    }) == "assegno"
    assert classifica_movimento_operativo({
        "tipo": "uscita", "categoria": "Stipendi e salari"
    }) == "cedolino"
    assert classifica_movimento_operativo({
        "tipo": "entrata", "descrizione": "ACCREDITO POS NUMIA"
    }) == "pos"
    assert classifica_movimento_operativo({
        "tipo": "uscita", "descrizione": "SDD SEPA FORNITORE"
    }) == "fattura"
