"""Bug trovato in audit 15/07/2026: controlla_scadenze_f24() interrogava
COLLECTION_F24 e COLLECTION_F24_COMMERCIALISTA come se fossero due
collection diverse (concatenando i risultati), ma sono la STESSA
collection "f24_unificato" dall'unificazione del 13/07 — ogni F24 veniva
quindi contato/notificato due volte. In più ciascuna delle due query
riconosceva "pagato" solo su UNO dei due schemi campo (stato="pagato" vs
status="paid"): un F24 pagato con lo schema inglese (status="paid",
creato da POST /api/f24) non veniva MAI riconosciuto come pagato da
nessuna delle due query — generava un falso alert "scaduto" ogni giorno
via Telegram/email/campanella."""
import asyncio
from datetime import date, timedelta

from app.services import f24_scadenze_notifiche as mod


def _matches(doc, query):
    for k, v in query.items():
        if isinstance(v, dict) and "$nin" in v:
            if doc.get(k) in v["$nin"]:
                return False
        else:
            if doc.get(k) != v:
                return False
    return True


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    def find(self, query, *a, **k):
        return _FakeCursor([d for d in self.docs if _matches(d, query)])

    async def update_one(self, query, update, *a, upsert=False, **k):
        for d in self.docs:
            if all(d.get(k2) == v2 for k2, v2 in query.items()):
                d.update(update.get("$set", {}))
                return
        if upsert:
            self.docs.append(dict(update.get("$set", {})))


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

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


def test_f24_pagato_con_schema_inglese_non_genera_alert(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    scadenza_vicina = (date.today() + timedelta(days=2)).isoformat()
    db["f24_unificato"].docs = [
        # Pagato con lo schema inglese (creato da POST /api/f24): NON deve
        # generare alert, prima ci finiva sempre dentro.
        {"id": "f24-pagato-eng", "status": "paid", "scadenza": scadenza_vicina,
         "importo_totale": 500.0},
        # Pagato con lo schema italiano: non deve generare alert.
        {"id": "f24-pagato-ita", "stato": "pagato", "data_scadenza": scadenza_vicina,
         "importo_totale": 300.0},
        # Genuinamente non pagato (nessuno dei due campi): deve generare
        # esattamente UN alert, non due.
        {"id": "f24-non-pagato", "scadenza": scadenza_vicina, "importo_totale": 700.0},
    ]

    esito = _run(mod.controlla_scadenze_f24())

    id_notificati = [
        s["f24_id"] for s in esito["scadenze_imminenti"] + esito["scadenze_scadute"]
    ]
    assert "f24-pagato-eng" not in id_notificati
    assert "f24-pagato-ita" not in id_notificati
    assert id_notificati.count("f24-non-pagato") == 1
    assert esito["totale_alert"] == 1
