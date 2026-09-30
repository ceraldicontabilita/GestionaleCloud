"""F24 stampati da programmi che perdono la virgola nel livello testo.

«1.03712» e' 1.037,12: letto come 1.037 x 100 il saldo usciva di centinaia di
migliaia di euro e l'import bloccava il modello. E un codice 4731 (ritenute)
non era fra quelli dell'Erario, quindi la riga spariva.
"""
import fitz
import pytest

from app.services.f24_canonico import richiedi_quadratura_f24
from app.services.parser_f24 import _importo_cents_da_token, parse_f24_commercialista


def _pdf(righe):
    doc = fitz.open()
    pagina = doc.new_page(width=595, height=842)
    for x, y, testo in righe:
        pagina.insert_text((x, y), testo, fontsize=8)
    return doc.tobytes()


@pytest.mark.parametrize("token,cents", [
    ("1.03712", 103712), ("4.37100", 437100), ("99035", 99035),
    ("1.139,04", 113904), ("137,37", 13737), ("1.037,00", 103700),
])
def test_importo_senza_virgola_ha_i_centesimi_in_coda(token, cents):
    assert _importo_cents_da_token([(400, token)]) == cents


def test_codice_4731_resta_nell_erario_e_il_modello_quadra():
    parsed = parse_f24_commercialista(pdf_content=_pdf([
        (100, 240, "1001"), (140, 240, "07"), (170, 240, "2022"), (350, 240, "569,67"), (470, 240, "0,00"),
        (100, 256, "4731"), (140, 256, "07"), (170, 256, "2021"), (350, 256, "27,00"), (470, 256, "0,00"),
        (100, 272, "1701"), (140, 272, "07"), (170, 272, "2022"), (350, 272, "0,00"), (470, 272, "101,92"),
        (100, 300, "EURO"), (300, 300, "+"), (470, 300, "494,75"),
    ]))
    assert [r["codice_tributo"] for r in parsed["sezione_erario"]] == ["1001", "4731", "1701"]
    assert parsed["totali"]["totale_debito_cents"] == 59667


def test_errore_di_quadratura_elenca_le_righe_lette():
    parsed = parse_f24_commercialista(pdf_content=_pdf([
        (100, 240, "1001"), (140, 240, "07"), (170, 240, "2022"), (350, 240, "569,67"), (470, 240, "0,00"),
        (100, 300, "EURO"), (300, 300, "+"), (470, 300, "1,00"),
    ]))
    with pytest.raises(ValueError) as errore:
        richiedi_quadratura_f24(parsed)
    testo = str(errore.value)
    assert "saldo stampato: 100 cent" in testo and "E1001/2022 D56967 C0" in testo


def test_due_pagine_senza_numero_modello_hanno_un_saldo_per_pagina():
    doc = fitz.open()
    for righe in (
        [(100, 240, "1001"), (140, 240, "11"), (170, 240, "2023"), (350, 240, "100,00"), (470, 240, "0,00"),
         (100, 300, "EURO"), (300, 300, "+"), (470, 300, "100,00")],
        [(100, 240, "1012"), (140, 240, "11"), (170, 240, "2023"), (350, 240, "246,27"), (470, 240, "0,00"),
         (100, 300, "EURO"), (300, 300, "+"), (470, 300, "246,27")],
    ):
        pagina = doc.new_page(width=595, height=842)
        for x, y, testo in righe:
            pagina.insert_text((x, y), testo, fontsize=8)
    parsed = parse_f24_commercialista(pdf_content=doc.tobytes())
    assert parsed["validazione"]["saldo_quadrato"] is True
    assert parsed["totali"]["saldo_delega_cents"] == 34627
    richiedi_quadratura_f24(parsed)
