"""Regressioni: ogni ingresso F24 deve delegare al servizio canonico."""

import asyncio
from pathlib import Path

from app.routers import ai_parser
from app.services import document_data_saver, f24_canonico, upload_ai_processor


class _Upload:
    filename = "f24-test.pdf"

    async def read(self):
        return b"%PDF-fixture-anonima"


def test_ai_parser_salva_f24_solo_tramite_ingresso_canonico(monkeypatch):
    class _Db:
        def __getitem__(self, name):
            raise AssertionError(f"accesso diretto inatteso a {name}")

    monkeypatch.setattr(ai_parser.Database, "get_db", staticmethod(lambda: _Db()))

    async def fake_parse(**_kwargs):
        return {
            "success": True,
            "sezione_erario": [{"codice_tributo": "1040"}],
            "sezione_inps": [],
            "sezione_regioni": [],
            "sezione_imu": [],
        }

    calls = []

    async def fake_import(db, content, filename, *, source):
        calls.append((db, content, filename, source))
        return {"success": True, "duplicate": False, "f24_id": "f24-canonico"}

    monkeypatch.setattr(ai_parser, "parse_f24_ai", fake_parse)
    monkeypatch.setattr(f24_canonico, "importa_modello_bytes", fake_import)

    result = asyncio.run(ai_parser.parse_f24_endpoint(_Upload(), True, False))

    assert result["saved_id"] == "f24-canonico"
    assert result["collection"] == "f24_unificato"
    assert calls[0][1:] == (
        b"%PDF-fixture-anonima",
        "f24-test.pdf",
        "ai_parser_f24",
    )


def test_document_data_saver_delega_a_salva_f24(monkeypatch):
    calls = []

    async def fake_save(db, doc, source=None):
        calls.append((db, doc, source))
        return "f24-canonico"

    monkeypatch.setattr(f24_canonico, "salva_f24", fake_save)
    db = object()
    result = asyncio.run(document_data_saver.save_f24_to_gestionale(
        db,
        {"codice_fiscale": "RSSMRA00A00A000A", "totale_versamento": "284,00"},
        {"filename": "f24.pdf"},
    ))

    assert result == {"status": "saved", "collection": "f24_unificato", "id": "f24-canonico"}
    assert calls[0][0] is db
    assert calls[0][2] == "document_ai"


def test_upload_ai_non_archivia_un_parse_fallito_nel_registro_f24(monkeypatch):
    class _Db:
        def __getitem__(self, name):
            raise AssertionError(f"scrittura inattesa a {name}")

    async def fake_parse(**_kwargs):
        return {"success": False, "error": "test parser fallito"}

    monkeypatch.setattr(upload_ai_processor, "parse_f24_ai", fake_parse)
    result = asyncio.run(upload_ai_processor.process_upload_f24(
        _Db(), b"%PDF-fixture-anonima", "f24.pdf"
    ))

    assert result["success"] is False
    assert result["document_id"] is None
    assert "non salvato" in result["message"]


def test_nessun_writer_f24_diretto_fuori_dal_servizio_canonico():
    root = Path(__file__).resolve().parents[1] / "app"
    forbidden = (
        'db["f24_unificato"].insert_one',
        "db['f24_unificato'].insert_one",
        "db[COLL_F24].insert_one",
    )
    findings = []
    for path in root.rglob("*.py"):
        if path.name == "f24_canonico.py":
            continue
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                findings.append(f"{path.relative_to(root)}: {token}")
    assert findings == []


def test_chiave_canonica_distingue_f24_manuali_con_importi_diversi():
    base = {
        "data_scadenza": "2026-08-16",
        "periodo_riferimento": "07/2026",
        "codici_tributo": ["6007"],
    }
    assert f24_canonico.chiave_f24({**base, "importo": 100.0}) != f24_canonico.chiave_f24(
        {**base, "importo": 200.0}
    )
