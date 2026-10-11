import asyncio
import base64
from unittest.mock import AsyncMock

from mongomock_motor import AsyncMongoMockClient
from app.services.post_download_pipeline import processa_verbali_da_email


def test_copia_usa_writer_canonico_relata_non_crea_secondo_verbale(monkeypatch):
    from app.services import verbali_document_import as writer
    from app.services import notifiche_pec_verbali as pec
    db = AsyncMongoMockClient().db
    imported = AsyncMock(return_value={"verbale_id": "v1"})
    linked = AsyncMock(return_value={"agganciate": 1})
    monkeypatch.setattr(writer, "process_verbale_document", imported)
    monkeypatch.setattr(writer, "_extract_text", lambda b: b.decode())
    monkeypatch.setattr(pec, "aggancia_notifiche_pec", linked)

    async def run():
        for id_, text in (("copy", "Verbale n. A26111311018"), ("relata", "Relazione di notificazione")):
            await db.verbali_email_attachments.insert_one({
                "id": id_, "filename": id_ + ".pdf", "pdf_data": base64.b64encode(text.encode()).decode(),
                "email_subject": "Atto 20260355546 del 27/07/2026 [upec9470772]",
                "email_date": "Fri, 9 Oct 2026 10:45:37 +0200",
            })
        await processa_verbali_da_email(db)
        await processa_verbali_da_email(db)
        imported.assert_awaited_once()
        assert imported.call_args.kwargs["parsed_metadata"] == {"data_notifica": "2026-10-09"}
        assert imported.call_args.kwargs["source"] == "email_verbale"
        assert await db.verbali_noleggio.count_documents({}) == 0
        assert linked.await_count == 2
        copy = await db.verbali_email_attachments.find_one({"id": "copy"})
        assert copy["documento_associato_id"] == "v1"
    asyncio.run(run())


def test_importi_scadenza_del_verbale_prevalgono_su_bollettino(monkeypatch):
    from app.services.verbali_document_import import leggi_documento_verbale
    from app.services import verbali_document_import as writer, pagopa_receipts
    text = ("Verbale n. A26111311018 - cronologico Registro n. 20260355546 data verbale 27/07/2026 "
            "Art. 201 del D.Lgs. In data 27/07/2026 alle ore 09:48 in piazza nazionale 49, il proprietario "
            "del mezzo targato HB411GV ha violato i seguenti articoli: Art. 7 C. 1 F) E C. 15. "
            "Obbligato in solido in qualità di locatario: CERALDI GROUP SRL, residente a NAPOLI "
            "Società di locazione: LEASYS S.P.A., residente a TORINO "
            "entro 5 giorni è ammesso il pagamento di Euro 52,40. "
            "Dal sesto al sessantesimo giorno è ammesso il pagamento di Euro 65,00.")
    monkeypatch.setattr(writer, "_extract_text", lambda _: text)
    monkeypatch.setattr(pagopa_receipts, "parse_receipt_pdf", lambda *a, **kw: {"importo": 0.56})
    result = asyncio.run(leggi_documento_verbale(b"pdf", "documento.pdf"))
    assert result["importo"] == 52.40
    assert result["is_receipt"] is False
    assert result["ai_data"]["articolo_cds"] == "7"
    assert result["ai_data"]["obbligato_in_solido"] == "CERALDI GROUP SRL"
    assert result["ai_data"]["societa_locazione"] == "LEASYS S.P.A."


def test_data_emissione_del_pdf_salvata_come_data_verbale(monkeypatch):
    from app.services import verbali_document_import as writer
    from app.services import pagopa_receipts
    db = AsyncMongoMockClient().db
    text = "Verbale n. A26111311018 data verbale 27/07/2026 targato HB411GV entro 5 giorni euro 52,40"
    monkeypatch.setattr(writer, "_extract_text", lambda _: text)
    monkeypatch.setattr(pagopa_receipts, "parse_receipt_pdf", lambda *a, **kw: {})
    async def run():
        result = await writer.process_verbale_document(db, document_id="d1", content=b"pdf", filename="originale.pdf")
        verbale = await db.verbali_noleggio.find_one({"id": result["verbale_id"]})
        assert verbale["data_verbale"] == "2026-07-27"
    asyncio.run(run())
