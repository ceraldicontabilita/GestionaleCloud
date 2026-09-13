from app.routers.prima_nota_module.cassa import _movimento_e_bancario_errato_in_cassa


def test_pagamento_fattura_cassa_esplicito_non_e_bancario():
    movimento = {
        "source": "sync_fatture",
        "categoria": "Fatture",
        "descrizione": "Pagamento Fatt. 77/A - Fornitore",
        "fattura_id": "fatt-77",
        "riferimento": "FATT-fatt-77",
        "metodo_pagamento_effettivo": "cassa",
    }

    assert _movimento_e_bancario_errato_in_cassa(movimento) is False


def test_fattura_senza_metodo_non_viene_cancellata_per_deduzione():
    movimento = {
        "source": "sync_fatture",
        "categoria": "Fatture",
        "descrizione": "Pagamento Fatt. 77/A - Fornitore",
        "fattura_id": "fatt-77",
    }

    assert _movimento_e_bancario_errato_in_cassa(movimento) is False


def test_movimento_con_evidenza_bancaria_reale_viene_segnalato():
    movimento = {
        "source": "csv_import",
        "categoria": "Fatture",
        "descrizione": "BONIFICO SEPA FATTURA 77/A",
        "fattura_id": "fatt-77",
    }

    assert _movimento_e_bancario_errato_in_cassa(movimento) is True
