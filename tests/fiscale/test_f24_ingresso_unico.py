"""AV3-06: un solo ingresso per i modelli F24, da ogni canale.

- I router non leggono ne' scrivono da soli: passano da `importa_modello_bytes`.
- Un PDF caricato in lotto (ZIP, multiplo) viene letto: niente gusci `pending`.
- Una copia dello stesso PDF non riscrive la provenienza del primo arrivo.
"""
import asyncio
import io
import re
import zipfile
from pathlib import Path

from mongomock_motor import AsyncMongoMockClient

import app.routers.f24 as pacchetto_f24
from app.services import f24_canonico
from app.services.f24_canonico import salva_f24


def _parsed(saldo_cents=10000):
    return {
        "dati_generali": {"codice_fiscale": "04523831214", "data_versamento": "2026-07-16"},
        "sezione_erario": [{"codice_tributo": "6006", "anno": "2026", "importo_debito": saldo_cents / 100,
                            "importo_debito_cents": saldo_cents, "importo_credito_cents": 0}],
        "sezione_inps": [], "sezione_regioni": [], "sezione_tributi_locali": [],
        "totali": {"saldo_netto": saldo_cents / 100, "saldo_delega_cents": saldo_cents},
        "validazione": {"saldo_quadrato": True, "parser_version": "test"},
    }


def test_nessun_router_f24_scrive_o_legge_modelli_da_solo():
    cartella = Path(pacchetto_f24.__file__).parent
    for modulo in sorted(cartella.glob("*.py")):
        sorgente = modulo.read_text(encoding="utf-8")
        # L'unica eccezione e' la creazione a mano (`POST /api/f24`, senza PDF),
        # un fatto dichiarato dal titolare: un solo punto, con la sua fonte.
        assert sorgente.count("salva_f24(") == (1 if modulo.name == "f24_main.py" else 0), \
            f"{modulo.name} scrive modelli da solo"
        if modulo.name == "f24_main.py":
            assert 'source="f24_manual_create"' in sorgente
        assert not re.search(r"parse_f24_commercialista\(", sorgente), f"{modulo.name} legge modelli da solo"
        assert not re.search(r'\["f24_unificato"\]\.insert', sorgente), modulo.name


def test_copia_dello_stesso_pdf_non_riscrive_la_provenienza(monkeypatch):
    db = AsyncMongoMockClient()["ingresso_unico"]
    monkeypatch.setattr("app.services.parser_f24.parse_f24_commercialista", lambda pdf_content: _parsed())

    async def scenario():
        primo = await f24_canonico.importa_modello_bytes(
            db, b"%PDF-uno", "F24 IVA.PDF", source="gmail_scan",
            source_metadata={"attachment_id": "att-1", "email_subject": "F24"})
        secondo = await f24_canonico.importa_modello_bytes(
            db, b"%PDF-uno", "F24 IVA (2).PDF", source="documenti_upload_auto",
            source_metadata={"attachment_id": "att-2"})
        assert primo["duplicate"] is False and secondo["duplicate"] is True
        assert primo["f24_id"] == secondo["f24_id"]
        assert await db["f24_unificato"].count_documents({}) == 1
        modello = await db["f24_unificato"].find_one({})
        assert modello["file_name"] == "F24 IVA.PDF"
        assert modello["import_source"] == "gmail_scan"
        assert modello["source_metadata"]["attachment_id"] == "att-1"
        occ = modello["source_occurrences"]
        assert [(p["file_name"], p["attachment_id"], p["import_source"]) for p in occ] == [
            ("F24 IVA (2).PDF", "att-2", "documenti_upload_auto")]
        # La stessa copia vista due volte non si annota due volte.
        await f24_canonico.importa_modello_bytes(
            db, b"%PDF-uno", "F24 IVA (2).PDF", source="documenti_upload_auto",
            source_metadata={"attachment_id": "att-2"})
        modello = await db["f24_unificato"].find_one({})
        assert len(modello["source_occurrences"]) == 1

    asyncio.run(scenario())


def test_un_lettore_corretto_rinfresca_le_righe_sul_posto(monkeypatch):
    db = AsyncMongoMockClient()["rilettura"]
    vecchio = _parsed(); vecchio["validazione"]["parser_version"] = "v1"
    nuovo = _parsed(); nuovo["validazione"]["parser_version"] = "v2"
    nuovo["sezione_erario"][0]["descrizione"] = "IVA giugno"
    letture = iter([vecchio, nuovo])
    monkeypatch.setattr("app.services.parser_f24.parse_f24_commercialista", lambda pdf_content: next(letture))

    async def scenario():
        await f24_canonico.importa_modello_bytes(db, b"%PDF-x", "a.pdf", source="drive")
        await f24_canonico.importa_modello_bytes(db, b"%PDF-x", "a.pdf", source="upload")
        assert await db["f24_unificato"].count_documents({}) == 1
        modello = await db["f24_unificato"].find_one({})
        assert modello["validazione"]["parser_version"] == "v2"
        assert modello["sezione_erario"][0]["descrizione"] == "IVA giugno"
        assert modello["import_source"] == "drive"

    asyncio.run(scenario())


def test_salva_f24_diretto_conserva_il_primo_arrivo():
    db = AsyncMongoMockClient()["salva"]
    base = {**_parsed(), "pdf_hash": "h1", "file_name": "primo.pdf", "created_at": "2026-01-01T00:00:00+00:00"}

    async def scenario():
        id1 = await salva_f24(db, dict(base), source="a")
        id2 = await salva_f24(db, {**base, "file_name": "secondo.pdf", "created_at": "2026-02-02T00:00:00+00:00"}, source="b")
        assert id1 == id2
        doc = await db["f24_unificato"].find_one({"id": id1})
        assert doc["file_name"] == "primo.pdf" and doc["created_at"].startswith("2026-01-01")
        assert doc["import_source"] == "a"
        assert doc["source_occurrences"][0]["file_name"] == "secondo.pdf"

    asyncio.run(scenario())


def _upload(nome: str, contenuto: bytes):
    from starlette.datastructures import UploadFile
    return UploadFile(filename=nome, file=io.BytesIO(contenuto))


def test_upload_multiplo_e_zip_leggono_ogni_pdf(monkeypatch):
    from app.routers.f24 import f24_main

    db = AsyncMongoMockClient()["lotto"]
    monkeypatch.setattr(f24_main.Database, "get_db", staticmethod(lambda: db))

    def lettore(pdf_content):
        if pdf_content == b"%PDF-vuoto":
            return {"dati_generali": {}, "sezione_erario": [], "totali": {}}
        return _parsed(20000 if pdf_content == b"%PDF-2" else 10000)

    monkeypatch.setattr("app.services.parser_f24.parse_f24_commercialista", lettore)

    async def scenario():
        esito = await f24_main.upload_f24_multiple(files=[
            _upload("uno.pdf", b"%PDF-1"), _upload("copia.pdf", b"%PDF-1"),
            _upload("pratica.pdf", b"%PDF-vuoto"), _upload("nota.txt", b"x"),
        ])
        assert (esito["imported"], esito["duplicates"], esito["errors"]) == (1, 1, 2)
        stati = {d["file"]: d["status"] for d in esito["details"]}
        assert stati == {"uno.pdf": "imported", "copia.pdf": "duplicate", "pratica.pdf": "error", "nota.txt": "error"}
        assert await db["f24_unificato"].count_documents({}) == 1
        modello = await db["f24_unificato"].find_one({})
        assert modello["status"] == "da_pagare" and modello["sezione_erario"]

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("cartella/due.pdf", b"%PDF-2")
            z.writestr("__MACOSX/._due.pdf", b"x")
            z.writestr("uno.pdf", b"%PDF-1")
        esito_zip = await f24_main.upload_f24_zip(file=_upload("lotto.zip", buf.getvalue()))
        assert (esito_zip["total"], esito_zip["imported"], esito_zip["duplicates"]) == (2, 1, 1)
        assert await db["f24_unificato"].count_documents({"status": "pending"}) == 0
        assert await db["f24_unificato"].count_documents({}) == 2

    asyncio.run(scenario())
