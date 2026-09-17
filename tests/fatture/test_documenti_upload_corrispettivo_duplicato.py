import asyncio
from io import BytesIO

from fastapi import UploadFile

from app.routers import documenti as documenti_mod
from app.parsers import corrispettivi_parser
from app.routers.invoices import corrispettivi_helpers


def test_upload_auto_dichiara_esplicitamente_il_corrispettivo_duplicato(monkeypatch):
    monkeypatch.setattr(documenti_mod, "detect_document_type", lambda *_: "corrispettivo")
    monkeypatch.setattr(documenti_mod.Database, "get_db", lambda: object())
    monkeypatch.setattr(
        corrispettivi_parser,
        "parse_corrispettivo_xml",
        lambda _xml: {"data": "2026-07-06", "totale": 2006.30},
    )

    async def duplicato(*_args, **_kwargs):
        return {
            "action": "duplicate",
            "corrispettivo_id": "corr-esistente",
            "data": "2026-07-06",
            "totale": 2006.30,
            "prima_nota_cassa_id": None,
            "prima_nota_banca_id": None,
        }

    monkeypatch.setattr(corrispettivi_helpers, "ingest_corrispettivo_parsed", duplicato)
    upload = UploadFile(filename="corrispettivo-test.xml", file=BytesIO(b"<Corrispettivi/>"))

    result = asyncio.run(documenti_mod.upload_documento_automatico(file=upload))

    assert result["action"] == "duplicate"
    assert result["success"] is False
    assert result["duplicate"] is True
    assert result["imported"] == 0
    assert result["prima_nota_cassa_id"] is None
    assert result["prima_nota_banca_id"] is None
