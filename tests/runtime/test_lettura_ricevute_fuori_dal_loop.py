"""La lettura delle ricevute (testo e OCR) non gira sull'event loop: un PDF scansionato lo bloccava
per minuti, l'health check di Render scadeva e il servizio si riavviava ogni 20 minuti."""
import asyncio
import threading

from app.services import pagopa_receipts, verbali_document_import


def test_import_receipt_legge_il_pdf_in_un_altro_thread(monkeypatch):
    visti = {}

    def finto(content, filename=None):
        visti["thread"] = threading.current_thread()
        return {"is_payment_receipt": False}

    monkeypatch.setattr(pagopa_receipts, "parse_receipt_pdf", finto)

    async def prova():
        try:
            await pagopa_receipts.import_receipt(
                None, content=b"%PDF", filename="r.pdf", company_id="x")
        except Exception:
            pass  # il database finto non serve: conta solo dove e' girata la lettura
        return threading.current_thread()

    principale = asyncio.run(prova())
    assert visti["thread"] is not principale


def test_i_chiamanti_async_usano_to_thread():
    import inspect
    from app.routers import documenti
    from app.services import document_import_preview

    for modulo in (verbali_document_import, document_import_preview, documenti):
        assert "asyncio.to_thread(" in inspect.getsource(modulo)
    assert "asyncio.to_thread(parse_receipt_pdf" in inspect.getsource(documenti)
    assert "asyncio.to_thread(parse_receipt_pdf" in inspect.getsource(verbali_document_import)
    assert "asyncio.to_thread(parse_receipt_pdf" in inspect.getsource(pagopa_receipts.import_receipt)


def test_la_proiezione_bancaria_classifica_i_movimenti_in_un_thread():
    import inspect
    from app.services import proiezione_bancaria

    sorgente = inspect.getsource(proiezione_bancaria.proietta_movimenti_bancari_semantici)
    assert "asyncio.to_thread(classifica_movimento_ec" in sorgente
