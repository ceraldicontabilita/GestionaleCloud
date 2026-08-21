import io
import zipfile

from render_workflows.calderone import iter_pdfs


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
