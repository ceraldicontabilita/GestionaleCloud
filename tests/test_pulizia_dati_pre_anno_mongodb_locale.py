"""Collaudo distruttivo su MongoDB locale usa-e-getta (mongomock).

Il database esiste solo nella memoria del processo di test, non usa Atlas,
non legge MONGO_URL e viene eliminato esplicitamente al termine.
"""
import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.routers.prima_nota_module import manutenzione


def test_pulizia_su_mongodb_usa_e_getta_preserva_paghe(monkeypatch):
    async def scenario():
        client = AsyncMongoMockClient()
        nome_db = "usa_e_getta_pulizia_pregressi"
        db = client[nome_db]
        monkeypatch.setattr(
            manutenzione.Database, "get_db", staticmethod(lambda: db)
        )

        await db["cedolini"].insert_one({"id": "ced-old", "anno": 2024})
        await db["prima_nota_salari"].insert_one({
            "id": "sal-old", "data": "2024-05-01", "cedolino_id": "ced-old",
            "movimenti_bancari_ids": ["ec-payroll-old"],
        })
        await db["estratto_conto_movimenti"].insert_many([
            {"id": "ec-payroll-old", "data": "2024-05-27", "tipo": "uscita"},
            {"id": "ec-generic-old", "data": "2024-05-28", "tipo": "uscita"},
            {"id": "ec-current", "data": "2026-05-28", "tipo": "uscita"},
        ])
        await db["invoices"].insert_many([
            {"id": "invoice-old", "invoice_date": "2025-01-10"},
            {"invoice_date": "2024-01-10", "legacy": True},
            {"id": "invoice-current", "invoice_date": "2026-01-10"},
        ])

        anteprima = await manutenzione.pulizia_dati_pre_anno(
            anno_da_mantenere=2026, dry_run=True, crea_backup=True, _admin={}
        )
        assert anteprima["totale_eliminati"] == 0
        assert anteprima["collections"]["invoices"]["trovati_pre_anno"] == 2

        esito = await manutenzione.pulizia_dati_pre_anno(
            anno_da_mantenere=2026, dry_run=False, crea_backup=True, _admin={}
        )
        assert esito["cedolini_preservati"] is True
        assert await db["cedolini"].count_documents({}) == 1
        assert await db["prima_nota_salari"].count_documents({}) == 1
        assert await db["estratto_conto_movimenti"].count_documents({"id": "ec-payroll-old"}) == 1
        assert await db["estratto_conto_movimenti"].count_documents({"id": "ec-generic-old"}) == 0
        assert await db["invoices"].count_documents({"id": "invoice-old"}) == 0
        assert await db["invoices"].count_documents({"legacy": True}) == 0
        assert await db["invoices"].count_documents({"id": "invoice-current"}) == 1
        backup_invoice = esito["collections"]["invoices"]["backup_collection"]
        assert backup_invoice
        assert await db[backup_invoice].count_documents({}) == 2

        await client.drop_database(nome_db)
        assert nome_db not in await client.list_database_names()

    asyncio.run(scenario())


def test_migrazione_una_tantum_verifica_e_non_si_ripete(monkeypatch):
    async def scenario():
        client = AsyncMongoMockClient()
        nome_db = "usa_e_getta_migrazione_una_tantum"
        db = client[nome_db]
        monkeypatch.setattr(
            manutenzione.Database, "get_db", staticmethod(lambda: db)
        )

        await db["cedolini"].insert_one({"id": "ced-2023", "anno": 2023})
        await db["prima_nota_salari"].insert_one({
            "id": "sal-2023", "data": "2023-05-01",
            "cedolino_id": "ced-2023",
        })
        await db["prima_nota_cassa"].insert_many([
            {"id": "old", "data": "2025-12-31"},
            {"id": "new", "data": "2026-01-01"},
        ])

        primo = await manutenzione.esegui_pulizia_pregressi_una_tantum()
        secondo = await manutenzione.esegui_pulizia_pregressi_una_tantum()

        assert primo["verification_ok"] is True
        assert primo["totale_eliminati"] == 1
        assert secondo == {"skipped": True, "reason": "already_completed"}
        assert await db["prima_nota_cassa"].count_documents({"id": "old"}) == 0
        assert await db["prima_nota_cassa"].count_documents({"id": "new"}) == 1
        assert await db["cedolini"].count_documents({}) == 1
        assert await db["prima_nota_salari"].count_documents({}) == 1
        marker = await db["migration_runs"].find_one({
            "id": manutenzione.PULIZIA_PREGRESSI_MARKER
        })
        assert marker["status"] == "completed"

        await client.drop_database(nome_db)

    asyncio.run(scenario())
