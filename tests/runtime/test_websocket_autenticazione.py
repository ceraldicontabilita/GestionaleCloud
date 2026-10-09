"""Autenticazione WebSocket (bug #25, audit 19/07/2026 — vedi docstring di
_autentica_websocket in app/routers/websocket_realtime.py): AuthenticationMiddleware
NON protegge mai lo scope "websocket" — BaseHTTPMiddleware di Starlette salta
dispatch() per qualunque scope diverso da "http" (comportamento di libreria,
non un bug applicativo). La protezione reale vive in _autentica_websocket,
chiamata esplicitamente da ciascun endpoint /ws/*. Questo file testa quella
funzione direttamente: prima di oggi, zero test coprivano l'autenticazione
WebSocket."""
import asyncio

from jose import jwt

from app.config import settings
from app.database import Database
from app.routers.websocket_realtime import _autentica_websocket


class _FakeWebSocket:
    def __init__(self, token=None, cookie_token=None):
        self.query_params = {"token": token} if token else {}
        self.cookies = {"access_token": cookie_token} if cookie_token else {}
        self.chiusa_con = None

    async def close(self, code=1000, reason=""):
        self.chiusa_con = (code, reason)


class _FakeBlacklistColl:
    def __init__(self, revocati=None):
        self._revocati = revocati or set()

    async def find_one(self, query, *a, **k):
        if query.get("token_hash") in self._revocati:
            return {"token_hash": query["token_hash"]}
        return None


class _FakeDb:
    def __init__(self, revocati=None):
        self._coll = _FakeBlacklistColl(revocati)

    def __getitem__(self, name):
        return self._coll


class _FakeDbNonDisponibile:
    def __getitem__(self, name):
        raise ConnectionError("registro revoche non disponibile")


def _token_valido():
    return jwt.encode({"sub": "user-1"}, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def test_nessun_token_rifiutato(monkeypatch):
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: _FakeDb()))
    ws = _FakeWebSocket()
    ok = asyncio.run(_autentica_websocket(ws))
    assert ok is False
    assert ws.chiusa_con == (4401, "Authentication required")


def test_token_non_valido_rifiutato(monkeypatch):
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: _FakeDb()))
    ws = _FakeWebSocket(token="questo-non-e-un-jwt")
    ok = asyncio.run(_autentica_websocket(ws))
    assert ok is False
    assert ws.chiusa_con == (4401, "Invalid or expired token")


def test_token_valido_da_query_param_accettato(monkeypatch):
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: _FakeDb()))
    ws = _FakeWebSocket(token=_token_valido())
    ok = asyncio.run(_autentica_websocket(ws))
    assert ok is True
    assert ws.chiusa_con is None


def test_token_valido_da_cookie_accettato(monkeypatch):
    """Il codice reale usa il cookie come fallback se manca ?token= (client
    browser che aprono il websocket lasciano mandare il cookie in automatico)."""
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: _FakeDb()))
    ws = _FakeWebSocket(cookie_token=_token_valido())
    ok = asyncio.run(_autentica_websocket(ws))
    assert ok is True
    assert ws.chiusa_con is None


def test_token_revocato_rifiutato(monkeypatch):
    """Un token revocato al logout non deve restare valido per il websocket
    fino a scadenza naturale (review Codex su PR #65, citata nel modulo)."""
    from app.utils.token_blacklist import _hash

    token = _token_valido()
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: _FakeDb(revocati={_hash(token)})))
    ws = _FakeWebSocket(token=token)
    ok = asyncio.run(_autentica_websocket(ws))
    assert ok is False
    assert ws.chiusa_con == (4401, "Sessione terminata (logout)")


def test_registro_revoche_non_disponibile_chiude_websocket(monkeypatch):
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: _FakeDbNonDisponibile()))
    ws = _FakeWebSocket(token=_token_valido())
    ok = asyncio.run(_autentica_websocket(ws))
    assert ok is False
    assert ws.chiusa_con == (1013, "Verifica sessione temporaneamente non disponibile")


def test_query_param_ha_precedenza_sul_cookie_se_entrambi_presenti(monkeypatch):
    """Comportamento del codice reale: `or` tra query_params e cookies,
    quindi il token da query vince se presente ed è valido di per sé."""
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: _FakeDb()))
    ws = _FakeWebSocket(token=_token_valido(), cookie_token="valore-diverso-non-jwt")
    ok = asyncio.run(_autentica_websocket(ws))
    assert ok is True
