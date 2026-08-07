"""Regressioni: PDF stipendio e banca non devono produrre match casuali."""
from datetime import datetime
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.routers.bonifici_module.pdf_parser import (
    extract_filename_metadata,
    extract_transfers_from_text,
)
from app.routers.bonifici_module.riconciliazione import (
    trova_movimento_bancario_univoco,
)
from app.services.bonifici_pdf_ingest import seleziona_salario_univoco
from app.services.payment_document_links import (
    collega_bonifico_fatture,
    payment_document_ref,
    seleziona_fatture_bonifico,
    valuta_fattura_bonifico,
)


def test_nome_e_mese_pagamento_dal_filename_nei_due_ordini():
    primo = extract_filename_metadata("Verdi Paolo bonifico marzo.pdf")
    secondo = extract_filename_metadata("bonifico marzo Neri Lucia1.pdf")
    assert primo == {
        "beneficiario_nome": "Verdi Paolo",
        "mese_pagamento_file": 3,
        "anno_pagamento_file": None,
    }
    assert secondo["beneficiario_nome"] == "Neri Lucia"
    assert secondo["mese_pagamento_file"] == 3


def test_parser_pdf_usa_campi_etichettati_e_filename():
    testo = """
    Data esecuzione: 04/04/2026
    Importo bonifico: EUR 1.234,56
    Causale: stipendio marzo 2026
    Ordinante: IMPRESA TEST SRL
    """
    parsed = extract_transfers_from_text(
        testo, filename="Rossi Mario bonifico marzo 2026.pdf"
    )[0]
    assert parsed["importo"] == 1234.56
    assert parsed["beneficiario"]["nome"] == "Rossi Mario"
    assert parsed["periodo_mese"] == 3
    assert parsed["periodo_anno"] == 2026
    assert parsed["mese_pagamento_file"] == 3
    assert isinstance(parsed["data"], datetime)


def test_parser_distinta_stipendi_bpm_non_scambia_colonne():
    testo = """
    Distinta Stipendi - Sintetico
    Tot. distinta:
    1.234,56 EUR
    Data esecuzione:
    04/04/2026
    Beneficiario
    IBAN beneficiario
    Descrizione causale
    Importo
    TEST DIPENDENTE
    IT60X0542811101000000123456
    TEST DIPENDENTE ACC STIPENDIO
    1.234,56 EUR
    """
    parsed = extract_transfers_from_text(
        testo, filename="Test Dipendente bonifico aprile.pdf"
    )[0]

    assert parsed["importo"] == 1234.56
    assert parsed["beneficiario"]["nome"] == "TEST DIPENDENTE"
    assert parsed["beneficiario"]["iban"] == "IT60X0542811101000000123456"
    assert parsed["causale"] == "TEST DIPENDENTE ACC STIPENDIO"
    assert parsed["causale"] != parsed["beneficiario"]["nome"]
    assert isinstance(parsed["data"], datetime)


def test_parser_distinta_bpm_con_beneficiario_intercalato_conserva_causale():
    parsed = extract_transfers_from_text(
        """
        Data esecuzione: 02/04/2026
        Tot. distinta: 600,00 EUR
        Beneficiario
        PARISI ANTONIO
        IBAN beneficiario
        Descrizione causale
        Importo
        IT60X0542811101000000123456
        POCCI SALVATORE
        600,00 EUR
        """,
        filename="bonifico marzo Parisi Antonio.pdf",
    )[0]
    assert parsed["beneficiario"]["nome"] == "PARISI ANTONIO"
    assert parsed["causale"] == "POCCI SALVATORE"
    assert parsed["importo"] == 600.0


def test_parser_importo_dopo_etichetta_in_layout_a_colonne():
    parsed = extract_transfers_from_text(
        """
        Data operazione
        Beneficiario
        Descrizione causale
        IBAN
        Importo
        02/04/2026
        TEST DIPENDENTE
        ACCONTO STIPENDIO
        IT60X0542811101000000123456
        850,00 EUR
        """,
        filename="Test Dipendente bonifico aprile.pdf",
    )[0]
    assert parsed["importo"] == 850.0
    assert parsed["beneficiario"]["nome"] == "Test Dipendente"


def test_bonifico_marzo_senza_competenza_associa_busta_febbraio():
    parsed = extract_transfers_from_text(
        """
        Data esecuzione: 04/03/2026
        Importo bonifico: EUR 900,00
        Beneficiario: Verdi Paolo
        Causale: pagamento emolumenti
        """,
        filename="Verdi Paolo bonifico marzo.pdf",
    )[0]
    righe = [
        {"id": "feb", "dipendente": "PAOLO VERDI", "importo_busta": 900.0,
         "mese": 2, "anno": 2026, "riconciliato": False},
        {"id": "mar", "dipendente": "PAOLO VERDI", "importo_busta": 900.0,
         "mese": 3, "anno": 2026, "riconciliato": False},
    ]
    assert parsed["periodo_mese"] is None
    assert parsed["mese_pagamento_file"] == 3
    assert seleziona_salario_univoco(parsed, righe)["id"] == "feb"


def test_salario_richiede_nome_importo_e_periodo_esatti():
    bonifico = {
        "importo": 1234.56,
        "beneficiario": {"nome": "Rossi Mario"},
        "periodo_mese": 3,
        "periodo_anno": 2026,
    }
    righe = [
        {"id": "ok", "dipendente": "MARIO ROSSI", "importo_busta": 1234.56,
         "mese": 3, "anno": 2026, "riconciliato": False},
        {"id": "mese-errato", "dipendente": "MARIO ROSSI", "importo_busta": 1234.56,
         "mese": 2, "anno": 2026, "riconciliato": False},
        {"id": "nome-errato", "dipendente": "BIANCHI LUCA", "importo_busta": 1234.56,
         "mese": 3, "anno": 2026, "riconciliato": False},
    ]
    assert seleziona_salario_univoco(bonifico, righe)["id"] == "ok"


def test_pdf_acconto_si_associa_entro_il_residuo():
    bonifico = {
        "importo": 1000.0,
        "data": "2026-04-02",
        "beneficiario": {"nome": "Carotenuto Antonella"},
        "causale": "Carotenuto Antonella acconto stipendio",
    }
    righe = [{
        "id": "marzo", "dipendente": "CAROTENUTO ANTONELLA",
        "importo_busta": 1430.0, "mese": 3, "anno": 2026,
        "riconciliato": False,
    }]
    assert seleziona_salario_univoco(bonifico, righe)["id"] == "marzo"


def test_pdf_con_beneficiario_e_causale_di_due_dipendenti_resta_da_verificare():
    bonifico = {
        "importo": 600.0,
        "data": "2026-04-02",
        "beneficiario": {"nome": "Parisi Antonio"},
        "causale": "Pocci Salvatore",
    }
    righe = [
        {"id": "parisi", "dipendente": "PARISI ANTONIO", "importo_busta": 1485.0,
         "mese": 3, "anno": 2026, "riconciliato": False},
        {"id": "pocci", "dipendente": "POCCI SALVATORE", "importo_busta": 600.0,
         "mese": 3, "anno": 2026, "riconciliato": False},
    ]
    assert seleziona_salario_univoco(bonifico, righe) is None


def test_salario_ambiguo_non_viene_scelto_per_ordine_database():
    bonifico = {
        "importo": 900.0,
        "beneficiario": {"nome": "Rossi Mario"},
    }
    righe = [
        {"id": "uno", "dipendente": "ROSSI MARIO", "importo_busta": 900.0,
         "mese": 1, "anno": 2026, "riconciliato": False},
        {"id": "due", "dipendente": "ROSSI MARIO", "importo_busta": 900.0,
         "mese": 2, "anno": 2026, "riconciliato": False},
    ]
    assert seleziona_salario_univoco(bonifico, righe) is None


def test_match_banca_richiede_nome_e_importo_non_solo_data():
    bonifico = {
        "id": "b1", "importo": 900.0, "data": "2026-04-03",
        "beneficiario": {"nome": "Rossi Mario"},
    }
    movimenti = [
        {"id": "sbagliato", "importo": 900.0, "tipo": "uscita", "data": "2026-04-03",
         "descrizione_originale": "BONIFICO FAVORE BIANCHI LUCA"},
        {"id": "giusto", "importo": 900.0, "tipo": "uscita", "data": "2026-04-04",
         "descrizione_originale": "STIPENDIO MARZO FAVORE MARIO ROSSI"},
    ]
    indice, movimento = trova_movimento_bancario_univoco(bonifico, movimenti, set())
    assert indice == 1
    assert movimento["id"] == "giusto"


def test_match_banca_ambiguo_non_riconcilia():
    bonifico = {
        "id": "b1", "importo": 900.0, "data": "2026-04-03",
        "beneficiario": {"nome": "Rossi Mario"},
    }
    movimenti = [
        {"id": "m1", "importo": -900.0, "data": "2026-04-03",
         "descrizione": "BONIFICO ROSSI MARIO"},
        {"id": "m2", "importo": -900.0, "data": "2026-04-04",
         "descrizione": "BONIFICO MARIO ROSSI"},
    ]
    assert trova_movimento_bancario_univoco(bonifico, movimenti, set()) is None


def test_fattura_bonifico_richiede_numero_importo_e_fornitore():
    bonifico = {
        "importo": 120.50,
        "beneficiario": {"nome": "FORNITORE TEST SRL"},
        "causale": "Pagamento fattura FT-88 Fornitore Test Srl",
    }
    fattura = {
        "id": "f1", "invoice_number": "FT-88", "total_amount": 120.50,
        "supplier_name": "FORNITORE TEST SRL",
    }
    assert valuta_fattura_bonifico(bonifico, fattura)["compatibile"] is True
    assert valuta_fattura_bonifico({**bonifico, "importo": 120.51}, fattura)["compatibile"] is False
    assert valuta_fattura_bonifico({**bonifico, "causale": "Pagamento fornitore"}, fattura)["compatibile"] is False


def test_distinta_bonifico_associa_solo_tutti_i_numeri_con_somma_esatta():
    bonifico = {
        "importo": 300.00,
        "beneficiario": {"nome": "LEASYS ITALIA SPA"},
        "causale": "FAVORE LEASYS ITALIA SPA FATTURE 202610239916 202610430648",
    }
    fatture = [
        {"id": "f1", "invoice_number": "202610239916", "total_amount": 100.00,
         "supplier_name": "LEASYS ITALIA SPA"},
        {"id": "f2", "invoice_number": "202610430648", "total_amount": 200.00,
         "supplier_name": "LEASYS ITALIA SPA"},
        {"id": "f3", "invoice_number": "NON-CITATA", "total_amount": 300.00,
         "supplier_name": "LEASYS ITALIA SPA"},
    ]
    assert [item["id"] for item in seleziona_fatture_bonifico(bonifico, fatture)] == ["f1", "f2"]
    assert seleziona_fatture_bonifico({**bonifico, "importo": 299.99}, fatture) == []


def test_documento_pagamento_e_un_riferimento_non_una_copia_pdf():
    riferimento = payment_document_ref({
        "id": "b1", "source_file": "bonifico.pdf", "document_hash": "abc",
        "data": "2026-07-17", "importo": 42.62, "pdf_data": "BASE64",
    })
    assert riferimento["view_url"] == "/api/archivio-bonifici/transfers/b1/pdf"
    assert riferimento["sha256"] == "abc"
    assert "pdf_data" not in riferimento


def test_collegamento_scrive_id_su_bonifico_e_fattura_senza_copiare_pdf():
    db = SimpleNamespace(
        bonifici_transfers=MagicMock(update_one=AsyncMock()),
        invoices=MagicMock(update_one=AsyncMock()),
        estratto_conto_movimenti=MagicMock(update_one=AsyncMock()),
        prima_nota_banca=MagicMock(update_many=AsyncMock()),
    )
    transfer = {"id": "b1", "importo": 10, "pdf_data": "NON_COPIARE"}
    asyncio.run(collega_bonifico_fatture(db, transfer, [{"id": "f1"}], auto=True))

    transfer_update = db.bonifici_transfers.update_one.await_args.args[1]
    invoice_update = db.invoices.update_one.await_args.args[1]
    assert transfer_update["$set"]["fattura_ids"] == ["f1"]
    assert invoice_update["$addToSet"]["payment_document_ids"] == "b1"
    assert "pdf_data" not in str(invoice_update)
