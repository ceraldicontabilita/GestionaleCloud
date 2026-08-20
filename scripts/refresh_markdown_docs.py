"""Classifica i Markdown di GestionaleCloud e rigenera il relativo indice.

I documenti generati da altri script vengono solo inventariati: modificarli
qui renderebbe il loro contenuto divergente dalla sorgente che li produce.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REVIEW_DATE = "2026-08-20"

GENERATED = {
    "memoria/AUDIT_FRONTEND_DEAD_CODE.md",
    "memoria/AUDIT_STATIC_REPORT.md",
    "memoria/ENDPOINT_CLASSIFICAZIONE_FINALE.md",
    "memoria/MAPPA_ENDPOINT_COMPLETA.md",
    "memoria/MAPPA_ROUTER.md",
}

CURRENT = {
    ".github/copilot-instructions.md",
    "CLAUDE.md",
    "DESIGN.md",
    "LOGICA_FUNZIONAMENTO.md",
    "PRODUCT.md",
    "README.md",
    "docs/FISCAL_ACCOUNTING_POLICY.md",
    "docs/MARKDOWN_INVENTORY.md",
    "docs/MCP_GESTIONALE_RUNBOOK.md",
    "docs/MCP_GESTIONALE_SPEC.md",
    "docs/rt-locale-drive.md",
    "frontend/README.md",
    "memoria/DISASTER_RECOVERY_DRIVE.md",
    "memoria/FORNITORI_REGOLA_CANONICA.md",
    "memoria/INDEX.md",
    "memoria/MAPPA_MODULI.md",
}

REFERENCE = {
    "memoria/DRIVE_ESTRATTI_CONTO.md",
    "memoria/LOGICA_LIBRO_MASTRO.md",
    "memoria/PIANO_CONTI_UFFICIALE_CERALDI.md",
    "memoria/SPECIFICA_F24_CEDOLINI_IRES_IRAP_CHAT.md",
    "memoria/SPECIFICA_IVA.md",
}

MARKER_RE = re.compile(
    r"\n?<!-- gestionalecloud-doc\n.*?\n-->\n?",
    flags=re.DOTALL,
)
NOTICE_RE = re.compile(
    r"\n?> \[!(?:NOTE|IMPORTANT)\]\n> (?:Snapshot storico|Documento di riferimento).*?\n(?=\n|#)",
    flags=re.DOTALL,
)


def tracked_markdown() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "*.md"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    paths = {line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()}
    paths.discard("memoria/MAPPA_COLLEZIONI.md")
    paths.discard("memoria/DISASTER_RECOVERY_MONGODB.md")
    paths.add("memoria/DISASTER_RECOVERY_DRIVE.md")
    paths.add("docs/MARKDOWN_INVENTORY.md")
    return sorted(path for path in paths if (ROOT / path).exists() or path == "docs/MARKDOWN_INVENTORY.md")


def classify(path: str) -> str:
    if path in GENERATED:
        return "generated"
    if path in CURRENT:
        return "current"
    if path in REFERENCE or path.startswith("memoria/moduli/"):
        return "reference"
    if path.startswith("memoria/endpoints/") and path not in {
        "memoria/endpoints/09-frontend-fatture-riconciliazione-audit.md",
        "memoria/endpoints/RICONCILIAZIONE_AUDIT.md",
    }:
        return "reference"
    return "historical"


def marker(status: str) -> str:
    return (
        "<!-- gestionalecloud-doc\n"
        f"status: {status}\n"
        f"reviewed_at: {REVIEW_DATE}\n"
        "storage_architecture: drive-only\n"
        "-->"
    )


def notice(status: str) -> str:
    if status == "historical":
        return (
            "> [!NOTE]\n"
            "> Snapshot storico: non descrive lo stato operativo corrente. "
            "Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, "
            "`CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`."
        )
    if status == "reference":
        return (
            "> [!IMPORTANT]\n"
            "> Documento di riferimento del dominio. Per persistenza e cutover "
            "vale l'architettura Drive-only descritta nei documenti correnti; "
            "eventuali nomi Mongo/collection restano compatibilità o contesto storico."
        )
    return ""


def update_document(path: str, status: str) -> None:
    if status == "generated":
        return
    target = ROOT / path
    raw = target.read_text(encoding="utf-8-sig")
    raw = MARKER_RE.sub("\n", raw, count=1)
    raw = NOTICE_RE.sub("\n", raw, count=1)
    text = raw.lstrip("\ufeff\n")

    # YAML frontmatter (`--- ... ---`) precede a volte il titolo MD
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            text = text[end + 5 :].lstrip("\n")

    lines = text.splitlines()
    if not lines or not lines[0].startswith("#"):
        raise ValueError(f"{path}: manca il titolo Markdown iniziale")
    title = lines[0]
    body = "\n".join(lines[1:]).lstrip("\n")
    output = [title, "", marker(status)]
    status_notice = notice(status)
    if status_notice:
        output.extend(["", status_notice])
    if body:
        output.extend(["", body.rstrip()])
    target.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def inventory(paths: list[str]) -> str:
    counts = {status: 0 for status in ("current", "reference", "generated", "historical")}
    rows: list[str] = []
    for path in paths:
        status = classify(path)
        counts[status] += 1
        role = {
            "current": "Autorità operativa corrente",
            "reference": "Dettaglio di dominio subordinato ai documenti correnti",
            "generated": "Artefatto meccanico; rigenerare dalla sorgente indicata",
            "historical": "Snapshot/audit datato, conservato come evidenza",
        }[status]
        rows.append(f"| `{path}` | `{status}` | {role} |")

    return f"""# Inventario Markdown — GestionaleCloud

{marker("current")}

Inventario rigenerato il {REVIEW_DATE} da `scripts/refresh_markdown_docs.py`.
Classifica i documenti senza riscrivere gli artefatti prodotti da altri script.

## Significato degli stati

| Stato | Significato |
|---|---|
| `current` | Descrive il comportamento o le regole operative correnti. |
| `reference` | Approfondimento di dominio; l'architettura corrente prevale. |
| `generated` | Output di uno script, da non modificare manualmente. |
| `historical` | Audit, piano o fotografia datata, conservata come prova. |

## Riepilogo

- Correnti: **{counts['current']}**
- Riferimento: **{counts['reference']}**
- Generati: **{counts['generated']}**
- Storici: **{counts['historical']}**
- Totale: **{len(paths)}**

## Elenco completo

| File | Stato | Uso |
|---|---|---|
{chr(10).join(rows)}

## Regola architetturale

La destinazione è Drive-only: originali in Google Drive e registri in Google
Sheets/Excel collegato a Drive. MongoDB è compatibilità transitoria fino alla
verifica completa di copia, scrittura, ricostruzione e cutover; i documenti
storici che lo indicano come database primario non sono più autorità.
"""


def main() -> None:
    paths = tracked_markdown()
    for path in paths:
        if path == "docs/MARKDOWN_INVENTORY.md":
            continue
        update_document(path, classify(path))
    output = inventory(paths)
    (ROOT / "docs" / "MARKDOWN_INVENTORY.md").write_text(output, encoding="utf-8")
    print(f"Markdown classificati: {len(paths)}")


if __name__ == "__main__":
    main()
