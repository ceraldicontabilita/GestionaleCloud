"""Regressioni per il doppio Piano dei Conti osservato in produzione.

Il frontend carica elenco e bilancio in parallelo. Con la collezione vuota,
entrambi gli endpoint inizializzavano tutti i conti e producevano due copie
per codice; il bilancio sommava poi due volte gli stessi saldi.
"""

import asyncio
from copy import deepcopy

import app.routers.accounting.piano_conti as pc


class _Cursor:
    def __init__(self, docs, projection=None):
        self._docs = [deepcopy(doc) for doc in docs]
        self._projection = projection or {}

    def sort(self, key, direction):
        self._docs.sort(key=lambda doc: doc.get(key, ""), reverse=direction < 0)
        return self

    async def to_list(self, length):
        docs = self._docs[:length]
        if self._projection.get("_id") == 0:
            for doc in docs:
                doc.pop("_id", None)
        return docs


class _UpdateResult:
    def __init__(self, upserted_id=None):
        self.upserted_id = upserted_id


class _Collection:
    def __init__(self, docs=None):
        self.docs = [deepcopy(doc) for doc in (docs or [])]
        self._lock = asyncio.Lock()

    def find(self, query=None, projection=None):
        return _Cursor(self.docs, projection)

    async def insert_many(self, docs):
        # Riproduce la finestra concorrente del vecchio codice.
        await asyncio.sleep(0)
        for doc in docs:
            stored = deepcopy(doc)
            stored.setdefault("_id", f"legacy-{len(self.docs)}")
            self.docs.append(stored)
            doc["_id"] = stored["_id"]

    async def update_one(self, query, update, upsert=False):
        async with self._lock:
            for doc in self.docs:
                if all(doc.get(key) == value for key, value in query.items()):
                    return _UpdateResult()
            if not upsert:
                return _UpdateResult()
            stored = deepcopy(update["$setOnInsert"])
            stored.update(query)
            self.docs.append(stored)
            return _UpdateResult(stored.get("_id"))


class _Db:
    def __init__(self, conti=None):
        self.collection = _Collection(conti)

    def __getitem__(self, name):
        assert name == "piano_conti"
        return self.collection


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _conto(codice, nome, categoria):
    return {
        "id": f"id-{codice}-{nome}",
        "codice": codice,
        "nome": nome,
        "categoria": categoria,
        "natura": "finanziario",
        "attivo": True,
        "created_at": "2026-08-04T13:41:54+00:00",
    }


def test_get_piano_conti_restituisce_un_solo_record_per_codice(monkeypatch):
    conti = [
        _conto("01.01.01", "Cassa", "attivo"),
        _conto("01.01.01", "Cassa", "attivo"),
        _conto("04.01.01", "Ricavi", "ricavi"),
        _conto("04.01.01", "Ricavi", "ricavi"),
    ]
    db = _Db(conti)
    monkeypatch.setattr(pc.Database, "get_db", staticmethod(lambda: db))

    async def _saldi(_db, anno=None):
        return {"01.01.01": 100.0, "04.01.01": 50.0}

    monkeypatch.setattr(pc, "_calcola_saldi_piano_conti", _saldi)

    result = _run(pc.get_piano_conti(anno="2026"))

    assert result["totale"] == 2
    assert [row["codice"] for row in result["conti"]] == ["01.01.01", "04.01.01"]
    assert len(result["grouped"]["attivo"]) == 1
    assert len(result["grouped"]["ricavi"]) == 1


def test_bilancio_non_somma_due_volte_un_codice_duplicato(monkeypatch):
    conti = [
        _conto("01.01.01", "Cassa", "attivo"),
        _conto("01.01.01", "Cassa", "attivo"),
        _conto("05.01.01", "Acquisti", "costi"),
        _conto("05.01.01", "Acquisti", "costi"),
    ]
    db = _Db(conti)
    monkeypatch.setattr(pc.Database, "get_db", staticmethod(lambda: db))

    async def _saldi(_db, anno=None):
        return {"01.01.01": 100.0, "05.01.01": 25.0}

    monkeypatch.setattr(pc, "_calcola_saldi_piano_conti", _saldi)

    result = _run(pc.get_bilancio(anno="2026"))

    assert result["stato_patrimoniale"]["attivo"]["totale"] == 100.0
    assert result["conto_economico"]["costi"]["totale"] == 25.0
    assert len(result["stato_patrimoniale"]["attivo"]["conti"]) == 1


def test_inizializzazione_concorrente_crea_un_solo_conto_per_codice():
    db = _Db()

    async def _inizializza_due_endpoint():
        await asyncio.gather(
            pc.inizializza_piano_conti_base(db),
            pc.inizializza_piano_conti_base(db),
        )

    _run(_inizializza_due_endpoint())

    codici = [doc["codice"] for doc in db.collection.docs]
    codici_attesi = {
        conto["codice"]
        for gruppo in pc.STRUTTURA_BASE.values()
        for conto in gruppo["conti_tipici"]
    }
    assert len(codici) == len(codici_attesi)
    assert set(codici) == codici_attesi

