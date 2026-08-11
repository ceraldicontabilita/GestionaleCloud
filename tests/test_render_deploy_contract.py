from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _production_service():
    config = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    services = config.get("services", [])
    assert len(services) == 1
    return services[0]


def _environment_values(service):
    return {
        item["key"]: item.get("value")
        for item in service.get("envVars", [])
        if "value" in item
    }


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

    assert service["startCommand"] == "python -m app.process_supervisor"
    assert service["healthCheckPath"] == "/api/health"


def test_render_pins_a_python_runtime_compatible_with_rapidocr():
    service = _production_service()
    python_version = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    requirements = (ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8")

    assert _environment_values(service)["PYTHON_VERSION"] == python_version
    assert tuple(map(int, python_version.split(".")[:2])) < (3, 13)
    assert "rapidocr_onnxruntime==1.4.4" in requirements.splitlines()
