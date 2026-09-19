"""
test_farciture_riparto.py
──────────────────────────
Regression test per la divisione proporzionale nei gusti (richiesta Enzo
03/07/2026: "prendo 40 cornetti perché ne voglio fare 8 per tipo" — se in
Colazione sono impostati 4+4+4+4+4=20, prelevare 40 raddoppia ogni gusto).
La somma finale deve tornare SEMPRE esattamente pezzi_totali, qualunque
sia il resto della divisione (funzione pura, nessuna rete/DB).
"""
from app.lotti.routers.farciture import _riparto_proporzionale


def test_multiplo_esatto_raddoppia():
    quote = {"vuoto": 4, "crema": 4, "cioccolato": 4, "marmellata": 4, "crema e amarena": 4}
    assert _riparto_proporzionale(quote, 40) == {
        "vuoto": 8, "crema": 8, "cioccolato": 8, "marmellata": 8, "crema e amarena": 8
    }


def test_somma_sempre_esatta_anche_non_divisibile():
    quote = {"vuoto": 4, "crema": 4, "cioccolato": 4, "marmellata": 4, "crema e amarena": 4}
    for pezzi in range(1, 47):
        risultato = _riparto_proporzionale(quote, pezzi)
        assert sum(risultato.values()) == pezzi, (pezzi, risultato)
        assert all(v >= 0 for v in risultato.values())


def test_proporzioni_sbilanciate():
    quote = {"vuoto": 2, "crema": 8, "cioccolato": 4, "marmellata": 4, "crema e amarena": 2}
    risultato = _riparto_proporzionale(quote, 10)
    assert sum(risultato.values()) == 10
    assert risultato["crema"] > risultato["vuoto"]  # crema pesa 4x vuoto nel preset


def test_zero_pezzi_richiesti():
    quote = {"vuoto": 4, "crema": 4}
    assert _riparto_proporzionale(quote, 0) == {"vuoto": 0, "crema": 0}


def test_nessuna_proporzione_configurata():
    assert _riparto_proporzionale({"vuoto": 0, "crema": 0}, 10) == {"vuoto": 0, "crema": 0}
