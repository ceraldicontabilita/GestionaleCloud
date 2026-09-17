"""Richiesta utente 15/07/2026: l'export ZIP mensile per il commercialista
(GET /api/commercialista/export-completo/{anno}/{mese}) deve contenere
SOLO Prima Nota Cassa, Prima Nota Banca e Assegni emessi (CSV), più le
fatture ESTERE ricevute via email nel mese come PDF allegati — mai le
fatture italiane (che arrivano sempre via SDI/XML) né corrispettivi/
riepilogo IVA/buste paga (dati che il commercialista riceve già altrove)."""
import asyncio
import io
import zipfile

from app.routers import commercialista as mod


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    async def to_list(self, n=None):
        return list(self._docs[:n] if n else self._docs)


def _matches(doc, query):
    for k, v in query.items():
        if isinstance(v, dict) and "$regex" in v:
            if not str(doc.get(k, "")).startswith(v["$regex"].lstrip("^")):
                return False
        elif isinstance(v, dict) and "$nin" in v:
            if doc.get(k) in v["$nin"]:
                return False
        else:
            if doc.get(k) != v:
                return False
    return True


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    def find(self, query=None, projection=None, *a, **k):
        return _FakeCursor([d for d in self.docs if _matches(d, query or {})])

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if _matches(d, query):
                return dict(d)
        return None


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


def test_export_completo_contiene_solo_cassa_banca_assegni_e_fatture_estere(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    db["prima_nota_cassa"].docs = [
        {"data": "2026-05-10", "descrizione": "Corrispettivi", "categoria": "Corrispettivi", "importo": 500.0, "tipo": "entrata"},
    ]
    db["prima_nota_banca"].docs = [
        {"data": "2026-05-12", "descrizione": "Bonifico fornitore", "categoria": "Fornitori", "importo": -300.0, "tipo": "uscita"},
    ]
    db["assegni"].docs = [
        {"numero": "0001-11", "stato": "emesso", "data_emissione": "2026-05-15",
         "beneficiario": "Fornitore SRL", "importo": 200.0, "causale": "Saldo fattura"},
        # Non ancora emesso: non deve comparire.
        {"numero": "0001-12", "stato": "vuoto", "data_emissione": None},
    ]
    # Fattura ITALIANA nel mese: non deve mai comparire nell'export.
    db["invoices"].docs = [
        {"id": "it-1", "source": "xml_upload", "invoice_date": "2026-05-05", "invoice_number": "IT001"},
        # Fattura ESTERA nel mese: deve essere allegata come PDF.
        {"id": "est-1", "source": "email_gmail_estera", "invoice_date": "2026-05-06",
         "invoice_number": "EST001", "documento_inbox_id": "doc-1"},
    ]
    db["documents_inbox"].docs = [
        {"id": "doc-1", "filename": "fattura_estera_EST001.pdf", "pdf_data": "ZmludG8gcGRm"},  # b"finto pdf"
    ]

    response = _run(mod.export_dati_completi(2026, 5))

    chunks = []

    async def _collect():
        async for chunk in response.body_iterator:
            chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode())
    _run(_collect())
    zip_bytes = b"".join(chunks)

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()

        assert "prima_nota_cassa_2026-05.csv" in names
        assert "prima_nota_banca_2026-05.csv" in names
        assert "assegni_emessi_2026-05.csv" in names
        assert "fatture_estere/fattura_estera_EST001.pdf" in names

        # Mai più generati: fatture italiane, corrispettivi, riepilogo IVA, buste paga.
        assert "fatture_2026-05.csv" not in names
        assert "corrispettivi_2026-05.csv" not in names
        assert "riepilogo_iva_2026-05.txt" not in names
        assert "buste_paga_2026-05.csv" not in names

        assegni_csv = zf.read("assegni_emessi_2026-05.csv").decode()
        assert "0001-11" in assegni_csv
        assert "0001-12" not in assegni_csv  # ancora "vuoto", non emesso

        pdf_bytes = zf.read("fatture_estere/fattura_estera_EST001.pdf")
        assert pdf_bytes == b"finto pdf"
