"""Guardie audit: CORS Menu e contratto Render."""

from pathlib import Path

import yaml
from starlette.middleware.cors import CORSMiddleware


ROOT = Path(__file__).resolve().parents[2]


def test_menu_cors_non_usa_wildcard_con_credenziali():
    from app.menu.server import app

    cors = [m for m in app.user_middleware if m.cls is CORSMiddleware]
    assert cors, "Menu deve dichiarare CORSMiddleware"
    kwargs = cors[0].kwargs
    origini = kwargs.get("allow_origins") or []
    assert "*" not in origini
    if kwargs.get("allow_credentials"):
        assert all(o != "*" for o in origini)


def test_render_dichiara_pin_hash_admin():
    config = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    keys = {item["key"]: item for item in config["services"][0]["envVars"]}
    assert "PIN_HASH_ADMIN" in keys
    assert keys["PIN_HASH_ADMIN"].get("sync") is False
    assert "value" not in keys["PIN_HASH_ADMIN"]


def test_produzione_verifica_le_quattro_app_su_gestionalecloud():
    testo = (ROOT / ".github" / "workflows" / "produzione.yml").read_text(encoding="utf-8")
    assert "https://gestionalecloud.onrender.com" in testo
    assert "/hr/api/health" in testo
    assert "/menu/api/health" in testo
    assert "/lotti/api/health" in testo
