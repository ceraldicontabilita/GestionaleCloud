from scripts.frontend_api_refs import file_api_refs
from scripts.audit_frontend_backend_contract import normalize_path


def test_preserva_slot_encode_uri_component_completo():
    refs = file_api_refs("fetch(`/api/download/${encodeURIComponent(fileId)}`)")
    assert "/api/download/${encodeURIComponent(fileId)}" in refs
    assert normalize_path(next(iter(refs))) == "/api/download/*"


def test_preserva_slot_template_condizionale_completo():
    refs = file_api_refs("api.post(`/api/agenti/decisioni/${id}/${approva ? 'approva' : 'rifiuta'}`)")
    assert "/api/agenti/decisioni/${id}/${approva ? 'approva' : 'rifiuta'}" in refs
    assert normalize_path(next(iter(refs))) == "/api/agenti/decisioni/*/*"
