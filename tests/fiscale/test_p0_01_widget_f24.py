"""P0.1 — Il widget scadenze conta i F24 da pagare leggendo SOLO la collezione
canonica `f24_unificato`, contando i documenti distinti una volta sola e coprendo
sia lo schema canonico (`scadenza`/`status`) sia quello legacy (`data_scadenza`/
`pagato`). Prima due count sommate raddoppiavano e la query legacy pescava a vuoto."""
import asyncio

from app.routers.scadenze import conta_f24_da_pagare


class _Coll:
    def __init__(self, docs):
        self.docs = docs

    async def count_documents(self, query):
        return sum(1 for d in self.docs if _match(d, query))


def _match(d, q):
    for k, cond in q.items():
        if k == "$or":
            if not any(_match(d, sub) for sub in cond):
                return False
        elif isinstance(cond, dict):
            for op, val in cond.items():
                v = _get(d, k)
                if op == "$nin" and v in val:
                    return False
                if op == "$ne" and v == val:
                    return False
                if op == "$lte" and not (v is not None and v <= val):
                    return False
                if op == "$gt" and not (v is not None and v > val):
                    return False
        else:
            if _get(d, k) != cond:
                return False
    return True


def _get(d, dotted):
    cur = d
    for p in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur


class _Db:
    def __init__(self, docs):
        self._coll = _Coll(docs)

    def __getitem__(self, name):
        assert name == "f24_unificato", f"widget deve leggere solo f24_unificato, non {name}"
        return self._coll


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


LIMITE = "2026-08-12"  # oggi + 30gg


def test_conta_f24_manuale_ed_email_senza_doppioni():
    docs = [
        # F24 manuale (schema canonico scadenza/status) da pagare
        {"id": "M1", "scadenza": "2026-07-16", "status": "da_pagare"},
        # F24 email (stesso schema) da pagare
        {"id": "E1", "scadenza": "2026-08-01", "status": "da_pagare"},
        # F24 legacy (data_scadenza/pagato) da pagare
        {"id": "L1", "data_scadenza": "2026-07-20", "pagato": False},
        # F24 già pagato -> NON contato (status)
        {"id": "P1", "scadenza": "2026-07-10", "status": "pagato"},
        # F24 già pagato -> NON contato (flag legacy)
        {"id": "P2", "data_scadenza": "2026-07-10", "pagato": True},
        # F24 fuori finestra 30gg -> NON contato
        {"id": "F1", "scadenza": "2026-12-31", "status": "da_pagare"},
        # F24 scadenza vuota -> NON contato (niente falsi positivi da "")
        {"id": "V1", "scadenza": "", "status": "da_pagare"},
    ]
    n = _run(conta_f24_da_pagare(_Db(docs), LIMITE))
    assert n == 3, f"attesi 3 F24 da pagare (M1,E1,L1), ottenuti {n}"


def test_nessun_doppio_conteggio_documento_con_entrambi_gli_schemi():
    # Un documento che ha SIA scadenza SIA data_scadenza va contato UNA volta.
    docs = [{"id": "D1", "scadenza": "2026-07-16", "data_scadenza": "2026-07-16",
             "status": "da_pagare", "pagato": False}]
    n = _run(conta_f24_da_pagare(_Db(docs), LIMITE))
    assert n == 1, f"il documento con entrambi gli schemi va contato una sola volta, ottenuti {n}"
