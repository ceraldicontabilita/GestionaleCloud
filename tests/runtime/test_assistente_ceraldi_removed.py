from fastapi import FastAPI

from app.router_registry import register_all_routers
from tests.route_table import elenco_route


def test_api_assistente_ceraldi_non_e_piu_montata():
    app = FastAPI()
    register_all_routers(app)

    paths = {route.path.rstrip("/") for route in elenco_route(app)}
    assert not any(path.startswith("/api/assistente") for path in paths)
