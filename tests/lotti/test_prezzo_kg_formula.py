"""
test_prezzo_kg_formula.py
──────────────────────────
Regression test per il bug corretto il 01/07/2026 in aggiorna_dizionario_prodotto
(fatture.py): formula prezzo_kg/quantita_kg SBAGLIATA per prodotti venduti a pezzi
con peso noto (confondeva "peso di UN pezzo" con "peso totale acquistato").
Vedi memory/STATO.md sezione "Bug formula prezzo/kg per prodotti 'a pezzo'".

Tutti i casi "reali" sono presi da righe fattura vere, verificate via GET /fatture?mesi=0
il 01/07/2026 (AP COMMERCIALE, BIG FOOD, F.lli Fiorentino). Nessun valore inventato.
"""
import pytest

from app.lotti.routers.xml_helpers import calcola_prezzo_quantita_kg


def test_burro_a_pezzi_peso_da_testo():
    # PARMAREGGIO BURRO BIO G125 (AP Commerciale, 18/05/2026): 2 pezzi da 125g,
    # prezzo 1.71156/pezzo. Caso originale del bug: quantita_kg deve moltiplicare
    # per i pezzi (non solo prendere il peso di uno), prezzo_kg deve dividere
    # (non moltiplicare per 1000).
    r = calcola_prezzo_quantita_kg(2.0, 1.71156, "PZ", "PARMAREGGIO BURRO BIO   G125")
    assert r["quantita_kg"] == pytest.approx(0.25, abs=1e-4)
    assert r["prezzo_kg"] == pytest.approx(13.6925, abs=1e-3)
    assert r["fonte"] == "testo"
    assert r["tipo_quantita_det"] == "confezioni"


def test_burro_a_pezzi_generalizza_a_confezioni_diverse():
    # PARMAREGGIO BURRO GR.200 (BIG FOOD, 21/11/2025): 16 pezzi da 200g, prezzo 1.89/pezzo.
    # Stesso prodotto/pattern testuale del caso sopra ma quantita/peso diversi: la formula
    # non deve essere hardcoded sul caso "2 pezzi x 125g".
    r = calcola_prezzo_quantita_kg(16.0, 1.89, "PZ", "PARMAREGGIO BURRO GR.200")
    assert r["quantita_kg"] == pytest.approx(3.2, abs=1e-4)
    assert r["prezzo_kg"] == pytest.approx(9.45, abs=1e-3)


def test_salame_peso_variabile_kg_diretto():
    # SALAME NAPOLI MORBIDO VISIONI (AP Commerciale, 02/04/2026): pesato, unita_misura=KG.
    # quantita e' GIA' il peso reale: nessuna moltiplicazione, prezzo_kg=prezzo diretto.
    r = calcola_prezzo_quantita_kg(0.9453, 9.98190000, "KG", "SALAME NAPOLI MORBIDO VISIONI")
    assert r["quantita_kg"] == pytest.approx(0.9453, abs=1e-4)
    assert r["prezzo_kg"] == pytest.approx(9.9819, abs=1e-3)
    assert r["fonte"] == "kg_strutturato"
    assert r["tipo_quantita_det"] == "totale"


def test_porchetta_peso_variabile_kg_diretto():
    # Stesso principio del salame, fornitore/peso/prezzo diversi (non hardcoded).
    r = calcola_prezzo_quantita_kg(1.1, 19.5455, "KG", "PORCHETTA DI ARICCIA IGP")
    assert r["quantita_kg"] == pytest.approx(1.1, abs=1e-4)
    assert r["prezzo_kg"] == pytest.approx(19.5455, abs=1e-3)


def test_olio_confezioni_senza_regola_nota_non_indovina():
    # OLIO EXTRAVERGINE OLIVA L.5 (F.lli Fiorentino): il testo "L.5" NON viene mai
    # interpretato automaticamente come peso — "L." e' anche prefisso comunissimo di
    # numero di LOTTO nei dati reali (es. "AGLIO L.372", "BASILICO L.417291": un pattern
    # generico L-prefisso darebbe falsi positivi su prodotti non liquidi). Senza una
    # regola nota confermata, il fallback e' grezzo (nessuna_info) — comportamento atteso,
    # non un difetto: il prodotto finisce nella coda /normalizzazione/prodotti-senza-peso.
    r = calcola_prezzo_quantita_kg(2.0, 27.50, "LT", "OLIO EXTRAVERGINE OLIVA L.5")
    assert r["fonte"] == "nessuna_info"
    assert r["quantita_kg"] == pytest.approx(2.0, abs=1e-4)


def test_olio_confezioni_con_regola_nota():
    # Stesso prodotto di sopra, ma con la regola già confermata (peso_confezione=5.0L,
    # tipo_quantita="confezioni" — dato reale in dizionario_prodotti, F.lli Fiorentino):
    # quantita=2 bottiglie da 5L, prezzo=27.50/bottiglia -> 10L totali, 5.50 EUR/L.
    regola = {"peso_confezione": 5.0, "unita_confezione": "l", "tipo_quantita": "confezioni"}
    r = calcola_prezzo_quantita_kg(2.0, 27.50, "LT", "OLIO EXTRAVERGINE OLIVA L.5", regola)
    assert r["quantita_kg"] == pytest.approx(10.0, abs=1e-4)
    assert r["prezzo_kg"] == pytest.approx(5.50, abs=1e-3)
    assert r["fonte"] == "regola_nota_confezioni"
    # priorita' 0: non ri-deriva/ri-scrive nulla, la regola esiste gia'
    assert r["peso_confezione_det"] is None


def test_priorita_0_regola_nota_confezioni_vince_su_testo():
    # Se una regola "confezioni" e' gia' nota, vince SEMPRE, anche se il testo di questa
    # specifica riga non contiene piu' l'indicazione di peso (es. fattura abbreviata).
    regola = {"peso_confezione": 0.125, "unita_confezione": "kg", "tipo_quantita": "confezioni"}
    r = calcola_prezzo_quantita_kg(3.0, 1.80, "PZ", "PARMAREGGIO BURRO BIO", regola)
    assert r["quantita_kg"] == pytest.approx(0.375, abs=1e-4)
    assert r["prezzo_kg"] == pytest.approx(14.4, abs=1e-3)
    assert r["fonte"] == "regola_nota_confezioni"


def test_priorita_0_regola_nota_totale_vince_anche_senza_unita_kg():
    # tipo="totale" vince anche se unita_misura di QUESTA fattura non e' "KG": usa
    # quantita/prezzo direttamente, ignora peso_confezione (li' e' solo informativo).
    regola = {"peso_confezione": 1.0, "unita_confezione": "kg", "tipo_quantita": "totale"}
    r = calcola_prezzo_quantita_kg(0.6, 15.0, "PZ", "QUALSIASI TESTO", regola)
    assert r["quantita_kg"] == pytest.approx(0.6, abs=1e-4)
    assert r["prezzo_kg"] == pytest.approx(15.0, abs=1e-3)
    assert r["fonte"] == "regola_nota_totale"


def test_regola_nota_ambigua_senza_tipo_quantita_viene_ignorata():
    # Dato reale (01/07/2026): 802/881 prodotti nel dizionario_prodotti hanno
    # peso_confezione>0 ma tipo_quantita MANCANTE (scritti dal vecchio auto-save prima
    # che questo fix esistesse — ambiguo, poteva essere "totale" o "confezioni").
    # NON va trattata come regola valida: si ricade su KG/testo, che ri-deriva e
    # ri-tagga tipo_quantita correttamente (auto-guarigione), invece di rischiare di
    # applicare la formula sbagliata a un numero storico ambiguo.
    regola_ambigua = {"peso_confezione": 5.0, "unita_confezione": "l"}  # niente tipo_quantita
    r = calcola_prezzo_quantita_kg(0.9453, 9.98190000, "KG", "SALAME NAPOLI MORBIDO VISIONI", regola_ambigua)
    assert r["fonte"] == "kg_strutturato"  # non "regola_nota_*"
    assert r["tipo_quantita_det"] == "totale"  # si ri-tagga per la prossima volta


def test_fallback_nessuna_informazione_non_esplode():
    r = calcola_prezzo_quantita_kg(3.0, 2.5, "PZ", "ARTICOLO GENERICO SENZA PESO")
    assert r["fonte"] == "nessuna_info"
    assert r["quantita_kg"] == pytest.approx(3.0, abs=1e-4)
    assert r["prezzo_kg"] == pytest.approx(2.5, abs=1e-3)


def test_quantita_o_prezzo_invalidi_non_esplode():
    for quantita, prezzo in [(0, 5.0), (5.0, 0), (-1, 5.0)]:
        r = calcola_prezzo_quantita_kg(quantita, prezzo, "PZ", "QUALSIASI")
        assert r["prezzo_kg"] is None
        assert r["quantita_kg"] == 0.0
