"""
Verità unica dei report endpoint (Piano residuo §P0.1): la route table
REALE (app.router_registry) e i documenti generati da
scripts/genera_mappa.py / scripts/genera_classificazione_endpoint.py
devono sempre dichiarare lo stesso numero di endpoint. Se questo test
fallisce, i documenti sono stati modificati a mano o non rigenerati dopo
un cambio di route: rilanciare gli script prima di committare.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI  # noqa: E402
from app.router_registry import register_all_routers  # noqa: E402
from tests.route_table import elenco_route  # noqa: E402

MEMORIA = os.path.join(os.path.dirname(__file__), "..", "memoria")


def _totale_route_reale():
    """Endpoint realmente montati (enumerazione condivisa in route_table)."""
    app = FastAPI()
    register_all_routers(app)
    return len(elenco_route(app))


def _leggi_totale(nome_file, pattern):
    path = os.path.join(MEMORIA, nome_file)
    with open(path, encoding="utf-8") as f:
        testo = f.read()
    m = re.search(pattern, testo)
    assert m, f"Pattern totale non trovato in {nome_file}"
    return int(m.group(1))


def test_mappa_router_coerente_con_route_table_reale():
    totale_reale = _totale_route_reale()
    totale_mappa = _leggi_totale("MAPPA_ROUTER.md", r"Totale \*\*(\d+) endpoint\*\*")
    assert totale_mappa == totale_reale, (
        f"MAPPA_ROUTER.md dichiara {totale_mappa} endpoint ma la route table "
        f"reale ne monta {totale_reale}: rilancia `python scripts/genera_mappa.py`"
    )


def test_mappa_endpoint_completa_coerente_con_route_table_reale():
    totale_reale = _totale_route_reale()
    totale_mappa = _leggi_totale(
        "MAPPA_ENDPOINT_COMPLETA.md", r"Totale \*\*(\d+) endpoint\*\*"
    )
    assert totale_mappa == totale_reale, (
        f"MAPPA_ENDPOINT_COMPLETA.md dichiara {totale_mappa} endpoint ma la "
        f"route table reale ne monta {totale_reale}: rilancia "
        "`python scripts/genera_mappa.py`"
    )


def test_endpoint_classificazione_coerente_con_route_table_reale():
    totale_reale = _totale_route_reale()
    totale_classificazione = _leggi_totale(
        "ENDPOINT_CLASSIFICAZIONE_FINALE.md", r"\*\*Totale endpoint:\*\* (\d+)"
    )
    assert totale_classificazione == totale_reale, (
        f"ENDPOINT_CLASSIFICAZIONE_FINALE.md dichiara {totale_classificazione} "
        f"endpoint ma la route table reale ne monta {totale_reale}: rilancia "
        "`python scripts/genera_classificazione_endpoint.py`"
    )


def test_endpoint_classificazione_somma_categorie_coerente():
    path = os.path.join(MEMORIA, "ENDPOINT_CLASSIFICAZIONE_FINALE.md")
    with open(path, encoding="utf-8") as f:
        testo = f.read()
    m = re.search(
        r"\*\*Totale endpoint:\*\* (\d+) · tenere: (\d+) · verificare: (\d+) · "
        r"admin-only \(migrazione/manutenzione\): (\d+)",
        testo,
    )
    assert m, "Riga di riepilogo non trovata in ENDPOINT_CLASSIFICAZIONE_FINALE.md"
    totale, tenere, verificare, admin = (int(g) for g in m.groups())
    assert tenere + verificare + admin == totale, (
        "In ENDPOINT_CLASSIFICAZIONE_FINALE.md le categorie "
        f"(tenere={tenere} + verificare={verificare} + admin-only={admin}) "
        f"non sommano al totale dichiarato ({totale})"
    )
