import asyncio

from app.services import verbali_pagamento_finder as mod


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, n):
        return list(self.docs[:n])


class _Collection:
    def __init__(self, docs=None):
        self.docs = docs or []

    def find(self, _query, _projection=None):
        return _Cursor(self.docs)


class _Db:
    def __init__(self, verbali):
        self.collections = {"verbali_noleggio": _Collection(verbali)}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _Collection())


def test_riconciliazione_strict_non_inventa_match_per_importo(monkeypatch):
    db = _Db([
        {"id": "v1", "numero_verbale": "A11111111111", "importo": 100.0, "stato": "salvato"},
        {"id": "v2", "numero_verbale": "A22222222222", "importo": 100.0, "stato": "salvato"},
    ])
    applied = []

    async def fake_find(_db, verbale):
        if verbale["id"] == "v1":
            return {"fonte": "estratto_conto", "importo": 100.0, "movimento_id": "m1"}
        return None

    async def fake_apply(_db, verbale_id, match):
        applied.append((verbale_id, match["movimento_id"]))
        return True

    monkeypatch.setattr(mod, "trova_pagamento_verbale", fake_find)
    monkeypatch.setattr(mod, "applica_pagamento_a_verbale", fake_apply)

    result = asyncio.run(mod.riconcilia_verbali_strict(db))

    assert result["riconciliati"] == 1
    assert result["non_riconciliati"] == 1
    assert result["riconciliati_banca"] == 1
    assert applied == [("v1", "m1")]
    assert "riferimento_strutturato" in result["regola"]
