#!/usr/bin/env python3
"""
Smoke test runtime Ceraldi ERP.

Esegue controlli HTTP minimi su backend e frontend gia' avviati.
Non modifica dati.

Uso:
    python scripts/smoke_app.py
    BACKEND_URL=http://localhost:8001 FRONTEND_URL=http://localhost:3000 python scripts/smoke_app.py
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8001").rstrip("/")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
TIMEOUT = float(os.environ.get("SMOKE_TIMEOUT", "12"))
SMOKE_ANNO = int(os.environ.get("SMOKE_ANNO", "2026"))
SMOKE_MESE = int(os.environ.get("SMOKE_MESE", "4"))


@dataclass
class Check:
    area: str
    name: str
    url: str
    method: str = "GET"
    expected: tuple[int, ...] = (200,)


BACKEND_CHECKS = [
    Check("backend", "health", f"{BACKEND_URL}/api/health"),
    Check("fornitori", "suppliers compat", f"{BACKEND_URL}/api/suppliers?limit=5"),
    Check("fornitori", "fornitori alias", f"{BACKEND_URL}/api/fornitori?limit=5"),
    Check("dashboard", "bilancio istantaneo", f"{BACKEND_URL}/api/dashboard/bilancio-istantaneo?anno=2026"),
    Check("fatture", "invoices", f"{BACKEND_URL}/api/invoices?limit=5"),
    Check("prima-nota", "cassa", f"{BACKEND_URL}/api/prima-nota/cassa?limit=5"),
    Check("magazzino", "warehouse", f"{BACKEND_URL}/api/warehouse/products?limit=5", expected=(200, 404)),
    Check("dipendenti", "dipendenti", f"{BACKEND_URL}/api/dipendenti?limit=5"),
    Check("cedolini", "cedolini", f"{BACKEND_URL}/api/cedolini?limit=5"),
    Check("scadenze", "prossime", f"{BACKEND_URL}/api/scadenze/prossime?giorni=30&limit=5"),
    Check(
        "attendance",
        "export consulente preview",
        f"{BACKEND_URL}/api/attendance/export-consulente/preview?anno={SMOKE_ANNO}&mese={SMOKE_MESE}",
    ),
    Check(
        "attendance",
        "export consulente csv",
        f"{BACKEND_URL}/api/attendance/export-consulente/csv?anno={SMOKE_ANNO}&mese={SMOKE_MESE}",
    ),
    Check(
        "attendance",
        "legacy import pdf disabled",
        f"{BACKEND_URL}/api/attendance/libro-unico/import-pdf",
        method="POST",
        expected=(410,),
    ),
]

FRONTEND_PATHS = [
    "/",
    "/fatture",
    "/fornitori",
    "/prima-nota",
    "/magazzino",
    "/riconciliazione",
    "/contabilita",
    "/dipendenti",
    "/cedolini",
    "/strumenti",
    "/admin",
]


def http_request(url: str, method: str = "GET") -> tuple[int, str]:
    data = b"{}" if method.upper() in {"POST", "PUT", "PATCH"} else None
    headers = {"User-Agent": "ceraldi-smoke-test/1.0"}
    if data is not None:
        headers["Content-Type"] = "application/json"
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
    ok = status in check.expected
    return {
        "ok": ok,
        "area": check.area,
        "name": check.name,
        "method": check.method,
        "url": check.url,
        "status": status,
        "expected": check.expected,
        "elapsed_ms": elapsed_ms,
        "sample": body[:180].replace("\n", " "),
    }


def main() -> int:
    results = []

    for check in BACKEND_CHECKS:
        results.append(run_check(check))

    for path in FRONTEND_PATHS:
        results.append(run_check(Check("frontend", path, f"{FRONTEND_URL}{path}", expected=(200,))))

    failures = [r for r in results if not r["ok"]]

    print(json.dumps({
        "backend_url": BACKEND_URL,
        "frontend_url": FRONTEND_URL,
        "checks": len(results),
        "failures": len(failures),
        "results": results,
    }, indent=2, ensure_ascii=False))

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
