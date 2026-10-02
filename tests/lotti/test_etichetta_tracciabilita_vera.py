"""L'etichetta del lotto dice lo stato vero della tracciabilita'.

Stampava sempre «TRACCIABILITA' REGISTRATA», anche con ingredienti non
tracciati: la sezione di dettaglio veniva costruita e mai inserita.
"""
from app.lotti.routers.stampa import build_escpos, build_pos_html

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


def test_escpos_usa_larghezza_compatta_senza_spezzare_i_dati_principali():
    lotto = {
        "prodotto": "Cassata Siciliana (variante di: cassattina)",
        "numero_lotto": "CASS.SICI-001-30pz-02102026",
        "pezzi": 30,
        "data_produzione": "02/10/2026",
        "data_scadenza": "05/10/2026",
        "scadenza_abbattuto": "01/12/2026",
        "frigo_numero": "Frigorifero N°2",
        "lotti_fornitori": {
            "lotti_scalati": [{
                "ingrediente": "zucchero semolato",
                "fornitore": "RONDINELLA MARKET S.R.L.",
                "fattura_ref": "18",
                "data_fattura": "05/01/2026",
            }],
        },
    }

    stampa = build_escpos(lotto, ["CEREALI/GLUTINE", "UOVA", "LATTE"], ["zucchero\n semolato"])

    font_a = b"\x1b\x4d\x00"
    font_b = b"\x1b\x4d\x01"
    spaziatura_zero = b"\x1b\x20\x00"
    assert font_a + spaziatura_zero + b"\x1d\x21\x10" in stampa
    assert font_b + spaziatura_zero + b"\x1b\x45\x01PRODOTTO: Cassata Siciliana (variante di: cassattina)\n" in stampa
    assert font_b + spaziatura_zero + b"- zucchero semolato\n" in stampa
    assert font_b + spaziatura_zero + b"RONDINELLA MARKET S.R.L. - Fatt. 18 del 05/01/2026\n" in stampa
    assert b"cassattina)\n" in stampa
    assert b"05/01\n/2026" not in stampa
