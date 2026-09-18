"""Il report architetturale deve restare eseguibile mentre il debito cala."""
from scripts.audit_architettura import collect


def test_audit_statico_analizza_tutto_il_backend_senza_errori_di_parse():
    report = collect()
    assert report["python_files"] > 0
    assert report["router_files"] > 0
    assert report["routes"] > 0
    assert report["parse_errors"] == []
