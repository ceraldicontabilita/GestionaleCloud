import asyncio
import hashlib
import io
import json
import zipfile

from app.services.sheets_document_store import MemorySheetsClient

from app.services import partenopay_archive_import as mod


def _archive():
    pdf = b"not-a-real-pdf"
    relative = "documenti/02_QUIETANZE/Ricevuta_302000600005080318.pdf"
    payload = {
        "summary": {},
        "records": [{
            "codice_avviso": "302000600005080318",
            "oggetto_pagamento": "Violazione CdS - TARGA: GG782PN - DATA: 20/01/2025 VERBALE N.: A25110069164- C.F.: 04523831214",
            "importo": 29.40, "data_pagamento": "23/01/2025", "ente": "COMUNE DI NAPOLI",
            "cf_piva": "04523831214", "files": [relative],
            "stati": "Avviso; Pagamento eseguito; Quietanza",
        }],
        "emails": [{"id": "gmail-1", "gmail_url": "https://mail.google.com/mail/u/0/#all/gmail-1",
                    "mittente": "partenopay@ext.comune.napoli.it", "allegati": [relative]}],
        "files": [{"file": relative, "nome": "Ricevuta_302000600005080318.pdf", "estensione": "pdf",
                   "categoria": "02_QUIETANZE", "codice_avviso": "302000600005080318",
                   "sha256": hashlib.sha256(pdf).hexdigest()}],
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("package_clean/data.json", json.dumps(payload))
        archive.writestr("package_clean/documenti/MANIFEST_SHA256.csv", "file,sha256\n")
        archive.writestr("package_clean/" + relative, pdf)
    return out.getvalue()


def test_dry_run_non_scrive_e_verifica_hash():
    db = MemorySheetsClient()["test"]
    result = asyncio.run(mod.import_partenopay_archive(db, _archive(), dry_run=True))
    assert result["success"] is True
    assert result["records"] == 1
    assert result["files_verified"] == 1
    assert asyncio.run(db["verbali_noleggio"].count_documents({})) == 0


def test_import_idempotente_e_pagato_solo_con_quietanza(monkeypatch):
    db = MemorySheetsClient()["test"]

    monkeypatch.setattr("app.services.email_drive_archive.archive_document_copy",
                        lambda *_args, **_kwargs: {"status": "archived", "area": "verbali"})
    first = asyncio.run(mod.import_partenopay_archive(db, _archive(), dry_run=False))
    second = asyncio.run(mod.import_partenopay_archive(db, _archive(), dry_run=False))
    assert first["inserted_or_updated"] == second["inserted_or_updated"] == 1
    assert asyncio.run(db["verbali_noleggio"].count_documents({})) == 1
    verbale = asyncio.run(db["verbali_noleggio"].find_one({}))
    assert verbale["numero_verbale"] == "A25110069164"
    assert verbale["targa"] == "GG782PN"
    assert verbale["stato_pagamento_documentale"] == "PAGATO_VERIFICATO"
    assert verbale["stato"] == "pagato"
    assert verbale["quietanza_ricevuta"] is True
    assert asyncio.run(db["notification_log"].count_documents({})) == 4


def test_hash_errato_blocca_import():
    raw = _archive()
    src = zipfile.ZipFile(io.BytesIO(raw))
    payload = json.loads(src.read("package_clean/data.json"))
    payload["files"][0]["sha256"] = "0" * 64
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for name in src.namelist():
            archive.writestr(name, json.dumps(payload) if name.endswith("data.json") else src.read(name))
    db = MemorySheetsClient()["test"]
    result = asyncio.run(mod.import_partenopay_archive(db, out.getvalue(), dry_run=False))
    assert result["success"] is False
    assert result["integrity_errors"][0]["errore"] == "sha256_non_coincide"
    assert asyncio.run(db["verbali_noleggio"].count_documents({})) == 0


def test_retry_non_riarchivia_documento_gia_copiato(monkeypatch):
    db = MemorySheetsClient()["test"]
    calls = []

    monkeypatch.setattr(
        "app.services.email_drive_archive.archive_document_copy",
        lambda *_args, **_kwargs: calls.append(True) or {"status": "archived", "area": "verbali"},
    )
    asyncio.run(mod.import_partenopay_archive(db, _archive(), dry_run=False))
    asyncio.run(mod.import_partenopay_archive(db, _archive(), dry_run=False))
    assert len(calls) == 1


def test_pagamento_senza_quietanza_resta_in_attesa_quietanza(monkeypatch):
    raw = _archive()
    src = zipfile.ZipFile(io.BytesIO(raw))
    payload = json.loads(src.read("package_clean/data.json"))
    payload["records"][0]["files"] = []
    payload["files"] = []
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("package_clean/data.json", json.dumps(payload))
        archive.writestr("package_clean/documenti/MANIFEST_SHA256.csv", "file,sha256\n")
    db = MemorySheetsClient()["test"]
    result = asyncio.run(mod.import_partenopay_archive(db, out.getvalue(), dry_run=False))
    assert result["success"] is True
    verbale = asyncio.run(db["verbali_noleggio"].find_one({}))
    assert verbale["stato"] == "pagato_attesa_quietanza"
    assert verbale["quietanza_ricevuta"] is False
