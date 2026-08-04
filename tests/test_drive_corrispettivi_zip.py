import io
import zipfile

import pytest

from app.services.drive_corrispettivi_ingest import (
    _xml_documents_from_source,
    is_corrispettivo_filename,
)


def _zip_bytes(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return buffer.getvalue()


def test_accetta_xml_e_zip_e_ignora_altri_formati():
    assert is_corrispettivo_filename("giorno.XML")
    assert is_corrispettivo_filename("corrispettivi.ZIP")
    assert not is_corrispettivo_filename("riepilogo.pdf")


def test_estrae_solo_xml_da_zip_senza_scrivere_su_disco():
    content = _zip_bytes([
        ("2026/uno.xml", b"<uno />"),
        ("DUE.XML", b"<due />"),
        ("note.txt", b"non contabile"),
    ])

    documents = _xml_documents_from_source("batch.zip", content)

    assert documents == [
        ("batch.zip::2026/uno.xml", b"<uno />"),
        ("batch.zip::DUE.XML", b"<due />"),
    ]


def test_rifiuta_zip_senza_xml_o_con_percorso_non_sicuro():
    with pytest.raises(ValueError, match="senza file XML"):
        _xml_documents_from_source("vuoto.zip", _zip_bytes([("note.txt", b"x")]))

    with pytest.raises(ValueError, match="Percorso non sicuro"):
        _xml_documents_from_source("insicuro.zip", _zip_bytes([("../uno.xml", b"<uno />")]))


def test_xml_singolo_resta_compatibile():
    assert _xml_documents_from_source("uno.xml", b"<uno />") == [
        ("uno.xml", b"<uno />"),
    ]
