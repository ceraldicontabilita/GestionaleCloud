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


def test_nome_anagrafico_nella_descrizione_basta_senza_parola_stipendio():
    result = classifica_destinazione_dipendente(
        {
            "descrizione_originale": (
                "VOSTRA DISPOSIZIONE RIF. 123 FAVORE CERALDI VALERIO "
                "COMPETENZE AGOSTO"
            ),
            "importo": -1400,
        },
        [{
            "id": "dip-valerio",
            "nome": "Valerio",
            "cognome": "Ceraldi",
            "codice_fiscale": "CRLVLR88H14F839O",
        }],
    )
    assert result["destinazione_dipendente"] is True
    assert result["identita_univoca"] is True
    assert result["dipendente_id"] == "dip-valerio"
    assert result["motivo_destinazione"] == "nome_completo_nella_descrizione"


def test_codice_fiscale_identifica_dipendente_anche_senza_nome_o_stipendio():
    result = classifica_destinazione_dipendente(
        {
            "descrizione": "VS.DISP. CRLVLR88H14F839O COMPETENZE 08/2026",
            "importo": -1400,
        },
        [{
            "id": "dip-valerio",
            "nome": "Valerio",
            "cognome": "Ceraldi",
            "codice_fiscale": "CRLVLR88H14F839O",
        }],
    )
    assert result["destinazione_dipendente"] is True
    assert result["identita_univoca"] is True
    assert result["motivo_destinazione"] == "codice_fiscale_dipendente"


def test_omonimi_senza_codice_fiscale_restano_ambigui():
    result = classifica_destinazione_dipendente(
        {"descrizione": "BONIFICO FAVORE ROSSI MARIO", "importo": -1200},
        [
            {"id": "d1", "nome": "Mario", "cognome": "Rossi"},
            {"id": "d2", "nome": "Mario", "cognome": "Rossi"},
        ],
    )
    assert result["destinazione_dipendente"] is False
    assert result["identita_univoca"] is False


def test_codice_fiscale_prevale_sul_nome_in_caso_di_omonimia():
    result = classifica_destinazione_dipendente(
        {
            "descrizione": (
                "VOSTRA DISPOSIZIONE MARIO ROSSI "
                "RSSMRA80A01F839X COMPETENZE"
            ),
            "importo": -1200,
        },
        [
            {
                "id": "d1", "nome": "Mario", "cognome": "Rossi",
                "codice_fiscale": "RSSMRA80A01F839X",
            },
            {
                "id": "d2", "nome": "Mario", "cognome": "Rossi",
                "codice_fiscale": "RSSMRA81A01F839Y",
            },
        ],
    )
    assert result["destinazione_dipendente"] is True
    assert result["identita_univoca"] is True
    assert result["dipendente_id"] == "d1"
    assert result["motivo_destinazione"] == "codice_fiscale_dipendente"


def test_conflitto_iban_codice_fiscale_non_attribuisce_persona_sbagliata():
    result = classifica_destinazione_dipendente(
        {
            "beneficiario": {
                "nome": "Mario Rossi",
                "iban": "IT60X0542811101000000123456",
            },
            "descrizione": "BONIFICO RSSMRA81A01F839Y COMPETENZE",
            "importo": -1200,
        },
        [
            {
                "id": "d1", "nome": "Mario", "cognome": "Rossi",
                "iban": "IT60X0542811101000000123456",
                "codice_fiscale": "RSSMRA80A01F839X",
            },
            {
                "id": "d2", "nome": "Luigi", "cognome": "Bianchi",
                "codice_fiscale": "RSSMRA81A01F839Y",
            },
        ],
    )
    assert result["destinazione_dipendente"] is True
    assert result["identita_univoca"] is False
    assert result["dipendente_id"] is None
    assert result["motivo_destinazione"] == "conflitto_iban_codice_fiscale"


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
