"""Un solo posto, e deve restare uno solo.

Due guardie diverse, tutte e due nate dallo stesso guasto.

**La prima**: le parole che significano «pagata» esistono in due copie, una in
Python e una in JavaScript, perché lo schermo e il server devono rispondere
uguale. Due copie divergono sempre — è successo con i cataloghi degli alert,
con i due parser dei cedolini, con le tre liste di `STATI_CHIUSI`. Qui il test
le confronta a ogni giro.

**La seconda**: chi chiede `fattura.pagato` a mano ricrea il difetto. Su 2.555
fatture quel campo esiste su 46: leggerlo direttamente vuol dire dichiarare
non pagate 639 fatture da 311.838,20 €, e filtrarci sopra con
`{"pagato": {"$ne": True}}` vuol dire prenderle tutte dentro, perché su un
campo assente quel confronto passa sempre.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.services.stato_pagamento_fattura import (
    PAROLE_ANNULLATA,
    PAROLE_DA_PAGARE,
    PAROLE_PAGATA,
    PAROLE_PARZIALE,
)

RADICE = Path(__file__).resolve().parents[2]
GEMELLO_JS = RADICE / "frontend/src/utils/statoFattura.js"
CANONICO_PY = "app/services/stato_pagamento_fattura.py"

# Moduli a cui la lettura diretta è concessa, con il motivo.
DEROGHE = {
    CANONICO_PY,                                  # è lui che definisce la risposta
    "app/services/riallinea_pagamenti_fatture.py",  # scrive i campi, non li interroga
}


def _lista_js(nome: str) -> set[str]:
    testo = GEMELLO_JS.read_text(encoding="utf-8")
    m = re.search(rf"export const {nome} = \[(.*?)\];", testo, re.S)
    assert m, f"{nome} non c'è più in {GEMELLO_JS.name}"
    return set(re.findall(r"'([^']+)'", m.group(1)))


def test_le_parole_di_python_e_javascript_sono_le_stesse():
    assert _lista_js("PAROLE_PAGATA") == set(PAROLE_PAGATA)
    assert _lista_js("PAROLE_ANNULLATA") == set(PAROLE_ANNULLATA)
    assert _lista_js("PAROLE_PARZIALE") == set(PAROLE_PARZIALE)
    assert _lista_js("PAROLE_DA_PAGARE") == set(PAROLE_DA_PAGARE)


SOSPETTO = re.compile(r'["\']pa(?:gato|id)["\']\s*:\s*\{\s*["\']\$ne["\']')

#: Filtri a mano su collezioni **dove il campo esiste davvero**, contati il
#: 20/09/2026: `scadenziario_fornitori` ce l'ha su 848 righe su 848, `cedolini`
#: su 3.256 su 3.256. Lì `$ne` funziona. Il numero può solo scendere.
TETTO_ALTRE_COLLEZIONI = 28


def _filtri_a_mano() -> tuple[list[str], list[str]]:
    """(quelli sulle fatture, quelli altrove) — le fatture non ne ammettono."""
    su_fatture: list[str] = []
    altrove: list[str] = []
    for percorso in sorted((RADICE / "app").rglob("*.py")):
        if "__pycache__" in str(percorso):
            continue
        relativo = str(percorso.relative_to(RADICE))
        if relativo in DEROGHE:
            continue
        righe = percorso.read_text(encoding="utf-8", errors="ignore").splitlines()
        for i, riga in enumerate(righe):
            if not SOSPETTO.search(riga):
                continue
            # A quale collezione sta chiedendo? Si guarda intorno alla query.
            intorno = "\n".join(righe[max(0, i - 12):i + 6])
            voce = f"{relativo}:{i + 1}"
            if re.search(r'db\[\s*["\']invoices["\']|Collections\.INVOICES', intorno):
                su_fatture.append(voce)
            else:
                altrove.append(voce)
    return su_fatture, altrove


def test_nessuno_filtra_le_fatture_su_pagato_a_mano():
    """Su `invoices` quel campo esiste su 46 righe su 2.555: `$ne` passa sempre."""
    su_fatture, _ = _filtri_a_mano()
    assert not su_fatture, (
        "Filtro su `pagato`/`paid` scritto a mano contro `invoices`: su 2.509 "
        "fatture quel campo non c'è, quindi il confronto passa sempre e ti "
        "riporta dentro anche le 639 già pagate. Usa FILTRO_NON_PAGATE (o "
        f"con_non_pagate) di app/services/stato_pagamento_fattura.py. {su_fatture}"
    )


def test_i_filtri_sulle_altre_collezioni_non_crescono():
    """Lì il campo c'è davvero (848/848, 3.256/3.256): si tollerano, non crescono."""
    _, altrove = _filtri_a_mano()
    assert len(altrove) <= TETTO_ALTRE_COLLEZIONI, (
        f"filtri a mano su `pagato`: {len(altrove)}, tetto {TETTO_ALTRE_COLLEZIONI}. "
        "Prima di aggiungerne uno, conta sul database quante righe di quella "
        f"collezione hanno davvero il campo. {altrove}"
    )


def test_una_sola_definizione_di_cosa_sia_chiusa():
    """Le tre `STATI_CHIUSI` parallele devono restare fuse in una."""
    definizioni = []
    for percorso in sorted((RADICE / "app").rglob("*.py")):
        if "__pycache__" in str(percorso):
            continue
        relativo = str(percorso.relative_to(RADICE))
        if relativo == CANONICO_PY:
            continue
        for n, riga in enumerate(percorso.read_text(encoding="utf-8", errors="ignore")
                                 .splitlines(), 1):
            if re.match(r"\s*STATI_CHIUSI\s*(:|=)(?!\s*$)", riga) and "import" not in riga:
                definizioni.append(f"{relativo}:{n}")
    assert not definizioni, (
        "`STATI_CHIUSI` ridefinita fuori dal posto canonico: tre liste diverse di "
        "cosa voglia dire «pagata» erano il difetto di partenza. Importa "
        f"PAROLE_PAGATA da app/services/stato_pagamento_fattura.py. {definizioni}"
    )


def test_il_frontend_non_chiede_piu_pagato_da_solo():
    """Ogni schermo passa da `ePagata`, sennò le 639 tornano invisibili."""
    colpevoli = []
    for base in ("frontend/src",):
        for percorso in sorted((RADICE / base).rglob("*.js*")):
            if any(x in str(percorso) for x in ("node_modules", ".test.", "statoFattura")):
                continue
            for n, riga in enumerate(percorso.read_text(encoding="utf-8", errors="ignore")
                                     .splitlines(), 1):
                # `f.pagato` su una fattura; le sanzioni del noleggio hanno un
                # loro `pagato` che non c'entra con le fatture.
                if re.search(r"\b(?:f|fattura|invoice)\.pagato\b", riga):
                    colpevoli.append(f"{percorso.relative_to(RADICE)}:{n}")
    assert not colpevoli, (
        "Lettura diretta di `.pagato` su una fattura: esiste su 46 righe su 2.555. "
        f"Usa `ePagata()` di frontend/src/utils/statoFattura.js. {colpevoli}"
    )
