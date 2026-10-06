"""Le date illeggibili sono dato mancante: mai un valore inventato."""
from app.parsers.estratto_conto_nexi_parser import EstrattoContoNexiParser
from app.services.distinte_bpm import parse_date_it


def _parser():
    return EstrattoContoNexiParser.__new__(EstrattoContoNexiParser)


def test_distinta_data_valida():
    assert parse_date_it("05/03/2026") == "2026-03-05"


def test_distinta_data_impossibile_e_mancante():
    assert parse_date_it("31/02/2026") is None
    assert parse_date_it("xx/yy/zzzz") is None
    assert parse_date_it("") is None


def test_nexi_mese_sconosciuto_non_diventa_gennaio():
    p = _parser()
    p.metadata = {}
    p._extract_metadata("Milano, 12 foobar 2026")
    assert "data_estratto_iso" not in p.metadata


def test_nexi_mese_noto():
    p = _parser()
    p.metadata = {}
    p._extract_metadata("Milano, 12 marzo 2026")
    assert p.metadata["data_estratto_iso"] == "2026-03-12"
