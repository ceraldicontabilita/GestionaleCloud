from app.parsers.estratto_conto_nexi_parser import EstrattoContoNexiParser


def test_metadata_nexi_accetta_titolo_addebito_senza_spazi():
    parser = EstrattoContoNexiParser()
    parser._extract_metadata(
        """
        Milano, 31 Gennaio 2026
        QUESTO MESE HA SPESO
        Euro 2.881,92
        QUESTOMESELESARANNOADDEBITATI
        Euro 2.883,92
        Imposta di bollo
        2,00
        """
    )
    assert parser.metadata["totale_spese_mese"] == 2881.92
    assert parser.metadata["totale_addebito"] == 2883.92
    assert parser.metadata["imposta_bollo"] == 2.0


def test_metadata_nexi_legge_totale_addebito_di_riepilogo():
    parser = EstrattoContoNexiParser()
    parser._extract_metadata(
        """
        Milano, 28 Febbraio 2026
        Totale spese con carte a saldo
        721,65
        Imposta di bollo
        2,00
        TOTALE ADDEBITO SUL SUO C/C
        723,65
        """
    )
    assert parser.metadata["totale_addebito"] == 723.65
    assert parser.metadata["imposta_bollo"] == 2.0
