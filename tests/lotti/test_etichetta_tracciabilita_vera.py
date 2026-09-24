"""L'etichetta del lotto dice lo stato vero della tracciabilita'.

Stampava sempre «TRACCIABILITA' REGISTRATA», anche con ingredienti non
tracciati: la sezione di dettaglio veniva costruita e mai inserita.
"""
from app.lotti.routers.stampa import build_pos_html

LOTTO = {"prodotto": "Sfogliatella", "numero_lotto": "L1"}


def test_ingredienti_non_tracciati_lo_dice():
    html = build_pos_html({**LOTTO, "lotti_fornitori": {"lotti_scalati": [{"fornitore": "X"}],
                                                       "ingredienti_non_trovati": ["Ricotta"]}}, [], ["Ricotta"])
    assert "INCOMPLETA" in html and "Ricotta" in html
    assert "TRACCIABILITÀ REGISTRATA" not in html


def test_tracciato_tutto():
    html = build_pos_html({**LOTTO, "lotti_fornitori": {"lotti_scalati": [{"fornitore": "X"}]}}, [], ["Farina"])
    assert "TRACCIABILITÀ REGISTRATA" in html


def test_senza_lotti_fornitori_non_dichiara_niente():
    html = build_pos_html(LOTTO, [], ["Farina"])
    assert "TRACCIABILITÀ REGISTRATA" not in html and "in elaborazione" in html
