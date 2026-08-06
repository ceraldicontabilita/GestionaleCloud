"""Genera memoria/ENDPOINT_CLASSIFICAZIONE_FINALE.md (PROMPT_DEFINITIVO §7).

Legge la route table REALE (app.router_registry) e classifica OGNI endpoint
incrociando l'uso in: frontend, scheduler, chat, app esterna, migrazione/manutenzione,
test. Propone una DECISIONE (tenere/deprecare/eliminare) con motivo.

RIGENERABILE: non modificare l'output a mano, rilancia lo script.
Uso: python scripts/genera_classificazione_endpoint.py
"""
import os
import re
import sys

sys.path.insert(0, os.getcwd())

from fastapi import FastAPI  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402
from app.router_registry import register_all_routers  # noqa: E402

OUT = "memoria/ENDPOINT_CLASSIFICAZIONE_FINALE.md"

# Prefissi prioritari indicati dal prompt §7
PRIORITARI = ["/api/batch", "/api/cedolini", "/api/dati-provvisori", "/api/exports",
              "/api/paghe", "/api/pos-accredito", "/api/report-pdf", "/api/realtime",
              "/api/trattenute-verbali"]

SCHEDULER_DIRS = ["app/services", "app/routers"]
SCHEDULER_HINT = re.compile(r"scheduler|cron|apscheduler|ingest|_orari|batch_reprocess|auto_")
CHAT_HINT = re.compile(r"chat|assistant|ai_engine|chatbot")
MIGRAZIONE_HINT = re.compile(r"migra|cleanup|pulizia|reset|reimport|inizializz|backfill|one[_-]?shot")


def _read(path):
    try:
        return open(path, encoding="utf-8", errors="ignore").read()
    except OSError:
        return ""


def _walk_texts(root, exts):
    for dirpath, _, files in os.walk(root):
        for f in files:
            if f.endswith(exts):
                yield os.path.join(dirpath, f), _read(os.path.join(dirpath, f))


def frontend_refs():
    refs = set()
    for _, txt in _walk_texts("frontend/src", (".js", ".jsx", ".ts", ".tsx")):
        for m in re.findall(r"/api/[a-zA-Z0-9_\-/${}.]+", txt):
            refs.add(m)
    return refs


def _norm(p):
    # normalizza i path param {id} -> * e rimuove trailing slash
    p = re.sub(r"\{[^}]+\}", "*", p)
    return p.rstrip("/") or "/"


def _fe_match(path, fe_norm):
    n = _norm(path)
    # match esatto o per prefisso significativo (almeno 2 segmenti dopo /api)
    for r in fe_norm:
        if r == n or r.startswith(n + "/") or n.startswith(r + "/"):
            return True
    # match sul prefisso a 3 segmenti (/api/x/y)
    segs = n.strip("/").split("/")
    if len(segs) >= 3:
        pref = "/" + "/".join(segs[:3])
        for r in fe_norm:
            if r == pref or r.startswith(pref + "/"):
                return True
    return False


def _grep_any(needle, texts):
    return any(needle in txt for txt in texts)



def _tutte_le_route(app):
    """Endpoint con il percorso FINALE, su ogni versione di FastAPI.

    Dalla 0.121 ``include_router`` non appiattisce piu' le rotte in
    ``app.routes``: le tiene dentro un ``_IncludedRouter``. Cercare solo le
    APIRoute di primo livello ne troverebbe ZERO e questo script riscriverebbe
    la classificazione vuota, senza sollevare errori. I contesti del router
    incluso portano il percorso gia' prefissato.
    """
    trovate = []
    for r in app.routes:
        if isinstance(r, APIRoute):
            trovate.append(r)
            continue
        contesti = getattr(r, "effective_route_contexts", None)
        if callable(contesti):
            trovate.extend(contesti())
    return trovate


def build():
    app = FastAPI()
    register_all_routers(app)

    fe = {_norm(r) for r in frontend_refs()}
    tests_txt = [txt for _, txt in _walk_texts("tests", (".py",))]

    # testi scheduler / chat (per nome funzione)
    sched_txt, chat_txt = [], []
    for d in SCHEDULER_DIRS:
        for fpath, txt in _walk_texts(d, (".py",)):
            base = os.path.basename(fpath)
            if SCHEDULER_HINT.search(base) or "scheduler" in txt.lower()[:2000]:
                sched_txt.append(txt)
            if CHAT_HINT.search(base):
                chat_txt.append(txt)

    rows = []
    for route in _tutte_le_route(app):
        # Path e metodi devono esserci entrambi: senza il filtro finirebbero
        # in classificazione righe vuote (docs, openapi.json).
        if not (getattr(route, "path", None) and getattr(route, "methods", None)):
            continue
        for metodo in sorted(route.methods - {"HEAD", "OPTIONS"}):
            fn = route.endpoint
            modulo = getattr(fn, "__module__", "?").replace("app.routers.", "")
            fname = getattr(fn, "__name__", "?")
            path = route.path

            is_migr = bool(MIGRAZIONE_HINT.search(path) or MIGRAZIONE_HINT.search(fname)
                           or MIGRAZIONE_HINT.search(modulo))
            is_fe = _fe_match(path, fe)
            is_sched = _grep_any(fname, sched_txt)
            is_chat = _grep_any(fname, chat_txt)
            is_test = _grep_any(path, tests_txt) or _grep_any(fname, tests_txt)

            # Decisione euristica (conservativa: default "verificare/tenere")
            if is_migr:
                decisione = "admin-only"
                motivo = "endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7)"
            elif is_fe or is_sched or is_chat:
                usi = [n for n, b in (("FE", is_fe), ("scheduler", is_sched), ("chat", is_chat)) if b]
                decisione = "tenere"
                motivo = "in uso: " + ", ".join(usi)
            else:
                decisione = "verificare"
                motivo = "nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare"

            prio = next((p for p in PRIORITARI if path.startswith(p)), "")
            rows.append({
                "metodo": metodo, "path": path, "router": modulo, "fn": fname,
                "fe": is_fe, "sched": is_sched, "chat": is_chat,
                "migr": is_migr, "test": is_test, "decisione": decisione,
                "motivo": motivo, "prio": prio,
            })

    rows.sort(key=lambda r: (r["prio"] == "", r["path"], r["metodo"]))
    return rows


def scrivi(rows):
    tot = len(rows)
    da_verif = sum(1 for r in rows if r["decisione"] == "verificare")
    da_admin = sum(1 for r in rows if r["decisione"] == "admin-only")
    da_ten = sum(1 for r in rows if r["decisione"] == "tenere")

    if not rows:
        # Guardia: senza endpoint le mappe verrebbero riscritte VUOTE, e lo
        # script uscirebbe con successo. E' gia' successo (FastAPI 0.121):
        # ~2.800 righe di documentazione cancellate in silenzio.
        raise SystemExit(
            "Nessun endpoint trovato: mappe NON riscritte. "
            "Probabile incompatibilita' con questa versione di FastAPI."
        )

    out = []
    out.append("# Classificazione endpoint (§7) — RIGENERABILE\n")
    out.append("> Generato da `scripts/genera_classificazione_endpoint.py` sulla route table reale.\n")
    out.append("> NON modificare a mano: rilancia lo script.\n")
    out.append(f"\n**Totale endpoint:** {tot} · tenere: {da_ten} · verificare: {da_verif} · "
               f"admin-only (migrazione/manutenzione): {da_admin}\n")
    out.append("\nColonne: FE=frontend, Sch=scheduler, Chat, Migr=migrazione/manutenzione, "
               "Test. Decisione conservativa: nulla viene eliminata in blocco (§7).\n")

    prioritari = [r for r in rows if r["prio"]]
    if prioritari:
        out.append("\n## Endpoint prioritari (§7)\n")
        out.append(_tabella(prioritari))

    out.append("\n## Tutti gli endpoint\n")
    out.append(_tabella(rows))

    out.append("\n## Note operative (§7)\n")
    out.append("- Gli endpoint marcati **deprecare** sono di migrazione/manutenzione one-shot: "
               "devono essere Admin-only, disabilitabili, documentati e non esposti a lungo.\n")
    out.append("- Gli endpoint **verificare** non hanno riferimenti noti automatici: "
               "verificare manualmente (potrebbero essere chiamati via strumenti esterni/Postman) "
               "prima di deprecare. NON eliminare in blocco.\n")
    open(OUT, "w", encoding="utf-8").write("".join(out))
    print(f"Scritto {OUT}: {tot} endpoint (tenere {da_ten}, verificare {da_verif}, admin-only {da_admin})")


def _b(x):
    return "sì" if x else "—"


def _tabella(rows):
    h = ("| Metodo/path | Router | FE | Sch | Chat | Migr | Test | Decisione | Motivo |\n"
         "|---|---|:-:|:-:|:-:|:-:|:-:|---|---|\n")
    body = []
    for r in rows:
        body.append(
            f"| `{r['metodo']} {r['path']}` | {r['router']} | {_b(r['fe'])} | {_b(r['sched'])} | "
            f"{_b(r['chat'])} | {_b(r['migr'])} | {_b(r['test'])} | {r['decisione']} | {r['motivo']} |\n")
    return h + "".join(body)


if __name__ == "__main__":
    scrivi(build())
