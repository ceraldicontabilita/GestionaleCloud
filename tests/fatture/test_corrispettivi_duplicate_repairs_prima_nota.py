import asyncio

from app.services.sheets_document_store import MemorySheetsClient

from app.routers.invoices.corrispettivi_helpers import ingest_corrispettivo_parsed


def test_zip_reimport_ripara_prima_nota_mancante_senza_duplicarla():
    db = MemorySheetsClient()["corrispettivi-duplicate-repair"]
    parsed = {
        "corrispettivo_key": "IT01234567890_2026-08-13_RT001_42",
        "data": "2026-08-13",
        "matricola_rt": "RT001",
        "id_dispositivo": "RT001",
        "pagato_contanti": 100.0,
        "pagato_elettronico": 0.0,
        "totale": 100.0,
    }

    async def scenario():
        await db["corrispettivi"].insert_one({
            "id": "corr-esistente",
            "corrispettivo_key": parsed["corrispettivo_key"],
            "data": parsed["data"],
            "matricola_rt": parsed["matricola_rt"],
            "id_dispositivo": parsed["id_dispositivo"],
            "pagato_contanti": 100.0,
            "pagato_elettronico": 0.0,
            "totale": 100.0,
            "status": "imported",
            "entity_status": "active",
            "prima_nota_cassa_id": None,
        })
        primo = await ingest_corrispettivo_parsed(db, parsed, filename="corr.xml")
        secondo = await ingest_corrispettivo_parsed(db, parsed, filename="corr.xml")
        righe = await db["prima_nota_cassa"].find({
            "data": "2026-08-13", "tipo": "entrata", "categoria": "Corrispettivi",
        }).to_list(10)
        record = await db["corrispettivi"].find_one({"id": "corr-esistente"})
        return primo, secondo, righe, record

    primo, secondo, righe, record = asyncio.run(scenario())

    assert primo["action"] == "duplicate"
    assert primo["accounting_repaired"] is True
    assert primo["prima_nota_cassa_id"]
    assert secondo["accounting_repaired"] is False
    assert len(righe) == 1
    assert record["prima_nota_cassa_id"] == righe[0]["id"]
