"""Due richieste e rollback attraversano il motore vero e il runtime ottimistico."""

import asyncio
import copy
import pytest
from fastapi import HTTPException
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services import bank_payment_allocations as bank
from tests.runtime.test_supabase_runtime_database import FakeRestSupabase


def seed():
    return {
        "invoices": [
            {
                "_id": "F1",
                "id": "F1",
                "total_amount": 100,
                "invoice_date": "2026-06-01",
                "supplier_vat": "01234567890",
                "supplier_name": "FORNITORE PROVA",
            }
        ],
        "estratto_conto_movimenti": [
            {
                "_id": m,
                "id": m,
                "importo": 100,
                "data": "2026-06-15",
                "tipo": "uscita",
                "riconciliato": False,
            }
            for m in ["M1", "M2"]
        ],
    }


async def pay(db, mid, iid="F1"):
    m = await db["estratto_conto_movimenti"].find_one({"id": mid})
    a = await bank.validate_bank_invoice_allocations(
        db, m, [{"id": iid, "quota_cents": 10000}]
    )
    return await bank.persist_bank_invoice_allocations(db, m, a, actor="test_isolato")


def test_due_processi_non_consumano_due_volte_la_stessa_fattura():
    async def scenario():
        shared = {k: {d["_id"]: copy.deepcopy(d) for d in v} for k, v in seed().items()}
        gate = asyncio.Event()
        waiting = 0

        class Process(FakeRestSupabase):
            async def _rpc(self, name, payload):
                nonlocal waiting
                if name == "gc_commit_documents":
                    waiting += 1
                    if waiting == 2:
                        gate.set()
                    await asyncio.wait_for(gate.wait(), 5)
                return await super()._rpc(name, payload)

        a, b = Process(), Process()
        a.remote = b.remote = shared
        results = await asyncio.gather(
            pay(a, "M1"), pay(b, "M2"), return_exceptions=True
        )
        assert (
            sum(isinstance(r, dict) and r.get("success") is True for r in results) == 1
        )
        errors = [r for r in results if isinstance(r, HTTPException)]
        assert len(errors) == 1 and errors[0].status_code == 409
        assert len(shared["bank_payment_allocations"]) == 1
        assert shared["invoices"]["F1"]["importo_pagato"] == 100
        assert len(shared["prima_nota_banca"]) == 1

    asyncio.run(scenario())


def test_errore_tardivo_annulla_quote_fattura_e_prima_nota(monkeypatch):
    async def broken(*args, **kwargs):
        raise RuntimeError("guasto simulato partita aperta")

    monkeypatch.setattr(bank, "_aggiorna_partita_aperta", broken)

    async def scenario():
        db = ClientArchivioMemoria()["rollback"]
        for k, rows in seed().items():
            for d in rows:
                await db[k].insert_one(d)
        with pytest.raises(RuntimeError):
            await pay(db, "M1")
        assert await db["bank_payment_allocations"].count_documents({}) == 0
        assert await db["prima_nota_banca"].count_documents({}) == 0
        assert "importo_pagato" not in await db["invoices"].find_one({"id": "F1"})
        assert (await db["estratto_conto_movimenti"].find_one({"id": "M1"}))[
            "riconciliato"
        ] is False

    asyncio.run(scenario())


def test_movimento_gia_consumato_non_paga_una_seconda_fattura():
    async def scenario():
        db = ClientArchivioMemoria()["movimento_unico"]
        for k, rows in seed().items():
            for d in rows:
                await db[k].insert_one(d)
        other = {**seed()["invoices"][0], "_id": "F2", "id": "F2"}
        await db["invoices"].insert_one(other)
        await pay(db, "M1")
        with pytest.raises(HTTPException) as e:
            await pay(db, "M1", "F2")
        assert e.value.status_code == 409
        assert await db["bank_payment_allocations"].count_documents({}) == 1
        assert "importo_pagato" not in await db["invoices"].find_one({"id": "F2"})

    asyncio.run(scenario())
