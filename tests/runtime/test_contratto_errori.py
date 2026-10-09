"""Contratto unico degli errori API (CLAUDE.md: ``code``, ``message``,
``details``, ``correlation_id``).

L'handler di prima rispondeva alle ``HTTPException`` con ``error`` e
``message`` ma senza ``detail``: il frontend legge ``detail`` in 264 punti,
quindi il messaggio di ogni errore sollevato da un endpoint spariva dalla
pagina. ``detail`` resta come l'endpoint l'ha sollevato, anche se e' un oggetto.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.exceptions import NotFoundError
from app.middleware.error_handler import add_exception_handlers

CAMPI = {"code", "message", "details", "correlation_id", "detail"}


def _client() -> TestClient:
    app = FastAPI()
    add_exception_handlers(app)

    @app.get("/stringa")
    def stringa():
        raise HTTPException(400, "Importo non valido")

    @app.get("/oggetto")
    def oggetto():
        raise HTTPException(409, detail={"message": "Due fatture compatibili", "candidati": ["a", "b"]})

    @app.get("/intestazioni")
    def intestazioni():
        raise HTTPException(401, "Token scaduto", headers={"WWW-Authenticate": "Bearer"})

    @app.get("/app-error")
    def app_error():
        raise NotFoundError("Fattura")

    @app.get("/numero")
    def numero(q: int):
        return q

    @app.get("/guasto")
    def guasto():
        raise RuntimeError("")

    return TestClient(app, raise_server_exceptions=False)


def test_http_exception_conserva_detail_e_da_il_contratto():
    r = _client().get("/stringa")
    corpo = r.json()
    assert r.status_code == 400
    assert CAMPI <= corpo.keys()
    assert corpo["code"] == "RICHIESTA_NON_VALIDA"
    assert corpo["message"] == corpo["detail"] == "Importo non valido"
    assert corpo["correlation_id"]


def test_detail_oggetto_resta_oggetto():
    corpo = _client().get("/oggetto").json()
    assert corpo["detail"]["candidati"] == ["a", "b"]
    assert corpo["details"] == corpo["detail"]
    assert corpo["message"] == "Due fatture compatibili"
    assert corpo["code"] == "CONFLITTO"


def test_intestazioni_dell_eccezione_non_si_perdono():
    r = _client().get("/intestazioni")
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


def test_rotta_inesistente_risponde_in_italiano():
    corpo = _client().get("/non-esiste").json()
    assert corpo["code"] == "NON_TROVATO"
    assert corpo["message"] == "Non trovato"


def test_app_error_e_validazione():
    c = _client()
    corpo = c.get("/app-error").json()
    assert CAMPI <= corpo.keys() and corpo["code"] == "NON_TROVATO"
    corpo = c.get("/numero?q=abc").json()
    assert corpo["code"] == "DATI_NON_VALIDI"
    assert isinstance(corpo["details"], list) and corpo["details"][0]["loc"] == ["query", "q"]


def test_guasto_non_espone_l_eccezione():
    r = _client().get("/guasto")
    corpo = r.json()
    assert r.status_code == 500
    assert corpo["code"] == "ERRORE_INTERNO"
    assert "RuntimeError" not in str(corpo)
    assert corpo["correlation_id"]


def test_handler_registrato_dall_app_vera():
    sorgente = (Path(__file__).resolve().parents[2] / "app" / "main.py").read_text(encoding="utf-8")
    assert "add_exception_handlers(app)" in sorgente


def test_middleware_autenticazione_usa_il_contratto():
    """Il middleware risponde prima degli exception handler: scriveva a mano
    ``{"detail": ...}`` e restava fuori dal contratto."""
    import json

    from app.middleware.error_handler import errore_http

    sorgente = (Path(__file__).resolve().parents[2] / "app" / "middleware" / "authentication.py").read_text(encoding="utf-8")
    assert "JSONResponse(" not in sorgente

    r = errore_http(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
    corpo = json.loads(r.body)
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"
    assert CAMPI <= corpo.keys()
    assert corpo["code"] == "NON_AUTENTICATO"
    assert corpo["detail"] == "Authentication required"
    assert corpo["message"] == "Accesso richiesto: entra con il PIN"
