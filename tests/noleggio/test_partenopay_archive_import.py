import asyncio
import hashlib
import io
import json
import zipfile

from app.services.archivio_documenti_memoria import ClientArchivioMemoria

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
    db = ClientArchivioMemoria()["test"]
    result = asyncio.run(mod.import_partenopay_archive(db, _archive(), dry_run=True))
    assert result["success"] is True
    assert result["records"] == 1
    assert result["files_verified"] == 1
    assert asyncio.run(db["verbali_noleggio"].count_documents({})) == 0


def test_import_idempotente_e_pagato_solo_con_quietanza(monkeypatch):
    db = ClientArchivioMemoria()["test"]

    monkeypatch.setattr("app.services.email_drive_archive.archive_document_copy",
                        lambda *_args, **_kwargs: {"status": "archived", "area": "verbali"})
    first = asyncio.run(mod.import_partenopay_archive(db, _archive(), dry_run=False))
    second = asyncio.run(mod.import_partenopay_archive(db, _archive(), dry_run=False))
    assert first["nuovi"] == 1 and first["inserted_or_updated"] == 1
    # Secondo giro: niente di nuovo, niente riscritto, nessun promemoria in piu'.
    assert second["nuovi"] == 0 and second["aggiornati"] == 0 and second["inserted_or_updated"] == 0
    assert second["invariati"] == 1 and second["email_nuove"] == 0 and second["file_nuovi"] == 0
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
    db = ClientArchivioMemoria()["test"]
    result = asyncio.run(mod.import_partenopay_archive(db, out.getvalue(), dry_run=False))
    assert result["success"] is False
    assert result["integrity_errors"][0]["errore"] == "sha256_non_coincide"
    assert asyncio.run(db["verbali_noleggio"].count_documents({})) == 0


def test_retry_non_riarchivia_documento_gia_copiato(monkeypatch):
    db = ClientArchivioMemoria()["test"]
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
    db = ClientArchivioMemoria()["test"]
    result = asyncio.run(mod.import_partenopay_archive(db, out.getvalue(), dry_run=False))
    assert result["success"] is True
    verbale = asyncio.run(db["verbali_noleggio"].find_one({}))
    assert verbale["stato"] == "pagato_attesa_quietanza"
    assert verbale["quietanza_ricevuta"] is False


def test_file_senza_sha256_dichiarato_non_e_verificato_e_non_scrive():
    """GC-17: prima un file senza hash passava come verificato e finiva sul
    documento ``partenopay_`` condiviso da tutti i file senza hash."""
    content = _archive()
    src = zipfile.ZipFile(io.BytesIO(content))
    payload = json.loads(src.read("package_clean/data.json"))
    payload["files"][0]["sha256"] = ""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as dst:
        for item in src.infolist():
            data = json.dumps(payload) if item.filename.endswith("data.json") else src.read(item.filename)
            dst.writestr(item.filename, data)
    db = ClientArchivioMemoria()["test"]
    result = asyncio.run(mod.import_partenopay_archive(db, out.getvalue(), dry_run=False))
    assert result["success"] is False
    assert result["integrity_errors"][0]["errore"] == "sha256_assente"
    assert asyncio.run(db["documents_inbox"].count_documents({})) == 0


def _con_manifest(righe_manifest: str) -> bytes:
    src = zipfile.ZipFile(io.BytesIO(_archive()))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as dst:
        for name in src.namelist():
            if name.endswith("MANIFEST_SHA256.csv"):
                dst.writestr(name, righe_manifest)
            else:
                dst.writestr(name, src.read(name))
    return out.getvalue()


_SHA_PDF = hashlib.sha256(b"not-a-real-pdf").hexdigest()
_PERCORSO = "documenti/02_QUIETANZE/Ricevuta_302000600005080318.pdf"


def test_manifest_corretto_e_contato():
    plan = mod.inspect_partenopay_archive(_con_manifest(f"file,sha256\n{_PERCORSO},{_SHA_PDF}\n"))
    assert plan["integrity_errors"] == []
    assert plan["manifest_righe"] == 1 and plan["manifest_verificati"] == 1
    assert plan["avvisi"] == []


def test_manifest_relativo_a_documenti_vale_come_quello_del_pacchetto():
    righe = f"percorso,sha256\n02_QUIETANZE/Ricevuta_302000600005080318.pdf,{_SHA_PDF}\n"
    plan = mod.inspect_partenopay_archive(_con_manifest(righe))
    assert plan["integrity_errors"] == [] and plan["manifest_verificati"] == 1


def test_manifest_con_hash_diverso_blocca_l_import():
    db = ClientArchivioMemoria()["test"]
    raw = _con_manifest(f"file,sha256\n{_PERCORSO},{'f' * 64}\n")
    result = asyncio.run(mod.import_partenopay_archive(db, raw, dry_run=False))
    assert result["success"] is False
    assert result["integrity_errors"][0]["errore"] == "manifest_sha256_non_coincide"
    assert asyncio.run(db["verbali_noleggio"].count_documents({})) == 0
    assert asyncio.run(db["documents_inbox"].count_documents({})) == 0


def test_file_dell_indice_assente_dal_manifest_blocca_l_import():
    raw = _con_manifest(f"file,sha256\naltro/file.pdf,{_SHA_PDF}\n")
    plan = mod.inspect_partenopay_archive(raw)
    assert plan["integrity_errors"][0]["errore"] == "non_nel_manifest"


def test_manifest_vuoto_e_un_avviso_non_una_prova():
    plan = mod.inspect_partenopay_archive(_archive())
    assert plan["manifest_righe"] == 0 and plan["manifest_verificati"] == 0
    assert "manifest_vuoto" in plan["avvisi"]


def test_reimport_non_sposta_la_scadenza_ne_crea_promemoria(monkeypatch):
    db = ClientArchivioMemoria()["test"]
    monkeypatch.setattr("app.services.email_drive_archive.archive_document_copy",
                        lambda *_a, **_k: {"status": "archived"})
    asyncio.run(mod.import_partenopay_archive(db, _archive(), dry_run=False))
    verbale = asyncio.run(db["verbali_noleggio"].find_one({}))
    asyncio.run(db["verbali_noleggio"].update_one(
        {"id": verbale["id"]}, {"$set": {"scadenza_operativa": "2020-01-01"}}))
    second = asyncio.run(mod.import_partenopay_archive(db, _archive(), dry_run=False))
    assert second["nuovi"] == 0
    assert asyncio.run(db["verbali_noleggio"].find_one({}))["scadenza_operativa"] == "2020-01-01"
    assert asyncio.run(db["notification_log"].count_documents({})) == 4


def test_codice_avviso_intero_o_float_non_diventa_identita():
    # Il codice avviso/IUV e' testo: un float ha gia' perso cifre e non si indovina.
    assert mod._testo_identificativo(302000600005080318) == "302000600005080318"
    assert mod._testo_identificativo(3.02000600005080318e17) == ""
    assert mod._testo_identificativo(" 3020 0060 0005 0803 18 ") == "302000600005080318"


def test_reimport_non_riporta_a_pagato_un_verbale_gia_riconciliato(monkeypatch):
    db = ClientArchivioMemoria()["test"]
    monkeypatch.setattr("app.services.email_drive_archive.archive_document_copy",
                        lambda *_a, **_k: {"status": "archived"})
    asyncio.run(mod.import_partenopay_archive(db, _archive(), dry_run=False))
    verbale = asyncio.run(db["verbali_noleggio"].find_one({}))
    asyncio.run(db["verbali_noleggio"].update_one({"id": verbale["id"]}, {"$set": {"stato": "riconciliato"}}))
    asyncio.run(mod.import_partenopay_archive(db, _archive(), dry_run=False))
    assert asyncio.run(db["verbali_noleggio"].find_one({}))["stato"] == "riconciliato"
