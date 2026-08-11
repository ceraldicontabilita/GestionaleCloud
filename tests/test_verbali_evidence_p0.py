import asyncio
from pathlib import Path

import pytest

from app.services.verbali_evidence import (
    amount_to_cents,
    describe_verbale_date,
    sanitize_verbale_evidence,
)
from app.database import Database
from app.routers.verbali_riconciliazione import riconcilia_verbale


class _Cursor:
    def __init__(self, docs):
        self.docs = list(docs)

    def limit(self, _limit):
        return self

    async def to_list(self, limit):
        return list(self.docs[:limit])


class _Collection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])
        self.updates = []

    async def find_one(self, query, _projection=None):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items() if not key.startswith("$")):
                return dict(doc)
        return None

    def find(self, _query, _projection=None):
        return _Cursor(self.docs)

    async def update_one(self, query, update):
        self.updates.append((query, update))
        return object()


class _Db:
    def __init__(self):
        self.collections = {
            "verbali_noleggio": _Collection([
                {"numero_verbale": "V-PREVIEW", "stato": "salvato", "importo": 51164.0}
            ]),
            "invoices": _Collection([
                {
                    "id": "inv-1",
                    "invoice_number": "F-1",
                    "supplier_name": "Noleggiatore",
                    "total_amount": 50.0,
                }
            ]),
            "verbali_noleggio_completi": _Collection(),
            "veicoli_noleggio": _Collection(),
        }

    def __getitem__(self, name):
        return self.collections.setdefault(name, _Collection())


@pytest.mark.parametrize("legacy_amount", [51164.00, 5164.00, 0.78, 5.74])
def test_importi_ocr_legacy_non_diventano_importi_operativi(legacy_amount):
    result = sanitize_verbale_evidence(
        {
            "numero_verbale": "TEST",
            "importo": legacy_amount,
            "source": "gmail_scan",
        }
    )

    assert result["importo"] is None
    assert result["importo_centesimi"] is None
    assert result["importo_verificato"] is False
    assert result["importo_stato"] == "DA_VERIFICARE"
    assert result["importo_candidato_presente"] is True


def test_importo_confermato_e_esposto_in_centesimi_esatti():
    result = sanitize_verbale_evidence(
        {
            "numero_verbale": "B26120386585",
            "importo": "34,90",
            "importo_verificato": True,
            "importo_stato": "VERIFICATO_PAGAMENTO",
            "importo_fonte": "movimento_bancario_univoco",
        }
    )

    assert amount_to_cents("34,90") == 3490
    assert result["importo"] == 34.90
    assert result["importo_centesimi"] == 3490
    assert result["importo_verificato"] is True


def test_prima_data_ocr_non_e_data_del_verbale():
    unverified = describe_verbale_date({"data_verbale": "2026-05-13"})
    verified = describe_verbale_date(
        {"data_verbale": "2026-05-13", "data_verbale_verificata": True}
    )

    assert unverified["data_verbale"] is None
    assert unverified["data_verbale_candidato_presente"] is True
    assert verified["data_verbale"] == "2026-05-13"


def test_stato_pagato_legacy_senza_importo_verificato_non_appare_come_pagato():
    result = sanitize_verbale_evidence(
        {"stato": "riconciliato", "importo": 5.74, "movimento_banca_id": "m1"}
    )

    assert result["stato"] == "da_verificare"
    assert result["stato_originale"] == "riconciliato"


def test_riconciliazione_verbale_e_preview_first_e_parser_non_persiste_importo():
    root = Path(__file__).resolve().parents[1]
    router_source = (root / "app/routers/verbali_riconciliazione.py").read_text(encoding="utf-8")
    parser_source = (root / "app/services/llm_document_parser.py").read_text(encoding="utf-8")

    assert "dry_run: bool = Query(" in router_source
    assert "if updates and not dry_run:" in router_source
    assert '"richiede_conferma": bool(proposte) and dry_run' in router_source
    assert 'update["importo"] = parsed["importo"]' not in parser_source
    assert 'update = {"importo": importo}' not in parser_source
    assert '"importo_candidato_centesimi": amount_to_cents(importo)' in parser_source


def test_anteprima_riconciliazione_non_scrive_e_applicazione_confermata_si(monkeypatch):
    db = _Db()
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))

    preview = asyncio.run(riconcilia_verbale("V-PREVIEW", dry_run=True))
    assert preview["dry_run"] is True
    assert preview["richiede_conferma"] is True
    assert preview["proposte"][0]["tipo"] == "FATTURA_VERBALE"
    assert db["verbali_noleggio"].updates == []
    assert db["invoices"].updates == []

    applied = asyncio.run(riconcilia_verbale("V-PREVIEW", dry_run=False))
    assert applied["dry_run"] is False
    assert len(db["verbali_noleggio"].updates) == 1
    assert len(db["invoices"].updates) == 1
