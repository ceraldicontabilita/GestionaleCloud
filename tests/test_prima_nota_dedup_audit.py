import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.database import Database
from app.routers.prima_nota_module.manutenzione import dedup_fatture_prima_nota


def _run(coro):
    return asyncio.run(coro)


def test_dedup_elenca_tutti_e_auto_risolve_solo_identita_certe(monkeypatch):
    async def scenario():
        db = AsyncMongoMockClient()["dedup_audit"]
        base = {
            "data": "2026-08-11", "importo": 180.56, "categoria": "Fatture",
            "status": "active", "descrizione": "Pagamento fattura FVL968 - 2M ITALIA",
        }
        await db.prima_nota_banca.insert_many([
            {**base, "id": "keep", "fattura_id": "INV-1", "created_at": "2026-08-11T08:00:00Z"},
            {**base, "id": "dup-1", "riferimento": "FATT-INV-1", "created_at": "2026-08-11T09:00:00Z"},
            {**base, "id": "dup-2", "fattura_id": "INV-1", "created_at": "2026-08-11T10:00:00Z"},
            # Stesso numero/data/importo senza identita canonica: va mostrato,
            # ma non cancellato automaticamente.
            {**base, "id": "uncertain-a", "numero_fattura": "FVL824", "created_at": "2026-08-11T11:00:00Z"},
            {**base, "id": "uncertain-b", "numero_fattura": "FVL824", "created_at": "2026-08-11T12:00:00Z"},
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
    assert banca["gruppi_duplicati"] == 2
    assert banca["movimenti_certi"] == 2
    assert banca["movimenti_da_verificare"] == 1
    assert banca["eliminati_effettivi"] == 2
    assert len(banca["dettagli"]) == 2
    assert sum(len(group["duplicati"]) for group in banca["dettagli"]) == 3
    assert {group["certezza"] for group in banca["dettagli"]} == {"certo", "da_verificare"}
    assert active_ids == {"keep", "uncertain-a", "uncertain-b"}

