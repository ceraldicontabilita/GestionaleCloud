from pathlib import Path

import json
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
    # Il comando deve restare IDENTICO a quello impostato nella dashboard
    # Render (che non recepisce render.yaml): e' `npm run build` del gestionale
    # a compilare anche le app portate pari pari (frontend_*/) tramite lo
    # script versionato, cosi' nessuna modifica in dashboard e' necessaria.
    assert "npm --prefix frontend install --include=dev --legacy-peer-deps" in build_command
    assert "npm --prefix frontend run build" in build_command
    package = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    assert package["scripts"]["build"] == "vite build && bash ../scripts/build_frontends.sh --apps"
    script = (ROOT / "scripts" / "build_frontends.sh").read_text(encoding="utf-8")
    assert 'if [ "${1:-}" != "--apps" ]; then' in script
    assert "for dir in frontend_*/" in script
    assert 'npm --prefix "$dir" run build' in script
    for app_frontend in ("frontend_lotti", "frontend_menu", "frontend_hr"):
        assert (ROOT / app_frontend / "package.json").is_file(), app_frontend


def test_render_serves_the_combined_app_with_health_check():
    service = _production_service()

    assert service["plan"] == "starter"
    assert service["startCommand"] == (
        "python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT"
    )
    assert service["healthCheckPath"] == "/api/health"
    assert _environment_values(service)["PROCESS_ROLE"] == "combined"
    assert _environment_values(service)["ENABLE_SCHEDULER"] == "true"
    assert "GOOGLE_SHEETS_LEDGER_FOLDER_ID" not in {
        item["key"] for item in service.get("envVars", [])
    }


def test_render_pins_a_python_runtime_compatible_with_rapidocr():
    service = _production_service()
    python_version = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    requirements = (ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8")

    assert _environment_values(service)["PYTHON_VERSION"] == python_version
    assert tuple(map(int, python_version.split(".")[:2])) < (3, 13)
    assert "rapidocr_onnxruntime==1.4.4" in requirements.splitlines()
