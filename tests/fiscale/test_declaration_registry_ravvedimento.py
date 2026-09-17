"""15/09/2026 (richiesta del titolare): un codice tributo puo' comparire in un
F24 successivo con un totale diverso da quello dichiarato (pagamento tardivo/
ravvedimento) — la prova e' la riga col codice, non il totale del modello.
Quando lo stesso F24 porta anche sanzioni/interessi da ravvedimento
(costante unica `CODICI_RAVVEDIMENTO`), quelle righe vanno sempre associate
al collegamento dichiarazione<->F24, non trattate come obbligazioni a parte.
"""
import asyncio

from app.services import declaration_registry as mod


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    async def to_list(self, n=None):
        return list(self._docs[:n] if n else self._docs)


class _FakeCollection:
    def __init__(self, docs):
        self.docs = docs

    def find(self, query=None, projection=None, *a, **k):
        return _FakeCursor(self.docs)


class _FakeDb:
    def __init__(self, declarations):
        self.collections = {mod.COLL_FISCAL_DOCUMENTS: _FakeCollection(declarations)}

    def __getitem__(self, name):
        return self.collections[name]


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def _riga(tax_code, periodo="2026", debit_cents=100000):
    return {
        "tax_code": tax_code, "reference_period": periodo,
        "debit_cents": debit_cents, "credit_cents": 0,
    }


def test_f24_tardivo_con_sanzione_e_interessi_viene_associato(monkeypatch):
    declaration = {
        "id": "decl-lipe-1", "document_type": "LIPE",
        "filename": "LIPE_2026_1.pdf", "source_metadata": {"tax_year": 2026},
    }
    db = _FakeDb([declaration])

    f24_puntuale = {
        "id": "f24-puntuale", "file_name": "f24_puntuale.pdf",
        # Stesso codice ma anno di riferimento diverso: non e' un candidato
        # per la dichiarazione 2026, resta fuori dai link.
        "righe_tributo_normalizzate": [_riga("6001", periodo="2025")],
        "payment_chain": {"relations": [], "axes": {"bank": "NON_VERIFICATA", "document_evidence": "QUIETANZA_NON_PRESENTE"}},
    }
    f24_tardivo = {
        "id": "f24-tardivo", "file_name": "f24_tardivo_ravvedimento.pdf",
        "righe_tributo_normalizzate": [
            _riga("6001"),
            _riga("8904", debit_cents=1500),  # sanzione ravvedimento IVA
            _riga("1991", debit_cents=320),   # interessi ravvedimento
        ],
        "payment_chain": {"relations": [], "axes": {"bank": "VERIFICATA", "document_evidence": "VERSATO_DOCUMENTALMENTE"}},
    }

    async def _fake_list_documents(self, *, include_pdf=False):
        return [f24_puntuale, f24_tardivo]

    monkeypatch.setattr(mod.TaxPaymentQueryService, "list_documents", _fake_list_documents)

    dossiers = _run(mod.list_declaration_dossiers(db, company_id="ceraldi"))

    assert len(dossiers) == 1
    links = dossiers[0]["f24_links"]
    by_id = {link["f24_id"]: link for link in links}

    # Il modello che non porta la riga 6001 non entra nei candidati.
    assert "f24-puntuale" not in by_id

    tardivo = by_id["f24-tardivo"]
    assert tardivo["pagamento_tardivo"] is True
    codici_ravvedimento_trovati = {r["tax_code"] for r in tardivo["ravvedimento_rows"]}
    assert codici_ravvedimento_trovati == {"8904", "1991"}


def test_f24_puntuale_senza_ravvedimento_non_lo_segnala(monkeypatch):
    declaration = {
        "id": "decl-lipe-2", "document_type": "LIPE",
        "filename": "LIPE_2026_2.pdf", "source_metadata": {"tax_year": 2026},
    }
    db = _FakeDb([declaration])

    f24_puntuale = {
        "id": "f24-puntuale-2", "file_name": "f24.pdf",
        "righe_tributo_normalizzate": [_riga("6001")],
        "payment_chain": {"relations": [], "axes": {"bank": "VERIFICATA", "document_evidence": "VERSATO_DOCUMENTALMENTE"}},
    }

    async def _fake_list_documents(self, *, include_pdf=False):
        return [f24_puntuale]

    monkeypatch.setattr(mod.TaxPaymentQueryService, "list_documents", _fake_list_documents)

    dossiers = _run(mod.list_declaration_dossiers(db, company_id="ceraldi"))

    link = dossiers[0]["f24_links"][0]
    assert link["pagamento_tardivo"] is False
    assert link["ravvedimento_rows"] == []
