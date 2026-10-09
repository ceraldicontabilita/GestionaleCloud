"""I prodotti finiti comprati non devono entrare nel vocabolario ingredienti.

Nella regex c'erano caratteri backspace (0x08) al posto dei confini di parola
`\\b`: «tappi» e «babà» non combaciavano mai e prendevano un canonico da
ingrediente, finendo nel FIFO delle ricette.
"""
from pathlib import Path

import pytest

from app.lotti.routers.schede_tecniche import RX_PRODOTTO_FINITO

SORGENTE = Path(__file__).resolve().parents[2] / "app/lotti/routers/schede_tecniche.py"


@pytest.mark.parametrize("testo", ["TAPPI SFOGLIA 40G", "tappo al cioccolato", "BABA' MIGNON", "Babà al rum"])
def test_prodotti_finiti_riconosciuti(testo):
    assert RX_PRODOTTO_FINITO.search(testo)


@pytest.mark.parametrize("testo", ["Tappeto antiscivolo", "Babbo Natale di cioccolato"])
def test_confini_di_parola(testo):
    assert not RX_PRODOTTO_FINITO.search(testo)


def test_nessun_carattere_di_controllo_nel_sorgente():
    assert "\x08" not in SORGENTE.read_text(encoding="utf-8")
