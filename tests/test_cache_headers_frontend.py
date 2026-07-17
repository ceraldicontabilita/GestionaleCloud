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
