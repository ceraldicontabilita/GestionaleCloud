from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs" / "MARKDOWN_INVENTORY.md"
ROW_RE = re.compile(r"^\| `([^`]+)` \| `(current|reference|generated|historical)` \|", re.MULTILINE)


def inventory_rows() -> dict[str, str]:
    return dict(ROW_RE.findall(INVENTORY.read_text(encoding="utf-8")))


def existing_repository_markdown() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files", "*.md"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    paths = {
        line.strip().replace("\\", "/")
        for line in result.stdout.splitlines()
        if line.strip() and (ROOT / line.strip()).exists()
    }
    paths.update({"docs/MARKDOWN_INVENTORY.md", "memoria/DISASTER_RECOVERY_DRIVE.md"})
    return paths


def test_legacy_collection_map_and_mongodb_runbook_are_removed() -> None:
    assert not (ROOT / "memoria" / "MAPPA_COLLEZIONI.md").exists()
    assert not (ROOT / "memoria" / "DISASTER_RECOVERY_MONGODB.md").exists()
    assert (ROOT / "memoria" / "DISASTER_RECOVERY_DRIVE.md").is_file()


def test_inventory_covers_every_repository_markdown() -> None:
    rows = inventory_rows()
    assert set(rows) == existing_repository_markdown()
    assert len(rows) == len(existing_repository_markdown())


def test_non_generated_documents_have_status_metadata() -> None:
    for path, status in inventory_rows().items():
        if status == "generated":
            continue
        text = (ROOT / path).read_text(encoding="utf-8")
        assert "<!-- gestionalecloud-doc" in text, path
        assert f"status: {status}" in text, path
        assert "storage_architecture: drive-only" in text, path


def test_current_documents_use_canonical_project_identity() -> None:
    forbidden = (
        "Gestionale2",
        "MAPPA_COLLEZIONI",
        "DISASTER_RECOVERY_MONGODB",
        "github.com/ceraldicontabilita/gestionale ",
    )
    for path, status in inventory_rows().items():
        if status != "current":
            continue
        text = (ROOT / path).read_text(encoding="utf-8")
        for value in forbidden:
            assert value not in text, f"{path}: contiene {value}"


def test_historical_documents_are_visibly_non_authoritative() -> None:
    for path, status in inventory_rows().items():
        if status != "historical":
            continue
        text = (ROOT / path).read_text(encoding="utf-8")
        assert "Snapshot storico" in text, path
        assert "LOGICA_FUNZIONAMENTO.md" in text, path


def test_drive_only_docs_state_real_cutover_boundary() -> None:
    logic = (ROOT / "LOGICA_FUNZIONAMENTO.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "DATA_BACKEND=sheets" in logic
    assert "compatibilità transitoria" in logic
    assert "ricostruzione completa" in logic
    assert "backend transitorio" in readme
