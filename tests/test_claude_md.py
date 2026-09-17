"""Guardia su CLAUDE.md: resta un file di regole e stato attuale.

La cronaca datata delle sessioni va in ``memoria/diario/``: qui dentro un
capitolo per giornata fa crescere il file senza limite e lascia i fatti
superati accanto a quelli che li correggono (successo fra il 14 e il
17/09/2026: 1.479 righe, una decina di contraddizioni).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTO = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
MAX_RIGHE = 650


def test_tetto_di_righe() -> None:
    righe = TESTO.count("\n") + 1
    assert righe <= MAX_RIGHE, (
        f"CLAUDE.md ha {righe} righe (tetto {MAX_RIGHE}): sposta la cronaca in "
        "memoria/diario/AAAA-MM-GG.md e riscrivi «Stato attuale» sul posto"
    )


def test_nessun_capitolo_datato() -> None:
    datati = re.findall(r"^#{2,4} \d{1,2}(?:-\d{1,2})?/\d{2}/\d{4}.*$", TESTO, re.MULTILINE)
    assert not datati, f"Titoli datati: vanno nel diario, non qui: {datati}"


def test_data_intestazione_non_precede_lo_stato() -> None:
    # reviewed_at del marcatore lo gestisce scripts/refresh_markdown_docs.py:
    # qui si controlla la data scritta a mano.
    ita = re.search(r"^Aggiornato il (\d{2})/(\d{2})/(\d{4})", TESTO, re.MULTILINE)
    stato = re.search(r"^## Stato attuale \(al (\d{2})/(\d{2})/(\d{4})", TESTO, re.MULTILINE)
    assert ita and stato
    assert ita.groups()[::-1] >= stato.groups()[::-1], (
        "«Stato attuale» è più recente di «Aggiornato il»: aggiorna l'intestazione"
    )


def test_sezioni_vive_e_diario_presenti() -> None:
    for titolo in ("## Stato attuale", "## Aperto", "## Diario"):
        assert titolo in TESTO, titolo
    for citato in re.findall(r"`(memoria/diario/[^`]+\.md)`", TESTO):
        if "AAAA" in citato:
            continue
        assert (ROOT / citato).is_file(), citato
