"""Prima Nota: un solo writer (`scritture_contabili.scrivi_movimento`).

CLAUDE.md §23: niente nuovi `insert_one` diretti sui registri di Prima Nota.
L'elenco sotto e' il debito residuo: puo' solo SCENDERE. Quando un punto
passa al motore, toglilo da qui (il test lo pretende).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_DIRETTO = re.compile(
    r"(?:prima_nota_(?:cassa|banca|salari)|COLLECTION_PRIMA_NOTA_\w+)[\"'\]\)]*\]?\s*\.insert_(?:one|many)\("
)

# file -> numero di scritture dirette ancora ammesse (debito noto).
RESIDUO = {
    "app/handlers/prima_nota.py": 1,
    "app/hr/routers/cedolini.py": 2,
    "app/routers/accounting/prima_nota_salari.py": 5,
    "app/routers/prima_nota_module/salari.py": 1,
    "app/routers/prima_nota_module/sync.py": 4,
    "app/services/email_full_download.py": 1,
    "app/services/salari_sync.py": 1,
    "app/services/salari_unificati_v2.py": 1,
}


def _conteggi() -> dict[str, int]:
    out: dict[str, int] = {}
    for f in (ROOT / "app").rglob("*.py"):
        rel = f.relative_to(ROOT).as_posix()
        if "/tests/" in rel or "__pycache__" in rel:
            continue
        n = len(_DIRETTO.findall(f.read_text(encoding="utf-8", errors="replace")))
        if n:
            out[rel] = n
    return out


def test_nessuna_nuova_scrittura_diretta_sulla_prima_nota() -> None:
    trovati = _conteggi()
    nuovi = {f: n for f, n in trovati.items() if n > RESIDUO.get(f, 0)}
    assert not nuovi, (
        f"Scritture dirette su Prima Nota fuori dal motore: {nuovi}. "
        "Usa app.services.scritture_contabili.scrivi_movimento."
    )


def test_il_debito_residuo_segue_la_realta() -> None:
    trovati = _conteggi()
    scesi = {f: (n, trovati.get(f, 0)) for f, n in RESIDUO.items() if trovati.get(f, 0) < n}
    assert not scesi, f"Debito sceso: aggiorna RESIDUO (ammesso, trovato): {scesi}"
