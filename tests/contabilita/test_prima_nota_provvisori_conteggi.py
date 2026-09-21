import asyncio

from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.routers.prima_nota_module import sync as sync_module


def _run(coro):
    return asyncio.run(coro)


def test_conteggi_provvisori_coincidono_con_vista_completa(monkeypatch):
    async def scenario():
        memoria = ClientArchivioMemoria()
        db = memoria["test_conteggi_provvisori"]
        monkeypatch.setattr(sync_module.Database, "get_db", staticmethod(lambda: db))

        await db["fornitori"].insert_many([
            {
                "id": "for-cassa",
                "partita_iva": "00000000001",
                "metodo_pagamento": "contanti",
            },
            {
                "id": "for-banca",
                "partita_iva": "00000000002",
                "metodo_pagamento": "bonifico",
            },
        ])
        await db["invoices"].insert_many([
            {
                "id": "f-cassa",
                "invoice_number": "C-1",
                "invoice_date": "2026-09-01",
                "supplier_vat": "00000000001",
                "supplier_name": "CASSA",
                "total_amount": 100.0,
                "status": "imported",
            },
            {
                "id": "f-banca",
                "invoice_number": "B-1",
                "invoice_date": "2026-09-02",
                "supplier_vat": "00000000002",
                "supplier_name": "BANCA",
                "total_amount": 200.0,
                "status": "imported",
            },
            {
                "id": "f-sospesa",
                "invoice_number": "S-1",
                "invoice_date": "2026-09-03",
                "supplier_vat": "00000000002",
                "supplier_name": "SOSPESA",
                "total_amount": 300.0,
                "status": "imported",
                "stato_pagamento": "sospesa",
            },
            {
                "id": "f-pagata",
                "invoice_number": "P-1",
                "invoice_date": "2026-09-04",
                "supplier_vat": "00000000001",
                "supplier_name": "PAGATA",
                "total_amount": 50.0,
                "status": "imported",
            },
        ])
        await db["prima_nota_cassa"].insert_one({
            "id": "pn-pagata",
            "fattura_id": "f-pagata",
            "riferimento": "FATT-f-pagata",
            "importo": 50.0,
            "data": "2026-09-04",
            "status": "active",
        })

        conteggi = await sync_module.get_conteggi_fatture_provvisorie(anno=2026)
        completo = await sync_module.get_fatture_provvisorie(anno=2026)

        assert conteggi["caricato"] is True
        assert conteggi["totale_da_decidere"] == len(completo["provvisori"])
        assert conteggi["totale_in_attesa_banca"] == len(completo["in_attesa_banca"])
        assert conteggi["totale_da_decidere"] == 2
        assert conteggi["totale_in_attesa_banca"] == 1
        assert conteggi["totale_aperti_mostrati"] == 3
        memoria.close()

    _run(scenario())
