"""Agente di stampa del negozio (`scripts/print_agent.py`).

Il backend non legge piu' `?token=`: l'agente deve autenticarsi solo con
l'intestazione `Authorization`, mandare il token solo al backend di Lotti e mai
in chiaro, e puntare al servizio vivo (i vecchi backend Render separati sono spenti).
"""
import importlib.util
import io
import json
import urllib.error
from pathlib import Path

import pytest

_PERCORSO = Path(__file__).resolve().parents[2] / "scripts" / "print_agent.py"
_spec = importlib.util.spec_from_file_location("print_agent", _PERCORSO)
agente = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(agente)

BACKEND = "https://gestionalecloud.onrender.com/lotti"


class _Risposta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FintoServer:
    """Registra ogni richiesta e risponde secondo `rispondi(req)`."""

    def __init__(self, rispondi):
        self.richieste = []
        self.rispondi = rispondi

    def __call__(self, req, timeout=None):
        self.richieste.append(req)
        esito = self.rispondi(req)
        if isinstance(esito, int):
            raise urllib.error.HTTPError(req.full_url, esito, "errore", {}, None)
        return _Risposta(esito if isinstance(esito, bytes) else json.dumps(esito).encode())


def _sessione(monkeypatch, rispondi):
    server = FintoServer(rispondi)
    monkeypatch.setattr(agente.urllib.request, "urlopen", server)
    return agente.Sessione(BACKEND, "123456"), server


@pytest.mark.parametrize("configurato,atteso", [
    ("https://vecchio-backend-lotti.onrender.com", BACKEND),
    ("https://gestionalecloud.onrender.com", BACKEND),
    ("https://gestionalecloud.onrender.com/lotti/", BACKEND),
    ("", BACKEND),
])
def test_backend_sempre_il_servizio_vivo(configurato, atteso):
    assert agente.normalizza_backend(configurato) == atteso


def test_backend_in_chiaro_rifiutato():
    with pytest.raises(ValueError):
        agente.normalizza_backend("http://gestionalecloud.onrender.com/lotti")


def test_pin_dalla_variabile_d_ambiente(monkeypatch):
    monkeypatch.setenv(agente.VARIABILE_PIN, "654321")
    assert agente.leggi_pin({"pin": "111111"}) == "654321"
    monkeypatch.delenv(agente.VARIABILE_PIN)
    assert agente.leggi_pin({"pin": "111111"}) == "111111"
    with pytest.raises(SystemExit):
        agente.leggi_pin({"pin": "INSERISCI_PIN_OPERATORE_STAMPA"})


def test_token_solo_nell_intestazione_e_mai_nell_url(monkeypatch):
    def rispondi(req):
        if req.full_url.endswith("/tablet-operatori/login"):
            return {"token": "jwt-1", "operatore": {"nome": "Stampa"}}
        return b"%PDF-1.4"

    sessione, server = _sessione(monkeypatch, rispondi)
    sessione.login()
    dati = sessione.chiama("GET", "http://gestionalecloud.onrender.com/lotti/api/stampa/lotto/L1")
    assert dati == b"%PDF-1.4"
    documento = server.richieste[-1]
    assert documento.full_url == "https://gestionalecloud.onrender.com/lotti/api/stampa/lotto/L1"
    assert documento.get_header("Authorization") == "Bearer jwt-1"
    assert "token" not in documento.full_url
    # il login non manda un token vecchio
    assert server.richieste[0].get_header("Authorization") is None


@pytest.mark.parametrize("url", [
    "https://altro-sito.it/documento.pdf",
    "https://gestionalecloud.onrender.com.evil.it/x",
    "//altro-sito.it/x",
    "https://gestionalecloud.onrender.com/lotti/api/x?token=abc",
])
def test_il_token_non_parte_verso_altri_domini_ne_in_query(monkeypatch, url):
    sessione, server = _sessione(monkeypatch, lambda req: b"")
    sessione.token = "jwt-1"
    with pytest.raises(ValueError):
        sessione.chiama("GET", url)
    assert server.richieste == []


def test_url_relativo_completato_col_backend(monkeypatch):
    sessione, server = _sessione(monkeypatch, lambda req: b"ok")
    sessione.token = "jwt-1"
    sessione.chiama("GET", "/lotti/api/stampa/lotto/L1")
    assert server.richieste[-1].full_url == "https://gestionalecloud.onrender.com/lotti/api/stampa/lotto/L1"


def test_documento_del_dominio_pubblico_e_accettato(monkeypatch):
    sessione, server = _sessione(monkeypatch, lambda req: b"etichetta")
    sessione.token = "jwt-1"
    dati = sessione.chiama("GET", "https://impresasemplice.online/lotti/api/stampa/lotto/L1")
    assert dati == b"etichetta"
    assert server.richieste[-1].full_url == "https://impresasemplice.online/lotti/api/stampa/lotto/L1"
    assert server.richieste[-1].get_header("Authorization") == "Bearer jwt-1"


def test_token_scaduto_durante_un_lavoro_nuovo_login_e_un_solo_tentativo(monkeypatch):
    stato = {"documento": 0}

    def rispondi(req):
        if req.full_url.endswith("/tablet-operatori/login"):
            return {"token": "jwt-nuovo"}
        stato["documento"] += 1
        return 401 if req.get_header("Authorization") == "Bearer jwt-vecchio" else b"pdf"

    sessione, server = _sessione(monkeypatch, rispondi)
    sessione.token = "jwt-vecchio"
    assert sessione.chiama("GET", f"{BACKEND}/api/stampa/lotto/L1") == b"pdf"
    assert sessione.token == "jwt-nuovo"
    assert stato["documento"] == 2


def test_giro_stampa_e_registra_l_esito(monkeypatch):
    stampati = []
    monkeypatch.setattr(agente, "stampa_pdf", lambda pdf, stampante, sumatra: stampati.append(stampante))

    def rispondi(req):
        url = req.full_url
        if "/coda/pendenti" in url:
            return {"jobs": [
                {"id": "j1", "url": f"{BACKEND}/api/stampa/lotto/L1", "formato": "pdf", "stampante_windows": "EPSON"},
                {"id": "j2", "url": "https://altro-sito.it/x.pdf", "formato": "pdf"},
            ]}
        if url.endswith("/esito"):
            return {"ok": True}
        return b"%PDF-1.4"

    sessione, server = _sessione(monkeypatch, rispondi)
    sessione.token = "jwt-1"
    assert agente.giro(sessione, {"reparto": ""}, "") == 1
    assert stampati == ["EPSON"]
    esiti = [json.loads(r.data) for r in server.richieste if r.full_url.endswith("/esito")]
    assert esiti[0] == {"ok": True}
    assert esiti[1]["ok"] is False and "ValueError" in esiti[1]["errore"]
    assert all(r.get_header("Authorization") == "Bearer jwt-1" for r in server.richieste)
    assert not any("altro-sito" in r.full_url for r in server.richieste)
