from app.routers.bonifici_module.classification import classifica_destinazione_dipendente
from app.routers.bonifici_module.associazioni import _valuta_fattura_bonifico


def test_bonifico_dipendente_per_iban_non_e_fattura():
    bonifico = {
        "beneficiario": {"nome": "Mario Rossi", "iban": "IT60 X054 2811 1010 0000 0123 456"},
        "causale": "competenze mese marzo",
        "importo": 1000,
    }
    dipendenti = [{
        "id": "d1", "nome": "Mario", "cognome": "Rossi",
        "iban": "IT60X0542811101000000123456",
    }]
    result = classifica_destinazione_dipendente(bonifico, dipendenti)
    assert result["destinazione_dipendente"] is True
    assert result["motivo_destinazione"] == "iban_dipendente"


def test_importo_identico_senza_prova_fornitore_non_autorizza_fattura():
    result = _valuta_fattura_bonifico(
        {"beneficiario": {"nome": "Mario Rossi"}, "importo": 1000, "causale": "stipendio marzo"},
        {"supplier_name": "Fornitore Srl", "total_amount": 1000, "invoice_number": "77"},
    )
    assert result["compatibile"] is False
    assert result["evidenze"] == ["importo_esatto"]


def test_importo_e_identita_fornitore_autorizzano_candidato():
    result = _valuta_fattura_bonifico(
        {"beneficiario": {"nome": "Fornitore Srl"}, "importo": 1000, "causale": "saldo fattura 77"},
        {"supplier_name": "Fornitore S.r.l.", "total_amount": 1000, "invoice_number": "77"},
    )
    assert result["compatibile"] is True
    assert "identita_fornitore" in result["evidenze"]


def test_importo_e_fornitore_senza_numero_fattura_non_autorizzano():
    result = _valuta_fattura_bonifico(
        {"beneficiario": {"nome": "Fornitore Srl"}, "importo": 1000, "causale": "saldo fornitore"},
        {"supplier_name": "Fornitore S.r.l.", "total_amount": 1000, "invoice_number": "77"},
    )
    assert result["compatibile"] is False
    assert "numero_fattura_in_causale" not in result["evidenze"]


def test_un_centesimo_di_differenza_non_autorizza_bonifico():
    result = _valuta_fattura_bonifico(
        {"beneficiario": {"nome": "Fornitore Srl"}, "importo": 1000.01, "causale": "saldo fattura 77"},
        {"supplier_name": "Fornitore S.r.l.", "total_amount": 1000.00, "invoice_number": "77"},
    )
    assert result["compatibile"] is False
    assert "importo_esatto" not in result["evidenze"]
