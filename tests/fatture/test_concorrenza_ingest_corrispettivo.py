"""Follow-up dal fix di registra_corrispettivo (PR #67): _find_existing_
corrispettivo (app/routers/invoices/corrispettivi_helpers.py) ha lo stesso
pattern find_one-poi-insert, ma su PIÙ livelli sequenziali (chiave XML,
poi data+matricola, poi data+totale) prima di eventualmente inserire.

Il test isolato con registro Sheets effimero (backend/tests/test_corrispettivi_ingest_
isolato.py) non basta per provare l'interleaving reale: registro Sheets effimero esegue le
operazioni senza cedere il controllo all'event loop, quindi due coroutine
lanciate con asyncio.gather non si intrecciano mai, anche se in produzione
(I/O di rete vero) potrebbero farlo. Questo file usa un fake DB che cede
DAVVERO il controllo (await asyncio.sleep(0)) a ogni operazione, come già
fatto per registra_corrispettivo, per verificare l'interleaving reale."""
import asyncio

from app.routers.invoices.corrispettivi_helpers import ingest_corrispettivo_parsed


def _match(doc, query):
    for k, v in query.items():
        if k == "$or":
            return any(_match(doc, sub) for sub in v)
        if isinstance(v, dict):
            if "$in" in v and doc.get(k) not in v["$in"]:
                return False
            if "$nin" in v and doc.get(k) in v["$nin"]:
                return False
            if "$ne" in v and doc.get(k) == v["$ne"]:
                return False
            if "$gte" in v and not (doc.get(k, 0) >= v["$gte"]):
                return False
            if "$lte" in v and not (doc.get(k, 0) <= v["$lte"]):
                return False
        else:
            if doc.get(k) != v:
                return False
    return True


class _RaceyColl:
    """Ogni operazione cede DAVVERO il controllo (await asyncio.sleep(0)),
    replicando l'interleaving possibile con I/O di rete reale."""

    def __init__(self):
        self.docs = []

    async def find_one(self, query, *a, **k):
        await asyncio.sleep(0)
        for d in self.docs:
            if _match(d, query):
                return dict(d)
        return None

    async def insert_one(self, doc):
        await asyncio.sleep(0)
        self.docs.append(dict(doc))

    async def update_one(self, query, update, *a, **k):
        await asyncio.sleep(0)
        for d in self.docs:
            if _match(d, query):
                d.update(update.get("$set", {}))
                return

    async def find_one_and_update(self, query, update, upsert=False):
        await asyncio.sleep(0)
        for d in self.docs:
            if _match(d, query):
                return dict(d)
        if upsert:
            self.docs.append(dict(update.get("$setOnInsert", {})))
        return None

    async def delete_many(self, query, *a, **k):
        await asyncio.sleep(0)

        class _R:
            deleted_count = 0
        return _R()


class _RaceyDb:
    def __init__(self):
        self.colls = {}

    def __getitem__(self, name):
        return self.colls.setdefault(name, _RaceyColl())


def _parsed():
    return {
        "corrispettivo_key": "RT001-2026-07-19",
        "data": "2026-07-19",
        "matricola_rt": "RT001",
        "partita_iva": "99999999901",
        "pagato_contanti": 80.0,
        "pagato_elettronico": 20.0,
        "totale_imponibile": 90.91,
        "totale_iva": 9.09,
        "totale": 100.0,
        "numero_documenti": 5,
    }


def test_due_upload_concorrenti_stesso_corrispettivo_non_duplicano_con_interleaving_reale():
    db = _RaceyDb()
    parsed = _parsed()

    async def _run():
        return await asyncio.gather(
            ingest_corrispettivo_parsed(db, parsed, filename="a.xml", source="xml", update_if_exists=True),
            ingest_corrispettivo_parsed(db, parsed, filename="b.xml", source="xml", update_if_exists=True),
        )

    esiti = asyncio.run(_run())

    record_corrispettivi = db.colls["corrispettivi"].docs
    assert len(record_corrispettivi) == 1, (
        f"attesi 1 record 'corrispettivi', trovati {len(record_corrispettivi)}: "
        f"_find_existing_corrispettivo non è atomico sotto interleaving reale. Esiti: {esiti}"
    )
