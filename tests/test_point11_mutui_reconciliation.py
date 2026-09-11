import asyncio

from app.routers import mutui


def _run(coro):
    return asyncio.run(coro)


class _Cursor:
    def __init__(self, rows): self.rows = list(rows)
    async def to_list(self, _n): return list(self.rows)[:_n]


class _Movimenti:
    def __init__(self, strong, fallback):
        self.strong = list(strong)
        self.fallback = list(fallback)
        self.calls = 0
    def find(self, query):
        self.calls += 1
        return _Cursor(self.strong if '$or' in query else self.fallback)


class _DB:
    def __init__(self, strong, fallback):
        self.estratto_conto_movimenti = _Movimenti(strong, fallback)


def test_match_forte_univoco():
    db = _DB([{'id': 'm1'}], [{'id': 'm1'}])
    movimento, ambiguo, criterio = _run(mutui._candidato_bancario_univoco(db, {'$or': []}, {}))
    assert movimento['id'] == 'm1'
    assert ambiguo is False
    assert criterio == 'causale_importo_data'
    assert db.estratto_conto_movimenti.calls == 1


def test_due_match_forti_non_sceglie_il_primo_e_non_fa_fallback():
    db = _DB([{'id': 'm1'}, {'id': 'm2'}], [{'id': 'm3'}])
    movimento, ambiguo, criterio = _run(mutui._candidato_bancario_univoco(db, {'$or': []}, {}))
    assert movimento is None
    assert ambiguo is True
    assert criterio == 'piu_candidati_con_causale'
    assert db.estratto_conto_movimenti.calls == 1


def test_fallback_solo_se_univoco():
    db = _DB([], [{'id': 'm3'}])
    movimento, ambiguo, criterio = _run(mutui._candidato_bancario_univoco(db, {'$or': []}, {}))
    assert movimento['id'] == 'm3'
    assert ambiguo is False
    assert criterio == 'importo_data_univoco'

    db2 = _DB([], [{'id': 'm3'}, {'id': 'm4'}])
    movimento, ambiguo, criterio = _run(mutui._candidato_bancario_univoco(db2, {'$or': []}, {}))
    assert movimento is None
    assert ambiguo is True
    assert criterio == 'piu_candidati_importo_data'


def test_source_manual_rejects_reused_or_non_outgoing_movements():
    source = open('app/routers/mutui.py', encoding='utf-8').read()
    assert 'Movimento bancario gia riconciliato con un altro documento' in source
    assert 'La rata mutuo richiede un movimento bancario di uscita' in source
    assert '.find_one(query_movimenti)' not in source
