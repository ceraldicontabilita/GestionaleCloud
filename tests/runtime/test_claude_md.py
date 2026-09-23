"""Guardia sui documenti canonici del repository.

Sono ammessi solo CLAUDE.md, README.md e PIANO_RISTRUTTURAZIONE.md. Il 18/09/2026
i 116 .md sparsi in docs/, memoria/ e .github/ sono stati cancellati: erano
diari e audit datati che rendevano impossibile capire quali regole fossero in
vigore. Il piano di ristrutturazione è invece un registro operativo esplicitamente
richiesto dal titolare e deve restare aggiornato insieme al codice. La guardia
continua a impedire la ricrescita di documentazione parallela.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TESTO = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
MAX_RIGHE = 900
AMMESSI = {"CLAUDE.md", "README.md", "PIANO_RISTRUTTURAZIONE.md"}


def _markdown_tracciati() -> set[str]:
    out = subprocess.run(
        ["git", "ls-files", "*.md"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return {riga.strip().replace("\\", "/") for riga in out.stdout.splitlines() if riga.strip()}


def test_solo_documenti_canonici_nel_repository() -> None:
    trovati = _markdown_tracciati()
    assert trovati == AMMESSI, (
        "I soli .md ammessi sono CLAUDE.md, README.md e PIANO_RISTRUTTURAZIONE.md. In piu' o in meno: "
        f"{sorted(trovati.symmetric_difference(AMMESSI))}"
    )


def test_tetto_di_righe() -> None:
    righe = TESTO.count("\n") + 1
    assert righe <= MAX_RIGHE, (
        f"CLAUDE.md ha {righe} righe (tetto {MAX_RIGHE}): riscrivi «Stato attuale» "
        "sul posto invece di aggiungere, e togli le voci chiuse da «Aperto»"
    )


def test_nessun_capitolo_datato() -> None:
    datati = re.findall(r"^#{2,4} \d{1,2}(?:-\d{1,2})?/\d{2}/\d{4}.*$", TESTO, re.MULTILINE)
    assert not datati, f"La cronaca datata sta in git, non qui: {datati}"


def test_data_intestazione_non_precede_lo_stato() -> None:
    ita = re.search(r"^Aggiornato il (\d{2})/(\d{2})/(\d{4})", TESTO, re.MULTILINE)
    stato = re.search(r"^## Stato attuale \(al (\d{2})/(\d{2})/(\d{4})", TESTO, re.MULTILINE)
    assert ita and stato
    assert ita.groups()[::-1] >= stato.groups()[::-1], (
        "«Stato attuale» e' piu' recente di «Aggiornato il»: aggiorna l'intestazione"
    )


def test_sezioni_vive_presenti() -> None:
    for titolo in ("## Stato attuale", "## Aperto", "## Come si tiene questo file"):
        assert titolo in TESTO, titolo


def test_nessun_sito_spento_nel_codice() -> None:
    """I domini morti erano rimasti nei workflow di verifica della produzione e
    in un link di Lotti: il collaudo interrogava un host spento e il bottone
    «Gestionale» portava nel vuoto. Qui non devono tornare.

    `impresasemplice.online` non e' in elenco: e' un dominio vivo dello stesso
    servizio Render (verificato il 23/09/2026 con `/lotti/api/health`)."""
    spenti = (
        "ceraldiapp.it",
        "appdipendenti.onrender.com",
        "lotti-frontend.onrender.com",
        "lotti-backend-2wwb.onrender.com",
        "lotti-backend-f2fg.onrender.com",
    )
    # app/lotti/tests e app/hr/tests sono i test originali delle app portate
    # pari pari: restano com'erano, non sono codice dell'ERP.
    cartelle = ("app", "scripts", "frontend/src", "frontend_hr/src", "frontend_lotti/src",
                "frontend_menu/src", "frontend_shared", "page_catalog.json", "render.yaml",
                ":!app/lotti/tests", ":!app/hr/tests")
    out = subprocess.run(
        ["git", "grep", "-lI", "-e", spenti[0], *sum((["-e", d] for d in spenti[1:]), []),
         "--", *cartelle],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    colpevoli = [r for r in out.stdout.splitlines() if r.strip()]
    assert not colpevoli, f"Domini spenti ancora citati nel codice: {colpevoli}"
