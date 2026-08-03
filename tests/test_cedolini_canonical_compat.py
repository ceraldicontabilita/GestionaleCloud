import asyncio
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient

from app.services.cedolini_canonical_compat import canonical_salary_rows


def _run(coro):
    return asyncio.run(coro)


def test_righe_canoniche_escludono_pre_2018_e_tengono_versione_corrente():
    db = AsyncMongoMockClient()["cedolini_canonical_test"]
    now = datetime.now(timezone.utc)
    old_version = ObjectId()
    current_version = ObjectId()
    pre_2018 = ObjectId()

    _run(db["cedolini"].insert_many([
        {
            "_id": old_version,
            "employee_name": "DIPENDENTE TEST",
            "tax_code": "TSTTST80A01F839X",
            "reference_period": "01/2025",
            "summary": {"net_pay": "900.00", "total_entitlement": "900.00"},
            "pay_kind": "ordinario",
            "source_hash": "a" * 64,
            "created_at": now - timedelta(days=1),
        },
        {
            "_id": current_version,
            "employee_name": "DIPENDENTE TEST",
            "tax_code": "TSTTST80A01F839X",
            "reference_period": "01/2025",
            "summary": {"net_pay": "1000.00", "total_entitlement": "1000.00"},
            "pay_kind": "ordinario",
            "source_hash": "b" * 64,
            "created_at": now,
        },
        {
            "_id": pre_2018,
            "employee_name": "DIPENDENTE TEST",
            "tax_code": "TSTTST80A01F839X",
            "reference_period": "12/2017",
            "summary": {"net_pay": "500.00"},
            "pay_kind": "ordinario",
            "source_hash": "c" * 64,
            "created_at": now,
        },
    ]))
    _run(db["cedolini_documenti"].insert_one({"_id": "b" * 64, "gridfs_id": ObjectId()}))
    _run(db["riconciliazioni_fonti"].insert_one({
        "module": "cedolini",
        "record_id": str(old_version),
        "amount": "400.00",
    }))

    rows = _run(canonical_salary_rows(db))

    assert len(rows) == 1
    assert rows[0]["id"] == f"canonical:{current_version}"
    assert rows[0]["anno"] == 2025
    assert rows[0]["importo_busta"] == 1000.0
    assert rows[0]["importo_bonifico"] == 400.0
    assert rows[0]["saldo"] == -600.0
    assert rows[0]["cedolino_disponibile"] is True


def test_filtro_anno_mese_sul_periodo_canonico():
    db = AsyncMongoMockClient()["cedolini_canonical_filter_test"]
    now = datetime.now(timezone.utc)
    _run(db["cedolini"].insert_many([
        {
            "employee_name": "UNO",
            "tax_code": "UNOUNO80A01F839X",
            "reference_period": "02/2024",
            "summary": {"net_pay": "700.00"},
            "pay_kind": "ordinario",
            "created_at": now,
        },
        {
            "employee_name": "DUE",
            "tax_code": "DUEDUE80A01F839X",
            "reference_period": "03/2024",
            "summary": {"net_pay": "800.00"},
            "pay_kind": "ordinario",
            "created_at": now,
        },
    ]))

    rows = _run(canonical_salary_rows(db, anno=2024, mese=2))

    assert [row["dipendente"] for row in rows] == ["UNO"]
