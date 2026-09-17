from pathlib import Path

from app.services.parser_f24 import (
    _data_versamento_da_testo,
    _rateazione_e_anno,
    parse_f24_commercialista,
)


def test_rateazione_0101_non_viene_persa_o_scambiata_per_anno():
    assert _rateazione_e_anno(["0101", "2025", "4.613", "50"]) == ("0101", "2025")
    assert _rateazione_e_anno(["2025", "95", "12"]) == ("", "2025")


def test_data_bancaria_con_cifre_separate():
    testo = "ESTREMI DEL VERSAMENTO\n0 4 0 8 2 0 2 6\n05034\n03406"
    assert _data_versamento_da_testo(testo) == "2026-08-04"


def test_f24_reale_isa_se_disponibile_sul_pc():
    percorso = Path(r"C:\Users\ceral\Downloads\F24 ravvedim adeg Isa e I acc Ires.pdf")
    if not percorso.exists():
        return
    parsed = parse_f24_commercialista(pdf_content=percorso.read_bytes())
    righe = {r["codice_tributo"]: r for r in parsed["sezione_erario"]}
    assert parsed["dati_generali"]["data_versamento"] == "2026-08-04"
    assert righe["2001"]["rateazione"] == "0101"
    assert righe["2001"]["importo_debito"] == 4613.50
    assert parsed["totali"]["saldo_finale"] == 5362.52
