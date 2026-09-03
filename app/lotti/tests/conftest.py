"""Configurazione comune dei test Lotti.

I vecchi file ``test_iteration*`` che usano ``requests`` sono collaudi HTTP
contro un backend avviato appositamente: non sono test unitari e non devono
provare per errore a contattare localhost o la produzione. Restano eseguibili
impostando esplicitamente ``REACT_APP_BACKEND_URL``.
"""

import os
from pathlib import Path

import pytest


LIVE_HTTP_TEST_FILES = {
    "test_email_ordini_iter66.py",
    "test_giacenze_iter69.py",
    "test_iteration46_features.py",
    "test_iteration47_features.py",
    "test_iteration48_features.py",
    "test_iteration52_features.py",
    "test_iteration53_features.py",
    "test_iteration54_features.py",
    "test_iteration55_bugfixes.py",
    "test_iteration56_nutritional.py",
    "test_iteration57_bom.py",
    "test_iteration72_bugfixes.py",
    "test_magazzino_bar_iter68.py",
    "test_magazzino_unificato_iter71.py",
    "test_ordini_fornitori_iter70.py",
    "test_ordini_fornitori.py",
    "test_p1_p2_features.py",
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

