"""
Configurazione test per il gestionale ERP Azienda in Cloud.

Fornisce fixture per:
- Mock del database MongoDB
- Dati di esempio per corrispettivi, fatture, cedolini, dipendenti
"""
import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

# Aggiungi app al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def sample_corrispettivi():
    """Corrispettivi di esempio per test liquidazione IVA."""
    return [
        {
            "data": "2025-06-15",
            "totale": 1220.00,
            "totale_imponibile": 1000.00,
            "totale_iva": 220.00,
            "partita_iva": "04523831214"
        },
        {
            "data": "2025-06-20",
            "totale": 610.00,
            "totale_imponibile": 500.00,
            "totale_iva": 110.00,
            "partita_iva": "04523831214"
        },
    ]


@pytest.fixture
def sample_fatture():
    """Fatture ricevute di esempio per test liquidazione IVA."""
    return [
        {
            "invoice_number": "FT-001",
            "supplier_name": "Fornitore Generico",
            "invoice_date": "2025-06-10",
            "data_ricezione": "2025-06-12",
            "total_amount": 366.00,
            "imponibile": 300.00,
            "iva": 66.00,
            "tipo_documento": "TD01",
        },
        {
            "invoice_number": "NC-001",
            "supplier_name": "Fornitore Generico",
            "invoice_date": "2025-06-05",
            "data_ricezione": "2025-06-06",
            "total_amount": 122.00,
            "imponibile": 100.00,
            "iva": 22.00,
            "tipo_documento": "TD04",  # Nota di credito
        },
    ]


@pytest.fixture
def sample_fattura_telefonia():
    """Fattura telefonia per test deducibilità 80% e IVA 50%."""
    return {
        "invoice_number": "FT-TIM-001",
        "supplier_name": "TIM S.p.A.",
        "invoice_date": "2025-06-10",
        "data_ricezione": "2025-06-12",
        "total_amount": 244.00,
        "imponibile": 200.00,
        "iva": 44.00,
        "tipo_documento": "TD01",
    }


@pytest.fixture
def sample_fattura_noleggio_auto():
    """Fattura noleggio auto per test deducibilità 20% su max €3.615,20."""
    return {
        "invoice_number": "FT-ARVAL-001",
        "supplier_name": "ARVAL Service Lease",
        "invoice_date": "2025-06-10",
        "total_amount": 6100.00,
        "imponibile": 5000.00,
        "iva": 1100.00,
        "tipo_documento": "TD01",
    }


@pytest.fixture
def sample_dipendente():
    """Dipendente di esempio per test cedolini e TFR."""
    return {
        "id": "dip-001",
        "nome_completo": "Mario Rossi",
        "codice_fiscale": "RSSMRA80A01H501Z",
        "status": "attivo",
        "mansione": "barista",
        "stipendio_orario": 10.50,
        "tfr_accantonato": 5000.00,
        "data_assunzione": "2020-01-15",
    }


@pytest.fixture
def sample_cedolino():
    """Cedolino di esempio per test contabilità."""
    return {
        "id": "ced-001",
        "employee_id": "dip-001",
        "dipendente_id": "dip-001",
        "dipendente_nome": "Mario Rossi",
        "mese": 6,
        "anno": 2025,
        "lordo": 1800.00,
        "netto": 1350.00,
        "inps_dipendente": 165.42,
        "irpef": 284.58,
        "inps_azienda": 540.00,
        "inail": 36.00,
        "tfr": 133.33,
        "costo_azienda": 2509.33,
        "stato": "confermato",
    }
