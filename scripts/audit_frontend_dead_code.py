"""Genera memoria/AUDIT_FRONTEND_DEAD_CODE.md (Piano residuo P1 §"audit reale
del frontend inutilizzato").

Costruisce il grafo di import REALE del frontend a partire dagli entry point
(`frontend/src/main.jsx`, `frontend/src/App.jsx`,
`frontend/src/navigation.config.js`) seguendo import statici, `import()`
dinamici, `lazy(() => import(...))` e re-export (`export { X } from "..."`,
`export * from "..."` — barrel file come `components/ds/index.js`). Ogni
file di `frontend/src` viene classificato in base a come/se è raggiunto.

Decisione conservativa (come da §7 del piano): nessun file viene eliminato
da questo script. Elimina SOLO i file marcati `ORFANO_ELIMINABILE`, uno alla
volta o in piccoli gruppi, con `yarn build && yarn lint` dopo ogni gruppo.

RIGENERABILE: non modificare l'output a mano, rilancia lo script.
Uso: python scripts/audit_frontend_dead_code.py
"""
import os
import re
import sys

FRONTEND_SRC = "frontend/src"
OUT = "memoria/AUDIT_FRONTEND_DEAD_CODE.md"

ENTRYPOINTS = ["main.jsx", "App.jsx", "navigation.config.js"]

EXTENSIONS = [".jsx", ".js", ".tsx", ".ts"]

IMPORT_RE = re.compile(r"""import\s+(?:[\w*${}\s,]+from\s+)?["']([^"']+)["']""")
EXPORT_FROM_RE = re.compile(r"""export\s+(?:\*(?:\s+as\s+\w+)?|\{[^}]*\})\s+from\s+["']([^"']+)["']""")
DYNAMIC_IMPORT_RE = re.compile(r"""import\(\s*["']([^"']+)["']\s*\)""")
DYNAMIC_TEMPLATE_RE = re.compile(r"""import\(\s*`([^`]*)`\s*\)""")
REQUIRE_RE = re.compile(r"""require\(\s*["']([^"']+)["']\s*\)""")

HOOK_DIR = f"{FRONTEND_SRC}/hooks"
MODAL_NAME_RE = re.compile(r"Modal|Dialog", re.IGNORECASE)


def normalizza_path(path):
    """Usa sempre '/' nel grafo e nell'output, anche quando gira su Windows."""
    return os.path.normpath(path).replace("\\", "/")


def tutti_i_file():
    out = []
    for root, dirs, files in os.walk(FRONTEND_SRC):
        dirs[:] = [d for d in dirs if d not in ("node_modules",)]
        for f in files:
            if os.path.splitext(f)[1] in EXTENSIONS:
                out.append(normalizza_path(os.path.join(root, f)))
    return out


def leggi(path):
    with open(path, encoding="utf-8", errors="ignore") as fh:
        return fh.read()


def risolvi(base_dir, spec):
    """Risolve uno specifier di import in un path file reale sotto frontend/src,
    oppure None se è un pacchetto esterno (npm) o un asset non-JS (css/svg/...)."""
    if spec.startswith("@/"):
        candidato = normalizza_path(os.path.join(FRONTEND_SRC, spec[2:]))
    elif spec.startswith("."):
        candidato = normalizza_path(os.path.join(base_dir, spec))
    else:
        return None  # pacchetto npm

    ext = os.path.splitext(candidato)[1]
    if ext in EXTENSIONS:
        return candidato if os.path.isfile(candidato) else None
    if ext:  # .css, .svg, .png, ... — non fa parte del grafo React
        return None

    for e in EXTENSIONS:
        p = candidato + e
        if os.path.isfile(p):
            return p

    if os.path.isdir(candidato):
        for e in EXTENSIONS:
            p = normalizza_path(os.path.join(candidato, "index" + e))
            if os.path.isfile(p):
                return p

    return None


def estrai_import(testo):
    """Ritorna (lista specifier statici/dinamici risolvibili, lista template dinamici grezzi)."""
    specifiers = []
    specifiers += IMPORT_RE.findall(testo)
    specifiers += EXPORT_FROM_RE.findall(testo)
    specifiers += DYNAMIC_IMPORT_RE.findall(testo)
    specifiers += REQUIRE_RE.findall(testo)
    dinamici_template = DYNAMIC_TEMPLATE_RE.findall(testo)
    return specifiers, dinamici_template


def costruisci_grafo():
    grafo = {}          # file -> set(file importati)
    incoming = {}        # file -> set(file che lo importano)
    dinamico_flag = {}   # file -> True se contiene un import() con template literal irrisolvibile

    for f in tutti_i_file():
        testo = leggi(f)
        base_dir = os.path.dirname(f)
        specifiers, dinamici_template = estrai_import(testo)
        dinamico_flag[f] = bool(dinamici_template)
        risolti = set()
        for spec in specifiers:
            r = risolvi(base_dir, spec)
            if r:
                risolti.add(r)
        grafo[f] = risolti
        for r in risolti:
            incoming.setdefault(r, set()).add(f)

    return grafo, incoming, dinamico_flag


def bfs(grafo, partenza):
    visitati = set(partenza)
    coda = list(partenza)
    while coda:
        cur = coda.pop()
        for nxt in grafo.get(cur, ()):
            if nxt not in visitati:
                visitati.add(nxt)
                coda.append(nxt)
    return visitati


def grep_basename_ovunque(path, tutti_i_testi):
    """Cerca il basename del file (senza estensione) in TUTTO il codice
    sorgente, per intercettare riferimenti dinamici non risolvibili
    staticamente (safety net conservativa prima di marcare ORFANO)."""
    basename = os.path.splitext(os.path.basename(path))[0]
    if basename == "index":
        return False  # troppo generico per essere un segnale utile
    pattern = re.compile(r"\b" + re.escape(basename) + r"\b")
    for altro_path, testo in tutti_i_testi.items():
        if altro_path == path:
            continue
        if pattern.search(testo):
            return True
    return False


def classifica(f, entrypoint_paths, direttamente_da_main, raggiungibili,
                incoming, dinamico_flag, tutti_i_testi):
    if f in entrypoint_paths:
        return "ENTRYPOINT"
    if f in raggiungibili:
        if f in direttamente_da_main and f.startswith(f"{FRONTEND_SRC}/pages/"):
            return "ROUTE_ATTIVA"
        if f.startswith(HOOK_DIR + "/"):
            return "HOOK_USATO"
        if MODAL_NAME_RE.search(os.path.basename(f)):
            return "MODALE_USATO"
        return "COMPONENTE_USATO"
    # non raggiunto dagli entry point di produzione
    if dinamico_flag.get(f):
        return "DINAMICO_DA_VERIFICARE"
    if grep_basename_ovunque(f, tutti_i_testi):
        return "DINAMICO_DA_VERIFICARE"
    # File di test (Vitest): mai raggiunti dal grafo di import dell'app per
    # design (li esegue il test runner, non main.jsx/App.jsx) — non sono
    # codice morto, categoria dedicata invece di finire tra gli orfani
    # eliminabili, dove ogni futuro file di test comparirebbe per sempre.
    basename = os.path.basename(f)
    if (re.search(r"\.(test|spec)\.[jt]sx?$", basename)
            or f.startswith(f"{FRONTEND_SRC}/test/")):
        return "TEST_ONLY"
    return "ORFANO_ELIMINABILE"


def main():
    grafo, incoming, dinamico_flag = costruisci_grafo()
    tutti = tutti_i_file()
    tutti_i_testi = {f: leggi(f) for f in tutti}

    entrypoint_paths = [normalizza_path(os.path.join(FRONTEND_SRC, e)) for e in ENTRYPOINTS]
    entrypoint_paths = [e for e in entrypoint_paths if os.path.isfile(e)]

    main_path = normalizza_path(os.path.join(FRONTEND_SRC, "main.jsx"))
    direttamente_da_main = grafo.get(main_path, set())

    raggiungibili = bfs(grafo, entrypoint_paths) - set(entrypoint_paths)

    righe = []
    conteggi = {}
    for f in sorted(tutti):
        cls = classifica(f, set(entrypoint_paths), direttamente_da_main,
                          raggiungibili, incoming, dinamico_flag, tutti_i_testi)
        conteggi[cls] = conteggi.get(cls, 0) + 1
        n_import_da = len(incoming.get(f, ()))
        righe.append((f, cls, n_import_da))

    out = ["# AUDIT FRONTEND DEAD CODE — GestionaleCloud", ""]
    out.append("> Generato da `scripts/audit_frontend_dead_code.py` seguendo il grafo di "
                "import reale a partire da `main.jsx`/`App.jsx`/`navigation.config.js` "
                "(import statici, `import()` dinamici, `lazy(() => import(...))`, "
                "re-export `export {X} from`/`export * from`).")
    out.append("> NON modificare a mano: rilancia lo script.")
    out.append("")
    out.append(f"**Totale file analizzati:** {len(tutti)}")
    out.append("")
    ordine = ["ENTRYPOINT", "ROUTE_ATTIVA", "COMPONENTE_USATO", "MODALE_USATO",
              "HOOK_USATO", "TEST_ONLY", "DINAMICO_DA_VERIFICARE", "ORFANO_ELIMINABILE"]
    out.append("| Classificazione | File |")
    out.append("|---|---:|")
    for c in ordine:
        out.append(f"| {c} | {conteggi.get(c, 0)} |")
    out.append("")

    orfani = [r for r in righe if r[1] == "ORFANO_ELIMINABILE"]
    dinamici = [r for r in righe if r[1] == "DINAMICO_DA_VERIFICARE"]

    out.append("## ORFANO_ELIMINABILE — candidati eliminazione")
    out.append("")
    out.append("Nessun import statico o dinamico risolvibile li raggiunge da "
                "`main.jsx`/`App.jsx`/`navigation.config.js`, e il nome del file "
                "non compare altrove nel codice (safety net anti falso-positivo). "
                "Decisione conservativa (§7): NON eliminare in blocco — verificare "
                "uno per uno, poi `yarn build && yarn lint` dopo ogni piccolo gruppo.")
    out.append("")
    if orfani:
        out.append("| File |")
        out.append("|---|")
        for f, _, _ in orfani:
            out.append(f"| `{f}` |")
    else:
        out.append("_Nessuno._")
    out.append("")

    out.append("## DINAMICO_DA_VERIFICARE")
    out.append("")
    out.append("Non raggiunti dal grafo di import statico, ma il nome del file compare "
                "altrove nel codice (possibile riferimento dinamico/stringa) oppure il "
                "file stesso usa un `import()` con template literal non risolvibile "
                "staticamente. Verificare manualmente prima di decidere.")
    out.append("")
    if dinamici:
        out.append("| File |")
        out.append("|---|")
        for f, _, _ in dinamici:
            out.append(f"| `{f}` |")
    else:
        out.append("_Nessuno._")
    out.append("")

    out.append("## Dettaglio completo")
    out.append("")
    out.append("| File | Classificazione | Importato da (n. file) |")
    out.append("|---|---|---:|")
    for f, cls, n in righe:
        out.append(f"| `{f}` | {cls} | {n} |")
    out.append("")

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")

    print(f"OK — {len(tutti)} file analizzati")
    for c in ordine:
        print(f"  {c}: {conteggi.get(c, 0)}")


if __name__ == "__main__":
    main()
