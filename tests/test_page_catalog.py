"""Guardie sul catalogo pagina -> route -> componente.

Il server frontend restituisce ``index.html`` anche per URL inesistenti. Un
semplice HTTP 200 non e quindi un collaudo di pagina. Questi test verificano la
raggiungibilita nel grafo React prima che il runtime smoke apra le route.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "page_catalog.json").read_text(encoding="utf-8"))
PAGES = CATALOG["pages"]
MAIN = (ROOT / "frontend/src/main.jsx").read_text(encoding="utf-8")


def test_catalogo_contiene_esattamente_le_66_schermate_numerate():
    assert [page["id"] for page in PAGES] == list(range(1, 67))
    assert len({page["path"] for page in PAGES}) == 66
    assert all(page["audit_status"] in {"unverified", "in_review", "verified"} for page in PAGES)


def test_ogni_schermata_ha_un_componente_raggiungibile_dal_suo_entrypoint():
    for page in PAGES:
        component = ROOT / page["component"]
        entry = ROOT / page["entry"]
        assert component.is_file(), f"Pagina {page['id']}: componente assente {component}"
        assert entry.is_file(), f"Pagina {page['id']}: entrypoint assente {entry}"

        if component != entry:
            component_name = component.name
            entry_source = entry.read_text(encoding="utf-8")
            assert component_name in entry_source, (
                f"Pagina {page['id']} {page['path']}: {component_name} non e importato "
                f"da {entry.relative_to(ROOT)}"
            )


def test_ogni_hub_del_catalogo_e_importato_dal_router_principale():
    for page in PAGES:
        entry = ROOT / page["entry"]
        if entry.name == "main.jsx":
            continue
        assert entry.name in MAIN, (
            f"Pagina {page['id']} {page['path']}: hub {entry.name} non importato da main.jsx"
        )


def test_ogni_componente_lazy_degli_hub_e_nel_catalogo():
    """Impedisce che una nuova sottopagina resti fuori dal collaudo globale.

    Le route principali sono famiglie wildcard: il solo ``main.jsx`` non vede
    le schermate caricate dagli hub. E proprio cosi che Dati ISA era rimasta
    esclusa dal precedente catalogo di 62 pagine.
    """
    componenti_catalogati = {
        (ROOT / page["component"]).resolve()
        for page in PAGES
    }
    hubs = sorted((ROOT / "frontend/src/pages/hub").glob("*Hub.jsx"))
    for hub in hubs:
        source = hub.read_text(encoding="utf-8")
        for relative in re.findall(
            r"lazy\(\(\)\s*=>\s*import\(['\"]([^'\"]+)['\"]\)\)", source
        ):
            component = (hub.parent / relative).resolve()
            assert component in componenti_catalogati, (
                f"{component.relative_to(ROOT)} e caricata da {hub.relative_to(ROOT)} "
                "ma manca da page_catalog.json"
            )


def test_ogni_pagina_lazy_top_level_operativa_e_nel_catalogo():
    """Blocca omissioni come Situazione fiscale dal collaudo globale."""
    componenti_catalogati = {
        (ROOT / page["component"]).resolve()
        for page in PAGES
    }
    main_dir = ROOT / "frontend/src"
    for relative in re.findall(
        r"lazy\(\(\)\s*=>\s*import\(['\"]([^'\"]+)['\"]\)\)", MAIN
    ):
        if "/hub/" in relative or relative.endswith("LegacyRouteResolver.jsx"):
            continue
        component = (main_dir / relative).resolve()
        assert component in componenti_catalogati, (
            f"{component.relative_to(ROOT)} e caricata dal router principale "
            "ma manca da page_catalog.json"
        )


def test_tutte_le_route_del_catalogo_sono_coperte_da_una_route_react_reale():
    exact = {"/", "/login", "/gestione-riservata"}
    wildcard_prefixes: set[str] = set()

    for raw in re.findall(r'path:\s*"([^"]+)"', MAIN):
        if raw == "*" or ":" in raw:
            continue
        path = raw if raw.startswith("/") else f"/{raw}"
        if path.endswith("/*"):
            wildcard_prefixes.add(path[:-2])
        else:
            exact.add(path)

    dynamic_prefixes = {"/verbali-noleggio"}
    for page in PAGES:
        path = page["path"]
        covered = (
            path in exact
            or any(path == prefix or path.startswith(f"{prefix}/") for prefix in wildcard_prefixes)
            or any(path.startswith(f"{prefix}/:") for prefix in dynamic_prefixes)
        )
        assert covered, f"Pagina {page['id']} non raggiungibile dal router React: {path}"


def test_vecchie_url_non_vengono_piu_spacciate_per_schermate_canoniche():
    paths = {page["path"] for page in PAGES}
    assert paths.isdisjoint({"/magazzino", "/dipendenti", "/cedolini"})


def test_il_prompt_master_e_il_catalogo_macchina_non_divergono():
    report = (ROOT / "PROMPT_MASTER.md").read_text(encoding="utf-8")
    rows = re.findall(
        r"^(\d+)\. \*\*[^*]+\*\* — `([^`]+)` — accesso ",
        report,
        flags=re.MULTILINE,
    )
    documented = {int(identifier): path for identifier, path in rows}
    assert len(documented) == 66
    assert documented == {page["id"]: page["path"] for page in PAGES}
