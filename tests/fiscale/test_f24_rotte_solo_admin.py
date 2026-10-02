"""I dati fiscali (doppi pagamenti F24, avviso bonario) sono solo admin, in lettura compresa."""
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.routers import f24_analisi
from app.routers.f24 import avviso_bonario
from app.utils.dependencies import get_current_admin_user


def _client_non_admin():
    app = FastAPI()
    app.include_router(f24_analisi.router, prefix="/api/f24-analisi")
    app.include_router(avviso_bonario.router, prefix="/api/f24")

    def _nega():
        raise HTTPException(status_code=403, detail="Solo admin")

    app.dependency_overrides[get_current_admin_user] = _nega
    return TestClient(app)


def test_ogni_rotta_f24_analisi_nega_il_non_admin():
    client = _client_non_admin()
    for metodo, url in [
        ("get", "/api/f24-analisi/doppi-pagamenti"),
        ("get", "/api/f24-analisi/tabella"),
        ("get", "/api/f24-analisi/F1"),
        ("get", "/api/f24-analisi/F1/associazione"),
        ("put", "/api/f24-analisi/doppi-pagamenti/x/stato"),
        ("post", "/api/f24-analisi/doppi-pagamenti/rileva"),
    ]:
        risposta = getattr(client, metodo)(url, **({"json": {"stato": "x"}} if metodo == "put" else {}))
        assert risposta.status_code == 403, (metodo, url, risposta.status_code)


def test_avviso_bonario_nega_il_non_admin():
    risposta = _client_non_admin().post("/api/f24/avviso-bonario/controllo", json={
        "righe": [{"codice_tributo": "1001", "periodo": "01/2026", "importo": 10.0}]})
    assert risposta.status_code == 403
