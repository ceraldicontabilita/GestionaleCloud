"""
Estrattore matrice API — audit canonico Fase C.

Produce memoria/AUDIT_MATRICE_DATI.json con:
- backend: tutte le route FastAPI registrate (metodo, path, tag, file, funzione)
- frontend: tutte le chiamate /api/... trovate in frontend/src (file, riga, metodo, path)
- incrocio: endpoint orfani (mai chiamati dal frontend) e chiamate rotte
  (il frontend chiama un path che il backend non espone)

L'incrocio normalizza i parametri: /api/x/{id} combacia con /api/x/${...},
/api/x/123, ecc. Gli endpoint orfani NON sono automaticamente eliminabili:
possono essere usati da scheduler, chat AI, app esterna (erp_bridge),
webhook o essere API pubbliche. La classificazione finale e' nel report.

Uso:  python scripts/estrai_matrice_api.py
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("SECRET_KEY", "x" * 32)
os.environ.setdefault("DB_NAME", "audit_db")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")


def dump_backend_routes():
    from fastapi.routing import APIRoute
    # Importa l'app REALE (app/main.py), che include sia il registry sia le
    # route dichiarate direttamente (/api/health, /api/ping, lock-status...)
    from app.main import app

    routes = []
    for r in app.routes:
        if not isinstance(r, APIRoute):
            continue
        fn = r.endpoint
        mod = getattr(fn, "__module__", "")
        try:
            import inspect
            src_file = inspect.getsourcefile(fn) or ""
            src_line = inspect.getsourcelines(fn)[1]
        except Exception:
            src_file, src_line = "", 0
        routes.append({
            "path": r.path,
            "methods": sorted(m for m in r.methods if m != "HEAD"),
            "tags": list(r.tags or []),
            "module": mod,
            "file": str(Path(src_file).relative_to(ROOT)) if src_file.startswith(str(ROOT)) else src_file,
            "line": src_line,
            "name": fn.__name__,
        })
    return routes


API_CALL_RE = re.compile(
    r"""(?:api|axios)\s*\.\s*(get|post|put|delete|patch)\s*\(\s*(`[^`]+`|'[^']+'|"[^"]+")""",
    re.X | re.S,
)
FETCH_RE = re.compile(r"""fetch\s*\(\s*(`[^`]*/api/[^`]*`|'[^']*/api/[^']*'|"[^"]*/api/[^"]*")""")


def dump_frontend_calls():
    calls = []
    src = ROOT / "frontend" / "src"
    for f in src.rglob("*.js*"):
        if "node_modules" in f.parts:
            continue
        text = f.read_text(errors="replace")
        for m in API_CALL_RE.finditer(text):
            raw = m.group(2)[1:-1]
            calls.append({
                "file": str(f.relative_to(ROOT)),
                "line": text.count("\n", 0, m.start()) + 1,
                "method": m.group(1).upper(),
                "raw": raw,
            })
        for m in FETCH_RE.finditer(text):
            raw = m.group(1)[1:-1]
            contesto = text[m.start():m.start() + 300]
            method = "POST" if re.search(r"method\s*:\s*['\"]POST", contesto) else "GET"
            calls.append({
                "file": str(f.relative_to(ROOT)),
                "line": text.count("\n", 0, m.start()) + 1,
                "method": method,
                "raw": raw,
            })
    return calls


def normalize_frontend(raw: str) -> str:
    """Trasforma una chiamata frontend in un pattern confrontabile."""
    p = raw
    # ${var} attaccato a fine path SENZA slash prima (es. "statistiche${params}")
    # e' quasi sempre una query string costruita a monte ("?anno=..."): via.
    p = re.sub(r"(?<=[\w-])\$\{[^}]*\}$", "", p)
    # template literal ${...} -> {P} (PRIMA del taglio query: un ternario
    # "${a ? 'x' : 'y'}" contiene '?' che non e' una query string)
    p = re.sub(r"\$\{[^}]*\}", "{P}", p)
    # togli query string
    p = p.split("?")[0]
    # concatenazioni troncate tipo '/api/x/' + id: la stringa finisce con /
    if not p.startswith("/"):
        # es. `${API_URL}/api/...` gia' gestito da {P}; path relativi ignorati
        idx = p.find("/api/")
        if idx == -1:
            return ""
        p = p[idx:]
    if not p.startswith("/api"):
        return ""
    # rimuovi slash finale (concatenazione)
    return p


def normalize_backend(path: str) -> str:
    return re.sub(r"\{[^}]*\}", "{P}", path)


def match(calls, routes):
    """Incrocia chiamate frontend e route backend."""
    route_index = {}
    for r in routes:
        norm = normalize_backend(r["path"])
        for m in r["methods"]:
            route_index.setdefault((m, norm), []).append(r)

    # indicizza anche per prefisso (per path costruiti dinamicamente)
    def find_route(method, norm_call):
        if (method, norm_call) in route_index:
            return route_index[(method, norm_call)], "esatto"
        # tolleranza: segmento variabile frontend {P} puo' coprire piu' segmenti
        # o il backend puo' avere piu' parametri: confronto segmento a segmento
        cand = []
        cseg = norm_call.strip("/").split("/")
        for (m, rnorm), rs in route_index.items():
            if m != method:
                continue
            rseg = rnorm.strip("/").split("/")
            if len(rseg) != len(cseg):
                continue
            ok = all(a == b or a == "{P}" or b == "{P}" for a, b in zip(cseg, rseg))
            if ok:
                cand.extend(rs)
        if cand:
            return cand, "parametrico"
        return [], ""

    chiamate_rotte = []
    endpoint_usati = set()
    for c in calls:
        norm = normalize_frontend(c["raw"])
        if not norm:
            continue
        c["norm"] = norm
        found, kind = find_route(c["method"], norm)
        if found:
            for r in found:
                endpoint_usati.add((tuple(r["methods"]), r["path"]))
            c["match"] = kind
        else:
            c["match"] = "NESSUNO"
            chiamate_rotte.append(c)

    orfani = [
        r for r in routes
        if (tuple(r["methods"]), r["path"]) not in endpoint_usati
    ]
    return chiamate_rotte, orfani


def main():
    routes = dump_backend_routes()
    calls = dump_frontend_calls()
    rotte, orfani = match(calls, routes)

    out = {
        "totale_endpoint_backend": len(routes),
        "totale_chiamate_frontend": len(calls),
        "endpoint_backend": routes,
        "chiamate_frontend": calls,
        "chiamate_rotte": rotte,
        "endpoint_orfani": orfani,
        "n_chiamate_rotte": len(rotte),
        "n_endpoint_orfani": len(orfani),
    }
    dest = ROOT / "memoria" / "AUDIT_MATRICE_DATI.json"
    dest.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"Endpoint backend:   {len(routes)}")
    print(f"Chiamate frontend:  {len(calls)}")
    print(f"Chiamate ROTTE:     {len(rotte)}")
    print(f"Endpoint orfani:    {len(orfani)}")
    print(f"Scritto: {dest.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
