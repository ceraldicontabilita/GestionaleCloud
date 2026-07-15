"""Richiesta utente 15/07/2026: "sii sicuro che tutti i cedolini che ci
sono sono stati caricati in contabilità". La quadratura esistente
(verifica_quadratura_elaborate) controlla solo Drive ↔ documents_inbox (il
file è arrivato nel gestionale) ma non che sia davvero diventato un
cedolino vero in `cedolini` — un parsing fallito o un dipendente non
riconosciuto lasciano il documento con processed=False per sempre, senza
nessun avviso. verifica_documenti_bloccati chiude questo buco: segnala i
documenti (Drive o email) mai processati oltre una soglia di ore."""
import asyncio
from datetime import datetime, timedelta, timezone

from app.services import drive_cedolini_ingest as mod


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def _matches(doc, query):
    for k, v in query.items():
        if isinstance(v, dict) and "$ne" in v:
            if doc.get(k) == v["$ne"]:
                return False
        elif isinstance(v, dict) and "$lt" in v:
            if not (doc.get(k) or "") < v["$lt"]:
                return False
        else:
            if doc.get(k) != v:
                return False
    return True


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, n=None):
        return list(self._docs[:n] if n else self._docs)


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    def find(self, query=None, projection=None, *a, **k):
        return _FakeCursor([d for d in self.docs if _matches(d, query or {})])


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


def _iso(hours_ago):
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


def test_segnala_documenti_mai_processati_oltre_la_soglia():
    db = _FakeDb()
    db["documents_inbox"].docs = [
        # Drive, mai processato, vecchio: bloccato.
        {"id": "d1", "category": "busta_paga", "processed": False, "filename": "vecchio.pdf",
         "created_at": _iso(10)},
        # Drive, processato: OK, non deve comparire.
        {"id": "d2", "category": "busta_paga", "processed": True, "filename": "ok.pdf",
         "created_at": _iso(10)},
        # Drive, non processato ma recente: in attesa del prossimo giro, non un buco.
        {"id": "d3", "category": "busta_paga", "processed": False, "filename": "recente.pdf",
         "created_at": _iso(1)},
        # Non un cedolino: ignorato.
        {"id": "d4", "category": "fattura", "processed": False, "created_at": _iso(10)},
    ]
    db["cedolini_email_attachments"].docs = [
        {"id": "e1", "processed": False, "filename": "email_vecchio.pdf", "created_at": _iso(20)},
    ]

    esito = _run(mod.verifica_documenti_bloccati(db))

    ids = {b["id"] for b in esito["bloccati"]}
    assert ids == {"d1", "e1"}
    assert esito["totale_bloccati"] == 2
    canali = {b["id"]: b["canale"] for b in esito["bloccati"]}
    assert canali["d1"] == "drive"
    assert canali["e1"] == "email"


def test_nessun_documento_bloccato_ritorna_zero():
    db = _FakeDb()
    db["documents_inbox"].docs = [
        {"id": "d1", "category": "busta_paga", "processed": True, "created_at": _iso(10)},
    ]
    db["cedolini_email_attachments"].docs = []

    esito = _run(mod.verifica_documenti_bloccati(db))

    assert esito["totale_bloccati"] == 0
    assert esito["bloccati"] == []
