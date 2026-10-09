"""L'elaborazione AI delle email legge un PDF per volta, per id.

25/09/2026 05:18: `process-email-batch?limit=100` caricava 100 PDF insieme e il
server e' stato ucciso per memoria (2 GB); con lui sono cadute
Auto-Associazione e Riconciliazione F24 (502).
"""
import asyncio
import base64

from mongomock_motor import AsyncMongoMockClient


def test_elenco_senza_pdf_e_pdf_letto_per_id(monkeypatch):
    import app.services.ai_integration_service as svc

    db = AsyncMongoMockClient()["t"]
    pdf = base64.b64encode(b"%PDF-1.4 finto").decode()
    asyncio.run(db.documents_inbox.insert_many([
        {"id": f"d{i}", "filename": f"f{i}.pdf", "category": "f24", "pdf_data": pdf} for i in range(3)
    ]))
    letture_elenco = []
    coll = db.documents_inbox
    originale = coll.find

    def find_spia(filtro=None, proiezione=None, *a, **k):
        letture_elenco.append(proiezione)
        return originale(filtro, proiezione, *a, **k)

    coll.find = find_spia

    class DbUnaCollezione(dict):
        def __getitem__(self, nome):
            return coll

    db_spia = DbUnaCollezione()
    ricevuti = []

    async def finto_ai(db, document_id, pdf_data, document_type, collection):
        ricevuti.append((document_id, pdf_data))
        return {"success": True, "detected_type": "f24"}

    monkeypatch.setattr(svc, "process_document_with_ai", finto_ai)
    esito = asyncio.run(svc.process_email_documents_batch(db_spia, limit=10))

    assert esito["success"] == 3
    assert letture_elenco and letture_elenco[0].get("pdf_data") == 0  # elenco senza PDF
    assert all(p == b"%PDF-1.4 finto" for _, p in ricevuti)          # PDF preso per id
