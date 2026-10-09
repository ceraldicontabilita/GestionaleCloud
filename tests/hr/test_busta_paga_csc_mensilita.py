"""La 13ª/14ª delle buste CSC si riconosce dalla sua voce, non solo dalla testata.

Busta reale di luglio 2020 («Quattordicesima 2020»): l'unica competenza e'
«852 14A MENSILITA' 57,33+ 8,08017 463,24+», netto 324,00. Il lettore
guardava solo le prime 80 righe e la voce cadeva dopo: la busta risultava
«mensile», e la rilettura dal PDF (28/09/2026) avrebbe riclassificato 36
buste giuste come mensili.
"""
from app.parsers.busta_paga_multi_template import _detect_tipo_cedolino

TESTATA = "\n".join(f"riga di testata {i}" for i in range(90))


def _busta(*voci):
    return TESTATA + "\n" + "\n".join(voci) + "\nTOTALE TRATTENUTE 139,84-\n"


def test_la_14a_csc_con_la_sola_sua_voce_e_una_quattordicesima():
    testo = _busta("852 14A MENSILITA' 57,33+ 8,08017 463,24+",
                   "999 RETRIBUZIONE T.F.R. 100,00 463,24+")
    assert _detect_tipo_cedolino(testo) == "quattordicesima"


def test_la_13a_csc_con_la_sola_sua_voce_e_una_tredicesima():
    assert _detect_tipo_cedolino(_busta("851 13A MENSILITA' 100,00+ 8,08017 808,02+")) == "tredicesima"


def test_la_voce_accanto_alla_retribuzione_resta_mensile():
    testo = _busta("001 RETRIBUZIONE ORDINARIA 172,00+ 8,08017 1.389,79+",
                   "852 14A MENSILITA' 57,33+ 8,08017 463,24+")
    assert _detect_tipo_cedolino(testo) == "mensile"


def test_un_rateo_non_e_la_voce_della_mensilita():
    assert _detect_tipo_cedolino(_busta("001 RETRIBUZIONE 172,00+ 8,08017 1.389,79+",
                                        "RATEO 14A MENSILITA' 115,82")) == "mensile"


def test_la_13a_csc_scritta_senza_lettera_e_una_tredicesima():
    """Busta reale di dicembre 2018: «850 13 MENSILITA' 86,00+ 8,44173 725,99+»."""
    assert _detect_tipo_cedolino(_busta("850 13 MENSILITA' 86,00+ 8,44173 725,99+")) == "tredicesima"


def test_la_cig_con_il_rateo_di_13a_resta_mensile():
    """Busta reale di settembre 2020 (CIG pagata dall'INPS più il rateo di 13ª)."""
    testo = _busta("1621 CIG /ASS ORD. PAGAMENTO DIRETTO 65,00+ 75,33 347,10+",
                   "858 RATEO 13A MENSILITA' 30,00+ 8,18168 245,45+")
    assert _detect_tipo_cedolino(testo) == "mensile"
