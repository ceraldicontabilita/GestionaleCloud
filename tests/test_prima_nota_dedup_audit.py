import asyncio

from app.services.sheets_document_store import MemorySheetsClient

from app.database import Database
from app.routers.prima_nota_module.manutenzione import (
    dedup_fatture_prima_nota,
    ripristina_dedup_fatture_errato,
)


def _run(coro):
    return asyncio.run(coro)


def test_dedup_usa_operazione_e_non_fattura_condivisa(monkeypatch):
    async def scenario():
        db = MemorySheetsClient()["dedup_audit"]
        base = {
            "data": "2026-08-11", "importo": 180.56, "categoria": "Fatture",
            "status": "active", "descrizione": "Pagamento fattura FVL968 - 2M ITALIA",
        }
        await db.prima_nota_banca.insert_many([
            {**base, "id": "check-1", "fattura_id": "INV-1", "source": "assegno_estratto_conto", "descrizione": "Assegno n. 0208770767", "created_at": "2026-08-11T08:00:00Z"},
            {**base, "id": "check-2", "fattura_id": "INV-1", "source": "assegno_estratto_conto", "descrizione": "Assegno n. 0208770851", "created_at": "2026-08-11T09:00:00Z"},
            {**base, "id": "dup-a", "fattura_id": "INV-2", "source": "estratto_conto_auto", "estratto_conto_id": "EC-77", "created_at": "2026-08-11T10:00:00Z"},
            {**base, "id": "dup-b", "fattura_id": "INV-2", "source": "estratto_conto_auto", "estratto_conto_id": "EC-77", "created_at": "2026-08-11T11:00:00Z"},
        ])
        monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
        report = await dedup_fatture_prima_nota(
            applica=False, auto_risolvi_certi=True, anno=2026
        )
        active = await db.prima_nota_banca.find(
            {"status": {"$nin": ["deleted", "archived"]}}, {"_id": 0, "id": 1}
        ).to_list(20)
        return report, {row["id"] for row in active}

    report, active_ids = _run(scenario())
    banca = report["banca"]
    assert banca["gruppi_duplicati"] == 1
    assert banca["movimenti_certi"] == 1
    assert banca["eliminati_effettivi"] == 1
    assert len(banca["dettagli"]) == 1
    assert active_ids == {"check-1", "check-2", "dup-a"}


def test_ripristina_tutto_quello_nascosto_dalla_regola_errata(monkeypatch):
    async def scenario():
        db = MemorySheetsClient()["dedup_restore"]
        await db.prima_nota_banca.insert_many([
            {"id": "a", "status": "deleted", "deleted_reason": "dedup_fatture_prima_nota"},
            {"id": "b", "status": "deleted", "deleted_reason": "altra_causa"},
        ])
        monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
        result = await ripristina_dedup_fatture_errato()
        rows = await db.prima_nota_banca.find({}, {"_id": 0}).to_list(10)
        return result, {row["id"]: row for row in rows}

    result, rows = _run(scenario())
    assert result["ripristinati"] == 1
    assert rows["a"]["status"] == "active"
    assert rows["a"]["restored_reason"] == "rollback_dedup_basato_su_fattura_id"
    assert rows["b"]["status"] == "deleted"
