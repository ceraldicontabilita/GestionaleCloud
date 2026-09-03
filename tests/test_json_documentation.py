"""Guardie per la documentazione JSON generata dal codice corrente."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "page_catalog.json").read_text(encoding="utf-8"))


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def repository_json_files() -> list[Path]:
    # "build" = output CRA delle app portate pari pari (frontend_lotti,
    # frontend_menu): compilato su Render, mai versionato, come "dist".
    excluded_parts = {
        ".claude", ".git", ".pytest_cache", "node_modules", "dist", "build", "tmp",
    }
    result: list[Path] = []
    for path in ROOT.rglob("*.json"):
        parts = path.relative_to(ROOT).parts
        if any(part in excluded_parts for part in parts):
            continue
        if any(part.startswith(".codex") or part.startswith(".verify") for part in parts):
            continue
        result.append(path)
    return sorted(result)


def test_catalogo_e_mappe_pagina_hanno_la_stessa_revisione():
    assert CATALOG["schema_version"] == 2
    assert len(CATALOG["pages"]) == 66
    revision = CATALOG["source_revision"]

    for page in CATALOG["pages"]:
        path = ROOT / page["documentation_file"]
        assert path.is_file(), f"Mappa pagina assente: {path}"
        document = load_json(path)
        assert document["_meta"]["schema_version"] == 2
        assert document["_meta"]["source_revision"] == revision
        assert document["route"] == page["path"]
        assert document["catalog_id"] == page["id"]
        for source in document["frontend"]["file_verificati"]:
            assert (ROOT / source).is_file(), f"Sorgente pagina assente: {source}"
        for source in document["backend"]["file_verificati"]:
            assert (ROOT / source).is_file(), f"Sorgente backend assente: {source}"


def test_mappe_popup_referenziano_solo_sorgenti_esistenti():
    popup_paths = sorted((ROOT / "memoria/popup").glob("*.json"))
    assert len(popup_paths) == 36
    for path in popup_paths:
        document = load_json(path)
        assert document["_meta"]["schema_version"] == 2
        assert document["_meta"]["document_type"] == "popup_source_map"
        assert document["_meta"]["source_revision"] == CATALOG["source_revision"]
        assert document["aperto_da"], f"Pagina di origine popup assente: {path.name}"
        assert document["file_verificati"], f"Sorgenti popup assenti: {path.name}"
        for source in document["file_verificati"]:
            assert (ROOT / source).is_file(), f"Sorgente popup assente: {source}"


def test_inventario_json_e_completo_e_verificabile():
    inventory_path = ROOT / "memoria/JSON_INVENTORY.json"
    inventory = load_json(inventory_path)
    actual = [path for path in repository_json_files() if path != inventory_path]
    entries = inventory["entries"]

    assert inventory["total_excluding_self"] == len(actual) == len(entries)
    assert [item["path"] for item in entries] == [
        path.relative_to(ROOT).as_posix() for path in actual
    ]
    assert inventory["hash_mode"] == "canonical_json_utf8"
    for path, item in zip(actual, entries, strict=True):
        value = load_json(path)
        canonical = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        assert item["valid_json"] is True
        assert item["sha256"] == hashlib.sha256(canonical).hexdigest()


def test_conoscenza_operativa_e_valutazioni_restano_di_sola_lettura():
    kb = load_json(ROOT / "app/knowledge/chat_kb.json")
    assert kb["meta"]["versione"] == "5.0-drive-sheets-operational"
    assert kb["storage_operativo"]["stato_corrente"] == "google_drive_sheets"
    assert kb["storage_operativo"]["backend_predefinito"] == "sheets"
    assert kb["storage_operativo"]["compatibilita"] == "nessun_backend_alternativo"

    evals = load_json(ROOT / "gestionale_mcp/evals/read_only_evals.json")
    assert len({item["id"] for item in evals}) == len(evals)
    assert all(item["read_only"] is True for item in evals)
