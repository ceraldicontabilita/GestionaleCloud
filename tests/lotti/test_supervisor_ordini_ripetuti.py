"""Il supervisore deve dedurre ordini ripetuti dagli ordini, non dalle fatture."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.lotti.routers import supervisor_operativo as supervisor


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, _limit):
        return self.docs


class _Ordini:
    def __init__(self, docs):
        self.docs = docs

    def find(self, filtro, _projection):
        assert "data_ordine" in filtro
        assert "stato" in filtro
        return _Cursor([
            doc for doc in self.docs
            if doc["data_ordine"] >= filtro["data_ordine"]["$gte"]
            and doc["stato"] in filtro["stato"]["$in"]
        ])


def _ordine(id_, giorno, prodotti, stato="bozza"):
    return {"id": id_, "data_ordine": giorno, "stato": stato,
            "prodotti": prodotti}


def test_righe_di_fattura_e_doppia_riga_nello_stesso_ordine_non_sono_ordini_ripetuti(monkeypatch):
    oggi = datetime.now(timezone.utc).date().isoformat()
    riga = {"prodotto_id": "p-1", "nome": "Farina", "fornitore": "Fornitore"}
    # Il codice non legge lotti_fornitori, anche se contiene tre righe uguali.
    db = SimpleNamespace(
        ordini_fornitori=_Ordini([_ordine("o-1", oggi, [riga, riga])]),
        lotti_fornitori=SimpleNamespace(aggregate=lambda *_: 1 / 0),
    )
    monkeypatch.setattr(supervisor, "db", db)
    alerts = []
    asyncio.run(supervisor.check_ordini_ripetuti(alerts))
    assert alerts == []


def test_due_ordini_distinti_stesso_prodotto_e_fornitore_sono_verificabili(monkeypatch):
    oggi = datetime.now(timezone.utc).date().isoformat()
    vecchio = (datetime.now(timezone.utc).date() - timedelta(days=90)).isoformat()
    riga = {"prodotto_id": "p-1", "nome": "Farina", "fornitore": "Fornitore"}
    stesso_nome_altro_id = {**riga, "prodotto_id": "p-2"}
    altri = {**riga, "fornitore": "Altro fornitore"}
    docs = [
        _ordine("o-1", oggi, [riga]),
        _ordine("o-2", oggi, [riga]),
        _ordine("o-7", oggi, [riga], stato="ricevuto_parziale"),
        _ordine("o-3", oggi, [stesso_nome_altro_id]),
        _ordine("o-4", oggi, [altri]),
        _ordine("o-5", vecchio, [riga]),
        _ordine("o-6", oggi, [riga], stato="annullato"),
    ]
    monkeypatch.setattr(supervisor, "db", SimpleNamespace(ordini_fornitori=_Ordini(docs)))
    alerts = []
    asyncio.run(supervisor.check_ordini_ripetuti(alerts))
    assert len(alerts) == 1
    assert alerts[0]["contatore"] == 3
    assert [item["id"] for item in alerts[0]["items"]] == ["o-1", "o-2", "o-7"]
    assert alerts[0]["route"] == "ordini"
