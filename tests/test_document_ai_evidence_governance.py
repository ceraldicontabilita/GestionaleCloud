from pathlib import Path

from app.routers import document_ai


def test_ai_success_is_probable_not_verified():
    result = document_ai._attach_ai_evidence_status({
        "structured_data": {"success": True, "data": {"totale": 10}}
    })
    assert result["evidence_status"] == "probabile"
    assert result["review_required"] is True


def test_ai_explicit_error_is_conflict():
    result = document_ai._attach_ai_evidence_status({
        "structured_data": {"success": False, "error": "schema non coerente"}
    })
    assert result["evidence_status"] == "conflitto"


def test_ai_router_non_scrive_piu_direttamente_nei_registri_operativi():
    source = Path("app/routers/document_ai.py").read_text(encoding="utf-8")
    assert "save_extracted_data_to_gestionale" not in source
    assert source.count("save_to_gestionale=False") >= 2
    assert "blocked_pending_review" in source
