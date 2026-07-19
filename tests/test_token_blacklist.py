"""Copre app/utils/token_blacklist.py — revoca JWT al logout (audit
sicurezza 19/07/2026). Prima di questo test la funzione non aveva
copertura, nonostante sia il meccanismo che impedisce a un token rubato
di restare valido dopo il logout esplicito."""
import asyncio

from app.utils import token_blacklist as tb


class _FakeCollection:
    """db["token_blacklist"] in memoria: solo update_one/find_one, le
    uniche due operazioni usate dal modulo reale."""

    def __init__(self):
        self._docs = {}

    async def update_one(self, filtro, update, upsert=False):
        key = filtro["token_hash"]
        if key not in self._docs:
            self._docs[key] = update["$setOnInsert"]

    async def find_one(self, filtro, projection=None):
        return self._docs.get(filtro["token_hash"])


class _FakeDb:
    def __init__(self):
        self._coll = _FakeCollection()

    def __getitem__(self, name):
        assert name == tb.COLLECTION
        return self._coll


class _DbCheGuastaSempre:
    """Simula un database irraggiungibile: ogni accesso solleva."""

    def __getitem__(self, name):
        raise ConnectionError("Atlas non raggiungibile (simulato)")


def test_token_revocato_risulta_revocato():
    db = _FakeDb()
    asyncio.run(tb.revoca_token(db, "token-abc", exp=None))
    assert asyncio.run(tb.is_revocato(db, "token-abc")) is True


def test_token_mai_revocato_non_e_revocato():
    db = _FakeDb()
    assert asyncio.run(tb.is_revocato(db, "token-mai-visto")) is False


def test_token_diverso_da_quello_revocato_resta_valido():
    """Due token diversi non devono interferire tra loro (hash distinti)."""
    db = _FakeDb()
    asyncio.run(tb.revoca_token(db, "token-A"))
    assert asyncio.run(tb.is_revocato(db, "token-A")) is True
    assert asyncio.run(tb.is_revocato(db, "token-B")) is False


def test_token_vuoto_non_esplode():
    db = _FakeDb()
    asyncio.run(tb.revoca_token(db, ""))  # no-op, non deve sollevare
    assert asyncio.run(tb.is_revocato(db, "")) is False


def test_fail_open_se_verifica_blacklist_fallisce():
    """Design esplicito (docstring del modulo): un errore nella verifica
    della blacklist NON deve bloccare la richiesta — fail-open, perché la
    firma/scadenza del JWT restano il controllo di sicurezza primario."""
    db = _DbCheGuastaSempre()
    assert asyncio.run(tb.is_revocato(db, "qualunque-token")) is False


def test_revoca_con_errore_db_non_solleva():
    """revoca_token è best-effort (vedi docstring): un errore di scrittura
    non deve propagarsi al chiamante (il logout non deve fallire per questo)."""
    db = _DbCheGuastaSempre()
    asyncio.run(tb.revoca_token(db, "token-x"))  # non deve sollevare
