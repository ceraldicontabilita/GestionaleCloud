"""Verifica il pacchetto autosufficiente di ricostruzione GestionaleCloud."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from scripts.genera_kit_ricostruzione import PACKAGE_NAME, generate


def test_rebuild_kit_is_complete_integral_and_single_root(tmp_path: Path):
    output = tmp_path / "kit.zip"
    result = generate(output)

    assert output.is_file()
    assert hashlib.sha256(output.read_bytes()).hexdigest() == result["sha256"]
    assert output.with_suffix(".zip.sha256").is_file()

    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        assert {name.split("/", 1)[0] for name in names} == {PACKAGE_NAME}
        prefix = f"{PACKAGE_NAME}/"
        assert f"{prefix}00_START_HERE.md" in names
        assert f"{prefix}00_PROMPT_DA_INCOLLARE.txt" in names
        assert f"{prefix}01_MASTER/PROMPT_MASTER.md" in names
        assert len([name for name in names if name.startswith(f"{prefix}03_PAGINE/") and Path(name).name[:2].isdigit() and name.endswith(".md")]) == 66
        logic_names = [name for name in names if name.startswith(f"{prefix}03_PAGINE/LOGICA_JSON/") and name.endswith(".json")]
        assert len(logic_names) == 66
        page_names = [name for name in names if name.startswith(f"{prefix}03_PAGINE/") and Path(name).name[:2].isdigit() and name.endswith(".md")]
        for name in page_names:
            document = archive.read(name).decode("utf-8")
            assert "## Logica operativa specifica" in document
            assert "## Fonti e registri letti" in document
            assert "## Scritture ed effetti consentiti" in document
            assert "## Collegamenti con le altre pagine" in document
            assert "## Divieti e protezioni specifiche" in document
            assert "## Criteri specifici di completamento" in document

        manifest = json.loads(archive.read(f"{prefix}MANIFEST.json"))
        spec = json.loads(archive.read(f"{prefix}09_MACHINE_READABLE/RECONSTRUCTION_SPEC.json"))
        endpoints = json.loads(archive.read(f"{prefix}05_API/ENDPOINTS.json"))
        variables = json.loads(archive.read(f"{prefix}06_CONFIG/VARIABLES.json"))

    assert manifest["counts"]["pages"] == 66
    assert manifest["counts"]["page_logic_contracts"] == 66
    assert manifest["counts"]["popups"] == 36
    assert manifest["counts"]["sheets"] == 30
    assert spec["active_endpoints"] + spec["quarantined_endpoints"] == manifest["counts"]["endpoints"]
    assert len(endpoints) == manifest["counts"]["endpoints"]
    assert len(variables) == manifest["counts"]["variables"]
    assert all(item["default"] is None for item in variables if item["default_redacted"])


def test_rebuild_kit_generation_is_deterministic(tmp_path: Path):
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    generate(first)
    generate(second)
    assert hashlib.sha256(first.read_bytes()).digest() == hashlib.sha256(second.read_bytes()).digest()
