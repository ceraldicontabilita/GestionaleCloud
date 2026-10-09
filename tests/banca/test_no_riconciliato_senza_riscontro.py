"""Caso Leasys (utente, 19/07/2026): una fattura non pagata risultava in
Prima Nota Banca come se fosse riconciliata. Causa trovata:
aggiorna_metodi_pagamento_da_fornitori marcava fattura.riconciliato=True
SOLO perché il fornitore ha metodo "banca" in anagrafica, senza nessun
riscontro con un movimento bancario reale. Test-guardia: la funzione non
deve più scrivere il campo 'riconciliato' in nessuna circostanza — il
metodo di pagamento non è mai prova di un pagamento avvenuto."""
import asyncio

from app.routers.fatture_module.pagamento import aggiorna_metodi_pagamento_da_fornitori


class _FatturaCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, n):
        return self._docs


class _FatturaColl:
    def __init__(self, docs):
        self._docs = docs
        self.updates = []

    def find(self, query, proj):
        return _FatturaCursor(self._docs)

    async def update_one(self, filtro, update):
        self.updates.append((filtro, update))


class _FornitoreColl:
    def __init__(self, docs):
        self._docs = docs

    def find(self, query, proj):
        async def _gen():
            for d in self._docs:
                yield d
        return _gen()


class _Db(dict):
    pass


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def test_non_marca_piu_riconciliato_per_metodo_banca(monkeypatch):
    fatture = _FatturaColl([
        {"id": "F-LEASYS", "fornitore_partita_iva": "IT999", "supplier_vat": None, "fornitore_piva": None},
    ])
    fornitori = _FornitoreColl([
        {"partita_iva": "IT999", "piva": "IT999", "metodo_pagamento": "banca"},
    ])
    db = _Db({"invoices": fatture, "fornitori": fornitori})

    from app.database import Database
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))

    esito = _run(aggiorna_metodi_pagamento_da_fornitori())

    assert esito["fatture_aggiornate"] == 1
    assert esito["fatture_riconciliate_auto"] == 0
    assert len(fatture.updates) == 1
    _, update = fatture.updates[0]
    campi = update["$set"]
    assert campi["metodo_pagamento"] == "banca"
    assert "riconciliato" not in campi, (
        "aggiorna_metodi_pagamento_da_fornitori non deve marcare 'riconciliato' "
        "solo per il metodo di pagamento del fornitore: nessun riscontro reale."
    )
