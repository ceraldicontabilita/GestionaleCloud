"""Piano residuo op.16: il CRUD fatture emesse non aveva mai normalizzato i
campi canonici italiani. Verifica che normalizza_fattura_emessa riempia i
campi mancanti dalle alternative inglesi/legacy senza toccare quelli già
presenti."""
from app.routers.invoices.invoices_emesse import normalizza_fattura_emessa


def test_riempie_campi_canonici_da_alternative_inglesi():
    data = {
        "number": "FE-001",
        "invoice_date": "2026-07-01",
        "customer": "Cliente Srl",
        "taxable_amount": 1000.0,
        "vat": 220.0,
        "total_amount": 1220.0,
    }
    out = normalizza_fattura_emessa(data)
    assert out["numero_fattura"] == "FE-001"
    assert out["data_fattura"] == "2026-07-01"
    assert out["cliente"] == "Cliente Srl"
    assert out["imponibile"] == 1000.0
    assert out["iva"] == 220.0
    assert out["totale"] == 1220.0
    # campi originali non rimossi (retrocompatibilità lettori esistenti)
    assert out["taxable_amount"] == 1000.0


def test_non_sovrascrive_campi_canonici_gia_presenti():
    data = {"imponibile": 500.0, "taxable_amount": 999.0, "iva": 110.0}
    out = normalizza_fattura_emessa(data)
    assert out["imponibile"] == 500.0
    assert out["iva"] == 110.0


def test_nessuna_alternativa_disponibile_non_aggiunge_campo():
    data = {"cliente": "Cliente Srl"}
    out = normalizza_fattura_emessa(data)
    assert "imponibile" not in out
    assert "iva" not in out
