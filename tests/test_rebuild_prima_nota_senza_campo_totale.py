"""Bug segnalato dall'utente 15/07/2026 (screenshot Prima Nota): dopo aver
lanciato "Ricostruisci da corrispettivi" i corrispettivi storici creati dal
vecchio data_propagation.py::propagate_corrispettivo_to_prima_nota (voce
"Corrispettivo contanti", categoria "Corrispettivi", source
"corrispettivo_import" ma SENZA il campo "totale" sul documento
corrispettivi — solo pagato_contanti/pagato_elettronico) sparivano da Prima
Nota invece di essere ricostruiti: rebuild_prima_nota_from_corrispettivi
eliminava il vecchio movimento (il purge filtra su categoria/source, non sul
corrispettivo sorgente) ma poi saltava la ricreazione perché il guard
controllava solo corr["totale"], non i fallback (pagato_contanti +
pagato_elettronico) già usati da _create_prima_nota_movements."""
import asyncio

from app.routers.invoices.corrispettivi_helpers import rebuild_prima_nota_from_corrispettivi


def _matches(doc, query):
    if not query:
        return True
    for k, v in query.items():
        if isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]:
                return False
        elif isinstance(v, dict) and "$ne" in v:
            if doc.get(k) == v["$ne"]:
                return False
        elif isinstance(v, dict) and "$regex" in v:
            if not str(doc.get(k, "")).startswith(v["$regex"].lstrip("^")):
                return False
        else:
            if doc.get(k) != v:
                return False
    return True


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if _matches(d, query):
                return dict(d)
        return None

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, *a, **k):
        for d in self.docs:
            if _matches(d, query):
                d.update(update.get("$set", {}))
                return

    async def delete_many(self, query, *a, **k):
        before = len(self.docs)
        self.docs = [d for d in self.docs if not _matches(d, query)]
        return type("R", (), {"deleted_count": before - len(self.docs)})()

    def find(self, query=None, projection=None, *a, **k):
        return _FakeCursor([d for d in self.docs if _matches(d, query or {})])


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def __getitem__(self, item):
        return self

    async def to_list(self, n=None):
        return list(self._docs[:n] if n else self._docs)


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def test_rebuild_ricrea_corrispettivo_senza_campo_totale():
    db = _FakeDb()
    # Corrispettivo storico: nessun campo "totale", solo la suddivisione.
    db["corrispettivi"].docs = [{
        "id": "corr-vecchio", "data": "2026-06-29",
        "pagato_contanti": 649.70, "pagato_elettronico": 0.0,
    }]
    # Vecchia riga creata da data_propagation.py (solo contanti, nessuna
    # uscita "POS Verso Banca", descrizione diversa).
    db["prima_nota_cassa"].docs = [{
        "id": "mov-vecchio", "data": "2026-06-29", "tipo": "entrata",
        "importo": 649.70, "categoria": "Corrispettivi",
        "descrizione": "Corrispettivo contanti 2026-06-29",
        "source": "corrispettivo_import", "corrispettivo_id": "corr-vecchio",
    }]

    res = _run(rebuild_prima_nota_from_corrispettivi(db, anno=2026))

    assert res["corrispettivi_saltati"] == 0
    assert res["corrispettivi_processati"] == 1
    cassa = db["prima_nota_cassa"].docs
    assert len(cassa) == 1
    assert cassa[0]["descrizione"] == "Corrispettivi 2026-06-29"
    assert cassa[0]["importo"] == 649.70


def test_rebuild_somma_contanti_ed_elettronico_senza_totale():
    db = _FakeDb()
    db["corrispettivi"].docs = [{
        "id": "corr-1", "data": "2026-06-28",
        "pagato_contanti": 400.0, "pagato_elettronico": 163.0,
    }]

    res = _run(rebuild_prima_nota_from_corrispettivi(db, anno=2026))

    assert res["corrispettivi_saltati"] == 0
    cassa = db["prima_nota_cassa"].docs
    entrata = next(d for d in cassa if d["tipo"] == "entrata")
    uscita = next(d for d in cassa if d["tipo"] == "uscita")
    assert entrata["importo"] == 563.0
    assert uscita["importo"] == 163.0
    assert uscita["categoria"] == "POS Verso Banca"
    banca = db["prima_nota_banca"].docs
    assert len(banca) == 1
    assert banca[0]["importo"] == 163.0
