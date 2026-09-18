from app.routers import fatture_module, operazioni_module, batch_operations, openapi_it, prima_nota_module
from app.routers.operazioni_module import smart


def _paths(router):
    return {route.path for route in router.routes}


def test_mass_repair_and_auto_reconciliation_routes_are_disabled():
    assert "/auto-ricostruisci-dati" not in _paths(fatture_module.router)
    assert "/smart/riconcilia-auto" not in _paths(operazioni_module.router)
    assert "/smart/riconcilia-auto/status" not in _paths(operazioni_module.router)
    assert "/smart/associa-stipendi-auto" not in _paths(operazioni_module.router)
    assert "/auto-riconcilia-tutto" not in _paths(batch_operations.router)
    assert "/aisp/riconcilia-automatica" not in _paths(openapi_it.router)
    assert "/auto-ricostruisci-dati" not in _paths(fatture_module.router)
    assert "/salari/auto-ricostruisci-dati" not in _paths(prima_nota_module.router)


def test_automatic_reconciliation_worker_is_not_callable():
    assert not hasattr(smart, "riconcilia_automatico")
    assert not hasattr(smart, "avvia_riconciliazione_automatica")
    assert not hasattr(smart, "stato_riconciliazione_automatica")
