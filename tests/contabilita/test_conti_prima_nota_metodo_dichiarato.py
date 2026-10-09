"""Il conto di tesoreria di una riga dichiarata segue il metodo, mai BPM d'ufficio."""
from app.services.bonifica_prima_nota_conti import campi_conto_mancanti


def _riga(metodo, **extra):
    return {"id": "r", "tipo": "uscita", "categoria": "Fatture", "importo": 100,
            "source": "report_pagamenti_titolare", "metodo_pagamento": metodo, **extra}


def test_banca_e_assegno_su_bpm():
    assert campi_conto_mancanti("banca", _riga("banca"))["conto_contabile"] == "19.01.01"
    assert campi_conto_mancanti("banca", _riga("assegno"))["conto_contabile"] == "19.01.01"


def test_carta_sumup_sulla_mastercard():
    campi = campi_conto_mancanti("banca", _riga("carta", descrizione="Pagata con carta SumUp"))
    assert campi["conto_contabile"] == "19.01.05"


def test_carta_senza_indicazione_resta_senza_conto_di_tesoreria():
    campi = campi_conto_mancanti("banca", _riga("carta"))
    assert "conto_contabile" not in campi
    assert campi["conto_tesoreria_da_definire"] is True
    assert campi["conto_contropartita"]
    # idempotente: al secondo giro niente da scrivere sul conto
    secondo = campi_conto_mancanti("banca", {**_riga("carta"), **campi})
    assert "conto_contabile" not in secondo and "conto_tesoreria_da_definire" not in secondo


def test_riga_non_dichiarata_prende_il_conto_del_registro():
    campi = campi_conto_mancanti("cassa", {"id": "c", "tipo": "uscita", "categoria": "Fatture",
                                           "importo": 10, "source": "conferma_provvisori"})
    assert campi["conto_contabile"] == "19.03.03"
