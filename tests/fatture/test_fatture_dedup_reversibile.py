import asyncio

from app.routers.fatture_module import crud
from app.services.archivio_documenti_memoria import MemorySheetsClient


def _run(coro):
    return asyncio.run(coro)


def test_cleanup_archivia_solo_stesso_originale_e_non_cancella(monkeypatch):
    db = MemorySheetsClient()["fatture-dedup-reversibile"]
    monkeypatch.setattr(crud.Database, "get_db", lambda: db)

    base = {
        "invoice_number": "1", "supplier_vat": "IT000",
        "invoice_date": "2026-01-01", "total_amount": 100,
        "status": "imported",
    }

    async def scenario():
        await db["invoices"].insert_many([
            {**base, "id": "canonico", "file_hash": "same", "created_at": "2026-01-01"},
            {**base, "id": "duplicato", "file_hash": "same", "created_at": "2026-01-02"},
            {**base, "id": "collisione", "file_hash": "different", "created_at": "2026-01-03"},
        ])
        await db["scadenziario_fornitori"].insert_one({
            "id": "scad-dup", "fattura_id": "canonico", "status": "attivo",
        })
        result = await crud.pulisci_duplicati_invoices()
        docs = await db["invoices"].find({}).to_list(10)
        derivato = await db["scadenziario_fornitori"].find_one({"id": "scad-dup"})
        return result, {d["id"]: d for d in docs}, derivato

    result, docs, derivato = _run(scenario())
    assert result["fatture_eliminate"] == 0
    assert result["fatture_archiviate"] == 1
    assert len(docs) == 3
    assert docs["canonico"]["status"] == "archived"
    assert docs["canonico"]["duplicate_of"] == "duplicato"
    assert docs["collisione"]["status"] == "imported"
    assert derivato["status"] == "archived"
    assert derivato["duplicate_of"] == "duplicato"
