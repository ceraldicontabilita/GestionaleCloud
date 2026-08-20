from app.services import drive_declaration_upload as upload


def test_duplicate_is_reused_without_writing_drive(monkeypatch):
    digest = __import__('hashlib').sha256(b'%PDF-existing').hexdigest()
    monkeypatch.setattr(upload.index, 'load_full_catalog', lambda service: (
        {'root_id': 'root'}, {'documents': [{
            'ID documento': 'DOC-EXISTING', 'SHA-256': digest,
            'Percorso Drive': '01_DICHIARAZIONI_FISCALI/770/2026/existing.pdf',
        }]},
    ))
    result = upload.upload_declaration(
        content=b'%PDF-existing', filename='existing.pdf', category='modello_770',
        filing_year=2026, service=object(),
    )
    assert result['duplicate'] is True
    assert result['document_id'] == 'DOC-EXISTING'


def test_automatic_classification_requires_a_declaration_type(monkeypatch):
    monkeypatch.setattr(upload, 'extract_pdf_pages', lambda _content: [{'text': 'testo generico'}])
    monkeypatch.setattr(upload, 'classify_document', lambda *_args: {'document_type': 'ALTRO_FISCALE'})
    try:
        upload._classification(b'%PDF-test', 'altro.pdf', 'automatica')
    except ValueError as exc:
        assert 'scegliere manualmente' in str(exc)
    else:
        raise AssertionError('classificazione incerta accettata')
