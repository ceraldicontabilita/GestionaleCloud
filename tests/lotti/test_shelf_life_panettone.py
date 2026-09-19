"""
test_shelf_life_panettone.py
─────────────────────────────
Caso Enzo 23/07/2026: "il panettone artigianale è un prodotto cotto che va
conservato per 3 mesi — non deve darmi un giorno perché c'è l'uovo dentro".
I prodotti a LUNGA CONSERVAZIONE (lievitati da ricorrenza, secchi da forno)
non vengono accorciati dagli ingredienti cotti nell'impasto (uova, latte,
burro); le farciture post-cottura (crema, panna...) accorciano come sempre.
"""
from app.lotti.routers.shelf_life import calcola_scadenza

ING_PANETTONE = ["Farina", "Uova", "Burro", "Zucchero", "Uvetta", "Canditi", "Lievito naturale", "Latte"]


def test_panettone_ambiente_90_giorni():
    r = calcola_scadenza("Panettone Artigianale", ING_PANETTONE, "ambiente")
    assert r["giorni"] == 90, r
    assert r["ingrediente_critico"] is None


def test_panettone_frigo_e_freezer():
    assert calcola_scadenza("Panettone Artigianale", ING_PANETTONE, "frigo")["giorni"] == 90
    assert calcola_scadenza("Panettone Artigianale", ING_PANETTONE, "abbattitore_negativo")["giorni"] == 180


def test_panettone_farcito_con_crema_si_accorcia():
    """La crema aggiunta DOPO la cottura accorcia eccome (prudenza HACCP)."""
    r = calcola_scadenza("Panettone farcito", ING_PANETTONE + ["Crema pasticcera"], "frigo")
    assert r["giorni"] < 90
    assert "crema" in (r["ingrediente_critico"] or "")


def test_biscotti_con_uova_non_scadono_domani():
    r = calcola_scadenza("Biscotti di pasta frolla", ["Farina", "Uova", "Burro", "Zucchero"], "ambiente")
    assert r["giorni"] == 30, r


def test_pandoro_colomba_taralli():
    assert calcola_scadenza("Pandoro", ING_PANETTONE, "ambiente")["giorni"] == 90
    assert calcola_scadenza("Colomba pasquale", ING_PANETTONE, "ambiente")["giorni"] == 60
    assert calcola_scadenza("Taralli sugna e pepe", ["Farina", "Sugna", "Pepe", "Mandorle"], "ambiente")["giorni"] == 30


def test_roccoco_senza_accento():
    assert calcola_scadenza("Roccoco", ["Farina", "Mandorle", "Uova"], "ambiente")["giorni"] == 30


def test_prodotti_freschi_restano_prudenti():
    """La regola vale SOLO per i prodotti a lunga conservazione: una torta
    con panna resta corta come prima."""
    r = calcola_scadenza("Torta di compleanno", ["Pan di Spagna", "Panna fresca", "Uova"], "frigo")
    assert r["giorni"] <= 4
