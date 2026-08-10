from app.main import app
from tests.route_table import elenco_route


def test_endpoint_fiscali_documenti_sono_realmente_montati():
    route = {
        (rotta.path, metodo)
        for rotta in elenco_route(app)
        for metodo in rotta.methods
    }

    attesi = {
        ("/api/documenti/drive/fiscal/status", "GET"),
        ("/api/documenti/drive/fiscal/discover", "POST"),
        ("/api/documenti/drive/fiscal/sync", "POST"),
        ("/api/documenti/tax-codes/status", "GET"),
        ("/api/documenti/tax-codes/sync", "POST"),
        ("/api/fiscal/summary", "GET"),
        ("/api/fiscal/obligations", "GET"),
        ("/api/fiscal/f24-rows", "GET"),
        ("/api/fiscal/f24-documents", "GET"),
        ("/api/fiscal/evidence/{entity_type}/{entity_id}", "GET"),
        ("/api/fiscal/collections", "GET"),
    }

    assert attesi <= route
