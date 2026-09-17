import hashlib

from app.services.drive_invoice_ingest import (
    _add_source_occurrence,
    _drive_source_metadata,
)


def test_drive_source_metadata_include_identita_hash_e_link_originale():
    content = b"fattura-xml-reale-sostituita-da-byte-di-test"
    metadata = _drive_source_metadata(
        {
            "id": "drive-file-1",
            "name": "fattura.xml",
            "mimeType": "text/xml",
            "modifiedTime": "2026-09-12T10:00:00Z",
            "md5Checksum": "provider-md5",
            "size": str(len(content)),
            "parents": ["folder-1"],
        },
        content,
        parent_id="folder-1",
        source_path="2026/Da elaborare",
    )

    assert metadata["drive_file_id"] == "drive-file-1"
    assert metadata["source_document_id"] == "drive-file-1"
    assert metadata["file_hash"] == hashlib.sha256(content).hexdigest()
    assert metadata["source_web_view_link"].endswith("/drive-file-1/view")
    assert metadata["source_occurrences"] == [
        {"parent_id": "folder-1", "path": "2026/Da elaborare"}
    ]


def test_rebuild_conserva_tutte_le_occorrenze_dello_stesso_file_drive():
    unique = {}
    file_info = {"id": "drive-file-1", "name": "fattura.xml"}

    _add_source_occurrence(unique, file_info, "2025/Elaborate", "folder-a")
    _add_source_occurrence(unique, file_info, "2026/Elaborate", "folder-b")
    _add_source_occurrence(unique, file_info, "2026/Elaborate", "folder-b")

    assert len(unique) == 1
    assert unique["drive-file-1"]["_source_occurrences"] == [
        {"parent_id": "folder-a", "path": "2025/Elaborate"},
        {"parent_id": "folder-b", "path": "2026/Elaborate"},
    ]
