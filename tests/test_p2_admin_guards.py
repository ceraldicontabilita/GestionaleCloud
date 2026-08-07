"""P2 §12 — Gli endpoint distruttivi di migrazione/manutenzione richiedono il ruolo
ADMIN (dependency get_current_admin_user). Prima erano aperti/senza controllo ruolo."""
from fastapi import FastAPI

from app.router_registry import register_all_routers
from app.utils.dependencies import get_current_admin_user
from tests.route_table import elenco_route


def _app():
    app = FastAPI()
    register_all_routers(app)
    return app


def _route_ha_admin(app, path_frag, metodo):
    for r in elenco_route(app):
        if path_frag in r.path and metodo in r.methods:
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
        ("/pulizia-pre-anno", "POST"),
        ("/migrazione-pulisci-bancari-cassa", "POST"),
        ("/cleanup-duplicati-forte", "POST"),
        ("/mittenti/migra-legacy", "POST"),
        ("/dizionario-email/reset", "DELETE"),
        ("/inizializza-piano-esteso", "POST"),
        ("/pulizia-duplicati", "POST"),
        ("/backfill-autoroute", "POST"),
        ("/reset-riconciliazione", "POST"),
        # ERP-001 (19/07/2026): scrittura di massa su movimenti_banca,
        # prima richiamabile da qualunque utente autenticato non in sola
        # lettura.
        ("/apply-suggestions", "POST"),
        ("/decisioni/{decision_id}/approva", "POST"),
        ("/decisioni/{decision_id}/rifiuta", "POST"),
        ("/automazioni/ferma", "POST"),
        ("/automazioni/riprendi", "POST"),
    ]
    for frag, metodo in casi:
        res = _route_ha_admin(app, frag, metodo)
        assert res is True, f"{metodo} {frag}: manca la guardia admin (res={res})"
