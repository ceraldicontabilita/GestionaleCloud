"""Bug segnalato dall'utente 18/07/2026 (screenshot): chiesto "gennaio"
alla chat, rispondeva col totale dell'INTERO anno — il mese era ignorato."""
import asyncio

from app.routers import chat_router as mod


def test_estrai_mese_dai_nomi():
    assert mod._estrai_mese("corrispettivi di gennaio") == 1
    assert mod._estrai_mese("Fatture di SETTEMBRE 2026") == 9
    assert mod._estrai_mese("corrispettivi 03/2026") == 3
    assert mod._estrai_mese("corrispettivi 2026") is None


def test_periodo_mese_e_anno():
    assert mod._periodo("corrispettivi gennaio 2026") == ("2026-01", "A gennaio 2026")
    assert mod._periodo("corrispettivi 2026")[0] == "2026"


class _Cur:
    def __init__(self, docs): self._d = docs
    async def to_list(self, n): return self._d


class _Coll:
    def __init__(self, docs): self._docs = docs
    def find(self, query, proj=None):
        prefisso = query["data"]["$regex"].lstrip("^")
        return _Cur([d for d in self._docs if d["data"].startswith(prefisso)])


class _Db:
    def __init__(self, docs): self._c = _Coll(docs)
    def __getitem__(self, name): return self._c


def test_risposta_corrispettivi_filtra_il_mese():
    db = _Db([
        {"data": "2026-01-10", "totale": 100.0, "pagato_contanti": 60.0, "pagato_elettronico": 40.0},
        {"data": "2026-02-11", "totale": 900.0, "pagato_contanti": 0.0, "pagato_elettronico": 900.0},
    ])
    loop = asyncio.new_event_loop()
    try:
        res = loop.run_until_complete(mod._risposta_corrispettivi(db, "corrispettivi di gennaio 2026"))
    finally:
        loop.close()
    assert res["summary"]["totale"] == 100.0
    assert res["summary"]["count"] == 1
    assert res["response"].startswith("A gennaio 2026")
