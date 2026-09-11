from __future__ import annotations

import asyncio
from pathlib import Path

from app.routers.operazioni_module import smart
from app.routers.operazioni_module.common import ConfermaBatchRequest

ROOT = Path(__file__).resolve().parents[1]


class _Result:
    matched_count = 1


class _Collection:
    def __init__(self):
        self.calls = []

    async def update_one(self, query, update):
        self.calls.append((query, update))
        return _Result()


class _Db:
    def __init__(self):
        self.collection = _Collection()

    def __getitem__(self, name):
        assert name == "f24_unificato"
        return self.collection


def test_dichiarazione_f24_banca_non_diventa_pagamento_verificato(monkeypatch):
    db = _Db()
    monkeypatch.setattr(smart.Database, "get_db", staticmethod(lambda: db))
    request = ConfermaBatchRequest(operazioni=[{
        "operazione_id": "f24-1",
        "metodo_pagamento": "banca",
        "tipo": "f24",
    }])

    response = asyncio.run(smart.conferma_f24_batch(request))
    fields = db.collection.calls[0][1]["$set"]

    assert response["stato"] == "attesa_verifica_bancaria"
    assert fields["riconciliato"] is False
    assert fields["status"] == "da_pagare"
    assert fields["stato_pagamento"] == "DA_VERIFICARE_BANCA"
    assert fields["pagato"] is False
    assert fields["pagato_manualmente"] is False
    assert fields["pagamento_dichiarato_manualmente"] is True
    assert fields["pagamento_verificato_banca"] is False
    assert fields["tipo_riconciliazione"] == "manuale_da_verificare_banca"
    assert "data_riconciliazione" not in fields


def test_f24_viewer_usa_endpoint_reale_e_non_download_generico():
    source = (ROOT / "frontend/src/pages/RiconciliazioneUnificata.jsx").read_text(encoding="utf-8")
    assert "/api/download/" not in source
    assert "/api/f24-riconciliazione/commercialista/${encodeURIComponent(f.id)}/pdf" in source
    assert "fetchUrl={pdfViewer.fetchUrl}" in source
    assert "Paga con Banca" not in source
    assert "Attesa banca" in source
