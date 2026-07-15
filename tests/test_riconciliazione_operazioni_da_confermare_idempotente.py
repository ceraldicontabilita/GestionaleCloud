"""Bug trovato nell'audit funzionale del 15/07/2026: un movimento bancario
ambiguo (più fatture candidate con punteggio di match simile) resta
riconciliato=False finché l'utente non conferma/ignora l'operazione. Lo
scheduler rilancia riconcilia_movimenti_banca() ogni 30 minuti
(app/scheduler.py) e prima di questo fix rielaborava lo stesso movimento
creando un NUOVO record in operazioni_da_confermare ad ogni passaggio,
invece di riusare quello già aperto — duplicati illimitati per lo stesso
movimento finché l'operatore non interviene."""
import asyncio

from app.services import riconciliazione_bancaria as mod


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if all(d.get(k2) == v2 for k2, v2 in query.items()):
                return dict(d)
        return None

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


def _operazione(mov_id="mov-1"):
    return {
        "id": "op-x", "tipo": "riconciliazione_dubbio", "movimento_ec_id": mov_id,
        "importo": 100.0, "stato": "da_confermare",
    }


def test_non_duplica_operazione_gia_aperta_per_stesso_movimento():
    db = _FakeDb()

    creata1 = _run(mod._crea_operazione_da_confermare_idempotente(db, _operazione()))
    # Secondo passaggio dello scheduler sullo stesso movimento ancora non
    # confermato: prima del fix creava un secondo record identico.
    creata2 = _run(mod._crea_operazione_da_confermare_idempotente(db, _operazione()))

    assert creata1 is True
    assert creata2 is False
    assert len(db[mod.COLLECTION_OPERAZIONI_DA_CONFERMARE].docs) == 1


def test_crea_nuova_operazione_se_la_precedente_e_stata_confermata():
    db = _FakeDb()
    db[mod.COLLECTION_OPERAZIONI_DA_CONFERMARE].docs = [
        {**_operazione(), "stato": "confermata"},  # già risolta dall'utente
    ]

    creata = _run(mod._crea_operazione_da_confermare_idempotente(db, _operazione()))

    assert creata is True
    assert len(db[mod.COLLECTION_OPERAZIONI_DA_CONFERMARE].docs) == 2


def test_movimenti_diversi_creano_operazioni_distinte():
    db = _FakeDb()

    creata1 = _run(mod._crea_operazione_da_confermare_idempotente(db, _operazione("mov-1")))
    creata2 = _run(mod._crea_operazione_da_confermare_idempotente(db, _operazione("mov-2")))

    assert creata1 is True
    assert creata2 is True
    assert len(db[mod.COLLECTION_OPERAZIONI_DA_CONFERMARE].docs) == 2
