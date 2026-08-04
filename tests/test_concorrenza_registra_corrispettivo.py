"""Test di concorrenza reale su app/services/scritture_contabili.py
(motore unico, regola canonica POS — LOGICA_FUNZIONAMENTO.md §4).

La guardia di idempotenza di registra_corrispettivo è un classico
check-then-act: find_one("già esiste?") seguito, se assente, da un
insert_one. Sequenzialmente funziona; questo test verifica se regge
anche con due chiamate concorrenti sullo STESSO corrispettivo, usando
un fake DB che cede realmente il controllo all'event loop
(await asyncio.sleep(0)) a ogni operazione — senza questo yield, due
coroutine lanciate con asyncio.gather in puro Python non si
intreccerebbero mai e il test non proverebbe nulla sull'interleaving
reale che avviene con Motor/pymongo su una connessione di rete vera."""
import asyncio

from app.services import scritture_contabili as sc


def _match(doc, query):
    for k, v in query.items():
        if isinstance(v, dict):
            if "$in" in v and doc.get(k) not in v["$in"]:
                return False
            if "$nin" in v and doc.get(k) in v["$nin"]:
                return False
            if "$ne" in v and doc.get(k) == v["$ne"]:
                return False
        elif doc.get(k) != v:
            return False
    return True


class _RaceyColl:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, *a, **k):
        await asyncio.sleep(0)  # simula la latenza di un find_one di rete
        for d in self.docs:
            if _match(d, query):
                return dict(d)
        return None

    async def insert_one(self, doc):
        await asyncio.sleep(0)  # simula la latenza di un insert_one di rete
        self.docs.append(dict(doc))

        class _Result:
            inserted_id = doc.get("id")

        return _Result()

    async def find_one_and_update(self, query, update, upsert=False):
        # UN SOLO yield per l'intera operazione: in MongoDB reale
        # find_one_and_update è atomica (un solo round-trip), quindi qui il
        # controllo e l'eventuale scrittura avvengono senza cedere di nuovo
        # il controllo — è esattamente il comportamento che il fix in
        # scritture_contabili.py assume e su cui fa affidamento.
        await asyncio.sleep(0)
        for d in self.docs:
            if _match(d, query):
                return dict(d)  # stato "prima": esisteva già
        if upsert:
            nuovo = dict(update.get("$setOnInsert", {}))
            self.docs.append(nuovo)
        return None


class _RaceyDb:
    def __init__(self):
        self.colls = {}

    def __getitem__(self, name):
        return self.colls.setdefault(name, _RaceyColl())


def _corrispettivo():
    return {
        "id": "corr-1",
        "data": "2026-07-19",
        "matricola_rt": "RT001",
        "totale": 100.0,
        "totale_imponibile": 82.0,
        "totale_iva": 18.0,
        "pagato_contanti": 100.0,
        "pagato_elettronico": 0.0,
    }


def test_chiamata_singola_resta_idempotente_su_retry_sequenziale():
    """Caso base (sequenziale, non concorrente): la seconda chiamata deve
    riconoscere il duplicato tramite la guardia find_one — nessuna sorpresa,
    verifica solo che il fake DB si comporti come atteso prima del test
    di interleaving vero sotto."""
    db = _RaceyDb()
    esito1 = asyncio.run(sc.registra_corrispettivo(db, _corrispettivo()))
    esito2 = asyncio.run(sc.registra_corrispettivo(db, _corrispettivo()))

    assert esito1.get("gia_esistente") is not True
    assert esito2.get("gia_esistente") is True
    entrate = [d for d in db.colls["prima_nota_cassa"].docs
               if d.get("tipo") == "entrata" and d.get("categoria") == "Corrispettivi"]
    assert len(entrate) == 1


def test_due_registrazioni_concorrenti_dello_stesso_corrispettivo():
    """Due coroutine lanciate DAVVERO in concorrenza (asyncio.gather) per
    lo stesso corrispettivo (stessa data/matricola). Se la guardia
    find_one-poi-insert non è atomica, entrambe possono superare il
    controllo prima che l'altra abbia scritto, producendo un doppio
    movimento in Prima Nota Cassa — vietato dalla regola canonica POS."""
    db = _RaceyDb()

    async def _run():
        return await asyncio.gather(
            sc.registra_corrispettivo(db, _corrispettivo()),
            sc.registra_corrispettivo(db, _corrispettivo()),
        )

    esiti = asyncio.run(_run())

    entrate_cassa = [
        d for d in db.colls["prima_nota_cassa"].docs
        if d.get("tipo") == "entrata" and d.get("categoria") == "Corrispettivi"
    ]
    assert len(entrate_cassa) == 1, (
        f"attesa 1 sola scrittura di cassa per il corrispettivo, trovate "
        f"{len(entrate_cassa)}: la guardia di idempotenza (find_one poi insert) "
        f"non è atomica e sotto interleaving reale crea un doppio movimento "
        f"in Prima Nota Cassa. Esiti delle due chiamate: {esiti}"
    )
