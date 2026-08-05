from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_indici_join_piano_conti_creati_allavvio():
    source = (ROOT / "app" / "database.py").read_text(encoding="utf-8")
    assert "idx_dizionario_descrizione" in source
    assert "idx_invoices_invoice_date" in source


def test_frontend_non_duplica_il_calcolo_dei_saldi():
    source = (ROOT / "frontend" / "src" / "pages" / "PianoDeiConti.jsx").read_text(
        encoding="utf-8"
    )
    assert "buildBalanceSummary(groupedConti)" in source
    assert "api.get(`/api/piano-conti/bilancio?anno=${annoGlobale}`)" not in source
