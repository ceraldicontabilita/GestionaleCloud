"""Un guasto che non si vede non esiste, finché non costa.

Il modo in cui questo gestionale ha sbagliato, ogni volta, è lo stesso: **il
silenzio**. La chiave letta con il nome sbagliato non solleva, torna `None`.
L'evento che non raggiunge nessun handler non solleva, non fa niente. E
`except Exception: pass` è la forma scritta di quel silenzio: qualunque cosa
vada storta lì dentro, nessuno lo saprà mai.

Il 19/09/2026 ce n'erano **235** in `app/`, di cui **42 su percorsi che
toccano i soldi**. Fra quelli:

- l'evento `CORRISPETTIVO_REGISTRATO` che, se non partiva, lasciava il
  corrispettivo fuori dalla prima nota — senza una riga di log;
- l'audit di sicurezza di una cancellazione **massiva** di fatture;
- la simulazione della liquidazione TFR: se falliva, tredicesima,
  quattordicesima e ferie restavano a zero e le rate uscivano più basse del
  dovuto, in silenzio;
- `anni_esclusi` non interpretabile: il filtro veniva ignorato e il risultato
  comprendeva anni che andavano esclusi.

Due confini, diversi per severità:

1. **Sui soldi: zero gestori muti a eccezione ampia.** Nessuna deroga. Se una
   cosa può fallire dove si contano euro, deve lasciare una riga.
2. **Altrove: una cricchetta.** Il numero può solo scendere. Non si chiede di
   sistemarli tutti oggi; si chiede che non ne nascano di nuovi.

Restano legittimi i gestori a **eccezione stretta** (`ValueError`,
`TypeError`…) attorno a una conversione con un default dichiarato: lì il
`pass` *è* la decisione, non la sua assenza.

Terza forma di silenzio, trovata scrivendo questa guardia: un `logger.warning`
con più segnaposto che argomenti. Non scrive la riga — solleva mentre la
scrive, ed è `logging` a inghiottire l'errore. Ce n'erano due, tutti e due su
avvisi che contano (il tetto dei 50.000 documenti in manutenzione prima nota,
il buco di corrispettivi recuperato da Drive).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]
APP = RADICE / "app"

# Un modulo "tocca i soldi" se il suo percorso contiene una di queste parole.
SOLDI = (
    "contab", "banca", "bank", "fattur", "invoice", "prima_nota", "piano_conti",
    "iva", "f24", "paghe", "cedolin", "tfr", "bonific", "pagament",
    "corrispettiv", "pos_", "riconcili", "scrittur", "partite",
)

# Eccezioni "ampie": prendono tutto, quindi ingoiano anche ciò che non ti aspetti.
AMPIE = {"Exception", "BaseException"}

# Cricchetta sui moduli che non toccano i soldi: può solo scendere.
TETTO_ALTROVE = 123


def _sul_denaro(percorso: Path) -> bool:
    return any(s in str(percorso).lower() for s in SOLDI)


def _muti() -> tuple[list[str], list[str]]:
    """(muti sui soldi, muti altrove) — solo quelli a eccezione ampia."""
    soldi: list[str] = []
    altrove: list[str] = []
    for percorso in sorted(APP.rglob("*.py")):
        if "__pycache__" in str(percorso):
            continue
        try:
            albero = ast.parse(percorso.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for nodo in ast.walk(albero):
            if not isinstance(nodo, ast.ExceptHandler):
                continue
            # una docstring da sola non è un'azione: conta come corpo vuoto
            corpo = [
                c for c in nodo.body
                if not (isinstance(c, ast.Expr)
                        and isinstance(c.value, ast.Constant)
                        and isinstance(c.value.value, str))
            ]
            if len(corpo) != 1 or not isinstance(corpo[0], ast.Pass):
                continue
            ampia = nodo.type is None or ast.unparse(nodo.type) in AMPIE
            if not ampia:
                continue
            voce = f"{percorso.relative_to(RADICE)}:{nodo.lineno}"
            (soldi if _sul_denaro(percorso) else altrove).append(voce)
    return soldi, altrove


def test_nessun_guasto_muto_dove_si_contano_gli_euro() -> None:
    soldi, _ = _muti()
    assert not soldi, (
        "`except Exception: pass` su un percorso che tocca i soldi. Scrivi cosa "
        "si perde, non «errore»: chi legge il log deve capire quale dato non "
        f"c'è più. {soldi}"
    )


def test_il_silenzio_altrove_puo_solo_calare() -> None:
    _, altrove = _muti()
    assert len(altrove) <= TETTO_ALTROVE, (
        f"gestori muti a eccezione ampia: {len(altrove)}, tetto {TETTO_ALTROVE}. "
        "Non se ne aggiungono: dai una riga di log a quello nuovo."
    )


def test_il_tetto_segue_la_realta() -> None:
    """Se sono scesi, il tetto scende con loro: altrimenti la cricchetta molla."""
    _, altrove = _muti()
    assert len(altrove) >= TETTO_ALTROVE - 5, (
        f"i muti altrove sono scesi a {len(altrove)}: abbassa TETTO_ALTROVE a "
        "questo numero, sennò il margine si riapre da solo"
    )


def test_nessun_except_nudo_in_tutta_app() -> None:
    """`except:` prende anche Ctrl-C e l'arresto del processo: è sempre un bug."""
    nudi = []
    for percorso in sorted(APP.rglob("*.py")):
        if "__pycache__" in str(percorso):
            continue
        try:
            albero = ast.parse(percorso.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for nodo in ast.walk(albero):
            if isinstance(nodo, ast.ExceptHandler) and nodo.type is None:
                nudi.append(f"{percorso.relative_to(RADICE)}:{nodo.lineno}")
    assert not nudi, (
        "`except:` senza tipo cattura anche KeyboardInterrupt e SystemExit: "
        f"scrivi almeno `except Exception`. {nudi}"
    )


SEGNAPOSTO = re.compile(r"%[-+ #0]*[\d*]*(?:\.\d+)?[hlL]?([diouxXeEfFgGcrsa%])")
LIVELLI = {"debug", "info", "warning", "error", "critical", "exception"}


def test_ogni_riga_di_log_ha_gli_argomenti_che_promette() -> None:
    """Più `%s` che argomenti e la riga non viene scritta: solleva mentre la scrive."""
    guasti = []
    for percorso in sorted(APP.rglob("*.py")):
        if "__pycache__" in str(percorso):
            continue
        try:
            albero = ast.parse(percorso.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for nodo in ast.walk(albero):
            if not (isinstance(nodo, ast.Call)
                    and isinstance(nodo.func, ast.Attribute)
                    and nodo.func.attr in LIVELLI
                    and not nodo.keywords):  # exc_info=... cambia il conteggio
                continue
            if not nodo.args or not isinstance(nodo.args[0], ast.Constant):
                continue
            testo = nodo.args[0].value
            if not isinstance(testo, str):
                continue
            attesi = sum(1 for m in SEGNAPOSTO.finditer(testo) if m.group(1) != "%")
            forniti = len(nodo.args) - 1
            # Un messaggio senza segnaposto e senza argomenti va benissimo;
            # se ne ha uno solo dei due, la riga si perde o mente.
            if attesi != forniti:
                guasti.append(
                    f"{percorso.relative_to(RADICE)}:{nodo.lineno} "
                    f"{attesi} segnaposto, {forniti} argomenti: {testo[:60]!r}")
    assert not guasti, (
        "Riga di log che non verrà mai scritta: i `%s` e gli argomenti non "
        f"tornano. {guasti}"
    )
