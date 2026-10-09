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
RESIDUO: dict[str, int] = {}


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


_DINAMICO = re.compile(r"\bdb\[\s*(?!\")(?!')(?!backup)[A-Za-z_]\w*\s*\]\.insert_(?:one|many)\(")
_FILE_REGISTRI = (
    "app/routers/prima_nota_module/sync.py",
    "app/routers/prima_nota_module/cassa.py",
    "app/routers/prima_nota_module/banca.py",
    "app/routers/prima_nota_module/manutenzione.py",
    "app/routers/sync_relazionale.py",
    "app/routers/rapido.py",
    "app/services/data_propagation.py",
)


def test_nei_file_dei_registri_niente_insert_su_collezione_variabile() -> None:
    colpevoli = [
        f for f in _FILE_REGISTRI
        if _DINAMICO.search((ROOT / f).read_text(encoding="utf-8"))
    ]
    assert not colpevoli, f"insert su collezione in variabile (Prima Nota?): {colpevoli}"
