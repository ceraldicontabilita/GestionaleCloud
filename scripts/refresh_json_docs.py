"""Rigenera le mappe JSON documentali dal codice corrente.

Non modifica configurazioni tecniche, snapshot contabili o dataset ufficiali.
Le mappe di pagina/popup diventano indici statici verificabili e non copie
manuali della logica applicativa, che tendono a diventare obsolete.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
PAGE_DIR = ROOT / "memoria" / "pagine"
POPUP_DIR = ROOT / "memoria" / "popup"

PAGE_FILE_BY_PATH = {
    "/": "dashboard.json",
    "/login": "login.json",
    "/gestione-riservata": "gestione-riservata.json",
    "/tracciabilita": "tracciabilita-haccp.json",
    "/hr": "hr-gestione.json",
    "/portale": "hr-portale.json",
    "/menu": "menu-pubblico.json",
    "/menu/ordini": "menu-ordini.json",
    "/menu/cassa": "menu-cassa.json",
    "/menu/cucina": "menu-cucina.json",
    "/menu/magazzino": "menu-magazzino.json",
    "/menu/sale": "menu-sale.json",
    "/menu/gestione": "menu-gestione.json",
    "/menu-banco": "menu-banco.json",
    "/rapido": "inserimento-rapido.json",
    "/fatture": "fatture.json",
    "/fatture/corrispettivi": "corrispettivi.json",
    "/fornitori": "fornitori.json",
    "/prima-nota": "prima-nota.json",
    "/prima-nota/pulizia": "prima-nota-pulizia.json",
    "/noleggio": "noleggio-flotta.json",
    "/noleggio/verbali": "noleggio-verbali.json",
    "/noleggio/costi": "noleggio-costi.json",
    "/verbali-noleggio/:identificativo": "dettaglio-verbale.json",
    "/contabilita": "contabilita-piano-conti.json",
    "/contabilita/bilancio": "contabilita-bilancio.json",
    "/contabilita/verifica": "contabilita-verifica.json",
    "/contabilita/controllo": "contabilita-controllo.json",
    "/contabilita/calendario": "contabilita-calendario.json",
    "/contabilita/cespiti": "contabilita-cespiti.json",
    "/contabilita/finanziaria": "contabilita-finanziaria.json",
    "/contabilita/chiusura": "contabilita-chiusura.json",
    "/contabilita/budget": "contabilita-budget.json",
    "/contabilita/mutui": "contabilita-mutui.json",
    "/contabilita/avanzata": "contabilita-avanzata.json",
    "/contabilita/utile": "contabilita-utile.json",
    "/contabilita/previsioni-acquisti": "contabilita-previsioni-acquisti.json",
    "/learning-machine": "learning-machine.json",
    "/scadenze": "scadenze.json",
    "/riconciliazione": "riconciliazione-bancaria.json",
    "/riconciliazione/archivio-bonifici": "archivio-bonifici.json",
    "/riconciliazione/assegni": "assegni.json",
    "/riconciliazione/paypal": "riconciliazione-paypal.json",
    "/riconciliazione/coerenza-pos": "coerenza-pos.json",
    "/riconciliazione/movimenti-banca": "strumenti-movimenti-banca.json",
    "/riconciliazione/pagopa": "integrazioni-pagopa.json",
    "/documenti/import": "documenti-import.json",
    "/documenti/archivio": "documenti-archivio.json",
    "/strumenti": "strumenti-verifica.json",
    "/strumenti/commercialista": "strumenti-commercialista.json",
    "/strumenti/pianificazione": "strumenti-pianificazione.json",
    "/strumenti/visure": "strumenti-visure.json",
    "/agenti": "agenti.json",
    "/impostazioni-f24-email": "impostazioni-f24-email.json",
    "/integrazioni": "integrazioni-openapi.json",
    "/admin": "admin.json",
    "/admin/elaborazioni": "admin-batch-reprocessing.json",
    "/admin/batch-processor": "admin-batch-processor.json",
    "/mappa-gestionale": "mappa-gestionale.json",
}

SOURCE_PATH_RE = re.compile(
    r"(?:/home/user/GestionaleCloud/)?"
    r"((?:app|frontend|scripts|docs|memoria|gestionale_mcp)/"
    r"[A-Za-z0-9_./-]+\.(?:py|jsx|js|mjs|md))"
)
API_RE = re.compile(r"[\"'`](/api/[A-Za-z0-9_./:${}?=&%\-]+)")


def dump_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def as_list(value: object) -> list[object]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def source_revision() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
    ).strip()


@lru_cache(maxsize=None)
def head_json(path: Path) -> dict:
    """Legge la versione tracciata come fallback durante il primo upgrade."""
    relative = path.relative_to(ROOT).as_posix()
    try:
        raw = subprocess.check_output(
            ["git", "show", f"HEAD:{relative}"], cwd=ROOT, text=True,
            encoding="utf-8", errors="strict",
            stderr=subprocess.DEVNULL,
        )
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return {}


def file_index() -> dict[str, list[Path]]:
    index: dict[str, list[Path]] = {}
    for base in (ROOT / "app", ROOT / "frontend" / "src", ROOT / "scripts"):
        for path in base.rglob("*"):
            if path.is_file():
                index.setdefault(path.name, []).append(path)
    return index


def normalize_source(value: object, index: dict[str, list[Path]]) -> list[str]:
    values = value if isinstance(value, list) else [value]
    result: list[str] = []
    for raw in values:
        if not isinstance(raw, str):
            continue
        matches = SOURCE_PATH_RE.findall(raw.replace("\\", "/"))
        for relative in matches:
            candidate = ROOT / relative
            if candidate.is_file():
                result.append(candidate.relative_to(ROOT).as_posix())
                continue
            alternatives = index.get(Path(relative).name, [])
            if len(alternatives) == 1:
                result.append(alternatives[0].relative_to(ROOT).as_posix())
        for filename in re.findall(
            r"(?<![A-Za-z0-9_.-])([A-Za-z0-9_-]+\.(?:py|jsx|js|mjs|md))",
            raw,
        ):
            alternatives = index.get(filename, [])
            if len(alternatives) == 1:
                result.append(alternatives[0].relative_to(ROOT).as_posix())
    return sorted(set(result))


def endpoints_for(sources: list[str]) -> list[str]:
    endpoints: set[str] = set()
    for relative in sources:
        path = ROOT / relative
        if path.suffix.lower() not in {".js", ".jsx", ".mjs", ".py"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for raw in API_RE.findall(text):
            endpoint = raw.split("?", 1)[0]
            endpoint = re.sub(r"\$\{[^}]*\}", "{param}", endpoint)
            endpoint = re.sub(r"\$\{.*$", "{param}", endpoint)
            endpoint = re.sub(r"(?:\{param\})+", "{param}", endpoint)
            endpoints.add(endpoint.rstrip("/&="))
    return sorted(endpoints)


def module_for(path: str) -> str:
    if path == "/":
        return "dashboard"
    head = path.strip("/").split("/", 1)[0]
    return {
        "login": "accesso",
        "gestione-riservata": "accesso",
        "rapido": "dashboard",
        "fatture-estere-verifica": "fatture",
        "salari": "personale",
        "ritenute": "personale",
        "verbali-noleggio": "noleggio",
        "iva": "contabilita",
        "situazione-fiscale": "contabilita",
        "impostazioni-f24-email": "integrazioni",
        "impostazioni-ai": "integrazioni",
        "utenti": "admin",
        "mappa-gestionale": "strumenti",
        "learning-machine": "strumenti",
        "scadenze": "contabilita",
        "agenti": "strumenti",
        "menu-banco": "menu",
    }.get(head, head)


def page_filename(path: str) -> str:
    if path in PAGE_FILE_BY_PATH:
        return PAGE_FILE_BY_PATH[path]
    slug = path.strip("/").replace("/", "-").replace(":", "") or "dashboard"
    return f"{slug}.json"


def old_page_docs() -> dict[str, dict]:
    docs: dict[str, dict] = {}
    for path in PAGE_DIR.glob("*.json"):
        try:
            docs[path.name] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
    return docs


def rewrite_page_docs(catalog: dict, revision: str, updated_at: str) -> set[str]:
    old_docs = old_page_docs()
    index = file_index()
    written: set[str] = set()

    for page in catalog["pages"]:
        filename = page_filename(page["path"])
        old = old_docs.get(filename, {})
        tracked = head_json(PAGE_DIR / filename)
        current_frontend = old.get("frontend", {}).get("file_verificati", [])
        current_backend = old.get("backend", {}).get("file_verificati", [])
        old_frontend = normalize_source([
            *as_list(current_frontend),
            *as_list(old.get("file_sorgente_frontend", [])),
            *as_list(tracked.get("file_sorgente_frontend", [])),
        ], index)
        old_backend = normalize_source([
            *as_list(current_backend),
            *as_list(old.get("file_sorgente_backend", [])),
            *as_list(tracked.get("file_sorgente_backend", [])),
        ], index)
        frontend = sorted(set([
            page["component"], page["entry"], *old_frontend,
        ]))
        frontend = [item for item in frontend if (ROOT / item).is_file()]
        sources = sorted(set(frontend + old_backend))
        document = {
            "_meta": {
                "schema_version": 2,
                "document_type": "page_source_map",
                "updated_at": updated_at,
                "source_revision": revision,
                "generator": "scripts/refresh_json_docs.py",
                "verification": "static_source_map",
            },
            "pagina": page["label"],
            "route": page["path"],
            "catalog_id": page["id"],
            "modulo": module_for(page["path"]),
            "accesso": page["access"],
            "stato_audit": page["audit_status"],
            "scopo": (
                f"Mappa tecnica della schermata «{page['label']}». "
                "Il comportamento operativo effettivo è definito dai sorgenti "
                "e dai test correnti, non da descrizioni storiche."
            ),
            "frontend": {
                "component": page["component"],
                "entry": page["entry"],
                "file_verificati": frontend,
            },
            "backend": {
                "file_verificati": old_backend,
                "endpoint_rilevati_nei_sorgenti": endpoints_for(sources),
            },
            "archivio_dati": {
                "stato_corrente": "google_drive_sheets",
                "backend_predefinito": "sheets",
                "compatibilita": "nessun_backend_alternativo",
                "fallback_automatico": "disabilitato",
            },
            "regole_di_lettura": [
                "HTTP 200 non prova il corretto funzionamento della schermata.",
                "Gli endpoint elencati sono riferimenti statici rilevati nei sorgenti.",
                "Associazioni automatiche solo con identità e provenienza certe.",
            ],
        }
        dump_json(PAGE_DIR / filename, document)
        written.add(filename)

    for filename, old in old_docs.items():
        if filename in written:
            continue
        frontend = normalize_source(old.get("file_sorgente_frontend", []), index)
        backend = normalize_source(old.get("file_sorgente_backend", []), index)
        raw_url = str(old.get("url") or "")
        match = re.search(r"https?://[^/]+([^\s(]*)", raw_url)
        route = urlsplit("https://example.test" + (match.group(1) if match else "/")).path
        title = old.get("pagina") or Path(filename).stem.replace("-", " ").title()
        dump_json(PAGE_DIR / filename, {
            "_meta": {
                "schema_version": 2,
                "document_type": "embedded_or_legacy_page_source_map",
                "updated_at": updated_at,
                "source_revision": revision,
                "generator": "scripts/refresh_json_docs.py",
                "verification": "not_in_canonical_page_catalog",
            },
            "pagina": title,
            "route_storica_o_interna": route,
            "catalog_status": "non_canonical",
            "scopo": "Componente incorporato o percorso storico; non è una delle 65 schermate canoniche.",
            "file_verificati": sorted(set(frontend + backend)),
            "endpoint_rilevati_nei_sorgenti": endpoints_for(frontend + backend),
        })
        written.add(filename)
    return written


def rewrite_popup_docs(revision: str, updated_at: str) -> int:
    index = file_index()
    count = 0
    for path in sorted(POPUP_DIR.glob("*.json")):
        old = json.loads(path.read_text(encoding="utf-8"))
        tracked = head_json(path)
        title = (
            old.get("nome_popup") or old.get("popup")
            or tracked.get("nome_popup") or tracked.get("popup")
            or path.stem.replace("-", " ").title()
        )
        raw_sources: list[object] = as_list(old.get("file_verificati", []))
        for key in ("file_sorgente", "file_sorgente_frontend", "file_sorgente_backend"):
            value = old.get(key, [])
            raw_sources.extend(value if isinstance(value, list) else [value])
            tracked_value = tracked.get(key, [])
            raw_sources.extend(
                tracked_value if isinstance(tracked_value, list) else [tracked_value]
            )
        for key in ("aperto_da", "pagine_da_cui_si_apre", "pagina_di_provenienza"):
            raw_sources.extend(as_list(old.get(key, [])))
            raw_sources.extend(as_list(tracked.get(key, [])))
        sources = normalize_source(raw_sources, index)
        opened_from = (
            old.get("aperto_da")
            or old.get("pagine_da_cui_si_apre")
            or old.get("pagina_di_provenienza")
            or tracked.get("aperto_da")
            or tracked.get("pagine_da_cui_si_apre")
            or tracked.get("pagina_di_provenienza")
            or []
        )
        if isinstance(opened_from, str):
            opened_from = [opened_from]
        dump_json(path, {
            "_meta": {
                "schema_version": 2,
                "document_type": "popup_source_map",
                "updated_at": updated_at,
                "source_revision": revision,
                "generator": "scripts/refresh_json_docs.py",
                "verification": "static_source_map",
            },
            "popup": title,
            "scopo": (
                f"Mappa tecnica del popup «{title}». Il comportamento e le "
                "mutazioni reali devono essere verificati nei sorgenti correnti."
            ),
            "aperto_da": opened_from,
            "file_verificati": sources,
            "endpoint_rilevati_nei_sorgenti": endpoints_for(sources),
            "regole_ux": [
                "Il popup deve avere chiusura visibile e non restare sovrapposto al documento.",
                "Le azioni distruttive o definitive richiedono una conferma esplicita.",
                "Le associazioni ambigue mostrano candidati e non vengono applicate automaticamente.",
            ],
        })
        count += 1
    return count


def rewrite_catalog(catalog: dict, revision: str, updated_at: str) -> None:
    for page in catalog["pages"]:
        page["module"] = module_for(page["path"])
        page["documentation_file"] = f"memoria/pagine/{page_filename(page['path'])}"
        page["component_status"] = "reachable_from_router"
    output = {
        "schema_version": 2,
        "application": "GestionaleCloud - Ceraldi ERP",
        "production_url": "https://impresasemplice.online",
        "updated_at": updated_at,
        "source_revision": revision,
        "description": (
            "Catalogo canonico delle 65 schermate. HTTP 200 non prova il funzionamento: "
            "componenti, route, dati e relazioni devono essere collaudati."
        ),
        "storage_state": {
            "current": "google_drive_sheets",
            "registry": "sheets",
            "originals": "drive",
            "compatibility": "nessun_backend_alternativo",
        },
        "pages": catalog["pages"],
    }
    dump_json(ROOT / "page_catalog.json", output)


def rewrite_chat_kb(revision: str, updated_at: str) -> None:
    path = ROOT / "app" / "knowledge" / "chat_kb.json"
    kb = json.loads(path.read_text(encoding="utf-8"))
    meta = kb.setdefault("meta", {})
    meta["versione"] = "5.0-drive-sheets-operational"
    meta["aggiornato_al"] = updated_at
    meta["source_revision"] = revision
    meta["repository"] = "ceraldicontabilita/GestionaleCloud"
    kb["storage_operativo"] = {
        "stato_corrente": "google_drive_sheets",
        "backend_predefinito": "sheets",
        "compatibilita": "nessun_backend_alternativo",
        "regola": (
            "La chat interroga soltanto strumenti backend autorizzati. Drive/Sheets "
            "è l'unico archivio operativo; non esiste fallback alternativo."
        ),
        "cartelle_canoniche": [
            "REGISTRO DATI", "PARTENOPAY", "CODICI TRIBUTO", "QUIETANZE", "DICHIARAZIONI",
        ],
    }
    implementation = kb.setdefault("implementazione_chat_intelligente", {})
    implementation["stato_attuale"] = {
        "stato": "implementata_con_strumenti_controllati",
        "frontend": "frontend/src/components/ChatIntelligente.jsx",
        "backend": "app/routers/chat_router.py e app/services/chat_ai_engine.py",
        "endpoint": "POST /api/chat/ask",
        "mcp": "gestionale_mcp espone strumenti di sola lettura",
        "nota": "Le azioni con effetti restano fuori dagli strumenti di risposta automatica.",
    }
    architecture = implementation.get("architettura_generale", {})
    flow = architecture.get("flusso", [])
    architecture["flusso"] = [
        "Il backend interroga i registri Sheets e legge gli originali autorizzati da Drive."
        if item.startswith("Il backend interroga") else item
        for item in flow
    ]
    tools = implementation.get("componenti_da_costruire", {}).get("strumenti_dati", {})
    if tools:
        tools["principio"] = (
            "Il modello AI non accede direttamente allo storage. Il backend espone "
            "strumenti autorizzati, tipizzati, paginati e registrati."
        )
        tools["regole"] = [
            "Il modello non può costruire query libere contro Sheets o Drive."
            if "query libere" in rule else rule
            for rule in tools.get("regole", [])
        ]
    dump_json(path, kb)


def rewrite_mcp_evals() -> None:
    path = ROOT / "gestionale_mcp" / "evals" / "read_only_evals.json"
    evals = json.loads(path.read_text(encoding="utf-8"))
    additions = [
        {
            "id": "drive-ledger-provenance",
            "prompt": "Mostra l'identità canonica e la provenienza Drive di una fattura senza modificarla.",
            "expected_tool": "gestionale_get_invoice_context",
            "criteria": ["canonical_id", "operation_id", "hash e provenienza", "sola lettura"],
            "read_only": True,
        },
        {
            "id": "partenopay-chain",
            "prompt": "Mostra verbale PartenoPay, targa, driver storico, quietanza e banca mantenendo le prove separate.",
            "expected_tool": "gestionale_get_operational_context",
            "criteria": ["targa e data infrazione", "driver storico", "prove separate", "ambigui non confermati"],
            "read_only": True,
        },
        {
            "id": "fiscal-declarations-drive",
            "prompt": "Elenca le dichiarazioni fiscali disponibili su Drive per anno e tipologia con hash e fonte.",
            "expected_tool": "gestionale_search_documents",
            "criteria": ["Drive come fonte", "anno e tipologia", "hash", "nessuno spostamento"],
            "read_only": True,
        },
    ]
    known = {item["id"] for item in evals}
    evals.extend(item for item in additions if item["id"] not in known)
    dump_json(path, evals)


def json_files() -> list[Path]:
    excluded_parts = {
        ".claude", ".git", ".pytest_cache", "node_modules", "dist", "tmp",
    }
    # Solo i file tracciati da git (come refresh_markdown_docs.py): copie di
    # lavoro non ancora committate non appartengono all'inventario.
    tracked = set(
        subprocess.run(
            ["git", "ls-files", "--cached", "--", "*.json"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.split("\n")
    )
    result: list[Path] = []
    for path in ROOT.rglob("*.json"):
        relative_path = path.relative_to(ROOT)
        parts = relative_path.parts
        if any(part in excluded_parts for part in parts):
            continue
        if any(part.startswith(".codex") or part.startswith(".verify") for part in parts):
            continue
        if relative_path.as_posix() not in tracked:
            continue
        result.append(path)
    return sorted(result)


def category_for(relative: str) -> tuple[str, str]:
    if relative == "page_catalog.json" or relative.startswith("memoria/pagine/") or relative.startswith("memoria/popup/"):
        return "documentazione_generata", "rigenerare_con_script"
    if relative in {"app/knowledge/chat_kb.json", "gestionale_mcp/evals/read_only_evals.json"}:
        return "conoscenza_operativa", "aggiornare_con_test"
    if relative.startswith("app/data/") or "FOTOGRAFIA_" in relative:
        return "dataset_o_snapshot", "preservare_contenuto_e_provenienza"
    return "configurazione_tecnica", "modificare_solo_se_richiesto_dal_codice"


def write_inventory(revision: str, updated_at: str) -> None:
    inventory_path = ROOT / "memoria" / "JSON_INVENTORY.json"
    entries = []
    for path in json_files():
        if path == inventory_path:
            continue
        value = json.loads(path.read_text(encoding="utf-8"))
        canonical = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        relative = path.relative_to(ROOT).as_posix()
        category, policy = category_for(relative)
        entries.append({
            "path": relative,
            "category": category,
            "policy": policy,
            "valid_json": True,
            "sha256": hashlib.sha256(canonical).hexdigest(),
        })
    dump_json(inventory_path, {
        "schema_version": 1,
        "updated_at": updated_at,
        "source_revision": revision,
        "scope": "Tutti i file JSON del repository esclusi artefatti, cache e dipendenze.",
        "hash_mode": "canonical_json_utf8",
        "total_excluding_self": len(entries),
        "entries": entries,
    })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--updated-at", default="2026-08-20")
    parser.add_argument("--source-revision", default=source_revision())
    args = parser.parse_args()

    catalog = json.loads((ROOT / "page_catalog.json").read_text(encoding="utf-8"))
    pages = rewrite_page_docs(catalog, args.source_revision, args.updated_at)
    popups = rewrite_popup_docs(args.source_revision, args.updated_at)
    rewrite_catalog(catalog, args.source_revision, args.updated_at)
    rewrite_chat_kb(args.source_revision, args.updated_at)
    rewrite_mcp_evals()
    write_inventory(args.source_revision, args.updated_at)
    print(json.dumps({
        "page_docs": len(pages),
        "popup_docs": popups,
        "catalog_pages": len(catalog["pages"]),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
