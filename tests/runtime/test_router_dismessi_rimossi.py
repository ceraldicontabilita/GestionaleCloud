"""Un router dismesso non deve sopravvivere negli import o nei soli test.

La bonifica riguarda solo i moduli qui elencati, non gli export dei domini
vivi, la riconciliazione bancaria canonica o il servizio trattenute.
"""
from pathlib import Path

import pytest

from tests.runtime.test_moduli_mai_importati import RADICE, _importati, _sorgenti

RIMOSSI = (
    "app/routers/reports/report_pdf.py",
    "app/routers/reports/simple_exports.py",
    "app/routers/batch_operations.py",
    "app/routers/trattenute_verbali.py",
)


@pytest.mark.parametrize("relativo", RIMOSSI)
def test_il_router_dismesso_non_ricompare(relativo):
    assert not (RADICE / relativo).exists(), (
        f"{relativo}: usare il dominio canonico, non ripristinare il router dismesso"
    )


def test_nessun_import_residuo_dei_router_dismessi():
    importati = _importati(_sorgenti())
    moduli = {".".join(Path(p).with_suffix("").parts) for p in RIMOSSI}
    residui = sorted(
        nome for nome in importati
        if any(nome == modulo or nome.startswith(modulo + ".") for modulo in moduli)
    )
    assert not residui, f"Import residui verso router rimossi: {residui}"


def test_reports_carica_solo_la_dashboard_attiva():
    from app.routers import reports

    assert reports.__all__ == ["dashboard"]
    assert reports.dashboard.router.routes
    assert not hasattr(reports, "report_pdf")
    assert not hasattr(reports, "simple_exports")


def test_il_servizio_trattenute_vivo_resta_disponibile():
    from app.services.trattenute_verbali_service import verifica_trattenute_retroattiva

    assert callable(verifica_trattenute_retroattiva)
