"""P0.12 — L'API pubblica v1 autentica via header `X-API-Key`; la query `?api_key=`
resta come fallback deprecato (con warning) ma non è più il canale principale.
La chiave non viene mai loggata."""
import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException

import app.routers.public_api as pub


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


@pytest.fixture(autouse=True)
def _stub_verify(monkeypatch):
    async def _fake(chiave):
        return {"client": "test", "chiave": chiave}
    monkeypatch.setattr(pub, "verify_api_key_header", _fake)


def test_header_x_api_key_funziona():
    res = _run(pub.richiedi_api_key(x_api_key="ak_abc", api_key=None))
    assert res["chiave"] == "ak_abc"


def test_query_deprecata_ancora_accettata():
    res = _run(pub.richiedi_api_key(x_api_key=None, api_key="ak_legacy"))
    assert res["chiave"] == "ak_legacy"


def test_chiave_mancante_401():
    with pytest.raises(HTTPException) as e:
        _run(pub.richiedi_api_key(x_api_key=None, api_key=None))
    assert e.value.status_code == 401


def test_endpoint_v1_non_usano_piu_query_obbligatoria():
    src = Path("app/routers/public_api.py").read_text(encoding="utf-8")
    assert 'x_api_key: str = Query(..., alias="api_key")' not in src
    assert "Depends(richiedi_api_key)" in src
