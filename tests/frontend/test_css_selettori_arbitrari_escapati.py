"""Guardia: in un file CSS la parentesi quadra di Tailwind va escappata.

Nel JSX una classe si scrive `className="bg-[#3f5a4e]"`. Nel CSS quella stessa
classe e' un SELETTORE, e li' `[` apre un selettore di attributo: `.bg-[#3f5a4e]`
non e' CSS valido. Il compilatore lo dice e butta la regola intera —

    ▲ [WARNING] Expected identifier but found "#3f5a4e" [css-syntax-error]

— otto volte a ogni deploy, nei log di Render del 20/09/2026. Tre di quelle
otto regole erano usate da pagine vere dell'ERP, che quindi rendevano senza il
colore previsto. Le altre cinque non le usava nessuno.

La forma giusta e' `.bg-\\[\\#3f5a4e\\]`. Un avviso di build che si ripete a ogni
deploy smette di essere letto: questa guardia lo trasforma in un test rosso.
"""
import re
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]
CARTELLE = ("frontend", "frontend_hr", "frontend_lotti", "frontend_menu")

# `[#` non preceduto da una barra rovesciata: la quadra e' rimasta nuda.
QUADRA_NUDA = re.compile(r"(?<!\\)\[#")


def _fogli_di_stile():
    for cartella in CARTELLE:
        sorgenti = RADICE / cartella / "src"
        if not sorgenti.is_dir():
            continue
        for foglio in sorgenti.rglob("*.css"):
            if "node_modules" in foglio.parts:
                continue
            yield foglio


def test_nessun_selettore_con_quadra_non_escapata():
    colpevoli = []
    for foglio in _fogli_di_stile():
        for numero, riga in enumerate(
            foglio.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if QUADRA_NUDA.search(riga):
                relativo = foglio.relative_to(RADICE)
                colpevoli.append(f"{relativo}:{numero}: {riga.strip()}")

    assert not colpevoli, (
        "Selettori Tailwind con valore arbitrario non escappati:\n  "
        + "\n  ".join(colpevoli)
        + "\n\nIn un file CSS `[` apre un selettore di attributo: il "
        "compilatore rifiuta la riga e la scarta in silenzio (un semplice "
        "WARNING), quindi la regola non arriva mai in produzione. "
        "Va scritta `.bg-\\[\\#3f5a4e\\]`."
    )
