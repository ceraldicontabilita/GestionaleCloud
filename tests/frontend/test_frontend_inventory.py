"""Guardrail sull'inventario delle quattro interfacce frontend.

RST-0008 fotografa entrypoint, toolchain, mount e radici asset attuali.
Finché la fusione non è completata, ogni cambiamento strutturale deve essere
esplicito nell'inventario, invece di avvenire in silenzio.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INV = json.loads((ROOT / "frontend_inventory.json").read_text(encoding="utf-8"))


def test_inventario_frontend_copre_esattamente_le_quattro_interfacce() -> None:
    items = INV["interfaces"]
    assert {item["id"] for item in items} == {"erp", "hr", "lotti", "menu"}
    assert len(items) == 4


def test_entrypoint_config_e_asset_root_dichiarati_esistono() -> None:
    for item in INV["interfaces"]:
        assert (ROOT / item["root"]).is_dir(), item
        assert (ROOT / item["entry"]).is_file(), item
        assert (ROOT / item["config"]).is_file(), item
        public_root = item.get("public_root")
        if public_root:
            assert (ROOT / public_root).is_dir(), item


def test_toolchain_dichiarata_corrisponde_ai_package_json() -> None:
    for item in INV["interfaces"]:
        package = json.loads(
            (ROOT / item["root"] / "package.json").read_text(encoding="utf-8")
        )
        scripts = package.get("scripts", {})
        build = scripts.get("build", "")
        if item["toolchain"] == "vite":
            assert "vite" in build, item
            assert "craco" not in build, item
        elif item["toolchain"] == "cra-craco":
            assert "craco" in build, item
            assert "react-scripts" in package.get("dependencies", {}), item
        else:
            raise AssertionError(f"Toolchain non riconosciuta: {item}")


def test_mount_frontend_sono_unici_e_coerenti() -> None:
    mounts = [item["mount"] for item in INV["interfaces"]]
    assert len(mounts) == len(set(mounts))
    assert mounts.count("/") == 1
    assert set(mounts) == {"/", "/hr", "/lotti", "/menu"}


def test_dipendenze_shared_dichiarate_esistono() -> None:
    for item in INV["interfaces"]:
        for shared in item.get("shared", []):
            assert (ROOT / shared).is_dir(), f"{item['id']} -> {shared}"
