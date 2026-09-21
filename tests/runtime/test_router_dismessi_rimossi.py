"""Il codice dismesso non sopravvive negli import o nei soli test.

Preserva export dei domini vivi, riconciliazione bancaria e servizio
trattenute. Il filtro del batch dismesso non diventa un servizio orfano.
"""
from pathlib import Path

import pytest

from tests.runtime.test_moduli_mai_importati import RADICE, _importati, _sorgenti

RIMOSSI = (
    "app/routers/reports/report_pdf.py",
    "app/routers/reports/simple_exports.py",
    "app/routers/batch_operations.py",
    "app/routers/trattenute_verbali.py",
    "app/services/riconciliazione_filters.py",
)


@pytest.mark.parametrize("relativo", RIMOSSI)
def test_il_componente_dismesso_non_ricompare(relativo):
    assert not (RADICE / relativo).exists(), (
        f"{relativo}: usare il dominio vivo, non ripristinare codice dismesso"
    )


def test_nessun_import_residuo_dei_componenti_dismessi():
    importati = _importati(_sorgenti())
    moduli = {".".join(Path(p).with_suffix("").parts) for p in RIMOSSI}
    residui = sorted(
        nome for nome in importati
        if any(nome == modulo or nome.startswith(modulo + ".") for modulo in moduli)
    )
    assert not residui, f"Import residui verso componenti rimossi: {residui}"


def test_reports_carica_solo_la_dashboard_attiva():
    from app.routers import reports

    assert reports.__all__ == ["dashboard"]
    assert reports.dashboard.router.routes
    assert not hasattr(reports, "report_pdf")
    assert not hasattr(reports, "simple_exports")


def test_il_servizio_trattenute_vivo_resta_disponibile():
    from app.services.trattenute_verbali_service import verifica_trattenute_retroattiva

    assert callable(verifica_trattenute_retroattiva)
