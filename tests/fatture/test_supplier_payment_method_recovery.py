import asyncio

from app.services.sheets_document_store import MemorySheetsClient
from app.services.supplier_payment_method_recovery import recover_supplier_payment_methods
from app.utils.iva_calculator import save_supplier_payment_method


def test_recupera_solo_metodo_storico_e_crea_backup():
    asyncio.run(_test_recupera_solo_metodo_storico_e_crea_backup())


async def _test_recupera_solo_metodo_storico_e_crea_backup():
    db = MemorySheetsClient()["supplier_method_recovery"]
    await db["fornitori"].insert_one({
        "id": "for-1", "partita_iva": "01234567890", "metodo_pagamento": "",
        "storico_metodi_pagamento": [
            {"metodo": "cassa", "registrato_il": "2026-01-01T10:00:00+00:00"},
            {"metodo": "banca", "registrato_il": "2026-06-01T10:00:00+00:00"},
        ],
    })

    preview = await recover_supplier_payment_methods(db, apply=False)
    assert preview["recuperabili"] == 1
    assert preview["ripristinati"] == 0

    applied = await recover_supplier_payment_methods(db, apply=True)
    assert applied["ripristinati"] == 1
    supplier = await db["fornitori"].find_one({"id": "for-1"})
    assert supplier["metodo_pagamento"] == "banca"
    backup = await db["supplier_payment_method_recovery_backup"].find_one({"supplier_id": "for-1"})
    assert backup["documento_originale"]["metodo_pagamento"] == ""


def test_non_deduce_senza_fonte_e_non_sovrascrive_configurato():
    asyncio.run(_test_non_deduce_senza_fonte_e_non_sovrascrive_configurato())


async def _test_non_deduce_senza_fonte_e_non_sovrascrive_configurato():
    db = MemorySheetsClient()["supplier_method_no_guess"]
    await db["fornitori"].insert_one({"id": "for-1", "partita_iva": "1", "metodo_pagamento": "misto"})
    await db["fornitori"].insert_one({"id": "for-2", "partita_iva": "2", "metodo_pagamento": ""})

    result = await recover_supplier_payment_methods(db, apply=True)
    assert result["gia_configurati"] == 1
    assert result["senza_fonte"] == 1
    assert result["ripristinati"] == 0


def test_blocca_conflitto_senza_data():
    asyncio.run(_test_blocca_conflitto_senza_data())


async def _test_blocca_conflitto_senza_data():
    db = MemorySheetsClient()["supplier_method_conflict"]
    await db["fornitori"].insert_one({"id": "for-1", "partita_iva": "1", "metodo_pagamento": ""})
    await db["supplier_payment_methods"].insert_one({
        "id": "dict-1", "supplier_vat": "1", "payment_method": "cassa"
    })
    await db["supplier_payment_history"].insert_one({
        "id": "hist-1", "supplier_vat": "1", "payment_method": "banca"
    })

    result = await recover_supplier_payment_methods(db, apply=True)
    assert result["conflitti"] == 1
    assert result["ripristinati"] == 0


def test_dizionario_persistente_ha_identita_canoniche_sheets():
    asyncio.run(_test_dizionario_persistente_ha_identita_canoniche_sheets())


async def _test_dizionario_persistente_ha_identita_canoniche_sheets():
    db = MemorySheetsClient()["supplier_method_dictionary_ids"]
    assert await save_supplier_payment_method(db, "01234567890", "Fornitore", "banca", "test")
    dictionary = await db["supplier_payment_methods"].find_one({"supplier_vat": "01234567890"})
    history = await db["supplier_payment_history"].find_one({"supplier_vat": "01234567890"})
    assert dictionary["id"] == "supplier-payment-method:01234567890"
    assert history["id"].startswith("supplier-payment-history:01234567890:")
