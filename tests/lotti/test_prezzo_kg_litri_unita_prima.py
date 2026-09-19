"""
test_prezzo_kg_litri_unita_prima.py
────────────────────────────────────
Regression per il bug trovato dall'audit del 05/07/2026: il motore prezzi
dell'IMPORT (estrai_quantita_da_descrizione → calcola_prezzo_quantita_kg in
routers/xml_helpers.py) NON riconosceva i litri/ml scritti con l'UNITÀ PRIMA
del numero ("OLIO LT.5", "LATTE LT 1,5", "SUCCO ML200"). La riga finiva in
'nessuna_info' e il prezzo del CONTENITORE veniva preso come €/kg: un olio da
5 litri a €40 risultava a 40 €/kg invece di 8 €/l. Silenzioso, superava il
sanity check. Vedi memory/STATO.md.

Le bevande in CL (già gestite) e i pesi KG/G restano invariati: sono qui come
guardia anti-regressione.
"""
import pytest

from app.lotti.routers.xml_helpers import (
    estrai_quantita_da_descrizione,
    calcola_prezzo_quantita_kg,
)


@pytest.mark.parametrize("descrizione,valore,unita", [
    # litri con unità "LT" prima del numero (il bug corretto)
    ("OLIO EXTRA VERGINE LT.5 X4", 5.0, "l"),
    ("OLIO GIRASOLE LT.10", 10.0, "l"),
    ("LATTE INTERO LT 1,5", 1.5, "l"),
    ("ACQUA NAT. LT 1,5 X6", 1.5, "l"),
    # ml con unità prima (succhi/bibite)
    ("SUCCO ACE ML200 CTX24", 200.0, "ml"),
    ("BIBITA ML330", 330.0, "ml"),
    # invariati: già corretti prima del fix, non devono cambiare
    ("BIRRA PERONI CL33X24", 33.0, "cl"),
    ("BIRRA CORONA 35,5CL X24", 35.5, "cl"),
    ("FARINA 00 KG.25", 25.0, "kg"),
    ("ZUCCHERO SEMOLATO KG 1", 1.0, "kg"),
    ("MOZZARELLA G125", 125.0, "g"),
    # KG deve vincere anche se c'è una L nel testo
    ("L. 5 KG PATATE", 5.0, "kg"),
])
def test_estrazione_unita(descrizione, valore, unita):
    assert estrai_quantita_da_descrizione(descrizione) == (valore, unita)


@pytest.mark.parametrize("descrizione", [
    # il singolo "L." è prefisso di numero LOTTO: NON deve diventare litri
    "AGLIO L.372",
    "BASILICO L.417291",
    "PREZZEMOLO L. 88",
    "OLIO EXTRAVERGINE OLIVA L.5",  # senza regola nota resta non interpretato
])
def test_lotto_non_diventa_litri(descrizione):
    # nessuno di questi deve essere letto come volume: o è un peso vero altrove
    # nel testo, o resta (1, "pz") → fallback 'nessuna_info' a valle.
    val, unita = estrai_quantita_da_descrizione(descrizione)
    assert unita != "l"


def test_olio_5l_prezzo_al_litro_non_a_bottiglia():
    # Olio 5L, 2 confezioni a €40/confezione. Prima: prezzo_kg=40 (nessuna_info).
    r = calcola_prezzo_quantita_kg(2.0, 40.0, "PZ", "OLIO EXTRA VERGINE LT.5 X4")
    assert r["fonte"] == "testo"
    assert r["prezzo_kg"] == pytest.approx(8.0, abs=1e-3)
    assert r["quantita_kg"] == pytest.approx(10.0, abs=1e-3)


def test_latte_al_litro():
    r = calcola_prezzo_quantita_kg(6.0, 1.20, "PZ", "LATTE INTERO LT 1,5")
    assert r["prezzo_kg"] == pytest.approx(0.8, abs=1e-3)
    assert r["quantita_kg"] == pytest.approx(9.0, abs=1e-3)
