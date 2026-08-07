"""Recupero storico POS dall'estratto conto, senza usare XML RT."""

from app.services.scritture_contabili import raggruppa_accrediti_pos_per_giorno


def test_somma_circuiti_stesso_giorno_e_unifica_copie():
    inter = {
        "id": "ec-inter", "data": "2026-08-04", "importo": 900.25,
        "rapporto": "BPM",
        "descrizione_originale": (
            "INC.POS CARTE CREDIT - NUMIA-INTER DEL 03/08/26 "
            "PDV 3757283/00011 CERALDI CAFFE NA"
        ),
    }
    copia_inter = {**inter, "id": "ec-inter-copia"}
    bancomat = {
        "id": "ec-bncmt", "data": "2026-08-04", "importo": 729.25,
        "rapporto": "BPM",
        "descrizione_originale": (
            "INCAS. TRAMITE P.O.S - NUMIA-BNCMT DEL 03/08/26 "
            "PDV 3757283/00012 CERALDI CAFFE' NA"
        ),
    }

    gruppi = raggruppa_accrediti_pos_per_giorno([inter, copia_inter, bancomat])

    assert gruppi == {
        "2026-08-03": {
            "totale": 1629.50,
            "estratto_conto_ids": ["ec-bncmt", "ec-inter"],
        }
    }


def test_esclude_commissioni_e_righe_senza_giorno_vendita():
    gruppi = raggruppa_accrediti_pos_per_giorno([
        {
            "id": "commissione", "data": "2026-08-04", "importo": 12.0,
            "descrizione": "COMMISSIONI NUMIA DEL 03/08/26",
        },
        {
            "id": "generica", "data": "2026-08-04", "importo": 100.0,
            "descrizione": "ACCREDITO NUMIA",
        },
    ])
    assert gruppi == {}
