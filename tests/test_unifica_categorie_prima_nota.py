"""Unificazione categorie Prima Nota (richiesta utente 17/07/2026, screenshot
del filtro con 8 nomi diversi per 3 concetti): "Fatture" per i pagamenti
fatture fornitori (prima anche Pagamento fornitore/Fornitori/fornitori),
"Versamento Banca" per i contanti cassa→banca (prima anche Versamento e
trasferimento_interno lato banca), "Prelevamento Banca" per i contanti
banca→cassa (prima Prelievo/trasferimento_interno lato cassa)."""
import asyncio

from app.routers.prima_nota_module import manutenzione as mod


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def _match(doc, query):
    for k, v in query.items():
        if isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]:
                return False
        elif doc.get(k) != v:
            return False
    return True


class _Result:
    def __init__(self, n):
        self.modified_count = n


class _Coll:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def count_documents(self, query):
        return sum(1 for d in self.docs if _match(d, query))

    async def update_many(self, query, update):
        n = 0
        for d in self.docs:
            if _match(d, query):
                d.update(update.get("$set", {}))
                n += 1
        return _Result(n)


class _Db:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _Coll())


def _db_esempio():
    db = _Db()
    db["prima_nota_cassa"].docs = [
        {"id": "1", "categoria": "Pagamento fornitore", "tipo": "uscita"},
        {"id": "2", "categoria": "fornitori", "tipo": "uscita"},
        {"id": "3", "categoria": "Versamento", "tipo": "uscita"},
        {"id": "4", "categoria": "trasferimento_interno", "tipo": "entrata"},
        {"id": "5", "categoria": "Corrispettivi", "tipo": "entrata"},
    ]
    db["prima_nota_banca"].docs = [
        {"id": "6", "categoria": "Fornitori", "tipo": "uscita"},
        {"id": "7", "categoria": "Versamento", "tipo": "entrata"},
        {"id": "8", "categoria": "Fatture", "tipo": "uscita"},
    ]
    return db


def test_dry_run_conta_senza_toccare(monkeypatch):
    db = _db_esempio()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    res = _run(mod.unifica_categorie(dry_run=True))

    assert res["dry_run"] is True
    assert res["totale_movimenti"] == 6
    assert db["prima_nota_cassa"].docs[0]["categoria"] == "Pagamento fornitore"


def test_rinomina_ai_nomi_canonici(monkeypatch):
    db = _db_esempio()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    res = _run(mod.unifica_categorie(dry_run=False))

    assert res["totale_movimenti"] == 6
    cassa = {d["id"]: d["categoria"] for d in db["prima_nota_cassa"].docs}
    banca = {d["id"]: d["categoria"] for d in db["prima_nota_banca"].docs}
    assert cassa["1"] == "Fatture"
    assert cassa["2"] == "Fatture"
    assert cassa["3"] == "Versamento Banca"
    assert cassa["4"] == "Prelevamento Banca"   # prelievo banca→cassa
    assert cassa["5"] == "Corrispettivi"        # non toccata
    assert banca["6"] == "Fatture"
    assert banca["7"] == "Versamento Banca"
    assert banca["8"] == "Fatture"              # già canonica

    # idempotente: rieseguire non cambia più nulla
    res2 = _run(mod.unifica_categorie(dry_run=False))
    assert res2["totale_movimenti"] == 0
