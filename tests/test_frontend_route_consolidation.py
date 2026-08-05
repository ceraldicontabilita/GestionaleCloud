from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"


def _read(relative_path: str) -> str:
    return (FRONTEND / relative_path).read_text(encoding="utf-8")


def test_router_registra_famiglie_canoniche_non_140_alias():
    source = _read("main.jsx")
    # Sono comprese login, root e 404: le varianti anno/mese/tab sono gestite
    # dagli hub tramite wildcard e non devono tornare a moltiplicare le route.
    assert source.count("path:") <= 35
    for canonical in (
        'path: "contabilita/*"',
        'path: "riconciliazione/*"',
        'path: "documenti/*"',
        'path: "strumenti/*"',
        'path: "iva/*"',
    ):
        assert canonical in source
    assert 'path: "bilancio/:anno"' not in source
    assert 'path: "scadenze/:anno/:mese"' not in source


def test_iva_ha_una_sola_pagina_operativa():
    gestione_iva = _read("pages/GestioneIVA.jsx")
    scadenze = _read("pages/Scadenze.jsx")
    verifica = _read("pages/VerificaCoerenza.jsx")

    assert "ConfrontoIvaCommercialista" in gestione_iva
    assert "ScadenzeIvaMensili" in gestione_iva
    assert "/api/scadenze/iva-mensile/" in gestione_iva
    assert "/api/verifica-coerenza/confronto-iva-completo/" in gestione_iva
    assert "/api/scadenze/iva-mensile/" not in scadenze
    assert "activeTab === 'iva'" not in verifica
    assert "IVA Mensile" not in verifica


def test_prima_nota_non_monta_pagina_provvisori_duplicata():
    hub = _read("pages/hub/PrimaNotaHub.jsx")
    assert "DatiProvvisoriPage" not in hub
    assert not (FRONTEND / "pages/DatiProvvisoriPage.jsx").exists()
    assert "sezione === 'provvisori'" in _read("pages/PrimaNota.jsx")
