"""Situazione fiscale legge il registro unico F24, non l'indice Excel su Drive.

L'indice stava nella cartella del canale cedolini, smontata col passaggio alla
cartella unica: ogni scheda rispondeva «Credenziali Google Drive non
disponibili». Modelli e quietanze ora vengono da ``carica_registro``.
"""
import asyncio

from app.routers import fiscal_control
from app.services import f24_controllo_incrociato as reg

RIGA_2003 = {"codice_tributo": "2003", "anno": "2024", "importo_debito": "1000.00"}
MODELLO_COPERTO = {
    "id": "F24-COPERTO", "file_name": "f24_giugno.pdf", "status": "da_pagare",
    "dati_generali": {"data_versamento": "2024-06-17"}, "totali": {"saldo_netto": "1000.00"},
    "sezione_erario": [RIGA_2003],
}
MODELLO_APERTO = {
    "id": "F24-APERTO", "file_name": "f24_luglio.pdf", "status": "da_pagare",
    "dati_generali": {"data_versamento": "2024-07-16"}, "totali": {"saldo_netto": "250.00"},
    "sezione_erario": [{"codice_tributo": "1001", "mese": "06", "anno": "2024", "importo_debito": "300.00"},
                       {"codice_tributo": "1631", "anno": "2024", "importo_credito": "50.00"}],
}
QUIETANZA = {
    "id": "Q-GIUGNO", "filename": "quietanza_giugno.pdf", "data_pagamento": "2024-06-17",
    "protocollo_telematico": "24061712345678901", "saldo": "1000.00", "f24_associati": [],
    "sezione_erario": [RIGA_2003],
}


def _registro():
    return {
        "f24": [MODELLO_COPERTO, MODELLO_APERTO],
        "quietanze": [reg._quietanza_legacy(QUIETANZA)],
        "movimenti": [], "quietanze_per_f24": {}, "movimenti_per_f24": {},
        "conteggi": {},
    }


class _Coll:
    async def count_documents(self, _query):
        return 3


class _Db(dict):
    def __getitem__(self, _name):
        return _Coll()


def _usa_registro(monkeypatch):
    async def _carica(_db):
        return _registro()

    monkeypatch.setattr(reg, "carica_registro", _carica)
    monkeypatch.setattr(fiscal_control.Database, "get_db", classmethod(lambda _cls: _Db()))


def test_summary_conta_dal_registro_senza_drive(monkeypatch):
    _usa_registro(monkeypatch)
    payload = asyncio.run(fiscal_control.summary(_admin={}))
    assert payload["canonical_source"] == "registro_f24"
    assert "drive_index" not in payload
    assert payload["counts"]["f24_documents"] == 2
    assert payload["counts"]["f24_rows"] == 4
    assert payload["counts"]["declarations"] == 3
    assert payload["counts"]["documentary_payment_documents"] == 1


def test_f24_rows_separano_modello_e_quietanza(monkeypatch):
    _usa_registro(monkeypatch)
    payload = asyncio.run(fiscal_control.f24_rows(
        tax_code=None, document_id=None, year=None, credits_only=False,
        offset=0, limit=200, _admin={},
    ))
    assert payload["sources"] == {"registro_f24": 4, "canonical": "registro_f24"}
    assert payload["items"][0]["payment_date"] == "2024-07-16"
    per_doc = {(r["document_id"], r["tax_code"]): r for r in payload["items"]}
    modello = per_doc[("F24-COPERTO", "2003")]
    assert modello["evidence_state"] == "MODELLO_F24_NON_PROVA_BANCARIA"
    assert modello["pdf_url"] == "/api/originale/f24/F24-COPERTO"
    quietanza = per_doc[("Q-GIUGNO", "2003")]
    assert quietanza["documentary_payment_status"] == "QUIETANZA_PRESENTE"
    assert quietanza["bank_status"] == "DA_VERIFICARE"
    assert per_doc[("F24-APERTO", "1631")]["credit_amount"] == 50.0

    crediti = asyncio.run(fiscal_control.f24_rows(
        tax_code=None, document_id=None, year=2024, credits_only=True,
        offset=0, limit=200, _admin={},
    ))
    assert [r["tax_code"] for r in crediti["items"]] == ["1631"]


def test_da_pagare_esclude_il_modello_coperto_da_quietanza(monkeypatch):
    _usa_registro(monkeypatch)
    da_pagare = asyncio.run(fiscal_control.obligations(status="TO_PAY", limit=5000, _admin={}))
    # la delega intera, anche la riga a credito
    assert {(r["document_id"], r["tax_code"]) for r in da_pagare["items"]} == {
        ("F24-APERTO", "1001"), ("F24-APERTO", "1631"),
    }
    pagati = asyncio.run(fiscal_control.obligations(status="PAID_ON_TIME", limit=5000, _admin={}))
    assert {r["document_id"] for r in pagati["items"]} == {"Q-GIUGNO"}


def test_confronto_fonti_dal_registro(monkeypatch):
    _usa_registro(monkeypatch)

    async def _nessuna_dichiarazione(_db, *, company_id, year=None, declaration_type=None):
        return []

    monkeypatch.setattr(fiscal_control, "list_declaration_dossiers", _nessuna_dichiarazione)
    result = asyncio.run(fiscal_control.source_certainty(year=2024, _admin={"role": "admin"}))
    assert result["sources"]["canonical"] == "registro_f24"
    assert result["sources"]["quietanza_drive_rows"] == 1
    assert result["sources"]["commercialista_f24_documents"] == 2
    coperto = [i for i in result["items"] if (i.get("accountant_document") or {}).get("document_id") == "F24-COPERTO"]
    assert coperto and coperto[0]["status"] == "CONCORDANTE"


def test_declarations_read_from_fiscal_documents(monkeypatch):
    """15/09/2026: l'elenco dichiarazioni legge fiscal_documents (Supabase),
    non piu' il vecchio indice Excel/Drive (radice sparita, sempre vuoto)."""
    from app.services import declaration_registry

    async def _fake_dossiers(_db, *, company_id, year=None, declaration_type=None):
        assert company_id
        return [{
            "id": "DOC-770", "document_type": "MODELLO_770", "filing_year": 2026,
            "tax_year": 2025, "filename": "770_2026.pdf", "f24_links": [],
            "f24_confirmed_count": 0, "f24_candidate_count": 0,
        }]

    monkeypatch.setattr(declaration_registry, "list_declaration_dossiers", _fake_dossiers)
    monkeypatch.setattr(fiscal_control, "list_declaration_dossiers", _fake_dossiers)
    monkeypatch.setattr(fiscal_control.Database, "get_db", classmethod(lambda _cls: object()))

    payload = asyncio.run(fiscal_control.declarations(
        year=2026, declaration_type="MODELLO_770", _admin={},
    ))
    assert payload["total"] == 1
    assert payload["sources"] == {"fiscal_documents": 1, "canonical": "fiscal_documents"}
    assert payload["items"][0]["filename"] == "770_2026.pdf"
    assert "source_kind" not in payload["items"][0]
