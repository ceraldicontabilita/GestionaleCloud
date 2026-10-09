import io

import openpyxl

from app.routers.bank.estratto_conto import parse_enti_file_contabili_xlsx
from app.services.nexi_carta import nexi_operation_identity


def _workbook_bytes():
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append([
        "Posizione", "Anagrafica", "Tipo Riga", "Flag Riga",
        "Data Contabile", "Codice Carta", "Data Valuta",
        "Codice Interno", "Importo Spesa", "Codice Valuta", "Insegna",
        "Località", "Codice Categoria Merceologica",
    ])
    sheet.append([
        "753904", "AZIENDA", "E", None, "31/05/2026", "558686******9998",
        "05/05/2026", "REF-1", "23,10", "EUR", "FORNITORE", "NAPOLI", "5814",
    ])
    sheet.append([
        "753904", "AZIENDA", "D", "P", "31/05/2026", "0000000000000000",
        "30/11/1999", None, "2", "EUR", "IMPOSTA DI BOLLO", None, None,
    ])
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_parse_enti_file_contabili_usa_data_operazione_e_segno_uscita():
    rows = parse_enti_file_contabili_xlsx(_workbook_bytes())

    assert rows is not None and len(rows) == 2
    assert rows[0]["data"].isoformat() == "2026-05-05"
    assert rows[0]["data_pagamento"].isoformat() == "2026-05-31"
    assert rows[0]["importo"] == -23.10
    assert rows[0]["tipo"] == "uscita"
    assert rows[0]["banca"] == "Nexi"
    assert rows[0]["external_reference"] == "REF-1"
    assert "FORNITORE" in rows[0]["descrizione_originale"]


def test_parse_enti_file_contabili_sostituisce_data_tecnica_del_bollo():
    rows = parse_enti_file_contabili_xlsx(_workbook_bytes())

    assert rows[1]["data"].isoformat() == "2026-05-31"
    assert rows[1]["importo"] == -2.0
    assert rows[1]["fornitore"] == "IMPOSTA DI BOLLO"


def test_chiave_carta_coincide_tra_excel_contabile_e_pdf_nexi():
    rows = parse_enti_file_contabili_xlsx(_workbook_bytes())
    excel_key, _ = nexi_operation_identity(
        "2026-05-05", 23.10, rows[0]["identity_description"], 1,
    )
    pdf_key, _ = nexi_operation_identity(
        "2026-05-05", 23.10, "FORNITORE NAPOLI", 1,
    )

    assert excel_key == pdf_key
