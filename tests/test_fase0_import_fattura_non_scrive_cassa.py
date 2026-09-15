"""Fase 0 (PROMPT_CLAUDE_CODE_FASE_0.md punto 2): l'import di una fattura XML
con fornitore a metodo cassa (o senza metodo) non deve più creare da solo una
riga in prima_nota_cassa né marcare la fattura pagata — resta "da confermare"
finché non interviene una conferma esplicita in Provvisori.
"""
import asyncio

from app.routers.invoices import fatture_upload as mod


def _matches(doc, query):
    for k, v in (query or {}).items():
        if k == "$or":
            if not any(_matches(doc, sub) for sub in v):
                return False
            continue
        if doc.get(k) != v:
            return False
    return True


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if _matches(d, query):
                return dict(d)
        return None

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, *a, **k):
        for d in self.docs:
            if _matches(d, query):
                d.update(update.get("$set", {}))
                break


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


def _fattura(fattura_id="FT-1", piva="12345678901"):
    return {"id": fattura_id, "supplier_vat": piva, "invoice_number": "1/2026"}


def test_fornitore_metodo_cassa_non_scrive_prima_nota_ne_marca_pagata():
    db = _FakeDb()
    db["fornitori"].docs = [{"partita_iva": "12345678901", "metodo_pagamento": "cassa"}]
    db["invoices"].docs = [_fattura()]

    result = _run(mod.auto_registra_prima_nota(db, _fattura(), "cassa"))

    assert db["prima_nota_cassa"].docs == []
    fattura_aggiornata = db["invoices"].docs[0]
    assert fattura_aggiornata.get("pagato") is not True
    assert fattura_aggiornata.get("stato_pagamento") != "pagata"
    assert fattura_aggiornata["stato_finanziario"] == "da_confermare_cassa"
    assert fattura_aggiornata["provvisorio"] is True
    assert result["stato_finanziario"] == "da_confermare_cassa"


def test_fornitore_senza_metodo_non_scrive_prima_nota_ne_marca_pagata():
    db = _FakeDb()
    db["fornitori"].docs = [{"partita_iva": "12345678901"}]  # nessun metodo_pagamento
    db["invoices"].docs = [_fattura()]

    _run(mod.auto_registra_prima_nota(db, _fattura(), ""))

    assert db["prima_nota_cassa"].docs == []
    fattura_aggiornata = db["invoices"].docs[0]
    assert fattura_aggiornata.get("pagato") is not True
    assert fattura_aggiornata.get("stato_pagamento") != "pagata"
    assert fattura_aggiornata["stato_finanziario"] == "da_confermare_cassa"
    assert fattura_aggiornata["decisione_pagamento_richiesta"] is True
