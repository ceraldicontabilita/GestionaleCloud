"""Gli interruttori dei giri SumUp e PayPal: assenti = acceso, «false» = spento."""
import pytest

from app.scheduler import _sync_acceso


@pytest.mark.parametrize("valore,atteso", [
    (None, True), ("true", True), ("1", True), ("", True),
    ("false", False), ("FALSE", False), ("0", False), (" no ", False),
])
def test_interruttore(monkeypatch, valore, atteso):
    if valore is None:
        monkeypatch.delenv("SUMUP_SYNC_ENABLED", raising=False)
    else:
        monkeypatch.setenv("SUMUP_SYNC_ENABLED", valore)
    assert _sync_acceso("SUMUP_SYNC_ENABLED") is atteso
