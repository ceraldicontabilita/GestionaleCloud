"""Le fatture fornitore non hanno scadenza (decisione del titolare, 19/09/2026):
il campo `giorni_pagamento` non si crea piu' e non si offre nel form."""
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]
CREATORI = [
    "app/routers/suppliers_module/base.py",
    "app/routers/suppliers_module/import_export.py",
    "app/routers/invoices/fatture_upload.py",
    "app/routers/paypal_api.py",
    "frontend/src/pages/Fornitori.jsx",
]


def test_nessun_punto_scrive_giorni_pagamento():
    for rel in CREATORI:
        assert "giorni_pagamento" not in (RADICE / rel).read_text(encoding="utf-8"), rel
