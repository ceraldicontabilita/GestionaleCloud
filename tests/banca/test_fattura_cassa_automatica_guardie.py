"""Fornitore «cassa»: la fattura non passa dalla banca (CLAUDE.md §29).

Decisione del titolare del 07/10/2026: il movimento in Prima Nota Cassa nasce
all'import, con la data della fattura, senza interrogare l'estratto conto.
La nota di credito non e' un pagamento al fornitore: resta provvisoria.
"""
import asyncio

from app.services.archivio_documenti_memoria import ClientArchivioMemoria

from app.routers.invoices import fatture_upload


def _scenario(monkeypatch, nome):
    db = ClientArchivioMemoria()[nome]

    async def vietato_cercare_estratto_conto(*args, **kwargs):
        raise AssertionError("una fattura cassa non deve cercare un match bancario")

    monkeypatch.setattr(
        fatture_upload, "find_ec_match_for_invoice", vietato_cercare_estratto_conto,
    )
    from app.routers.prima_nota_module import sync as sync_mod
    monkeypatch.setattr(sync_mod.Database, "get_db", staticmethod(lambda: db))

    eventi = []

    async def finto_propagate(event_type, payload, _db, source_module="", **_k):
        eventi.append((event_type, payload))
        return []

    from app.services import event_bus
    monkeypatch.setattr(event_bus, "propagate_event", finto_propagate)
    return db, eventi


def test_metodo_fornitore_cassa_scrive_cassa_senza_passare_dalla_banca(monkeypatch):
    async def scenario():
        db, eventi = _scenario(monkeypatch, "test_fattura_cassa_auto")
        await db["fornitori"].insert_one({
            "partita_iva": "01234567890",
            "metodo_pagamento": "cassa",
        })
        invoice = {
            "id": "fattura-cassa-1",
            "supplier_vat": "01234567890",
            "supplier_name": "FORNITORE CASSA",
            "invoice_number": "C-1",
            "invoice_date": "2026-10-02",
            "total_amount": 122.0,
            "tipo_documento": "TD01",
        }
        await db["invoices"].insert_one(dict(invoice))

        esito = await fatture_upload.auto_registra_prima_nota(db, invoice, "cassa")

        assert await db["prima_nota_cassa"].count_documents({}) == 1
        assert await db["prima_nota_banca"].count_documents({}) == 0
        mov = await db["prima_nota_cassa"].find_one({})
        assert mov["data"] == "2026-10-02"
        assert mov["importo"] == 122.0
        assert mov["metodo_pagamento_effettivo"] == "cassa"
        assert esito["pagato"] is True
        assert esito["stato_pagamento"] == "pagata"
        assert esito["data_pagamento"] == "2026-10-02"
        assert esito["metodo_pagamento_effettivo"] == "cassa"
        assert esito["decisione_pagamento_richiesta"] is False
        # Il dict in memoria e' allineato: `fattura.created` lo legge dopo.
        assert invoice["pagato"] is True
        assert [e[0] for e in eventi] == ["fattura.pagata"]

    asyncio.run(scenario())


def test_nota_di_credito_cassa_non_diventa_entrata_automatica(monkeypatch):
    async def scenario():
        db, eventi = _scenario(monkeypatch, "test_nota_credito_cassa")
        await db["fornitori"].insert_one({
            "partita_iva": "01234567890",
            "metodo_pagamento": "cassa",
        })
        invoice = {
            "id": "nc-cassa-1",
            "supplier_vat": "01234567890",
            "supplier_name": "FORNITORE CASSA",
            "invoice_number": "NC-1",
            "invoice_date": "2026-10-02",
            "total_amount": 50.0,
            "tipo_documento": "TD04",
        }
        await db["invoices"].insert_one(dict(invoice))

        esito = await fatture_upload.auto_registra_prima_nota(db, invoice, "cassa")

        # §32: la nota chiude con il rimborso reale o compensando la fattura
        # originale, non con un'entrata di cassa inventata all'import.
        assert esito is None
        assert await db["prima_nota_cassa"].count_documents({}) == 0
        salvata = await db["invoices"].find_one({"id": "nc-cassa-1"})
        from app.services.stato_pagamento_fattura import e_pagata
        assert e_pagata(salvata) is False
        assert eventi == []

    asyncio.run(scenario())


def test_fattura_senza_data_non_inventa_la_data_di_pagamento(monkeypatch):
    async def scenario():
        db, eventi = _scenario(monkeypatch, "test_cassa_senza_data")
        await db["fornitori"].insert_one({
            "partita_iva": "01234567890",
            "metodo_pagamento": "cassa",
        })
        invoice = {
            "id": "fattura-cassa-nodata",
            "supplier_vat": "01234567890",
            "supplier_name": "FORNITORE CASSA",
            "invoice_number": "C-2",
            "total_amount": 10.0,
        }
        await db["invoices"].insert_one(dict(invoice))

        esito = await fatture_upload.auto_registra_prima_nota(db, invoice, "cassa")

        assert esito is None
        assert await db["prima_nota_cassa"].count_documents({}) == 0
        assert eventi == []

    asyncio.run(scenario())
