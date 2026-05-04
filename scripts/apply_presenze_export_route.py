#!/usr/bin/env python3
"""
Applica in modo idempotente la rotta React per la pagina Export Presenze Consulente.

Modifica solo frontend/src/main.jsx:
- aggiunge lazy import HRPresenzeExport;
- aggiunge route /presenze/export prima delle route dinamiche /presenze/:dipendente.

Non tocca HRPresenze.jsx.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "frontend" / "src" / "main.jsx"

IMPORT_ANCHOR = 'const DipendentiHub = lazy(() => import("./pages/hr/HRPresenze.jsx"));\n'
IMPORT_LINE = 'const HRPresenzeExport = lazy(() => import("./pages/hr/HRPresenzeExport.jsx"));\n'
ROUTE_ANCHOR = '      { path: "presenze", element: <LazyPage><DipendentiHub /></LazyPage> },\n'
ROUTE_LINE = '      { path: "presenze/export", element: <LazyPage><HRPresenzeExport /></LazyPage> },\n'


def main() -> int:
    text = MAIN.read_text(encoding="utf-8")
    original = text

    if IMPORT_LINE not in text:
        if IMPORT_ANCHOR not in text:
            raise SystemExit("Anchor import DipendentiHub non trovato in frontend/src/main.jsx")
        text = text.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT_LINE, 1)

    if ROUTE_LINE not in text:
        if ROUTE_ANCHOR not in text:
            raise SystemExit("Anchor route presenze non trovato in frontend/src/main.jsx")
        text = text.replace(ROUTE_ANCHOR, ROUTE_ANCHOR + ROUTE_LINE, 1)

    if text == original:
        print("[OK] Route /presenze/export gia' presente")
        return 0

    MAIN.write_text(text, encoding="utf-8")
    print("[FIX] Aggiunta route /presenze/export in frontend/src/main.jsx")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
