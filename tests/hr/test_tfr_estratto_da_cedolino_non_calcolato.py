"""Bug trovato durante il lavoro sul registro TFR del 15/07/2026: il canale
cedolini via email/Drive (salari_unificati_v2.py::processa_cedolino_v2)
estraeva già dal testo del PDF la quota TFR reale del mese (regex "TFR
mese", salvata in cedolino_record["tfr_mese"]), ma non la
passava mai nel payload dell'evento CEDOLINO_IMPORTATO. Di conseguenza
handler_aggiorna_tfr (app/handlers/tfr.py) non trovava mai
payload["tfr_quota_mese"] e ricadeva SEMPRE sulla stima lordo/13.5 (art.
2120 c.c.), contraddicendo il requisito esplicito dell'utente: il TFR non
deve mai essere calcolato dal sistema quando il valore reale è già
stampato sul cedolino."""
import asyncio
import pytest

from app.services import salari_unificati_v2 as mod
from app.services.event_bus import EventTypes


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def limit(self, n):
        return self

    async def to_list(self, n=None):
        return list(self._docs[:n] if n else self._docs)


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []
        self.updates = []

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if all(d.get(k2) == v2 for k2, v2 in (query or {}).items()):
                return dict(d)
        return None

    def find(self, query=None, projection=None, *a, **k):
        return _FakeCursor([])

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, upsert=False, *a, **k):
        self.updates.append((query, update, upsert))


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


def test_tfr_reale_dal_pdf_passa_nel_payload_evento(monkeypatch):
    catturati = []

    async def _fake_propagate_event(event_type, payload, db, **kw):
        catturati.append((event_type, payload))
        return {}

    async def _fake_riconcilia(*a, **k):
        return False

    monkeypatch.setattr("app.services.event_bus.propagate_event", _fake_propagate_event)
    monkeypatch.setattr("app.services.cedolini_manager.riconcilia_stipendio_automatico", _fake_riconcilia)

    db = _FakeDb()
    cedolino_data = {
        "codice_fiscale": "RSSMRA80A01H501U",
        "nome_dipendente": "Mario Rossi",
        "mese": 6,
        "anno": 2026,
        "netto": 1500.0,
        "lordo": 2000.0,
    }
    pdf_text = "TFR mese: 95,50\nAltri dati busta paga..."

    esito = _run(mod.processa_cedolino_v2(db, cedolino_data, pdf_text=pdf_text))

    assert esito["success"] is True
    assert len(catturati) == 1
    evento, payload = catturati[0]
    assert evento == EventTypes.CEDOLINO_IMPORTATO
    # Valore reale estratto dal PDF, chiaramente diverso dalla stima
    # lordo/13.5 (2000/13.5 = 148.15): se il payload riportasse la stima
    # invece del dato stampato in busta, il test fallirebbe.
    assert payload["tfr_quota_mese"] == 95.50


@pytest.mark.parametrize("pdf_text,quota_anno", [("", None), ("Quota anno: 522,53", 522.53)])
def test_senza_tfr_mensile_il_payload_riporta_nullo_non_lo_stima(monkeypatch, pdf_text, quota_anno):
    catturati = []

    async def _fake_propagate_event(event_type, payload, db, **kw):
        catturati.append((event_type, payload))
        return {}

    async def _fake_riconcilia(*a, **k):
        return False

    monkeypatch.setattr("app.services.event_bus.propagate_event", _fake_propagate_event)
    monkeypatch.setattr("app.services.cedolini_manager.riconcilia_stipendio_automatico", _fake_riconcilia)

    db = _FakeDb()
    cedolino_data = {
        "codice_fiscale": "BNCNNA85B02H501X",
        "nome_dipendente": "Anna Bianchi",
        "mese": 7,
        "anno": 2026,
        "netto": 1300.0,
        "lordo": 1700.0,
    }

    esito = _run(mod.processa_cedolino_v2(db, cedolino_data, pdf_text=pdf_text))

    assert esito["success"] is True
    _, payload = catturati[0]
    # Nessun TFR mensile nel PDF: null distingue l'assenza da uno zero vero
    # e impedisce al handler di sostituire una stima lordo/13.5.
    assert payload["tfr_quota_mese"] is None
    assert payload["tfr_quota_anno"] == quota_anno
    record = db["cedolini"].updates[0][1]["$set"]
    assert record["tfr_mese"] is None
    assert record["tfr_quota_anno"] == quota_anno
