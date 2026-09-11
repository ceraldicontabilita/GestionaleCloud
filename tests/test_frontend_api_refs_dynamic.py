from scripts.frontend_api_refs import file_api_refs, frontend_api_refs
from scripts.audit_frontend_backend_contract import (
    main_routes,
    normalize_path,
    page_catalog_audit,
)


def test_preserva_slot_encode_uri_component_completo():
    refs = file_api_refs("fetch(`/api/download/${encodeURIComponent(fileId)}`)")
    assert "/api/download/${encodeURIComponent(fileId)}" in refs
    assert normalize_path(next(iter(refs))) == "/api/download/*"


def test_preserva_slot_template_condizionale_completo():
    refs = file_api_refs("api.post(`/api/agenti/decisioni/${id}/${approva ? 'approva' : 'rifiuta'}`)")
    assert "/api/agenti/decisioni/${id}/${approva ? 'approva' : 'rifiuta'}" in refs
    assert normalize_path(next(iter(refs))) == "/api/agenti/decisioni/*/*"


def test_inventario_esclude_file_test_e_spec(tmp_path):
    (tmp_path / "runtime.jsx").write_text("api.get('/api/runtime')", encoding="utf-8")
    (tmp_path / "runtime.test.jsx").write_text(
        "expect(source).not.toContain('/api/non-chiamare')", encoding="utf-8"
    )
    (tmp_path / "legacy.spec.js").write_text("api.get('/api/spec-only')", encoding="utf-8")
    tests_dir = tmp_path / "__tests__"
    tests_dir.mkdir()
    (tests_dir / "fixture.js").write_text("api.get('/api/fixture')", encoding="utf-8")

    assert frontend_api_refs(str(tmp_path)) == {"/api/runtime"}


def test_route_react_dinamica_viene_censita_come_forma_esatta():
    exact, _wildcard = main_routes()
    assert normalize_path('/verbali-noleggio/:identificativo') in exact


def test_catalogo_non_segnala_il_dettaglio_verbale_come_orfano():
    errors, warnings, _count = page_catalog_audit()
    assert not errors
    assert not [item for item in warnings if '/verbali-noleggio/' in item]
