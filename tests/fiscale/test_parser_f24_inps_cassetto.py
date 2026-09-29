"""Modello F24 stampato dal cassetto fiscale: la riga INPS ha l'anno fra i numeri.

Letta come riga Erario (codice = anno) finiva nella sezione sbagliata, e quando
l'importo era a credito (DM10 con «0,00 667,66») andava persa: il modello non
quadrava di quell'importo e l'import lo bloccava.
"""
import fitz

from app.services.parser_f24 import parse_f24_commercialista


def _pdf(righe):
    doc = fitz.open()
    pagina = doc.new_page(width=595, height=842)
    for x, y, testo in righe:
        pagina.insert_text((x, y), testo, fontsize=8)
    return doc.tobytes()


ERARIO = [
    (100, 240, "1001"), (140, 240, "02"), (170, 240, "2022"), (350, 240, "579,78"), (470, 240, "0,00"),
    (100, 256, "1701"), (140, 256, "02"), (170, 256, "2022"), (350, 256, "0,00"), (470, 256, "184,10"),
]


def test_dm10_a_credito_con_mese_a_una_cifra_non_si_perde():
    parsed = parse_f24_commercialista(pdf_content=_pdf(ERARIO + [
        (60, 352, "5100"), (100, 352, "DM10"), (150, 352, "5124776507"),
        (230, 352, "2"), (250, 352, "2022"), (350, 352, "0,00"), (470, 352, "667,66"),
    ]))

    [riga] = parsed["sezione_inps"]
    assert (riga["causale"], riga["periodo_riferimento"]) == ("DM10", "02/2022")
    assert riga["importo_debito_cents"] == 0 and riga["importo_credito_cents"] == 66766
    assert parsed["totali"]["totale_credito_cents"] == 18410 + 66766


def test_rc01_con_due_periodi_va_in_inps_e_non_in_erario_con_codice_anno():
    parsed = parse_f24_commercialista(pdf_content=_pdf(ERARIO + [
        (60, 368, "5100"), (100, 368, "RC01"), (150, 368, "5124776507"),
        (230, 368, "11"), (250, 368, "2022"), (280, 368, "11"), (300, 368, "2022"),
        (350, 368, "2.840,00"), (470, 368, "0,00"),
    ]))

    assert [r["codice_tributo"] for r in parsed["sezione_erario"]] == ["1001", "1701"]
    [riga] = parsed["sezione_inps"]
    assert (riga["causale"], riga["periodo_riferimento"]) == ("RC01", "11/2022")
    assert riga["importo_debito_cents"] == 284000
