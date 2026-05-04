#!/usr/bin/env python3
"""
Audit statico Ceraldi ERP.

Scansiona backend e frontend per bug pattern ricorrenti:
- datetime.utcnow()
- accessi Mongo a collection vietate/deprecate
- api.delete senza confirm vicino
- fetch GET in useEffect senza AbortController
- endpoint /api/suppliers e /api/fornitori
- residui legacy import PDF presenze
- presenza router export consulente

Uso:
    python scripts/audit_static.py

Il report viene scritto in memoria/AUDIT_STATIC_REPORT.md
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "app"
FRONTEND = ROOT / "frontend" / "src"
REPORT = ROOT / "memoria" / "AUDIT_STATIC_REPORT.md"


@dataclass
class Finding:
    severity: str
    path: str
    line: int
    rule: str
    detail: str


def iter_files(base: Path, suffixes: tuple[str, ...]):
    if not base.exists():
        return
    for path in base.rglob("*"):
        if path.is_file() and path.suffix in suffixes:
            if any(part in {"node_modules", "dist", "build", "__pycache__"} for part in path.parts):
                continue
            yield path


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def add(finds: list[Finding], severity: str, path: Path, line: int, rule: str, detail: str):
    finds.append(Finding(severity, rel(path), line, rule, detail))


def audit_backend(finds: list[Finding]):
    banned_collections = {
        '"suppliers"': "collection fornitori deprecata: usare costante che punta a fornitori",
        "'suppliers'": "collection fornitori deprecata: usare costante che punta a fornitori",
        '"employees"': "collection dipendenti deprecata: usare dipendenti",
        "'employees'": "collection dipendenti deprecata: usare dipendenti",
        '"warehouse_stocks"': "warehouse_stocks legacy: non usare come fonte primaria",
        "'warehouse_stocks'": "warehouse_stocks legacy: non usare come fonte primaria",
        '"f24_models"': "f24_models legacy: usare f24_unificato",
        "'f24_models'": "f24_models legacy: usare f24_unificato",
    }

    for path in iter_files(BACKEND, (".py",)):
        txt_lines = lines(path)
        for i, line in enumerate(txt_lines, start=1):
            if "datetime.utcnow()" in line:
                add(finds, "P2", path, i, "timezone", "Sostituire con datetime.now(timezone.utc).")

            for token, msg in banned_collections.items():
                if token in line and "COLL_" not in line and "Collections." not in line:
                    if "db[" in line or ".get_collection" in line or "count_documents" in line or "find" in line:
                        add(finds, "P1", path, i, "collection", msg)

            if "@router.post" in line or "@router.put" in line:
                window = "\n".join(txt_lines[i:i+8])
                if "Dict[str, Any]" in window and "Body(" not in window:
                    add(finds, "P1", path, i, "body", "POST/PUT con Dict[str, Any] senza Body(...).")

            if "/libro-unico/import-pdf" in line and "no_import_pdf.py" not in rel(path):
                add(
                    finds,
                    "P3",
                    path,
                    i,
                    "legacy-presenze-import-pdf",
                    "Riferimento legacy a import PDF presenze. Deve restare bloccato dal router 410 e non usato come flusso primario.",
                )


def audit_frontend(finds: list[Finding]):
    for path in iter_files(FRONTEND, (".jsx", ".js")):
        txt_lines = lines(path)
        for i, line in enumerate(txt_lines, start=1):
            if "api.delete" in line or ".delete(" in line:
                start = max(0, i - 8)
                context = "\n".join(txt_lines[start:i+3])
                if "confirm(" not in context and "window.confirm" not in context:
                    add(finds, "P1", path, i, "delete-confirm", "DELETE senza confirm vicino.")

            if "api.get(" in line:
                file_text = "\n".join(txt_lines)
                if "useEffect" in file_text and "AbortController" not in file_text and "signal:" not in file_text:
                    add(finds, "P3", path, i, "fetch-race", "api.get in componente con useEffect senza AbortController; verificare race condition.")
                    break

            if "/api/suppliers" in line:
                add(finds, "INFO", path, i, "fornitori-api", "API compatibile /api/suppliers: ok se backend usa collection fornitori.")

            if "/libro-unico/import-pdf" in line or "Importa PDF Libro Unico" in line:
                add(
                    finds,
                    "P2",
                    path,
                    i,
                    "legacy-presenze-import-pdf-ui",
                    "UI contiene ancora flusso legacy import PDF presenze. Preferire pagina/CTA export consulente.",
                )


def audit_required_files(finds: list[Finding]):
    required = [
        "app/routers/attendance_module/export_consulente.py",
        "app/routers/attendance_module/no_import_pdf.py",
        "frontend/src/pages/hr/HRPresenzeExport.jsx",
        "scripts/smoke_app.py",
    ]
    for path in required:
        if not (ROOT / path).exists():
            add(finds, "P1", ROOT / path, 0, "missing-required-file", "File richiesto mancante.")


def write_report(finds: list[Finding]):
    counts: dict[str, int] = {}
    for f in finds:
        counts[f.severity] = counts.get(f.severity, 0) + 1

    out = []
    out.append("# Audit statico automatico\n")
    out.append("Generato da `scripts/audit_static.py`.\n")
    out.append("\n## Sintesi\n")
    for sev in ["P1", "P2", "P3", "INFO"]:
        out.append(f"- {sev}: {counts.get(sev, 0)}")

    out.append("\n## Findings\n")
    for f in sorted(finds, key=lambda x: (x.severity, x.path, x.line)):
        out.append(f"### {f.severity} - {f.rule}\n")
        out.append(f"- File: `{f.path}:{f.line}`\n")
        out.append(f"- Dettaglio: {f.detail}\n")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(out), encoding="utf-8")


def main() -> int:
    finds: list[Finding] = []
    audit_backend(finds)
    audit_frontend(finds)
    audit_required_files(finds)
    write_report(finds)
    print(f"Audit completato: {REPORT}")
    print(f"Finding totali: {len(finds)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
