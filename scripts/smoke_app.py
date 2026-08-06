#!/usr/bin/env python3
"""
Smoke test runtime Ceraldi ERP.

Esegue controlli HTTP minimi su backend e frontend gia' avviati.
Non modifica dati.

Auth-aware:
- senza SMOKE_AUTH_TOKEN accetta 401 sugli endpoint API protetti;
- con SMOKE_AUTH_TOKEN verifica i codici applicativi reali, inclusi 200 e 410.

Uso:
    python scripts/smoke_app.py
    BACKEND_URL=http://localhost:8001 FRONTEND_URL=http://localhost:3000 python scripts/smoke_app.py
    SMOKE_AUTH_TOKEN=<jwt> python scripts/smoke_app.py
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8001").rstrip("/")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
TIMEOUT = float(os.environ.get("SMOKE_TIMEOUT", "12"))
SMOKE_ANNO = int(os.environ.get("SMOKE_ANNO", "2026"))
SMOKE_AUTH_TOKEN = (os.environ.get("SMOKE_AUTH_TOKEN") or "").strip()
HAS_AUTH = bool(SMOKE_AUTH_TOKEN)
ROOT = Path(__file__).resolve().parents[1]
PAGE_CATALOG = json.loads((ROOT / "page_catalog.json").read_text(encoding="utf-8"))
PAGES = PAGE_CATALOG["pages"]


@dataclass
class Check:
    area: str
    name: str
    url: str
    method: str = "GET"
    expected: tuple[int, ...] = (200,)
    protected: bool = False
    expected_without_auth: tuple[int, ...] | None = None

    def effective_expected(self) -> tuple[int, ...]:
        if self.protected and not HAS_AUTH:
            return self.expected_without_auth or (401,)
        return self.expected


BACKEND_CHECKS = [
    Check("backend", "health", f"{BACKEND_URL}/api/health"),
    Check("fornitori", "suppliers compat", f"{BACKEND_URL}/api/suppliers?limit=5", protected=True),
    Check("fornitori", "fornitori alias", f"{BACKEND_URL}/api/fornitori?limit=5", protected=True),
    Check("dashboard", "bilancio istantaneo", f"{BACKEND_URL}/api/dashboard/bilancio-istantaneo?anno={SMOKE_ANNO}", protected=True),
    Check("fatture", "invoices", f"{BACKEND_URL}/api/invoices?limit=5", protected=True),
    Check("prima-nota", "cassa", f"{BACKEND_URL}/api/prima-nota/cassa?limit=5", protected=True),
    Check("scadenze", "prossime", f"{BACKEND_URL}/api/scadenze/prossime?giorni=30&limit=5", protected=True),
]

FRONTEND_PATHS = [page.get("e2e_path", page["path"]) for page in PAGES]


def http_request(url: str, method: str = "GET") -> tuple[int, str]:
    data = b"{}" if method.upper() in {"POST", "PUT", "PATCH"} else None
    headers = {"User-Agent": "ceraldi-smoke-test/1.0"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if SMOKE_AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {SMOKE_AUTH_TOKEN}"
    req = Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read(4000).decode("utf-8", errors="replace")
            return resp.status, body
    except HTTPError as e:
        body = e.read(1000).decode("utf-8", errors="replace")
        return e.code, body
    except URLError as e:
        return 0, str(e)


def run_check(check: Check) -> dict:
    started = time.time()
    status, body = http_request(check.url, check.method)
    elapsed_ms = int((time.time() - started) * 1000)
    expected = check.effective_expected()
    ok = status in expected
    return {
        "ok": ok,
        "area": check.area,
        "name": check.name,
        "method": check.method,
        "url": check.url,
        "status": status,
        "expected": expected,
        "protected": check.protected,
        "auth_used": HAS_AUTH,
        "elapsed_ms": elapsed_ms,
        "sample": body[:180].replace("\n", " "),
    }


def run_frontend_check(path: str) -> dict:
    """Verifica solo la consegna della SPA per una route catalogata.

    Il server restituisce lo stesso index.html anche per URL inesistenti. La
    raggiungibilita React viene quindi verificata separatamente dai test del
    catalogo e il risultato qui e dichiarato esplicitamente ``delivery_only``.
    """
    started = time.time()
    status, body = http_request(f"{FRONTEND_URL}{path}")
    elapsed_ms = int((time.time() - started) * 1000)
    shell_ok = '<div id="root"' in body and bool(
        re.search(r'<script[^>]+src="/assets/[^"]+"', body)
    )
    return {
        "ok": status == 200 and shell_ok,
        "area": "frontend-delivery",
        "name": path,
        "method": "GET",
        "url": f"{FRONTEND_URL}{path}",
        "status": status,
        "expected": (200,),
        "protected": path not in {"/login", "/gestione-riservata"},
        "auth_used": False,
        "elapsed_ms": elapsed_ms,
        "sample": body[:180].replace("\n", " "),
        "spa_shell_valid": shell_ok,
        "scope": "delivery_only",
    }


def main() -> int:
    results = []

    for check in BACKEND_CHECKS:
        results.append(run_check(check))

    for path in FRONTEND_PATHS:
        results.append(run_frontend_check(path))

    # Almeno un asset JavaScript reale deve essere scaricabile. Senza questo
    # check anche un index.html vecchio o monco risulterebbe consegnato.
    _, index_body = http_request(f"{FRONTEND_URL}/")
    scripts = re.findall(r'<script[^>]+src="([^"]+)"', index_body)
    if scripts:
        asset_path = scripts[0]
        asset_url = asset_path if asset_path.startswith("http") else f"{FRONTEND_URL}{asset_path}"
        results.append(run_check(Check("frontend-assets", asset_path, asset_url)))
    else:
        results.append({
            "ok": False,
            "area": "frontend-assets",
            "name": "entry bundle",
            "url": FRONTEND_URL,
            "status": 0,
            "expected": (200,),
            "sample": "Nessun <script src=...> trovato in index.html",
        })

    failures = [r for r in results if not r["ok"]]

    print(json.dumps({
        "backend_url": BACKEND_URL,
        "frontend_url": FRONTEND_URL,
        "auth_used": HAS_AUTH,
        "catalog_pages": len(PAGES),
        "catalog_status": {
            status: sum(page["audit_status"] == status for page in PAGES)
            for status in ("verified", "in_review", "unverified")
        },
        "scope": (
            "API applicative + consegna delle 62 route catalogate"
            if HAS_AUTH
            else "health/auth-boundary + consegna SPA; NON equivale a 62 pagine funzionanti"
        ),
        "auth_note": (
            "Token presente: gli endpoint campione devono rispondere con esito applicativo."
            if HAS_AUTH
            else "Token assente: HTTP 401 prova soltanto che l'endpoint protetto esiste."
        ),
        "checks": len(results),
        "failures": len(failures),
        "results": results,
    }, indent=2, ensure_ascii=False))

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
