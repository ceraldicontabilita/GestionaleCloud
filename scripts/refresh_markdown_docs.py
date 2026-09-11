"""Classifica i Markdown di GestionaleCloud e rigenera il relativo indice.

I documenti generati da altri script vengono solo inventariati: modificarli
qui renderebbe il loro contenuto divergente dalla sorgente che li produce.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REVIEW_DATE = "2026-09-11"
CURRENT_STORAGE = "supabase-runtime-drive-originals"
LEGACY_STORAGE = "drive-only"

GENERATED = {
    "memoria/AUDIT_FRONTEND_BACKEND_CONTRACT.md",
    "memoria/AUDIT_FRONTEND_DEAD_CODE.md",
    "memoria/AUDIT_STATIC_REPORT.md",
    "memoria/ENDPOINT_CLASSIFICAZIONE_FINALE.md",
    "memoria/MAPPA_ENDPOINT_COMPLETA.md",
    "memoria/MAPPA_ROUTER.md",
}

CURRENT = {
    ".github/copilot-instructions.md",
    "AGENTS.md",
    "CLAUDE.md",
    "DESIGN.md",
    "LOGICA_FUNZIONAMENTO.md",
    "PROMPT_MASTER.md",
    "PRODUCT.md",
    "README.md",
    "docs/AI_GOVERNANCE.md",
    "docs/FISCAL_ACCOUNTING_POLICY.md",
    "docs/MARKDOWN_INVENTORY.md",
    "docs/MCP_GESTIONALE_RUNBOOK.md",
    "docs/MCP_GESTIONALE_SPEC.md",
    "docs/PROMPT_CEDOLINI_NETTO_DRIVE_SALARI.md",
    "docs/REGOLA_FISSA_ATTESE.md",
    "docs/RUNBOOK-RENDER-CALDERONE.md",
    "docs/rt-locale-drive.md",
    "frontend/README.md",
    "memoria/DISASTER_RECOVERY_DRIVE.md",
    "memoria/FORNITORI_REGOLA_CANONICA.md",
    "memoria/INDEX.md",
    "memoria/MAPPA_MODULI.md",
    "prompts/development/repository_audit.md",
    "prompts/documents/evidence_extraction.md",
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
    r"\n?> \[!(?:NOTE|IMPORTANT|WARNING)\]\n> "
    r"(?:Snapshot storico|Documento di riferimento|Specifica o piano approvato).*?\n(?=\n|#)",
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
    paths.add("memoria/DISASTER_RECOVERY_DRIVE.md")
    paths.add("docs/MARKDOWN_INVENTORY.md")
    paths.add("docs/REGOLA_FISSA_ATTESE.md")
    return sorted(path for path in paths if (ROOT / path).exists() or path == "docs/MARKDOWN_INVENTORY.md")


APP_PORTATE_PARI_PARI = (
    "app/lotti/", "frontend_lotti/",
    "app/menu/", "frontend_menu/",
    "app/hr/", "frontend_hr/",
)


def classify(path: str) -> str:
    if path in GENERATED:
        return "generated"
    if path.startswith(APP_PORTATE_PARI_PARI):
        return "current"
    if (
        path in CURRENT
        or path.startswith(".github/agents/")
        or path.startswith(".github/instructions/")
        or path.startswith(".github/skills/")
    ):
        return "current"
    if path in {
        "docs/obsidian-integration/README.md",
        "docs/obsidian-integration/MODELLO_NOTE.md",
        "docs/obsidian-integration/SICUREZZA_E_GOVERNANCE.md",
    }:
        return "reference"
    if (
        path.startswith("docs/obsidian-integration/")
        or path == "docs/OBSIDIAN_KNOWLEDGE_ARCHITECTURE_2026-08-20.md"
    ):
        return "planned"
    if path in REFERENCE or path.startswith("memoria/moduli/"):
        return "reference"
    if path.startswith("memoria/endpoints/") and path not in {
        "memoria/endpoints/09-frontend-fatture-riconciliazione-audit.md",
        "memoria/endpoints/RICONCILIAZIONE_AUDIT.md",
    }:
        return "reference"
    return "historical"


def storage_architecture(status: str) -> str:
    return CURRENT_STORAGE if status == "current" else LEGACY_STORAGE


def marker(status: str) -> str:
    return (
        "<!-- gestionalecloud-doc\n"
        f"status: {status}\n"
        f"reviewed_at: {REVIEW_DATE}\n"
        f"storage_architecture: {storage_architecture(status)}\n"
        "-->"
    )


def notice(status: str) -> str:
    if status == "historical":
        return (
            "> [!NOTE]\n"
            "> Snapshot storico: non descrive lo stato operativo corrente. "
            "Per l'architettura corrente usare `README.md`, `AGENTS.md` e "
            "`docs/AI_GOVERNANCE.md`."
        )
    if status == "reference":
        return (
            "> [!IMPORTANT]\n"
            "> Documento di riferimento del dominio. Per persistenza e cutover "
            "vale l'architettura corrente Supabase + Drive descritta nei documenti "
            "correnti; eventuali riferimenti Drive/Sheets sono contesto storico."
        )
    if status == "planned":
        return (
            "> [!WARNING]\n"
            "> Specifica o piano approvato, ma non ancora completamente operativo. "
            "Verificare il runbook corrente e il codice distribuito prima dell'uso."
        )
    return ""


def update_document(path: str, status: str) -> None:
    if status == "generated":
        return
    target = ROOT / path
    raw = target.read_text(encoding="utf-8-sig")
    raw = MARKER_RE.sub("\n", raw, count=1)
    raw = NOTICE_RE.sub("\n", raw)
    lines = raw.lstrip("\ufeff\n").splitlines()
    frontmatter: list[str] = []
    if lines and lines[0].strip() == "---":
        try:
            end = lines.index("---", 1)
        except ValueError as exc:
            raise ValueError(f"{path}: frontmatter YAML non chiuso") from exc
        frontmatter = lines[:end + 1]
        lines = lines[end + 1:]
        while lines and not lines[0].strip():
            lines.pop(0)

    if lines and lines[0].startswith("#"):
        title = lines[0]
        body_lines = lines[1:]
    elif frontmatter:
        name_line = next((line for line in frontmatter if line.startswith("name:")), "")
        title_text = name_line.partition(":")[2].strip().strip('"') or Path(path).stem
        title = f"# {title_text}"
        body_lines = lines
    else:
        raise ValueError(f"{path}: manca il titolo Markdown iniziale")

    body = "\n".join(body_lines).lstrip("\n")
    output = [*frontmatter]
    if frontmatter:
        output.append("")
    output.extend([title, "", marker(status)])
    status_notice = notice(status)
    if status_notice:
        output.extend(["", status_notice])
    if body:
        output.extend(["", body.rstrip()])
    target.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def inventory(paths: list[str]) -> str:
    counts = {
        status: 0
        for status in ("current", "reference", "planned", "generated", "historical")
    }
    rows: list[str] = []
    for path in paths:
        status = classify(path)
        counts[status] += 1
        role = {
            "current": "Autorità operativa corrente",
            "reference": "Dettaglio di dominio subordinato ai documenti correnti",
            "planned": "Specifica approvata ma non ancora completamente operativa",
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
| `planned` | Specifica o piano approvato, non ancora completamente operativo. |
| `generated` | Output di uno script, da non modificare manualmente. |
| `historical` | Audit, piano o fotografia datata, conservata come prova. |

## Riepilogo

- Correnti: **{counts['current']}**
- Riferimento: **{counts['reference']}**
- Pianificati: **{counts['planned']}**
- Generati: **{counts['generated']}**
- Storici: **{counts['historical']}**
- Totale: **{len(paths)}**

## Elenco completo

| File | Stato | Uso |
|---|---|---|
{chr(10).join(rows)}

## Regola architetturale

Supabase è il registro operativo strutturato. Google Drive conserva gli originali
documentali. Il runtime Google Sheets è mantenuto soltanto come compatibilità
transitoria di rollback/test e non deve essere esteso a nuovi flussi.
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
