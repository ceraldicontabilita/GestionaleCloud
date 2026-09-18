from app.services import drive_document_index as index


def test_indice_drive_classifica_solo_pdf_amministrativi(monkeypatch):
    records = [
        {"ID documento": "v1", "Dominio": "VERBALI AUTO", "Categoria": "NOTIFICHE POLIZIA LOCALE", "Anno": "2026", "Nome file": "verbale.pdf", "Estensione": "pdf", "SHA-256": "a", "Percorso Drive": "VERBALI AUTO/verbale.pdf", "Stato": "VERIFICATO"},
        {"ID documento": "t1", "Dominio": "TRIBUTI LOCALI - TARI TARES TARSU", "Categoria": "TARI", "Anno": "2024", "Nome file": "tari.pdf", "Estensione": "pdf", "SHA-256": "b", "Percorso Drive": "TRIBUTI LOCALI/tari.pdf", "Stato": "DA VERIFICARE"},
        {"ID documento": "p1", "Dominio": "CORRISPONDENZA PEC - FONTI", "Categoria": "testo_email", "Anno": "2026", "Nome file": "dimissioni.txt", "Estensione": "txt", "SHA-256": "c", "Percorso Drive": "PEC/dimissioni.txt", "Stato": "VERIFICATO"},
        {"ID documento": "id1", "Dominio": "DOCUMENTI AZIENDALI", "Categoria": "Documento di identita", "Anno": "2022", "Nome file": "carta.pdf", "Estensione": "pdf", "SHA-256": "d", "Percorso Drive": "DOCUMENTI AZIENDALI/carta.pdf", "ZIP origine": "ESTRAZIONE 5 MITTENTI", "Percorso nel pacchetto": "01_DOCUMENTI_PDF/tari/carta.pdf", "Stato": "VERIFICATO"},
    ]
    monkeypatch.setattr(index, "load_catalog", lambda service=None: ({}, records))

    payload = index.list_administrative_documents()

    assert payload["overview"] == {
        "counts": {"verbali": 1, "tributi_locali": 1, "riscossione": 0, "personale": 0, "famiglia": 0},
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


def test_indice_drive_separa_tari_personale_per_hash_e_la_esclude_dalla_contabilita(monkeypatch):
    personal_sha = "d3edc9fd5c999343a4370d441bf2e67fe672d41eb6c370e4a43b589d01bcd45a"
    records = [{
        "ID documento": "DOC-D3EDC9FD5C999343", "Dominio": "TRIBUTI LOCALI",
        "Categoria": "TARI", "Anno": "2025",
        "Nome file": "DOC_20240600051909_20240719_171752.pdf", "Estensione": "pdf",
        "SHA-256": personal_sha, "Percorso Drive": "TARI/2025/documento.pdf",
        "Stato": "CARICATO_UNICO",
    }]
    monkeypatch.setattr(index, "load_catalog", lambda service=None: ({}, records))

    payload = index.list_administrative_documents(area="famiglia")

    assert payload["total"] == 1
    item = payload["items"][0]
    assert item["administrative_area"] == "famiglia"
    assert item["accounting_scope"] == "personal_family"
    assert item["accounting_excluded"] is True
    assert item["parsed_metadata"]["contribuente"] == "Ceraldi Antonietta"
    assert item["parsed_metadata"]["anno_tributo"] == "2024"
    assert payload["overview"]["counts"]["tributi_locali"] == 0
    assert payload["overview"]["counts"]["famiglia"] == 1
