"""Un modulo che nessuno importa non è codice: è peso che confonde.

Il 19/09/2026 in `app/` c'erano sette moduli mai raggiunti da nessun import —
fra cui `app/schemas/f24_parser.py`, un intero motore di matching F24 che
nemmeno si caricava (`from schemas.accounting_rules`: pacchetto inesistente),
e `app/config/azienda.py`, gemello morto di `app/lotti/azienda.py` che pure
intimava «USARE SEMPRE QUESTE COSTANTI». Nessuno se ne accorgeva perché
cercare un import è un lavoro che nessuno rifà a mano.

Questa guardia è una **cricchetta**: la lista può solo accorciarsi. Chi
aggiunge un modulo deve agganciarlo a qualcosa; chi stacca l'ultimo lettore di
un modulo lo toglie nello stesso commit.

Il censimento fallisce in due modi, e tutti e due li ho fatti quel giorno:
- **import relativi non risolti** (`from .routers import dipendenti`): dava
  per morti 61 moduli invece di 14, compreso un router da 2.759 righe montato
  in `app/hr/main.py`;
- **import dinamici non visti** (`__import__("app.scripts.migra_...")`): dava
  per morti i sei script di migrazione, che `scripts/verifica_migrazioni_
  produzione.py` carica per nome.
Per questo si guarda **tutto** il repository, non solo `app/` e `tests/`, e si
cercano anche le stringhe `"app.qualcosa"`.
"""
from __future__ import annotations

import ast
import re
from functools import lru_cache
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]
ESCLUSI = ("__pycache__", ".claude", "node_modules", ".git")

# Moduli orfani tollerati, con il motivo. Può solo accorciarsi.
TOLLERATI = {
    # Unico codice che sa leggere `gestionale.blobs` (216 PDF, 4 MB). Nessun
    # documento cita una chiave `sha256:`, quindi l'archivio è già scollegato:
    # o lo si riaggancia, o si tolgono tabella e modulo insieme. Finché i dati
    # sono lì, la chiave per rileggerli resta.
    "app/services/blob_store.py",
}


@lru_cache(maxsize=1)
def _sorgenti() -> tuple[Path, ...]:
    return tuple(
        p for p in RADICE.rglob("*.py")
        if not any(parte in ESCLUSI for parte in p.relative_to(RADICE).parts)
    )


def _nome_modulo(percorso: Path) -> str:
    return str(percorso.relative_to(RADICE).with_suffix("")).replace("/", ".")


@lru_cache(maxsize=1)
def _importati(sorgenti: tuple[Path, ...]) -> frozenset[str]:
    visti: set[str] = set()
    for percorso in sorgenti:
        testo = percorso.read_text(encoding="utf-8", errors="ignore")
        pacchetto = str(percorso.parent.relative_to(RADICE)).replace("/", ".")
        try:
            albero = ast.parse(testo)
        except SyntaxError:
            albero = None
        if albero is not None:
            for nodo in ast.walk(albero):
                if isinstance(nodo, ast.Import):
                    visti.update(alias.name for alias in nodo.names)
                elif isinstance(nodo, ast.ImportFrom):
                    if nodo.level:  # import relativo: va risolto sul pacchetto
                        parti = pacchetto.split(".")
                        base = (
                            ".".join(parti[: len(parti) - (nodo.level - 1)])
                            if nodo.level > 1
                            else pacchetto
                        )
                        radice = f"{base}.{nodo.module}" if nodo.module else base
                    else:
                        radice = nodo.module or ""
                    if radice:
                        visti.add(radice)
                        visti.update(f"{radice}.{a.name}" for a in nodo.names)
        # import dinamici: __import__("app.x"), importlib, tabelle di nomi
        visti.update(re.findall(r"[\"']((?:app|scripts)\.[A-Za-z0-9_.]+)[\"']", testo))
    return frozenset(visti)


@lru_cache(maxsize=1)
def _orfani() -> frozenset[str]:
    sorgenti = _sorgenti()
    visti = _importati(sorgenti)
    orfani = set()
    for percorso in sorgenti:
        relativo = percorso.relative_to(RADICE)
        if relativo.parts[0] != "app" or percorso.name == "__init__.py":
            continue
        nome = _nome_modulo(percorso)
        if nome in visti or any(v.startswith(nome + ".") for v in visti):
            continue
        orfani.add(str(relativo))
    return frozenset(orfani)


def test_nessun_modulo_orfano_oltre_i_tollerati() -> None:
    nuovi = _orfani() - TOLLERATI
    assert not nuovi, (
        "Moduli in `app/` che nessuno importa: agganciali a chi li deve usare "
        f"oppure toglili nello stesso commit. {sorted(nuovi)}"
    )


def test_la_lista_dei_tollerati_non_cresce() -> None:
    """Se un tollerato non è più orfano, va tolto dalla lista: è la cricchetta."""
    risolti = TOLLERATI - _orfani()
    assert not risolti, (
        "Questi moduli ora hanno un lettore: togli la deroga da TOLLERATI. "
        f"{sorted(risolti)}"
    )


def test_il_censimento_vede_gli_import_dinamici() -> None:
    """Prova del bug che mi ha fatto dare per morti sei script vivi."""
    visti = _importati(_sorgenti())
    assert "app.scripts.migra_f24_unificato" in visti, (
        "`scripts/verifica_migrazioni_produzione.py` carica gli script di "
        "migrazione per nome: se non li vediamo, li cancelliamo per errore"
    )


def test_il_censimento_risolve_gli_import_relativi() -> None:
    """Prova del bug che mi ha fatto dare per morto un router da 2.759 righe."""
    orfani = _orfani()
    assert "app/hr/routers/employees/dipendenti.py" not in orfani, (
        "`app/hr/main.py` monta questo router con un import relativo: se non "
        "lo risolviamo, il censimento lo dichiara morto"
    )
