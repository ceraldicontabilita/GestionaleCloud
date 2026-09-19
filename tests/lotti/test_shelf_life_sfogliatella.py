"""
test_shelf_life_sfogliatella.py
────────────────────────────────
Regression test per calcola_scadenza (routers/shelf_life.py). Bug segnalato
da Enzo 20/07/2026 sul lotto Sfogliatella Riccia: l'ingrediente generico
"uova" sovrascriveva la scadenza-prodotto già corretta ("sfogliatella" in
congelatore: 90gg/3 mesi) con un valore peggiore (uova generiche: 60gg).
Il frigo (non congelata) era stato calibrato a 1 giorno da fonti web, poi
corretto a 3 giorni dallo stesso Enzo sullo stesso lotto ("1 GIORNI DI
SCADENZA è BREVE METTI 3 GIORNI") — la sua esperienza pratica di titolare
prevale sulla stima da fonti generiche. Funzione pura: nessuna rete/DB.
"""
from app.lotti.routers.shelf_life import calcola_scadenza


def _ingredienti_sfogliatella():
    return ["semola", "uova", "zucchero semolato", "strutto", "canditi", "sale fino"]


def test_sfogliatella_congelata_tre_mesi_non_sovrascritta_da_uova_generiche():
    out = calcola_scadenza(
        nome_prodotto="Sfogliatella Riccia",
        ingredienti=_ingredienti_sfogliatella(),
        metodo_conservazione="abbattitore_negativo",
    )
    assert out["giorni"] == 90
    # prodotto-driven, non un ingrediente a peggiorarla
    assert out["ingrediente_critico"] is None


def test_sfogliatella_in_frigo_scade_in_tre_giorni():
    out = calcola_scadenza(
        nome_prodotto="Sfogliatella Riccia",
        ingredienti=_ingredienti_sfogliatella(),
        metodo_conservazione="frigo",
    )
    assert out["giorni"] == 3


def test_prodotto_non_cotto_in_forno_uova_crude_restano_penalizzanti():
    # Una mousse (mai cotta dopo l'aggiunta delle uova) deve restare più
    # restrittiva delle uova "cotte": la regola PRODOTTI_COTTI_IN_FORNO non
    # deve applicarsi qui.
    out = calcola_scadenza(
        nome_prodotto="Mousse al cioccolato",
        ingredienti=["uova", "cioccolato"],
        metodo_conservazione="abbattitore_negativo",
    )
    assert out["giorni"] == 60
    assert out["ingrediente_critico"] == "uova"


def test_ingrediente_non_puo_allungare_oltre_il_default_prodotto():
    # Un ingrediente meno deperibile del default-prodotto non deve MAI
    # allungare la scadenza oltre quanto la categoria prodotto già prevede
    # (regola prudenziale: si prende sempre il minimo, mai il massimo).
    out = calcola_scadenza(
        nome_prodotto="Mousse al cioccolato",
        ingredienti=["burro"],  # burro: frigo 14gg, più lungo del default mousse (3gg)
        metodo_conservazione="frigo",
    )
    assert out["giorni"] == 3
