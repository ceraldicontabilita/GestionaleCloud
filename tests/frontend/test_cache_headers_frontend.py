"""Bug segnalato dall'utente 17/07/2026: dopo un deploy il telefono
continuava a mostrare l'app vecchia ("non vedo niente di live") perché
index.html veniva servito SENZA Cache-Control e il browser applicava la
cache euristica, caricando i chunk JS del bundle precedente.

Regola: index.html (e gli statici senza hash) si riconvalidano a ogni
apertura (no-cache); gli asset con hash nel nome hanno cache lunga
"immutable" — se cambia il contenuto cambia l'URL, mai stale.
"""
import os

from app import main as mod


def test_index_response_no_cache(tmp_path):
    f = tmp_path / "index.html"
    f.write_text("<html></html>")

    resp = mod._index_response(str(f))

    assert resp.headers["cache-control"] == "no-cache"


def test_asset_con_hash_cache_lunga_immutable(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    f = assets / "index-BJ8lb5ff.js"
    f.write_text("//js")

    resp = mod._static_response(str(f))

    assert resp.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_statico_senza_hash_riconvalida(tmp_path):
    f = tmp_path / "service-worker.js"
    f.write_text("//sw")

    resp = mod._static_response(str(f))

    assert resp.headers["cache-control"] == "no-cache"


def test_modulo_card_bb_raggiungibile_e_riconvalidato():
    from fastapi.testclient import TestClient

    # Nessun lifespan: la prova serve statici e non avvia scheduler né DB.
    client = TestClient(mod.app)
    response = client.get("/frontend-shared/tabelleCard.js")
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert response.headers["cache-control"] == "no-cache"
    assert "export function avviaTabelleCard" in response.text
    page = client.get("/convenzioni/")
    assert page.status_code == 200
    assert page.headers["cache-control"] == "no-cache"
    assert '/frontend-shared/tabelleCard.js' in page.text
