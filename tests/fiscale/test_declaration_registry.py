from app.services.declaration_registry import declaration_metadata
from app.services.fiscal_domain import DocumentType, classify_document


def test_770_keeps_filing_year_tax_year_and_protocol_separate():
    item = declaration_metadata({
        "id": "decl-1",
        "document_type": "MODELLO_770",
        "filename": "770_2024_imposta_2023_T241029181612999.pdf",
        "source_metadata": {},
    })
    assert item["filing_year"] == 2024
    assert item["tax_year"] == 2023
    assert item["protocol"] == "T241029181612999"


def test_new_declaration_types_are_classified_from_archive_names():
    assert classify_document("770_2025_imposta_2024_T251021.pdf")["document_type"] == DocumentType.MODELLO_770
    assert classify_document("IVA_2025_imposta_2024_T251021.pdf")["document_type"] == DocumentType.DICHIARAZIONE_IVA
    assert classify_document("IRAP_2025_imposta_2024_T251021.pdf")["document_type"] == DocumentType.DICHIARAZIONE_IRAP
    assert classify_document("760_2025_imposta_2024_T251021.pdf")["document_type"] == DocumentType.REDDITI_SC
