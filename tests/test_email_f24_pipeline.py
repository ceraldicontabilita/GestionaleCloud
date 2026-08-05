import asyncio
import base64

from mongomock_motor import AsyncMongoMockClient

from app.routers.f24 import email_f24


def test_email_quietanza_non_viene_scambiata_per_modello_f24(monkeypatch):
    async def scenario():
        db = AsyncMongoMockClient()["test_email_quietanza"]
        await db["email_allegati"].insert_one({
            "id": "a1", "original_filename": "quietanza.pdf",
            "extension": ".pdf", "processato": False,
            "pdf_data": base64.b64encode(b"quietanza").decode(),
        })
        monkeypatch.setattr(email_f24.Database, "get_db", staticmethod(lambda: db))
        monkeypatch.setattr(email_f24, "parse_quietanza_f24", lambda **_: {
            "dati_generali": {
                "protocollo_telematico": "12345678901234567",
                "data_pagamento": "2026-07-16",
            },
            "sezione_erario": [{"codice_tributo": "6006"}],
        })

        f24_chiamato = False

        def parse_f24_vietato(**_):
            nonlocal f24_chiamato
            f24_chiamato = True
            return {}

        monkeypatch.setattr(email_f24, "parse_f24_commercialista", parse_f24_vietato)

        async def importa(*_args, **_kwargs):
            return {
                "success": True, "duplicate": False, "saldo": 100,
                "f24_matchati": ["f1"],
            }

        monkeypatch.setattr(email_f24, "importa_quietanza_bytes", importa)
        esito = await email_f24.processa_allegati_f24()

        assert f24_chiamato is False
        assert esito["risultati"]["quietanze"] == 1
        assert esito["risultati"]["f24_commercialista"] == 0
        allegato = await db["email_allegati"].find_one({"id": "a1"})
        assert allegato["tipo_documento"] == "quietanza_f24"

    asyncio.run(scenario())


def test_email_f24_stesso_pdf_in_due_allegati_non_duplica(monkeypatch):
    async def scenario():
        db = AsyncMongoMockClient()["test_email_f24_dedup"]
        pdf_data = base64.b64encode(b"modello-f24-identico").decode()
        await db["email_allegati"].insert_many([
            {"id": "a1", "original_filename": "f24-a.pdf", "extension": ".pdf", "processato": False, "pdf_data": pdf_data},
            {"id": "a2", "original_filename": "f24-b.pdf", "extension": ".pdf", "processato": False, "pdf_data": pdf_data},
        ])
        monkeypatch.setattr(email_f24.Database, "get_db", staticmethod(lambda: db))
        monkeypatch.setattr(email_f24, "parse_quietanza_f24", lambda **_: {"dati_generali": {}})
        monkeypatch.setattr(email_f24, "parse_f24_commercialista", lambda **_: {
            "dati_generali": {"codice_fiscale": "04523831214", "data_versamento": "2026-07-16"},
            "sezione_erario": [{"codice_tributo": "6006", "importo_debito": 100}],
            "sezione_inps": [], "sezione_regioni": [], "sezione_tributi_locali": [],
            "totali": {"saldo_netto": 100}, "codici_univoci": ["6006"],
        })

        esito = await email_f24.processa_allegati_f24()

        assert esito["risultati"]["f24_commercialista"] == 1
        assert await db["f24_unificato"].count_documents({}) == 1
        dettagli = [d for d in esito["risultati"]["dettagli"] if d.get("tipo") == "F24"]
        assert [d["duplicato"] for d in dettagli] == [False, True]

    asyncio.run(scenario())
