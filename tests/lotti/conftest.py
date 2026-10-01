"""Configurazione comune dei test Lotti.

I pochi collaudi HTTP manuali rimasti usano ``requests`` contro un backend
avviato appositamente. Non sono test unitari e non devono provare per errore a
contattare localhost o la produzione. Restano eseguibili impostando
esplicitamente ``REACT_APP_BACKEND_URL``.

Questi file restano temporaneamente perché coprono comportamenti attivi che
non hanno ancora un equivalente isolato nella suite automatica.
"""

import os
from pathlib import Path

import pytest


LIVE_HTTP_TEST_FILES = {
    "test_email_ordini_iter66.py",
    "test_iteration56_nutritional.py",
    "test_iteration57_bom.py",
    "test_ordini_fornitori.py",
    "test_prezzi_alert_iter67.py",
}


def pytest_collection_modifyitems(items):
    if os.environ.get("REACT_APP_BACKEND_URL", "").strip():
        return

    live_skip = pytest.mark.skip(
        reason=(
            "collaudo HTTP live non eseguito: impostare REACT_APP_BACKEND_URL "
            "verso un backend di prova dedicato"
        )
    )
    for item in items:
        if Path(str(item.fspath)).name in LIVE_HTTP_TEST_FILES:
            item.add_marker(live_skip)

