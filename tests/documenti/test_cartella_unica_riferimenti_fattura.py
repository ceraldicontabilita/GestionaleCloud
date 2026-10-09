"""Il registro della cartella unica sa quale fattura ha creato ogni file.

07/10/2026: 4002 file `tipo='fattura'` in ELABORATE con `riferimenti = {}`,
quindi dopo l'azzeramento di `invoices` non si poteva rimettere in coda solo i
file delle fatture sparite. L'id della fattura (creata o gia' presente) sale dal
risultato dell'import e il registro lo conserva; niente id inventati.
"""
import asyncio
from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from mongomock_motor import AsyncMongoMockClient

from app.routers import documenti as documenti_mod
from app.routers.invoices import fatture_upload
from app.services import drive_cartella_unica as cu

from tests.documenti.test_drive_cartella_unica import ambiente, run  # noqa: F401 - fixture


PARSED = {"invoice_number": "7/2026", "supplier_vat": "01234567890",
          "invoice_date": "2026-03-01", "supplier_name": "ALFA", "total_amount": 10.0}


def test_riferimenti_del_risultato_solo_chiavi_valorizzate():
    assert cu.riferimenti_del_risultato({"success": True, "tipo_rilevato": "fattura"}) == {}
    assert cu.riferimenti_del_risultato({
        "success": True, "fattura_id": "inv-1", "invoice_number": "7/2026",
        "supplier_vat": "01234567890", "corrispettivo_id": None, "message": "x",
    }) == {"fattura_id": "inv-1", "invoice_number": "7/2026", "supplier_vat": "01234567890"}


def test_il_registro_conserva_fattura_id_dopo_un_import_riuscito_e_vuoto_senza_id(ambiente):  # noqa: F811
    drive, _, esiti = ambiente
    db = AsyncMongoMockClient()["t"]
    drive.aggiungi("f1", "con_id.xml", b"<xml>1</xml>", "inbox")
    drive.aggiungi("f2", "senza_id.xml", b"<xml>2</xml>", "inbox")
    drive.aggiungi("f3", "gia.xml", b"<xml>3</xml>", "inbox")
    esiti["con_id.xml"] = {"success": True, "tipo_rilevato": "fattura", "fattura_id": "inv-77",
                           "invoice_number": "7/2026", "supplier_vat": "01234567890"}
    esiti["senza_id.xml"] = {"success": True, "tipo_rilevato": "fattura", "message": "importata"}
    esiti["gia.xml"] = {"success": False, "duplicate": True, "tipo_rilevato": "fattura",
                        "fattura_id": "inv-vecchia", "invoice_number": "3/2026", "supplier_vat": "999"}

    esito = run(cu.giro(db))
    assert esito["elaborati"] == 3
    righe = {r["id"]: r for r in run(db[cu.REGISTRO].find({}, {"_id": 0}).to_list(10))}
    assert righe["f1"]["riferimenti"] == {"fattura_id": "inv-77", "invoice_number": "7/2026",
                                         "supplier_vat": "01234567890"}
    assert righe["f2"]["riferimenti"] == {}
    # Gia' presente: il registro punta alla fattura in archivio, non a una nuova.
    assert righe["f3"]["gia_presente"] is True
    assert righe["f3"]["riferimenti"]["fattura_id"] == "inv-vecchia"
    # Il comportamento di spostamento non cambia.
    assert all(drive.file[f]["parent"] == "elaborate" for f in ("f1", "f2", "f3"))


@pytest.fixture
def import_fattura(monkeypatch):
    db = AsyncMongoMockClient()["t"]
    monkeypatch.setattr(documenti_mod.Database, "get_db", lambda: db)

    async def tipo(*_):
        return "fattura"

    monkeypatch.setattr(documenti_mod, "rileva_tipo_documento", tipo)
    monkeypatch.setattr(fatture_upload, "parse_fattura_xml", lambda _xml: dict(PARSED))
    monkeypatch.setattr("app.services.fatture_emesse.e_fattura_emessa", lambda _p: False)

    async def anno(_db):
        return 2026

    monkeypatch.setattr("app.services.config_import.get_anno_importazione_attivo", anno)
    return db


def _upload():
    return UploadFile(filename="IT01234567890_00007.xml", file=BytesIO(b"<?xml version='1.0'?><F/>"))


def test_l_import_riuscito_porta_l_id_della_fattura_nel_risultato(import_fattura, monkeypatch):
    async def salva(db, body, filename, xml_raw=None):
        return {**body, "id": "inv-77"}

    monkeypatch.setattr(fatture_upload, "process_fattura_to_db", salva)
    esito = asyncio.run(documenti_mod.upload_documento_automatico(file=_upload()))
    assert esito["success"] is True and esito["imported"] == 1
    assert cu.riferimenti_del_risultato(esito) == {
        "fattura_id": "inv-77", "invoice_number": "7/2026", "supplier_vat": "01234567890"}


def test_la_fattura_gia_presente_porta_l_id_di_quella_in_archivio(import_fattura, monkeypatch):
    db = import_fattura
    chiave = fatture_upload.generate_invoice_key(
        PARSED["invoice_number"], PARSED["supplier_vat"], PARSED["invoice_date"])
    asyncio.run(db["invoices"].insert_one({"id": "inv-vecchia", "invoice_key": chiave,
                                           "invoice_number": "7/2026", "supplier_vat": "01234567890"}))

    async def doppione(db, body, filename, xml_raw=None):
        raise HTTPException(status_code=409, detail="Fattura duplicata")

    monkeypatch.setattr(fatture_upload, "process_fattura_to_db", doppione)
    esito = asyncio.run(documenti_mod.upload_documento_automatico(file=_upload()))
    assert esito["duplicate"] is True
    assert esito["fattura_id"] == "inv-vecchia"
    assert cu.riferimenti_del_risultato(esito)["fattura_id"] == "inv-vecchia"


def test_doppione_senza_fattura_in_archivio_non_inventa_un_id(import_fattura, monkeypatch):
    async def doppione(db, body, filename, xml_raw=None):
        raise HTTPException(status_code=409, detail="Fattura duplicata")

    monkeypatch.setattr(fatture_upload, "process_fattura_to_db", doppione)
    esito = asyncio.run(documenti_mod.upload_documento_automatico(file=_upload()))
    assert esito["duplicate"] is True and "fattura_id" not in esito
    assert cu.riferimenti_del_risultato(esito) == {}
