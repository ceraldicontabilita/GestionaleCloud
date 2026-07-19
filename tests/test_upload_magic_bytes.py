"""Copre app/utils/upload_validation.py — controllo del CONTENUTO reale
(magic bytes) di un upload dichiarato PDF, non solo l'estensione del
filename. Prima di questo file la funzione era referenziata solo in una
fixture di conftest.py, senza alcuna asserzione dedicata."""
import pytest
from fastapi import HTTPException

from app.utils.upload_validation import verifica_pdf_reale

_PDF_VALIDO = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<< >>\nendobj\n%%EOF"


def test_pdf_reale_passa():
    verifica_pdf_reale(_PDF_VALIDO, "fattura.pdf")  # non deve sollevare


def test_file_rinominato_con_estensione_pdf_ma_contenuto_diverso_viene_respinto():
    """Il caso a rischio esplicito nella docstring del modulo: un file
    rinominato con estensione .pdf che finirebbe comunque in un parser PDF."""
    contenuto_html = b"<html><body>non e' un pdf</body></html>"
    with pytest.raises(HTTPException) as exc:
        verifica_pdf_reale(contenuto_html, "finto.pdf")
    assert exc.value.status_code == 400
    assert "finto.pdf" in exc.value.detail


def test_file_vuoto_viene_respinto():
    with pytest.raises(HTTPException) as exc:
        verifica_pdf_reale(b"", "vuoto.pdf")
    assert exc.value.status_code == 400


def test_pdf_con_spazi_iniziali_passa_comunque():
    """Alcuni PDF reali hanno whitespace prima della firma %PDF-: la
    funzione fa lstrip() prima del controllo, non deve dare falso positivo."""
    verifica_pdf_reale(b"   \n" + _PDF_VALIDO, "con_spazi.pdf")


def test_immagine_png_rinominata_pdf_viene_respinta():
    """Un altro caso realistico: un'immagine con estensione .pdf sbagliata."""
    magic_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    with pytest.raises(HTTPException):
        verifica_pdf_reale(magic_png, "foto.pdf")
