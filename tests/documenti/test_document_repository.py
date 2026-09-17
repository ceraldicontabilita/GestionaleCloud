from app.db_collections import COLL_CEDOLINI, COLL_INVOICES
from app.document_repository import metadata_projection


def test_metadata_projection_esclude_payload_cedolino():
    assert metadata_projection(COLL_CEDOLINI) == {"_id": 0, "pdf_data": 0}


def test_metadata_projection_esclude_tutti_gli_originali_fattura():
    projection = metadata_projection(COLL_INVOICES)
    assert projection["_id"] == 0
    assert projection["fattura_allegata"] == 0
    assert projection["document_original_ref"] == 0
    assert projection["xml_raw"] == 0
    assert projection["foto"] == 0


def test_metadata_projection_non_altera_una_selezione_esplicita():
    projection = {"_id": 0, "id": 1, "pdf_data": 1}
    assert metadata_projection(COLL_CEDOLINI, projection) == projection
