import asyncio

from app.services import soci_accounting
from app.services.sheets_document_store import MemorySheetsClient


def _run(coro):
    return asyncio.run(coro)


def test_apporto_cassa_scrive_un_solo_fatto_con_due_proiezioni():
    async def scenario():
        db = MemorySheetsClient()["soci-cassa"]
        out = await soci_accounting.registra_movimento_socio(
            db,
            socio_id="vincenzo_ceraldi",
            tipo="apporto",
            importo=1000,
            data="2026-09-05",
            destinazione="cassa",
            descrizione="Apporto socio in contanti",
            operation_id="op-test-cassa",
        )
        assert out["operation_id"] == "op-test-cassa"
        assert await db["finanziamenti_soci_movimenti"].count_documents({"operation_id": "op-test-cassa"}) == 1
        assert await db["prima_nota_cassa"].count_documents({"operation_id": "op-test-cassa"}) == 1
        assert await db["prima_nota_banca"].count_documents({"operation_id": "op-test-cassa"}) == 0

        second = await soci_accounting.registra_movimento_socio(
            db,
            socio_id="vincenzo_ceraldi",
            tipo="apporto",
            importo=1000,
            data="2026-09-05",
            destinazione="cassa",
            operation_id="op-test-cassa",
        )
        assert second["idempotente"] is True
        assert await db["finanziamenti_soci_movimenti"].count_documents({"operation_id": "op-test-cassa"}) == 1
        assert await db["prima_nota_cassa"].count_documents({"operation_id": "op-test-cassa"}) == 1

    _run(scenario())


def test_apporto_banca_resta_attesa_e_poi_si_aggancia_senza_doppione():
    async def scenario():
        db = MemorySheetsClient()["soci-banca"]
        out = await soci_accounting.registra_movimento_socio(
            db,
            socio_id="vincenzo_ceraldi",
            tipo="apporto",
            importo=2500,
            data="2026-09-05",
            destinazione="banca",
            descrizione="Apporto socio Vincenzo Ceraldi",
            operation_id="op-test-banca",
        )
        pn_id = out["prima_nota_id"]
        pn = await db["prima_nota_banca"].find_one({"id": pn_id})
        assert pn["riconciliato"] is False
        assert pn["in_attesa_estratto_ufficiale"] is True

        await db["estratto_conto_movimenti"].insert_one({
            "id": "EC-SOCIO-1",
            "data": "2026-09-06",
            "tipo": "entrata",
            "importo": 2500,
            "descrizione_originale": "BONIFICO DA VINCENZO CERALDI FINANZIAMENTO SOCI",
        })
        stats = await soci_accounting.riconcilia_attese_soci_da_ec(
            db, anno=2026, movimento_ids=["EC-SOCIO-1"]
        )
        assert stats["riconciliati"] == 1
        assert await db["finanziamenti_soci_movimenti"].count_documents({"operation_id": "op-test-banca"}) == 1
        pn = await db["prima_nota_banca"].find_one({"id": pn_id})
        assert pn["riconciliato"] is True
        assert pn["estratto_conto_id"] == "EC-SOCIO-1"
        assert await db["prima_nota_banca"].count_documents({"operation_id": "op-test-banca"}) == 1

    _run(scenario())
