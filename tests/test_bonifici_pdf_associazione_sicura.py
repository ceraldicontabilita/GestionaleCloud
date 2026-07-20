"""Regressioni: PDF stipendio e banca non devono produrre match casuali."""
from datetime import datetime

from app.routers.bonifici_module.pdf_parser import (
    extract_filename_metadata,
    extract_transfers_from_text,
)
from app.routers.bonifici_module.riconciliazione import (
    trova_movimento_bancario_univoco,
)
from app.services.bonifici_pdf_ingest import seleziona_salario_univoco


def test_nome_e_periodo_dal_filename_nei_due_ordini():
    primo = extract_filename_metadata("Verdi Paolo bonifico marzo.pdf")
    secondo = extract_filename_metadata("bonifico marzo Neri Lucia1.pdf")
    assert primo == {
        "beneficiario_nome": "Verdi Paolo",
        "periodo_mese": 3,
        "periodo_anno": None,
    }
    assert secondo["beneficiario_nome"] == "Neri Lucia"
    assert secondo["periodo_mese"] == 3


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
    assert isinstance(parsed["data"], datetime)


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
