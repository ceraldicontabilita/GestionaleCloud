"""GC-17: il PDF di una busta paga si abbina solo al cedolino del suo dipendente."""
import asyncio

from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.email_full_download import smart_auto_associate


def _db(cedolini, dipendenti=()):
    db = ClientArchivioMemoria()["test"]

    async def seed():
        for c in cedolini:
            await db["cedolini"].insert_one(dict(c))
        for d in dipendenti:
            await db["dipendenti"].insert_one(dict(d))
        await db["cedolini_email_attachments"].insert_one({
            "id": "pdf-1", "associato": False, "pdf_data": "UERG", "pdf_hash": "h",
            "filename": "Busta paga - Vespa Vincenzo - Settembre 2024 - 2.pdf",
        })
    asyncio.run(seed())
    return db


def _pdf_di(db, cid):
    return asyncio.run(db["cedolini"].find_one({"id": cid})).get("pdf_data")


def test_non_finisce_sul_cedolino_di_un_altro_dipendente(monkeypatch):
    monkeypatch.setattr("app.services.hr_cedolini_deposito.deposita_cedolino_in_hr", lambda *_: asyncio.sleep(0))
    db = _db([
        {"id": "altro", "dipendente": "ROSSI MARIO", "mese": 9, "anno": 2024},
        {"id": "suo", "dipendente": "VESPA VINCENZO", "mese": 9, "anno": 2024},
    ])
    asyncio.run(smart_auto_associate(db))
    assert _pdf_di(db, "altro") is None
    assert _pdf_di(db, "suo") == "UERG"


def test_omonimo_di_cognome_non_basta(monkeypatch):
    monkeypatch.setattr("app.services.hr_cedolini_deposito.deposita_cedolino_in_hr", lambda *_: asyncio.sleep(0))
    db = _db([{"id": "fratello", "dipendente": "VESPA GIUSEPPE", "mese": 9, "anno": 2024}])
    stats = asyncio.run(smart_auto_associate(db))
    assert _pdf_di(db, "fratello") is None
    assert stats["associated"] == 0


def test_due_candidati_uguali_restano_da_associare(monkeypatch):
    monkeypatch.setattr("app.services.hr_cedolini_deposito.deposita_cedolino_in_hr", lambda *_: asyncio.sleep(0))
    db = _db([
        {"id": "a", "dipendente": "Vespa Vincenzo", "mese": 9, "anno": 2024},
        {"id": "b", "dipendente": "VESPA VINCENZO", "mese": 9, "anno": 2024},
    ])
    asyncio.run(smart_auto_associate(db))
    assert _pdf_di(db, "a") is None and _pdf_di(db, "b") is None


def test_nome_dall_anagrafica_quando_il_cedolino_ha_solo_l_id(monkeypatch):
    monkeypatch.setattr("app.services.hr_cedolini_deposito.deposita_cedolino_in_hr", lambda *_: asyncio.sleep(0))
    db = _db(
        [{"id": "c1", "employee_id": "e1", "mese": 9, "anno": 2024},
         {"id": "c2", "employee_id": "e2", "mese": 9, "anno": 2024}],
        [{"id": "e1", "nome": "Mario", "cognome": "Rossi"},
         {"id": "e2", "nome": "Vincenzo", "cognome": "Vespa"}],
    )
    asyncio.run(smart_auto_associate(db))
    assert _pdf_di(db, "c1") is None
    assert _pdf_di(db, "c2") == "UERG"
