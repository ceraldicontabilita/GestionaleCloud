import fitz

from app.routers import documenti
from app.services.pdf_text_extraction import (
    _sample_page_indexes,
    extract_pdf_text,
    pdf_has_searchable_text,
)


def _pdf_with_pages(*texts: str) -> bytes:
    document = fitz.open()
    try:
        for text in texts:
            page = document.new_page()
            if text:
                page.insert_textbox(
                    fitz.Rect(40, 40, 555, 800),
                    text,
                    fontsize=10,
                )
        return document.tobytes()
    finally:
        document.close()


def test_campionamento_include_prime_e_ultime_pagine():
    assert _sample_page_indexes(10, 5) == [0, 1, 2, 8, 9]
    assert _sample_page_indexes(3, 5) == [0, 1, 2]


def test_estrazione_legge_il_contenuto_utile_in_coda():
    pdf = _pdf_with_pages(
        "Copertina generica",
        "Indice",
        "Comunicazione introduttiva",
        "Allegato",
        "MODELLO DI PAGAMENTO UNIFICATO DELEGA IRREVOCABILE "
        "CODICE FISCALE CODICE TRIBUTO SEZIONE ERARIO SALDO FINALE 6099",
    )

    text = extract_pdf_text(pdf, max_pages=4)

    assert "[PAGINA 5]" in text
    assert "CODICE TRIBUTO" in text
    assert documenti.detect_document_type("documento.pdf", pdf) == "f24"


def test_estrazione_sceglie_testo_nativo_e_segnala_scansione_vuota():
    searchable = _pdf_with_pages("CODICE FISCALE 01234567890 CODICE TRIBUTO 6099")
    scanned = _pdf_with_pages("")

    assert "01234567890" in extract_pdf_text(searchable)
    assert pdf_has_searchable_text(searchable) is True
    assert extract_pdf_text(scanned) == ""
    assert pdf_has_searchable_text(scanned) is False
