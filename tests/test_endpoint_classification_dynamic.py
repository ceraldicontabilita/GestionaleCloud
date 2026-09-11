from __future__ import annotations

from scripts.genera_classificazione_endpoint import _fe_match, _norm, frontend_refs


def test_suffix_template_query_non_rende_endpoint_inutilizzato():
    refs = {_norm(ref) for ref in frontend_refs()}

    assert _fe_match('/api/agenti/run', refs)
    assert _fe_match('/api/fatture-ricevute/statistiche', refs)
    assert _fe_match('/api/iva/ricalcola-attribuzione', refs)
    assert _fe_match('/api/noleggio/fatture-non-associate', refs)
    assert _fe_match('/api/noleggio/riepilogo-controlli', refs)


def test_prefisso_non_prova_uso_endpoint_figlio():
    refs = {_norm('/api/esempio')}

    assert _fe_match('/api/esempio', refs)
    assert not _fe_match('/api/esempio/dettaglio', refs)


def test_parametri_dinamici_restano_compatibili_per_segmento():
    refs = {_norm('/api/fatture/${encodeURIComponent(id)}')}

    assert _fe_match('/api/fatture/{fattura_id}', refs)
    assert not _fe_match('/api/fatture/{fattura_id}/pdf', refs)
