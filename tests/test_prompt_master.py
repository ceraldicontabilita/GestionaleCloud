"""Guardie sulla specifica normativa unica di GestionaleCloud."""

from __future__ import annotations

import re
from pathlib import Path

from scripts import genera_prompt_master as master


ROOT = Path(__file__).resolve().parents[1]
PROMPT = (ROOT / "PROMPT_MASTER.md").read_text(encoding="utf-8")


def test_prompt_master_copre_catalogo_fogli_e_regole_atomiche():
    assert len(master.PAGE_PURPOSES) == 76
    assert set(master.PAGE_PURPOSES) == set(range(1, 77))
    assert len(master.SHEETS) == 30
    normalized = re.sub(r"\s+", " ", PROMPT)
    for required in (
        "in:anywhere",
        "Europe/Rome",
        "operation_id",
        "Scegli fattura",
        "PARTENOPAY/",
        "CODICI TRIBUTO/",
        "QUIETANZE/",
        "DICHIARAZIONI/",
        "Divieti assoluti",
    ):
        assert required in normalized


def test_prompt_master_elenca_tutte_le_variabili_senza_valori_segreti():
    names = set(master.settings_variables()) | set(master.direct_environment_names())
    assert names
    assert all(f"`{name}`" in PROMPT for name in names)

    for name in master.settings_variables():
        if master.sensitive(name) == "segreta":
            row = next(line for line in PROMPT.splitlines() if line.startswith(f"| `{name}` |"))
            assert "valore non riportato" in row


def test_prompt_master_elenca_l_intera_superficie_endpoint_e_le_cartelle_drive():
    endpoints = master.parse_endpoints()
    assert endpoints
    assert all(f"`{row['method']} {row['path']}`" in PROMPT for row in endpoints)

    folder_names = {
        name
        for name in set(master.settings_variables()) | set(master.direct_environment_names())
        if ("DRIVE" in name or "GDRIVE" in name) and "FOLDER" in name
    }
    assert folder_names
    assert all(f"| `{name}` |" in PROMPT for name in folder_names)
