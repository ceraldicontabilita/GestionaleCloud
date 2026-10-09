"""Bug trovato nell'audit funzionale del 15/07/2026: la voce "carburante"
in app/services/categorizzazione_contabile.py hardcodava deducibilita_ires/
irap a 100 ("se veicolo strumentale"), ma nessuna logica in questo file
distingue mai i due casi (veicolo strumentale vs uso promiscuo): restava
sempre 100%, in contrasto con le altre 4 fonti indipendenti del gestionale
(CENTRI_COSTO in learning_machine_cdc.py, classificazione_costi.py,
regole_categorizzazione.py, calcolo_imposte.py), che usano tutte 20% —
il valore corretto per un'attività con auto aziendali a uso promiscuo
(art. 164 TUIR, caso tipico bar/pasticceria).

Scenario concreto del bug: una fattura carburante da 100€ veniva mostrata
deducibile al 100% (90€ di variazione IRES "risparmiata" erroneamente)
da questo motore, mentre il calcolo IRES previsionale (calcolo_imposte.py)
e il Bilancio dettagliato (bilancio.py) la deducevano correttamente solo
al 20% — due numeri diversi per la stessa fattura a seconda della pagina."""
from app.services.categorizzazione_contabile import categorizza_fattura_completa


def test_carburante_deducibile_al_20_per_cento_come_le_altre_fonti():
    esito = categorizza_fattura_completa(
        linee=[{"descrizione": "Rifornimento benzina Eni Station", "prezzo_totale": 100.0}],
        fornitore="Eni Station",
    )

    riga = esito["dettaglio_linee"][0]
    assert riga["percentuale_deducibilita_ires"] == 20
    assert riga["percentuale_deducibilita_irap"] == 20
    assert esito["totale_deducibile_ires"] == 20.0
    assert esito["totale_deducibile_ires"] != 100.0
