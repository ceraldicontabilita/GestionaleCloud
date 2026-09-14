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
    # I documenti reali arrivano da importatori diversi: il totale non e'
    # sempre denominato importo_totale. Le card fornitori devono mostrare il
    # valore presente nel documento, senza sintetizzarlo.
    amount_fields = (
        ("importo_totale", 100.0), ("total_amount", 20.0),
        ("totale_documento", 30.0), ("totale", "50,00"),
    )
    for index, (amount_field, amount) in enumerate(amount_fields):
        await db["invoices"].insert_one({
            "id": f"invoice-{index}", "supplier_vat": "04518411212",
            "cedente_piva": "04518411212", amount_field: amount,
            "pagato": index == 0,
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


def test_fornitore_storico_senza_piva_resta_visibile_senza_piva_inventata():
    asyncio.run(_test_fornitore_storico_senza_piva_resta_visibile_senza_piva_inventata())


async def _test_fornitore_storico_senza_piva_resta_visibile_senza_piva_inventata():
    from app.database import Database
    from app.routers.suppliers_module import base

    db = MemorySheetsClient()["supplier_name_only"]
    await db["fornitori"].insert_one({
        "id": "legacy-supplier-1",
        "ragione_sociale": "Fornitore storico documentato",
        "legacy_source_id": "42",
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
    assert result[0]["id"] == "legacy-supplier-1"
    assert not result[0].get("partita_iva")


def test_match_key_nome_non_diventa_piva_e_non_fonde_id_distinti():
    asyncio.run(_test_match_key_nome_non_diventa_piva_e_non_fonde_id_distinti())


async def _test_match_key_nome_non_diventa_piva_e_non_fonde_id_distinti():
    from app.database import Database
    from app.routers.suppliers_module import base

    db = MemorySheetsClient()["supplier_same_name_distinct_ids"]
    await db["fornitori"].insert_many([
        {"id": "legacy-1", "name": "ALFA SRL", "match_key": "ALFASRL"},
        {"id": "legacy-2", "name": "ALFA S.R.L.", "match_key": "ALFASRL"},
    ])
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

    assert len(result) == 2
    assert {item["id"] for item in result} == {"legacy-1", "legacy-2"}
    assert all(not item.get("partita_iva") for item in result)
