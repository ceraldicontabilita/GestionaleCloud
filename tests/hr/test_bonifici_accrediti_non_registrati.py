"""Accrediti in entrata del 2023: decisione del titolare, non si registrano."""
import asyncio
from datetime import datetime, timezone

from mongomock_motor import AsyncMongoMockClient

import app.services.bonifici_pdf_ingest as ingest
from app.routers.bonifici_module.pdf_parser import extract_transfers_from_text

ACCREDITO = "\n".join([
    "DATA", "23/10/2023", "REGISTRIAMO A VOSTRO CREDITO PER CONTO DI:",
    "Satispay Europe S.A.", "IL SEGUENTE BONIFICO", "IMPORTO", "EUR", "2,40",
    "IBAN BENEFICIARIO", "IT13X0503403406000000005462",
])
DISPOSTO = "\n".join([
    "DATA", "12/03/2025", "REGISTRIAMO A VOSTRO DEBITO A FAVORE DI:",
    "Rossi Mario  80100 napoli", "IBAN BENEFICIARIO", "IT16I0329601601000067656035",
    "IMPORTO", "EUR 953,00",
])


def _parsed(testo):
    return extract_transfers_from_text(testo, filename="x.pdf")[0]


def test_la_direzione_si_legge_dal_testo():
    assert _parsed(ACCREDITO)["direzione"] == "entrata"
    assert _parsed(DISPOSTO)["direzione"] == "uscita"


def test_solo_gli_accrediti_del_2023_sono_esclusi():
    assert ingest.accredito_non_registrabile(_parsed(ACCREDITO)) is True
    assert ingest.accredito_non_registrabile(_parsed(DISPOSTO)) is False
    del_2024 = {**_parsed(ACCREDITO), "data": datetime(2024, 1, 5, tzinfo=timezone.utc)}
    assert ingest.accredito_non_registrabile(del_2024) is False
    # Un disposto del 2023 resta: la regola vale solo per i soldi in entrata.
    assert ingest.accredito_non_registrabile(
        {**_parsed(DISPOSTO), "data": datetime(2023, 3, 1, tzinfo=timezone.utc)}) is False


def test_un_accredito_nuovo_non_si_salva(monkeypatch):
    db = AsyncMongoMockClient()["gc"]
    monkeypatch.setattr(ingest, "read_pdf_bytes", lambda _c: ACCREDITO)
    esito = asyncio.run(ingest.importa_pdf_bonifico(db, b"%PDF-accredito", "ricevuta.pdf"))
    assert esito["status"] == ingest.STATO_NON_REGISTRATO
    assert asyncio.run(db.bonifici_transfers.count_documents({})) == 0


def test_un_accredito_gia_registrato_si_toglie_con_la_sua_coda_hr(monkeypatch):
    import hashlib

    from app.services import hr_pagamenti_deposito

    db = AsyncMongoMockClient()["gc"]
    db_hr = AsyncMongoMockClient()["hr"]
    monkeypatch.setattr(hr_pagamenti_deposito, "_db_hr", lambda: db_hr)
    monkeypatch.setattr(ingest, "read_pdf_bytes", lambda _c: ACCREDITO)
    contenuto = b"%PDF-accredito"
    digest = hashlib.sha256(contenuto).hexdigest()
    asyncio.run(db.bonifici_transfers.insert_one({
        "id": "t1", "document_hash": digest, "importo": 2.4,
        "hr_deposito": {"esito": "in_coda"},
    }))
    asyncio.run(db.documents_inbox.insert_one({"id": "i1", "bonifico_transfer_id": "t1"}))
    asyncio.run(db_hr.bonifici_da_associare.insert_many([
        {"id": "c1", "gestionale_transfer_id": "t1", "stato": "da_associare"},
        {"id": "c2", "gestionale_transfer_id": "t1", "stato": "associato"},
    ]))

    esito = asyncio.run(ingest.importa_pdf_bonifico(db, contenuto, "ricevuta.pdf"))

    assert esito["status"] == ingest.STATO_NON_REGISTRATO
    assert asyncio.run(db.bonifici_transfers.count_documents({})) == 0
    assert asyncio.run(db.documents_inbox.count_documents({})) == 0
    # La riga di coda ancora da associare sparisce; una gia' lavorata da una
    # persona resta.
    rimaste = asyncio.run(db_hr.bonifici_da_associare.find({}, {"_id": 0, "id": 1}).to_list(None))
    assert rimaste == [{"id": "c2"}]


def test_un_accredito_gia_collegato_non_si_tocca(monkeypatch):
    import hashlib

    db = AsyncMongoMockClient()["gc"]
    monkeypatch.setattr(ingest, "read_pdf_bytes", lambda _c: ACCREDITO)
    contenuto = b"%PDF-accredito"
    asyncio.run(db.bonifici_transfers.insert_one({
        "id": "t1", "document_hash": hashlib.sha256(contenuto).hexdigest(),
        "hr_deposito": {"esito": "arricchito"},
    }))
    asyncio.run(ingest.importa_pdf_bonifico(db, contenuto, "ricevuta.pdf"))
    assert asyncio.run(db.bonifici_transfers.count_documents({})) == 1
