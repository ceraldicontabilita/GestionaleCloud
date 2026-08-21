import io
import zipfile

from render_workflows.calderone import extract_net_from_words, iter_pdfs


def test_iter_pdfs_preserva_originali_nello_zip():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("dipendenti/cedolino.pdf", b"%PDF-1.4\noriginale")
        archive.writestr("note.txt", b"ignora")
    items = list(iter_pdfs("cedolini.zip", output.getvalue()))
    assert items == [("dipendenti/cedolino.pdf", b"%PDF-1.4\noriginale")]


def test_iter_pdfs_blocca_traversal():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("../cedolino.pdf", b"%PDF-1.4\n")
    try:
        list(iter_pdfs("cedolini.zip", output.getvalue()))
    except ValueError as exc:
        assert "non sicuro" in str(exc)
    else:
        raise AssertionError("traversal non bloccato")


def _words(*values):
    return [
        {"text": text, "x0": index * 50, "x1": index * 50 + 40, "top": 100}
        for index, text in enumerate(values)
    ]


def test_netto_prende_primo_importo_a_destra_non_arrotondamenti_o_lire():
    words = _words("ARR.", "ATTUALE", "TOTALE", "NETTO", "153,00+", "LIRE", "296.249+")
    assert extract_net_from_words(words) == [153]


def test_netto_riconosce_spazi_pdf_corrotto_e_netto_busta():
    assert extract_net_from_words(_words("NETTOsDELsMESE", "1.154,00€")) == [1154]
    assert extract_net_from_words(_words("NETTO", "BUSTA", "1.070,00")) == [1070]


def test_netto_riconosce_cella_sotto_allineata_alla_colonna():
    words = _words("ARR.", "ATTUALE", "TOTALE", "NETTO")
    words.extend([
        {"text": "0,05", "x0": 50, "x1": 80, "top": 111},
        {"text": "153,00+", "x0": 148, "x1": 190, "top": 111},
    ])
    assert extract_net_from_words(words) == [153]
