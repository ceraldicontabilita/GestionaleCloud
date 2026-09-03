"""
test_valore_affidabile.py
──────────────────────────
Regression test per il fix del 02/07/2026 ("Birra Corona 0,37€"): un min()
alla cieca su prezzi storici fa vincere per sempre un singolo prezzo-fattura
errato come "miglior prezzo". Il motore anti-outlier (utils.valore_affidabile)
sostituisce 3 implementazioni divergenti trovate in listino.py
(sync_da_fatture, _calcola_righe, import fattura) e prodotti_master.py
(rebuild comparatore 90gg) — un solo motore, testato una volta sola.
"""
from app.lotti.routers.utils import valore_affidabile


def test_lista_semplice_scarta_outlier():
    # scenario reale: cartone Corona 0,37€ (errore fattura) vs prezzi normali
    assert valore_affidabile([0.37, 23.5, 24.3]) == 23.5


def test_lista_semplice_prezzo_genuinamente_basso_resta():
    # nessun outlier (tutti entro 8x): il minimo vero resta il minimo
    assert valore_affidabile([20.0, 23.5, 24.3]) == 20.0


def test_lista_vuota_ritorna_none():
    assert valore_affidabile([]) is None


def test_singolo_elemento_non_rilevabile():
    # un solo valore: nessun termine di paragone, non c'è modo di sapere se è
    # un outlier — limite onesto, documentato in STATO.md.
    assert valore_affidabile([0.37]) == 0.37


def test_dict_per_fornitore_scarta_outlier():
    prezzi = {"DI COSMO": 0.37, "SUD INGROSSO": 23.80}
    fornitore, prezzo = valore_affidabile(list(prezzi.items()), chiave=1)
    assert fornitore == "SUD INGROSSO"


def test_dict_per_fornitore_prezzo_genuino_resta():
    prezzi = {"DI COSMO": 20.0, "SUD INGROSSO": 23.80}
    fornitore, prezzo = valore_affidabile(list(prezzi.items()), chiave=1)
    assert fornitore == "DI COSMO"


def test_lista_di_dict_con_chiave_prezzo():
    # forma usata da prodotti_master._esegui_rebuild (prezzi_recenti)
    prezzi_recenti = [
        {"prezzo": 0.37, "fornitore": "DI COSMO"},
        {"prezzo": 23.5, "fornitore": "SUD INGROSSO"},
        {"prezzo": 24.3, "fornitore": "LANGELLOTTI"},
    ]
    migliore = valore_affidabile(prezzi_recenti, chiave="prezzo")
    assert migliore["fornitore"] == "SUD INGROSSO"
