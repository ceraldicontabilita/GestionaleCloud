"""Il totale trattenute Zucchetti ha le migliaia: «6.691,15» non e' «691,15».

Busta di cessazione di giugno 2023 (con TFR): competenze 8.528,41, trattenute
6.691,15, netto del mese 1.837,26. La ricerca della coppia trattenute /
competenze partiva a meta' numero e leggeva 691,15; il netto calcolato
diventava 7.837,26 e il vecchio import HR l'aveva salvato come netto.
"""
from app.parsers.busta_paga_multi_template import parse_template_zucchetti_new

TOTALI = "Permessi\n436,32000\n43,33333\n479,65333\nORE\n{tratt}\n{comp}\nResiduo AP\n"


def _totali(tratt, comp):
    return parse_template_zucchetti_new(TOTALI.format(tratt=tratt, comp=comp))["totali"]


def test_le_trattenute_oltre_mille_si_leggono_intere():
    totali = _totali("6.691,15", "8.528,41")
    assert totali["trattenute"] == 6691.15 and totali["competenze"] == 8528.41


def test_le_trattenute_sotto_mille_restano_come_prima():
    totali = _totali("114,71", "1.228,13")
    assert totali["trattenute"] == 114.71 and totali["competenze"] == 1228.13


def test_un_pezzo_di_numero_non_e_una_riga():
    testo = "CAMPANIA\nx 8.733,77\n2.008,77\n"
    assert "trattenute" not in parse_template_zucchetti_new(testo)["totali"]
