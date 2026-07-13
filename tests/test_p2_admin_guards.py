"""P2 §12 — Gli endpoint distruttivi di migrazione/manutenzione richiedono il ruolo
ADMIN (dependency get_current_admin_user). Prima erano aperti/senza controllo ruolo."""
from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.router_registry import register_all_routers
from app.utils.dependencies import get_current_admin_user


def _app():
    app = FastAPI()
    register_all_routers(app)
    return app


def _route_ha_admin(app, path_frag, metodo):
    for r in app.routes:
        if isinstance(r, APIRoute) and path_frag in r.path and metodo in r.methods:
            deps = [d.call for d in r.dependant.dependencies]
            # cerca ricorsivamente get_current_admin_user tra le dipendenze
            trovate = _raccogli_dipendenze(r.dependant)
            return get_current_admin_user in trovate
    return None


def _raccogli_dipendenze(dependant):
    out = set()
    for d in dependant.dependencies:
        if d.call:
            out.add(d.call)
        out |= _raccogli_dipendenze(d)
    return out


def test_endpoint_distruttivi_sono_admin_only():
    app = _app()
    casi = [
        ("/reset-learning", "DELETE"),
        ("/reset-dizionario", "DELETE"),
        ("/force-reimport", "POST"),
        ("/reimporta-da-filesystem", "POST"),
        ("/cleanup-orphan-movements", "POST"),
        ("/migrazione-pulisci-bancari-cassa", "POST"),
    ]
    for frag, metodo in casi:
        res = _route_ha_admin(app, frag, metodo)
        assert res is True, f"{metodo} {frag}: manca la guardia admin (res={res})"
