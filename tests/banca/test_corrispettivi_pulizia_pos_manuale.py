"""Bug A segnalato dall'utente 14/07/2026: la quick-form "💳 POS" di Prima
Nota Cassa (PrimaNota.jsx::handleSavePos) crea un'uscita provvisoria
categoria "POS"/source "manual_pos" con la promessa "Sarà sovrascritto
quando arriva XML" — ma _delete_prima_nota_for_corrispettivo() puliva solo
i vecchi movimenti categoria "Corrispettivi", mai quelli categoria "POS":
l'uscita manuale restava per sempre, mai riconciliata con Coerenza POS
(che legge solo prima_nota_banca) e mai sostituita da "POS Verso Banca"
generato dal vero import XML — le due finivano per sommarsi, gonfiando le
uscite cassa. Verifica che ora venga ripulita quando arriva il
corrispettivo reale per la stessa data."""
import asyncio

from app.routers.invoices import corrispettivi_helpers as helpers_mod


def _matches(doc, query):
    if not query:
        return True
    for k, v in query.items():
        if k == "$or":
            if not any(_matches(doc, q) for q in v):
                return False
        elif isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]:
                return False
        else:
            if doc.get(k) != v:
                return False
    return True


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def delete_many(self, query, *a, **k):
        rimasti = [d for d in self.docs if not _matches(d, query)]
        rimossi = len(self.docs) - len(rimasti)
        self.docs = rimasti

        class _R:
            deleted_count = rimossi

        return _R()


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


def test_pulizia_rimuove_uscita_pos_manuale_stessa_data():
    db = _FakeDb()
    db["prima_nota_cassa"].docs = [
        {"id": "pn-manuale", "data": "2026-07-14", "tipo": "uscita",
         "categoria": "POS", "source": "manual_pos", "importo": 450.0, "provvisorio": True},
        {"id": "pn-altro", "data": "2026-07-14", "tipo": "entrata",
         "categoria": "Incasso", "source": "manual_entry", "importo": 20.0},
    ]

    _run(helpers_mod._delete_prima_nota_for_corrispettivo(db, "", "2026-07-14"))

    rimasti = db["prima_nota_cassa"].docs
    assert [d["id"] for d in rimasti] == ["pn-altro"]


def test_pulizia_non_tocca_pos_manuale_di_altra_data():
    db = _FakeDb()
    db["prima_nota_cassa"].docs = [
        {"id": "pn-manuale", "data": "2026-07-10", "tipo": "uscita",
         "categoria": "POS", "source": "manual_pos", "importo": 450.0},
    ]

    _run(helpers_mod._delete_prima_nota_for_corrispettivo(db, "", "2026-07-14"))

    assert len(db["prima_nota_cassa"].docs) == 1
