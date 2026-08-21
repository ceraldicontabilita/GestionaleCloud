import json

import pytest

from render_workflows import main


class _Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return json.dumps(
            {
                "status": "healthy",
                "database": "connected",
                "storage": "drive_sheets",
                "hydrated_rows": 27623,
                "hydration_errors": 0,
                "deploy_commit": "abc12345",
            }
        ).encode()


def test_fetch_production_health_returns_a_bounded_summary(monkeypatch):
    monkeypatch.setattr(main, "urlopen", lambda *_args, **_kwargs: _Response())

    result = main.fetch_production_health()

    assert result["status"] == "healthy"
    assert result["storage"] == "drive_sheets"
    assert result["hydrated_rows"] == 27623
    assert result["hydration_errors"] == 0
    assert result["deploy_commit"] == "abc12345"
    assert "checked_at" in result


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("status", "degraded", "Servizio non healthy"),
        ("storage", "unexpected", "Archivio inatteso"),
        ("hydration_errors", 2, "Errori idratazione presenti"),
    ],
)
def test_fetch_production_health_rejects_invalid_state(
    monkeypatch, field, value, message
):
    response = _Response()
    original_read = response.read

    def read():
        payload = json.loads(original_read())
        payload[field] = value
        return json.dumps(payload).encode()

    response.read = read
    monkeypatch.setattr(main, "urlopen", lambda *_args, **_kwargs: response)

    with pytest.raises(RuntimeError, match=message):
        main.fetch_production_health()
