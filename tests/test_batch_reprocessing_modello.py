"""Regressioni per il riprocessamento cedolini e il modello documentale."""

import asyncio
import base64


def test_modello_documentale_configurabile_senza_snapshot_ritirato(monkeypatch):
    from app.services.anthropic_llm_client import document_model_name

    monkeypatch.delenv("ANTHROPIC_DOCUMENT_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    assert document_model_name() == "claude-sonnet-4-6"

    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-5")
    assert document_model_name() == "claude-sonnet-5"

    monkeypatch.setenv("ANTHROPIC_DOCUMENT_MODEL", "claude-haiku-4-5")
    assert document_model_name() == "claude-haiku-4-5"


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, length):
        return list(self.docs)[:length]


class _Collection:
    def __init__(self, docs=None):
        self.docs = docs or []

    def find(self, *_args, **_kwargs):
        return _Cursor(self.docs)

    async def update_one(self, *_args, **_kwargs):
        return None


class _Db:
    def __init__(self):
        pdf = base64.b64encode(b"%PDF-cedolino-test").decode()
        self.collections = {
            "cedolini": _Collection([
                {"_id": "uno", "pdf_data": pdf},
                {"_id": "due", "pdf_data": pdf},
            ]),
            "payslips": _Collection(),
            "buste_paga": _Collection(),
            "extracted_documents": _Collection(),
        }

    def __getitem__(self, name):
        return self.collections[name]


def test_i_tentativi_restano_contati_quando_il_parser_fallisce(monkeypatch):
    from app.services import batch_reprocessing as modulo

    async def parser_in_errore(*_args, **_kwargs):
        raise RuntimeError("modello non disponibile")

    db = _Db()
    monkeypatch.setattr(modulo.Database, "get_db", lambda: db)
    monkeypatch.setattr(modulo, "parse_cedolino_enhanced", parser_in_errore)

    esito = asyncio.run(modulo.BatchReprocessingService().reprocess_all_cedolini(True))

    assert esito["cedolini_total"] == 2
    assert esito["cedolini_processed"] == 2
    assert esito["cedolini_success"] == 0
    assert esito["cedolini_errors"] == 2
