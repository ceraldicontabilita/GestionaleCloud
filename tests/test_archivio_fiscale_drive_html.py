from pathlib import Path


HTML = Path(__file__).parents[1] / "frontend" / "public" / "archivio-fiscale-drive.html"


def test_pagina_html_interattiva_usa_solo_api_drive():
    text = HTML.read_text(encoding="utf-8")
    assert "/api/documenti/drive/index/status" in text
    assert "/api/documenti/drive/index/overview" in text
    assert "/api/documenti/drive/index/document/" in text
    assert "/api/documenti-fiscali/upload" in text
    assert "documents_inbox" not in text.casefold()


def test_pagina_contiene_filtri_relazioni_e_link_pdf():
    text = HTML.read_text(encoding="utf-8")
    for marker in ('data-tab="declarations"', 'data-tab="f24"', 'id="year"',
                   'id="taxCode"', 'id="upload"', 'id="driveLink"'):
        assert marker in text
