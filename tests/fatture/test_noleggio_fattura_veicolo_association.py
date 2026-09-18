import asyncio

import pytest
from fastapi import HTTPException

from app.services.noleggio.associations import (
    COLLECTION_FATTURA_VEICOLO_LINKS,
    MANUAL_RULE_ID,
    associate_invoice_to_vehicle,
    normalize_company_id,
    normalize_contract_reference,
)
from app.services.noleggio.processors import scegli_veicolo_per_fattura
from app.services.noleggio.constants import COLLECTION


class FakeCollection:
    def __init__(self, name, db):
        self.name = name
        self.db = db

    async def find_one(self, _query, _projection=None):
        if self.name == "invoices":
            return self.db.invoice
        if self.name == COLLECTION:
            return self.db.vehicle
        return None

    async def update_one(self, query, update, upsert=False):
        self.db.update = {"query": query, "update": update, "upsert": upsert}


class FakeDb:
    def __init__(self, invoice, vehicle):
        self.invoice = invoice
        self.vehicle = vehicle
        self.update = None

    def __getitem__(self, name):
        return FakeCollection(name, self)


def test_normalizzazione_piva_e_contratto_non_dipende_dal_layout():
    assert normalize_company_id("IT 01924961004") == "01924961004"
    assert normalize_contract_reference("Contratto 607-4667") == "CONTRATTO6074667"
    target, certain = scegli_veicolo_per_fattura(
        {"contratto": "607-4667"},
        [
            ("AA000AA", {"contratto": "111"}),
            ("GX037HJ", {"contratto": "607 4667"}),
        ],
        set(),
    )
    assert (target, certain) == ("GX037HJ", True)


def test_associazione_fattura_veicolo_e_idempotente_e_tracciata():
    db = FakeDb(
        invoice={
            "_id": "inv-1",
            "invoice_number": "RLR0222312",
            "invoice_date": "2026-05-21",
            "supplier_name": "ALD Automotive Italia S.r.l.",
            "supplier_vat": "IT01924961004",
        },
        vehicle={
            "targa": "GX037HJ",
            "fornitore_piva": "01924961004",
            "contratto": "6074667",
        },
    )

    result = asyncio.run(
        associate_invoice_to_vehicle(db, invoice_id="inv-1", targa="gx037hj")
    )

    assert result["invoice_id"] == "inv-1"
    assert result["targa"] == "GX037HJ"
    assert result["rule_id"] == MANUAL_RULE_ID
    assert db.update["query"] == {"invoice_id": "inv-1"}
    assert db.update["upsert"] is True
    assert db.update["update"]["$setOnInsert"]["created_at"]
    assert COLLECTION_FATTURA_VEICOLO_LINKS == "noleggio_fattura_veicolo_links"


def test_associazione_blocca_fornitore_incompatibile():
    db = FakeDb(
        invoice={
            "_id": "inv-2",
            "invoice_number": "X",
            "supplier_vat": "01924961004",
        },
        vehicle={
            "targa": "AA000AA",
            "fornitore_piva": "04911190488",
        },
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(associate_invoice_to_vehicle(db, invoice_id="inv-2", targa="AA000AA"))

    assert exc.value.status_code == 409
    assert db.update is None
