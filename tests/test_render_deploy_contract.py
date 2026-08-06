from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _production_service():
    config = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    services = config.get("services", [])
    assert len(services) == 1
    return services[0]


def test_render_builds_backend_and_frontend_from_source():
    service = _production_service()
    build_command = service["buildCommand"]

    assert service["name"] == "GestionaleCloud"
    assert service["runtime"] == "python"
    assert "pip install -r backend/requirements.txt" in build_command
    assert "npm --prefix frontend install --include=dev --legacy-peer-deps" in build_command
    assert "npm --prefix frontend run build" in build_command


def test_render_serves_the_combined_app_with_health_check():
    service = _production_service()

    assert service["startCommand"] == "uvicorn app.main:app --host 0.0.0.0 --port $PORT"
    assert service["healthCheckPath"] == "/api/health"
