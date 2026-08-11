import asyncio
import base64

from mongomock_motor import AsyncMongoMockClient

from app.services import ripielaborazione_documenti as modulo
from app.services.ripielaborazione_documenti import RielaborazioneDocumentiService


def _pdf_fake() -> str:
    return base64.b64encode(b"%PDF-1.4 documento di prova").decode()


def test_anteprima_elenca_categorie_dinamiche():
    async def scenario():
        db = AsyncMongoMockClient()["rielaborazione-preview"]
        await db["documents_inbox"].insert_many([
            {"id": "1", "document_type": "f24", "pdf_data": _pdf_fake()},
            {"id": "2", "document_type": "tari_avviso", "pdf_data": _pdf_fake()},
            {"id": "3", "document_type": "tari_avviso", "pdf_data": _pdf_fake()},
            {"id": "4", "document_type": "cartella_ader", "pdf_data": _pdf_fake()},
        ])
        result = await RielaborazioneDocumentiService(db).anteprima()
        assert result["totale"] == 4
        assert result["categorie"]["tari_avviso"] == 2
        assert result["categorie"]["cartella_ader"] == 1
        assert result["categorie"]["f24"] == 1

    asyncio.run(scenario())


def test_simulazione_non_scrive_sul_documento(monkeypatch):
    async def parser_finto(**kwargs):
        return {"success": True, "tipo_documento": "fattura"}

    monkeypatch.setattr(modulo, "parse_document_with_ai", parser_finto)

    async def scenario():
        db = AsyncMongoMockClient()["rielaborazione-dry-run"]
        await db["documents_inbox"].insert_one({
            "id": "fatt-1", "document_type": "fattura_pdf", "pdf_data": _pdf_fake(),
        })
        result = await RielaborazioneDocumentiService(db).rielabora(dry_run=True)
        assert result["totale_successi"] == 1
        doc = await db["documents_inbox"].find_one({"id": "fatt-1"})
        assert "rielaborazione" not in doc

    asyncio.run(scenario())


def test_esecuzione_salva_esito_accanto_all_originale(monkeypatch):
    async def parser_finto(**kwargs):
        return {"success": True, "tipo_documento": "verbale", "numero_verbale": "V-1"}

    monkeypatch.setattr(modulo, "parse_document_with_ai", parser_finto)

    async def scenario():
        db = AsyncMongoMockClient()["rielaborazione-write"]
        originale = _pdf_fake()
        await db["documents_inbox"].insert_one({
            "id": "v-1", "document_type": "verbale", "pdf_data": originale,
        })
        result = await RielaborazioneDocumentiService(db).rielabora(dry_run=False)
        assert result["totale_successi"] == 1
        doc = await db["documents_inbox"].find_one({"id": "v-1"})
        assert doc["pdf_data"] == originale
        assert doc["rielaborazione"]["success"] is True
        assert doc["rielaborazione"]["stato"] == "rielaborato"
        assert doc["rielaborazione"]["risultato"]["numero_verbale"] == "V-1"

    asyncio.run(scenario())


def test_filtro_categoria_non_tocca_le_altre(monkeypatch):
    async def parser_finto(**kwargs):
        return {"success": True}

    monkeypatch.setattr(modulo, "parse_document_with_ai", parser_finto)

    async def scenario():
        db = AsyncMongoMockClient()["rielaborazione-filtro"]
        await db["documents_inbox"].insert_many([
            {"id": "a", "document_type": "f24", "pdf_data": _pdf_fake()},
            {"id": "b", "document_type": "tari_avviso", "pdf_data": _pdf_fake()},
        ])
        result = await RielaborazioneDocumentiService(db).rielabora(
            dry_run=False, categoria="tari_avviso"
        )
        assert result["totale_documenti"] == 1
        assert "rielaborazione" not in await db["documents_inbox"].find_one({"id": "a"})
        assert "rielaborazione" in await db["documents_inbox"].find_one({"id": "b"})

    asyncio.run(scenario())


def test_formato_senza_parser_specifico_resta_da_verificare_non_errore(monkeypatch):
    async def parser_finto(**kwargs):
        assert kwargs["document_type"] == "auto"
        return {
            "success": False,
            "detected_type": "altro",
            "error": "Tipo documento non supportato: altro",
        }

    monkeypatch.setattr(modulo, "parse_document_with_ai", parser_finto)

    async def scenario():
        db = AsyncMongoMockClient()["rielaborazione-fallback"]
        originale = _pdf_fake()
        await db["documents_inbox"].insert_one({
            "id": "ader-1", "document_type": "cartella_ader", "pdf_data": originale,
        })
        result = await RielaborazioneDocumentiService(db).rielabora(dry_run=False)
        assert result["totale_errori"] == 0
        assert result["totale_da_verificare"] == 1
        assert result["categorie"]["cartella_ader"]["da_verificare"] == 1
        doc = await db["documents_inbox"].find_one({"id": "ader-1"})
        assert doc["pdf_data"] == originale
        assert doc["rielaborazione"]["stato"] == "da_verificare"
        assert doc["rielaborazione"]["parser_usato"] == "auto"

    asyncio.run(scenario())
