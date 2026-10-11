from datetime import datetime, timezone
import pytest
from app.hr.routers import turni


@pytest.mark.parametrize(
    "instant,expected",
    [
        (datetime(2026, 10, 11, 22, 30, tzinfo=timezone.utc), "2026-10-12"),
        (datetime(2026, 10, 11, 20, 30, tzinfo=timezone.utc), "2026-10-05"),
    ],
)
def test_settimana_aziendale_segue_la_data_italiana(monkeypatch, instant, expected):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)

    monkeypatch.setattr(turni, "datetime", Clock)
    assert turni._lunedi_corrente() == expected
