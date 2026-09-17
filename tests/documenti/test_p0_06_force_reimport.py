"""P0.6 — L'endpoint estratto conto "force-reimport" NON cancella dati: il
contratto (docstring + risposta) deve dichiarare un import additivo con dedup,
non una cancellazione. Prima il docstring prometteva di cancellare l'anno."""
from pathlib import Path


def test_docstring_non_promette_cancellazione():
    src = Path("app/routers/bank/estratto_conto.py").read_text(encoding="utf-8")
    # la vecchia frase fuorviante non deve più esserci
    assert "Cancella TUTTI i record degli anni presenti nel CSV" not in src
    # deve dichiarare esplicitamente che NON cancella
    assert "NON cancella" in src
    # la risposta continua a riportare record_cancellati: 0 (veritiero)
    assert '"record_cancellati": 0' in src


def test_esiste_alias_onesto_reimport():
    src = Path("app/routers/bank/estratto_conto.py").read_text(encoding="utf-8")
    assert '@router.post("/reimport")' in src
