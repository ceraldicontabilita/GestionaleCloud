from app.services.parser_f24 import (
    _data_versamento_da_testo,
    _rateazione_e_anno,
)


def test_rateazione_0101_non_viene_persa_o_scambiata_per_anno():
    assert _rateazione_e_anno(["0101", "2025", "4.613", "50"]) == ("0101", "2025")
    assert _rateazione_e_anno(["2025", "95", "12"]) == ("", "2025")


def test_data_bancaria_con_cifre_separate():
    testo = "ESTREMI DEL VERSAMENTO\n0 4 0 8 2 0 2 6\n05034\n03406"
    assert _data_versamento_da_testo(testo) == "2026-08-04"


def test_data_non_viene_inventata_senza_estremi_versamento():
    testo = "MODELLO F24\nSALDO FINALE 2.029,67\nCODICE TRIBUTO 2003"
    assert _data_versamento_da_testo(testo) == ""
