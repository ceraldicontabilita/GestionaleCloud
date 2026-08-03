"""Genera le mappe autoritative del backend leggendo la route table REALE
(app.router_registry) e incrociandola con l'uso nel frontend.

Produce:
- memoria/MAPPA_ROUTER.md          → un prefisso per riga (route, FE, file)
- memoria/MAPPA_ENDPOINT_COMPLETA.md → ogni endpoint (metodo, path, FE)

Uso: python scripts/genera_mappa.py
La mappa è RIGENERABILE: non modificarla a mano, rilancia lo script.
"""
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.getcwd())

from fastapi import FastAPI  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402
from app.router_registry import register_all_routers  # noqa: E402

DATA_GEN = "rigenerata via scripts/genera_mappa.py"


def build_app():
    app = FastAPI()
    register_all_routers(app)
    return app


def frontend_refs():
    refs = set()
    for root, _, files in os.walk("frontend/src"):
        for f in files:
            if f.endswith((".js", ".jsx", ".ts", ".tsx")):
                txt = open(os.path.join(root, f), encoding="utf-8", errors="ignore").read()
                for m in re.findall(r"/api/[a-zA-Z0-9_\-/${}.]+", txt):
                    refs.add(m)

    def norm(p):
        p = re.sub(r"\$\{[^}]*\}", ":x", p)
        p = re.sub(r"\{[^}]*\}", ":x", p)
        p = re.sub(r":[a-zA-Z_]+", ":x", p)
        return p.rstrip("/")

    return set(norm(x) for x in refs)


# prefissi con chiamanti ESTERNI legittimi (app collegate, webhook, chatbot,
# scheduler): "non nel FE" non significa morto.
EXTERNAL = ("/api/erp/", "/api/public", "/api/f24-public", "/api/openapi",
            "/api/whatsapp", "/api/auth", "/api/legal", "/api/ai-parser",
            "/api/agenti", "/api/v1/", "/api/portal", "/api/paypal-api/webhook",
            "/data-deletion", "/privacy", "/terms")


def fe_flag(path, fe):
    if any(path.startswith(x) for x in EXTERNAL):
        return "ext"
    n = re.sub(r"\{[^}]*\}", ":x", path).rstrip("/")
    if n in fe:
        return "✓"
    for f in fe:
        if len(f) > len("/api/x") and (f.startswith(n) or n.startswith(f)):
            return "✓"
    return "—"


def module_of(route):
    ep = route.endpoint
    return getattr(ep, "__module__", "?").replace("app.routers.", "")


def main():
    app = build_app()
    fe = frontend_refs()

    routes = []
    for r in app.routes:
        if isinstance(r, APIRoute):
            methods = ",".join(sorted(m for m in r.methods if m not in ("HEAD", "OPTIONS")))
            tag = r.tags[0] if r.tags else "(no tag)"
            routes.append({
                "tag": tag, "path": r.path, "methods": methods,
                "module": module_of(r), "fe": fe_flag(r.path, fe),
            })

    # ---- prefisso a due livelli /api/<x> ----
    def prefix2(p):
        parts = p.strip("/").split("/")
        if parts and parts[0] == "api":
            return "/api/" + (parts[1] if len(parts) > 1 else "")
        return "/" + (parts[0] if parts else "")

    by_prefix = defaultdict(list)
    for r in routes:
        by_prefix[prefix2(r["path"])].append(r)

    # ---- MAPPA_ROUTER.md ----
    lines = ["# MAPPA ROUTER — GestionaleCloud", ""]
    lines.append(f"> {DATA_GEN} — leggendo la route table reale di `register_all_routers`.")
    lines.append(f"> Totale **{len(routes)} endpoint** in **{len(by_prefix)} prefissi**.")
    lines.append("")
    lines.append("Colonna FE: `✓` prefisso usato dal frontend · `ext` chiamante esterno "
                 "(app collegata / webhook / chatbot / scheduler / API pubblica) · "
                 "`—` nessun riferimento noto (candidato verifica).")
    lines.append("")
    lines.append("| Prefisso | Endpoint | FE | Moduli (file router) |")
    lines.append("|---|---:|:-:|---|")
    for pref in sorted(by_prefix):
        rs = by_prefix[pref]
        mods = sorted(set(r["module"] for r in rs))
        # FE riepilogo del prefisso
        flags = set(r["fe"] for r in rs)
        flag = "✓" if "✓" in flags else ("ext" if "ext" in flags else "—")
        lines.append(f"| `{pref}` | {len(rs)} | {flag} | {', '.join(mods)} |")
    open("memoria/MAPPA_ROUTER.md", "w", encoding="utf-8").write("\n".join(lines) + "\n")

    # ---- MAPPA_ENDPOINT_COMPLETA.md ----
    by_tag = defaultdict(list)
    for r in routes:
        by_tag[r["tag"]].append(r)
    out = ["# MAPPA ENDPOINT COMPLETA — GestionaleCloud", ""]
    out.append(f"> {DATA_GEN}. Ogni endpoint REALMENTE montato, per gruppo (tag).")
    out.append(f"> Totale **{len(routes)} endpoint** in **{len(by_tag)} gruppi**.")
    out.append("> FE: `✓` usato dal frontend · `ext` chiamante esterno · `—` nessun riferimento noto.")
    out.append("")
    n_fe = sum(1 for r in routes if r["fe"] == "✓")
    n_ext = sum(1 for r in routes if r["fe"] == "ext")
    n_no = sum(1 for r in routes if r["fe"] == "—")
    out.append(f"**Riepilogo uso:** ✓ frontend = {n_fe} · ext esterni = {n_ext} · — da verificare = {n_no}")
    out.append("")
    for tag in sorted(by_tag):
        rs = by_tag[tag]
        out.append(f"## {tag}  ({len(rs)})")
        out.append("")
        out.append("| Metodo | Path | FE | File |")
        out.append("|---|---|:-:|---|")
        for r in sorted(rs, key=lambda x: x["path"]):
            out.append(f"| {r['methods']} | `{r['path']}` | {r['fe']} | {r['module']} |")
        out.append("")
    open("memoria/MAPPA_ENDPOINT_COMPLETA.md", "w", encoding="utf-8").write("\n".join(out) + "\n")

    print(f"OK — {len(routes)} endpoint, {len(by_prefix)} prefissi, {len(by_tag)} tag")
    print(f"FE ✓={n_fe}  ext={n_ext}  —={n_no}")


if __name__ == "__main__":
    main()
