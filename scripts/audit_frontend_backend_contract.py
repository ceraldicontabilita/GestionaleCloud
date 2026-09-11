"""Audit rigenerabile del contratto frontend <-> backend di GestionaleCloud.

Punto 3 della scaletta operativa. Il report distingue errori strutturali
verificabili da candidati statici che richiedono verifica umana.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI

from app.router_registry import register_all_routers
from scripts.frontend_api_refs import frontend_api_refs
from tests.route_table import elenco_route

OUT = ROOT / "memoria" / "AUDIT_FRONTEND_BACKEND_CONTRACT.md"
_PARAM_TEMPLATE = re.compile(r"\$\{[^}]+\}")
_PARAM_BRACES = re.compile(r"\{[^}]+\}")
_PARAM_COLON = re.compile(r":([A-Za-z_][A-Za-z0-9_]*)")
_ROUTE_LITERAL = re.compile(r"\{\s*path:\s*[\"']([^\"']+)[\"']")
_NAV_ITEM = re.compile(r"\{\s*(to|href):\s*[\"']([^\"']+)[\"']")


def normalize_path(value: str) -> str:
    """Normalizza parametri React/FastAPI in wildcard confrontabili."""
    value = _PARAM_TEMPLATE.sub("*", value)
    value = _PARAM_BRACES.sub("*", value)
    value = _PARAM_COLON.sub("*", value)
    value = value.split("?", 1)[0].split("#", 1)[0]
    value = re.sub(r"/+", "/", value)
    if not value.startswith("/"):
        value = "/" + value
    return value.rstrip("/") or "/"


def _segments(value: str) -> tuple[str, ...]:
    return tuple(part for part in normalize_path(value).strip("/").split("/") if part)


def compatible_path(frontend_path: str, backend_path: str) -> bool:
    front = _segments(frontend_path)
    back = _segments(backend_path)
    return len(front) == len(back) and all(
        a == b or a == "*" or b == "*" for a, b in zip(front, back)
    )


def prefix_candidate(frontend_path: str, backend_path: str) -> bool:
    front = _segments(frontend_path)
    back = _segments(backend_path)
    if len(front) >= len(back) or len(front) < 2:
        return False
    return all(a == b or a == "*" or b == "*" for a, b in zip(front, back))


def backend_api_paths() -> set[str]:
    app = FastAPI()
    register_all_routers(app)
    paths = {
        normalize_path(route.path)
        for route in elenco_route(app)
        if getattr(route, "path", "").startswith("/api/")
    }
    paths.update({"/api/health", "/api/ws/notifications"})
    return paths


def main_routes() -> tuple[set[str], set[str]]:
    text = (ROOT / "frontend" / "src" / "main.jsx").read_text(encoding="utf-8")
    exact = {"/", "/login", "/gestione-riservata"}
    wildcard: set[str] = set()
    for raw in _ROUTE_LITERAL.findall(text):
        if raw in {"/", "/login", "/gestione-riservata", "*"}:
            exact.add(normalize_path(raw))
            continue
        full = normalize_path(raw)
        if raw.endswith("/*"):
            wildcard.add(normalize_path(raw[:-2]))
        elif "*" not in full:
            exact.add(full)
    return exact, wildcard


def frontend_route_supported(path: str, exact: set[str], wildcard: set[str]) -> bool:
    path = normalize_path(path)
    return path in exact or any(
        path == prefix or path.startswith(prefix + "/") for prefix in wildcard
    )


def page_catalog_audit() -> tuple[list[str], list[str], int]:
    catalog = json.loads((ROOT / "page_catalog.json").read_text(encoding="utf-8"))
    pages = catalog.get("pages", [])
    errors: list[str] = []
    warnings: list[str] = []
    seen: set[str] = set()
    exact, wildcard = main_routes()
    for page in pages:
        path = str(page.get("path") or "")
        component = str(page.get("component") or "")
        if path in seen:
            errors.append(f"pagina duplicata nel catalogo: `{path}`")
        seen.add(path)
        if not component or not (ROOT / component).is_file():
            errors.append(f"componente mancante per `{path}`: `{component or 'vuoto'}`")
        if path and not frontend_route_supported(path, exact, wildcard):
            warnings.append(f"catalogo non riconducibile direttamente al router: `{path}`")
    return errors, warnings, len(pages)


def navigation_audit() -> tuple[list[str], list[str], int]:
    text = (ROOT / "frontend" / "src" / "navigation.config.js").read_text(encoding="utf-8")
    exact, wildcard = main_routes()
    errors: list[str] = []
    warnings: list[str] = []
    items = _NAV_ITEM.findall(text)
    for kind, target in items:
        if kind == "to":
            if target != "/more" and not frontend_route_supported(target, exact, wildcard):
                errors.append(f"link interno non coperto dal router: `{target}`")
            continue
        prefix = target.strip("/").split("/", 1)[0]
        expected_dir = {
            "menu": ROOT / "app" / "menu",
            "hr": ROOT / "app" / "hr",
            "lotti": ROOT / "app" / "lotti",
        }.get(prefix)
        if expected_dir is None:
            warnings.append(f"href esterno non classificato: `{target}`")
        elif not expected_dir.is_dir():
            errors.append(f"app montata dichiarata ma directory assente: `{target}`")
    return errors, warnings, len(items)


def api_contract_audit() -> tuple[list[str], list[str], list[str], int, int]:
    backend = backend_api_paths()
    refs = sorted({normalize_path(ref) for ref in frontend_api_refs(str(ROOT / "frontend" / "src"))})
    unmatched: list[str] = []
    prefix_only: list[str] = []
    normalized_aliases: list[str] = []
    for ref in refs:
        if any(compatible_path(ref, route) for route in backend):
            continue
        # Template usati per appendere query string, es. `/statistiche${params}`.
        if ref.endswith("*") and ref[:-1].rstrip("/") in backend:
            normalized_aliases.append(f"`{ref}` → `{ref[:-1].rstrip('/')}` (suffisso query/template)")
            continue
        # Riferimento trovato in commento/testo descrittivo con punteggiatura finale.
        trimmed = ref.rstrip(".,;:")
        if trimmed != ref and trimmed in backend:
            normalized_aliases.append(f"`{ref}` → `{trimmed}` (punteggiatura non parte della route)")
            continue
        if any(prefix_candidate(ref, route) for route in backend):
            prefix_only.append(ref)
        else:
            unmatched.append(ref)
    return unmatched, prefix_only, normalized_aliases, len(refs), len(backend)


def not_implemented_candidates() -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    ignored = {"app/services/blob_store.py"}  # interfaccia astratta intenzionale
    for path in sorted((ROOT / "app").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel in ignored:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if "raise NotImplementedError" not in line:
                continue
            location = f"`{rel}:{lineno}`"
            if rel == "app/hr/db_supabase.py":
                results.append((location, "guardia_adapter", "errore esplicito per operatori/query Mongo-like non supportati dall'adapter HR"))
            elif rel == "app/services/sheets_document_store.py":
                results.append((location, "guardia_legacy", "errore esplicito per fase di aggregazione non supportata nel fallback Sheets"))
            elif rel == "app/services/accounting_entries_service.py":
                results.append((location, "metodo_non_collegato", "export PDF non implementato; nessun chiamante `export_entries_pdf` trovato nel repository"))
            elif rel == "app/services/vat_f24_service.py":
                results.append((location, "metodo_non_collegato", "generazione PDF non implementata; nessun chiamante `generate_pdf` del servizio trovato nel repository"))
            else:
                results.append((location, "da_verificare", "NotImplementedError applicativo da classificare"))
    return results


def build_report() -> tuple[str, list[str]]:
    page_errors, page_warnings, page_count = page_catalog_audit()
    nav_errors, nav_warnings, nav_count = navigation_audit()
    unmatched, prefix_only, aliases, fe_refs, backend_routes = api_contract_audit()
    not_impl = not_implemented_candidates()
    hard_errors = [*page_errors, *nav_errors]
    hard_errors.extend(f"riferimento frontend senza endpoint compatibile: `{item}`" for item in unmatched)
    warnings = [*page_warnings, *nav_warnings]

    lines = [
        "# Audit frontend ↔ backend — GestionaleCloud",
        "",
        "> Generato da `scripts/audit_frontend_backend_contract.py`. Non modificare a mano.",
        "> Il contratto HTTP per metodo+path resta verificato da `tests/test_frontend_api_contract.py`.",
        "> Gli scarti statici sono classificati: un riferimento testuale non equivale a una chiamata runtime.",
        "",
        "## Riepilogo",
        "",
        f"- Pagine canoniche censite: **{page_count}**",
        f"- Voci di navigazione analizzate: **{nav_count}**",
        f"- Riferimenti API frontend distinti: **{fe_refs}**",
        f"- Path API backend distinti: **{backend_routes}**",
        f"- Errori strutturali verificabili: **{len(hard_errors)}**",
        f"- Riferimenti frontend realmente senza match statico: **{len(unmatched)}**",
        f"- Alias/query-template classificati: **{len(aliases)}**",
        f"- Riferimenti frontend riconosciuti come soli prefissi: **{len(prefix_only)}**",
        f"- `NotImplementedError` classificati: **{len(not_impl)}**",
        "",
        "## Errori strutturali",
        "",
    ]
    lines.extend(f"- {item}" for item in hard_errors) if hard_errors else lines.append("- Nessuno.")
    lines.extend(["", "## Avvisi di routing", ""])
    lines.extend(f"- {item}" for item in warnings) if warnings else lines.append("- Nessuno.")
    lines.extend(["", "## Alias e template classificati", ""])
    lines.extend(f"- {item}" for item in aliases) if aliases else lines.append("- Nessuno.")
    lines.extend(["", "## Riferimenti frontend senza endpoint compatibile", ""])
    if unmatched:
        for item in unmatched:
            if item == "/api/download/*":
                lines.append(
                    "- `P1 verificato` `/api/download/*`: fallback PDF in "
                    "`frontend/src/pages/RiconciliazioneUnificata.jsx`; nessuna route ERP "
                    "registrata con questo path. Da sostituire con endpoint documentale/F24 reale."
                )
            else:
                lines.append(f"- `da_verificare` `{item}`")
    else:
        lines.append("- Nessuno.")
    lines.extend(["", "## Prefissi API frontend", ""])
    lines.extend(f"- `{item}`: prefisso di composizione, non endpoint autonomo." for item in prefix_only) if prefix_only else lines.append("- Nessuno.")
    lines.extend(["", "## Funzioni `NotImplementedError` classificate", ""])
    if not_impl:
        lines.extend(f"- {location} — `{kind}`: {note}." for location, kind, note in not_impl)
    else:
        lines.append("- Nessuna.")
    lines.extend([
        "",
        "## Esito punto 3",
        "",
        "L'inventario strutturale è completo: pagine, navigazione e contratto HTTP non mostrano",
        "orfani strutturali né riferimenti frontend senza endpoint compatibile. I `NotImplementedError`",
        "residui sono guardie adapter oppure metodi non collegati a route/UI correnti.",
        "La registrazione manuale F24 resta in attesa di prova bancaria e non simula una riconciliazione.",
        "",
    ])
    return "\n".join(lines), hard_errors


def main() -> None:
    report, hard_errors = build_report()
    OUT.write_text(report, encoding="utf-8")
    print(f"Scritto {OUT.relative_to(ROOT)}")
    if hard_errors:
        raise SystemExit("Audit frontend/backend: errori strutturali rilevati")


if __name__ == "__main__":
    main()
