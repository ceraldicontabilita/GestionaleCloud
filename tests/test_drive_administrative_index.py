from app.services import drive_document_index as index


def test_indice_drive_classifica_solo_pdf_amministrativi(monkeypatch):
    records = [
        {"ID documento": "v1", "Dominio": "VERBALI AUTO", "Categoria": "NOTIFICHE POLIZIA LOCALE", "Anno": "2026", "Nome file": "verbale.pdf", "Estensione": "pdf", "SHA-256": "a", "Percorso Drive": "VERBALI AUTO/verbale.pdf", "Stato": "VERIFICATO"},
        {"ID documento": "t1", "Dominio": "TRIBUTI LOCALI - TARI TARES TARSU", "Categoria": "TARI", "Anno": "2024", "Nome file": "tari.pdf", "Estensione": "pdf", "SHA-256": "b", "Percorso Drive": "TRIBUTI LOCALI/tari.pdf", "Stato": "DA VERIFICARE"},
        {"ID documento": "p1", "Dominio": "CORRISPONDENZA PEC - FONTI", "Categoria": "testo_email", "Anno": "2026", "Nome file": "dimissioni.txt", "Estensione": "txt", "SHA-256": "c", "Percorso Drive": "PEC/dimissioni.txt", "Stato": "VERIFICATO"},
    ]
    monkeypatch.setattr(index, "load_catalog", lambda service=None: ({}, records))

    payload = index.list_administrative_documents()

    assert payload["overview"] == {
        "counts": {"verbali": 1, "tributi_locali": 1, "riscossione": 0, "personale": 0},
        "total": 2,
        "requires_review": 1,
    }
    assert [item["id"] for item in payload["items"]] == ["v1", "t1"]
    assert all(item["source_kind"] == "drive_index" for item in payload["items"])


def test_indice_drive_filtra_area_anno_ricerca_e_revisioni(monkeypatch):
    records = [
        {"ID documento": "t1", "Dominio": "TRIBUTI LOCALI", "Categoria": "TARI", "Anno": "2024", "Nome file": "protocollo-123.pdf", "Estensione": "pdf", "SHA-256": "a", "Percorso Drive": "TARI/protocollo-123.pdf", "Stato": "DA VERIFICARE"},
        {"ID documento": "t2", "Dominio": "TRIBUTI LOCALI", "Categoria": "TARI", "Anno": "2023", "Nome file": "altro.pdf", "Estensione": "pdf", "SHA-256": "b", "Percorso Drive": "TARI/altro.pdf", "Stato": "VERIFICATO"},
    ]
    monkeypatch.setattr(index, "load_catalog", lambda service=None: ({}, records))

    payload = index.list_administrative_documents(
        area="tributi_locali", year="2024", q="protocollo-123", review_only=True,
    )

    assert payload["total"] == 1
    assert payload["items"][0]["id"] == "t1"
    assert payload["overview"]["total"] == 2
