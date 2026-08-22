import asyncio

from app.services.sheets_document_store import MemorySheetsClient, evaluate_expression


def test_eq_con_valore_opzionale_non_valuta_confronti_estranei():
    assert evaluate_expression({"$eq": ["$pagato", True]}, {"pagato": None}) is False


def test_statistiche_fatture_fornitore_su_sheets():
    asyncio.run(_test_statistiche_fatture_fornitore_su_sheets())


async def _test_statistiche_fatture_fornitore_su_sheets():
    from app.database import Database
    from app.routers.suppliers_module import base

    db = MemorySheetsClient()["supplier_invoice_stats"]
    await db["fornitori"].insert_one({
        "id": "supplier-1", "partita_iva": "04518411212",
        "ragione_sociale": "Fornitore", "fatture_count": 1,
    })
    for index, amount in enumerate((100.0, 20.0, 30.0, 50.0)):
        await db["invoices"].insert_one({
            "id": f"invoice-{index}", "supplier_vat": "04518411212",
            "cedente_piva": "04518411212", "importo_totale": amount,
            "total_amount": amount, "pagato": index == 0,
            "data_documento": f"2026-0{index + 1}-01",
        })

    original_get_db = Database.get_db
    Database.get_db = classmethod(lambda cls: db)
    try:
        result = await base.list_suppliers(
            skip=0, limit=500, search=None, metodo_pagamento=None,
            attivo=None, esclude_magazzino=None, stato_anagrafica=None,
            giorni_nuovo=90, prodotto=None, use_cache=False,
        )
    finally:
        Database.get_db = original_get_db

    assert len(result) == 1
    assert result[0]["fatture_count"] == 4
    assert result[0]["fatture_totale"] == 200.0
    assert result[0]["fatture_pagate"] == 100.0
    assert result[0]["fatture_non_pagate"] == 100.0
