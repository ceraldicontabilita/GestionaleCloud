"""
Audit React — audit canonico Fase C (deliverable 1 e 7).

Genera memoria/AUDIT_REACT.md con:
1. Elenco completo delle route React (da frontend/src/main.jsx): path,
   componente/redirect.
2. Componenti/pagine/moduli mai importati da nessun altro file (candidati
   codice morto). L'entry point (main.jsx) e i file di configurazione
   noti sono esclusi.

Uso:  python scripts/audit_react.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "frontend" / "src"
DEST = ROOT / "memoria" / "AUDIT_REACT.md"

ENTRY = {"main.jsx", "App.jsx"}


def elenco_route():
    """Estrae le route da main.jsx (path + elemento)."""
    text = (SRC / "main.jsx").read_text()
    route = []
    for m in re.finditer(
        r"""\{\s*(?:path:\s*["']([^"']+)["']|(index):\s*true)\s*,\s*element:\s*(.+?)\s*\}""",
        text,
    ):
        path = m.group(1) or "(index)"
        elem = re.sub(r"\s+", " ", m.group(3))
        elem = re.sub(r"</?LazyPage>", "", elem).strip()
        # riassumi
        nav = re.search(r'Navigate\s+to="([^"]+)"', elem)
        comp = re.search(r"<([A-Z][A-Za-z0-9]*)", elem)
        if nav:
            route.append((path, f"redirect → {nav.group(1)}"))
        elif comp:
            route.append((path, comp.group(1)))
        else:
            route.append((path, elem[:60]))
    return route


def moduli_non_importati():
    """File .jsx/.js in src mai importati da nessun altro file."""
    files = [
        f for f in SRC.rglob("*.js*")
        if "node_modules" not in f.parts and f.suffix in (".js", ".jsx")
    ]
    tutti_testi = {f: f.read_text(errors="replace") for f in files}

    # nomi base importabili: 'X' matcha "from './X'" / "from '../pages/X.jsx'" / import('..../X.jsx')
    orfani = []
    for f in files:
        rel = f.relative_to(SRC)
        if rel.name in ENTRY:
            continue
        stem = f.stem
        if stem == "index":
            # un barrel index.js e' importato come la sua cartella
            stem = f.parent.name
        pattern = re.compile(
            r"""(?:from\s*["'][^"']*[/]""" + re.escape(stem) + r"""(?:\.jsx?)?["'])"""
            r"""|(?:import\(\s*["'][^"']*[/]""" + re.escape(stem) + r"""(?:\.jsx?)?["']\s*\))"""
        )
        usato = any(
            g is not f and pattern.search(t)
            for g, t in tutti_testi.items()
        )
        if not usato:
            orfani.append(str(rel))
    return sorted(orfani)


def main():
    route = elenco_route()
    orfani = moduli_non_importati()

    righe = ["# Audit React — route e componenti\n"]
    righe.append("Generato da `scripts/audit_react.py`.\n")
    righe.append(f"## Route React ({len(route)})\n")
    righe.append("| Path | Componente / redirect |")
    righe.append("|---|---|")
    for p, e in route:
        righe.append(f"| `{p}` | {e} |")
    righe.append("")
    righe.append(f"## Moduli mai importati ({len(orfani)}) — candidati codice morto\n")
    righe.append("Verificare a mano prima di rimuovere (import dinamici non standard).\n")
    for o in orfani:
        righe.append(f"- `frontend/src/{o}`")
    righe.append("")

    DEST.write_text("\n".join(righe))
    print(f"Route: {len(route)}   Moduli orfani: {len(orfani)}")
    print(f"Scritto {DEST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
