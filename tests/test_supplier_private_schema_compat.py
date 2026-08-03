from app.routers.suppliers_module.base import (
    _legacy_supplier_view,
    _normalized_supplier_key,
)
from scripts.migrate_suppliers_to_private_db import (
    canonical_source,
    merged_values,
    normalize_payment_method,
)


def test_private_supplier_is_visible_to_legacy_ui():
    result = _legacy_supplier_view({
        "match_key": "01234567890", "vat": "IT01234567890",
        "name": "FORNITORE TEST SRL", "default_payment_method": "bonifico",
        "payment_days": 60, "inventory_enabled": False,
    })
    assert result["partita_iva"] == "01234567890"
    assert result["ragione_sociale"] == "FORNITORE TEST SRL"
    assert result["metodo_pagamento"] == "bonifico"
    assert result["giorni_pagamento"] == 60
    assert result["esclude_magazzino"] is True
    assert _normalized_supplier_key("IT 01234567890") == "01234567890"


def test_migration_uses_only_explicit_supported_payment_methods():
    assert normalize_payment_method("Bonifico bancario") == "bonifico"
    assert normalize_payment_method("Contanti") == "cassa"
    assert normalize_payment_method("da verificare") is None
    source = canonical_source({
        "partita_iva": "01234567890", "ragione_sociale": "TEST SRL",
        "metodo_pagamento": "PayPal", "metodo_pagamento_inferred": "cassa",
        "num_fatture": 4, "ultima_fattura": "2026-07-30",
    })
    assert source is not None
    assert source["default_payment_method"] == "paypal"
    assert source["source_invoice_count"] == 4
    assert source["source_last_invoice_year"] == 2026


def test_migration_preserves_curated_target_method():
    source = {
        "match_key": "01234567890", "name": "TEST SRL", "vat": "IT01234567890",
        "iban": "IT00TEST", "email": None, "locality": "Napoli",
        "default_payment_method": "cassa", "payment_area": "cassa",
        "payment_days": 30, "inventory_enabled": False,
        "source_invoice_count": 10, "source_last_invoice_year": 2026,
    }
    target = {
        **source, "iban": None, "default_payment_method": "bonifico",
        "payment_area": "banca", "source_invoice_count": 2, "source": "xml",
    }
    result = merged_values(source, target)
    assert result["default_payment_method"] == "bonifico"
    assert result["payment_area"] == "banca"
    assert result["iban"] == "IT00TEST"
    assert result["source_invoice_count"] == 10
