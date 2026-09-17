"""Richiesta utente 18/07/2026: "ho cliccato F24 ed ho sbagliato, come
riclassifico?" — prima non c'era modo di tornare indietro: il documento
spariva dall'elenco "da associare" e restava un record fantasma nella
collezione sbagliata (es. un F24 per un documento che era in realtà una
Cartella Esattoriale). de_associa_documento annulla l'associazione
sbagliata: elimina il record creato per errore e rimette il documento tra
i "da associare"."""
import asyncio

from fastapi import HTTPException

from app.routers.documenti_non_associati import de_associa_documento


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _Coll:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, q, proj=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                return dict(d)
        return None

    async def update_one(self, q, update):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                if "$unset" in update:
                    for k in update["$unset"]:
                        d.pop(k, None)
                if "$set" in update:
                    d.update(update["$set"])

    async def delete_one(self, q):
        before = len(self.docs)
        self.docs[:] = [d for d in self.docs if not all(d.get(k) == v for k, v in q.items())]
        return type("R", (), {"deleted_count": before - len(self.docs)})()


class _DB:
    def __init__(self):
        self._c = {}

    def __getitem__(self, name):
        return self._c.setdefault(name, _Coll())


def test_de_associa_rimuove_record_sbagliato_e_riappare_in_lista(monkeypatch):
    db = _DB()
    db["documenti_non_associati"].docs = [{
        "id": "d1", "category": "cartella_esattoriale", "associato": True,
        "associato_a": "f24_unificato", "associato_id": "r1",
        "associato_at": "2026-07-18T10:00:00",
    }]
    db["f24_unificato"].docs = [{
        "id": "r1", "source": "associazione_manuale", "documento_originale_id": "d1",
    }]

    import app.routers.documenti_non_associati as mod
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    res = _run(de_associa_documento(documento_id="d1"))
    assert res["success"] is True
    assert res["record_rimosso"] is True
    assert db["f24_unificato"].docs == []
    doc = db["documenti_non_associati"].docs[0]
    assert "associato" not in doc


def test_de_associa_non_tocca_record_esistente_arricchito(monkeypatch):
    """crea_nuovo=False (PDF aggiunto a un record GIA' esistente): mai
    cancellarlo, non è stato creato da questa associazione."""
    db = _DB()
    db["documenti_non_associati"].docs = [{
        "id": "d1", "associato": True, "associato_a": "invoices", "associato_id": "fatt-vera",
    }]
    db["invoices"].docs = [{"id": "fatt-vera", "invoice_number": "123", "supplier_name": "Vero fornitore"}]

    import app.routers.documenti_non_associati as mod
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    res = _run(de_associa_documento(documento_id="d1"))
    assert res["record_rimosso"] is False
    assert db["invoices"].docs == [{"id": "fatt-vera", "invoice_number": "123", "supplier_name": "Vero fornitore"}]


def test_de_associa_documento_non_associato_errore(monkeypatch):
    db = _DB()
    db["documenti_non_associati"].docs = [{"id": "d1", "associato": False}]
    import app.routers.documenti_non_associati as mod
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    try:
        _run(de_associa_documento(documento_id="d1"))
        assert False, "doveva sollevare HTTPException"
    except HTTPException as e:
        assert e.status_code == 400
