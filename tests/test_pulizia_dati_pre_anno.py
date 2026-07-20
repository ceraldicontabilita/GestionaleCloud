"""Regola utente 16/07/2026: in contabilità restano SOLO i dati dall'anno
operativo (2026) in poi — i movimenti/fatture di anni vecchi (2021-2022,
residui di backfill) falsavano riporti e saldi. Il dry_run (default) conta
senza eliminare; un documento senza data riconoscibile non si tocca mai."""
import asyncio

from app.routers.prima_nota_module import manutenzione as mod


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, n=None):
        return list(self._docs[:n] if n else self._docs)


class _Coll:
    def __init__(self, docs=None):
        self.docs = docs or []

    def find(self, query=None, projection=None, *a, **k):
        return _Cursor([dict(d) for d in self.docs])

    async def delete_many(self, query, *a, **k):
        ids = set(query["id"]["$in"])
        before = len(self.docs)
        self.docs = [d for d in self.docs if d.get("id") not in ids]

        class _R:
            deleted_count = before - len(self.docs)
        return _R()


class _Db:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _Coll())


def _setup(monkeypatch):
    db = _Db()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    db["prima_nota_banca"].docs = [
        {"id": "b21", "data": "2021-05-01", "importo": 100.0},
        {"id": "b22", "data": "2022-12-28", "importo": 50.0},
        {"id": "b26", "data": "2026-01-02", "importo": 70.0},
        {"id": "bND"},  # senza data: mai eliminato
    ]
    db["invoices"].docs = [
        {"id": "f22", "invoice_date": "2022-11-30"},
        {"id": "f26", "invoice_date": "2026-03-01"},
    ]
    db["estratto_conto_movimenti"].docs = [
        {"id": "e21", "data_contabile": "31/12/2021"},  # data italiana
        {"id": "e26", "data_contabile": "2026-02-01"},
    ]
    return db


def test_dry_run_conta_senza_eliminare(monkeypatch):
    db = _setup(monkeypatch)

    esito = _run(mod.pulizia_dati_pre_anno(anno_da_mantenere=2026, dry_run=True, crea_backup=False, _admin={}))

    assert esito["dry_run"] is True
    assert esito["collections"]["prima_nota_banca"]["trovati_pre_anno"] == 2
    assert esito["collections"]["prima_nota_banca"]["per_anno"] == {"2021": 1, "2022": 1}
    assert esito["collections"]["invoices"]["trovati_pre_anno"] == 1
    assert esito["collections"]["estratto_conto_movimenti"]["trovati_pre_anno"] == 1  # data GG/MM/AAAA riconosciuta
    assert esito["totale_eliminati"] == 0
    assert len(db["prima_nota_banca"].docs) == 4  # niente toccato


def test_esecuzione_elimina_solo_pre_anno(monkeypatch):
    db = _setup(monkeypatch)

    esito = _run(mod.pulizia_dati_pre_anno(anno_da_mantenere=2026, dry_run=False, crea_backup=False, _admin={}))

    assert esito["totale_eliminati"] == 4  # b21 b22 f22 e21
    ids_banca = {d.get("id") for d in db["prima_nota_banca"].docs}
    assert ids_banca == {"b26", "bND"}  # il 2026 resta, il senza-data resta
    assert {d["id"] for d in db["invoices"].docs} == {"f26"}
    assert {d["id"] for d in db["estratto_conto_movimenti"].docs} == {"e26"}


def test_preserva_cedolini_salario_e_bonifici_collegati(monkeypatch):
    db = _Db()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    db["cedolini"].docs = [{"id": "ced-2024", "anno": 2024}]
    db["prima_nota_salari"].docs = [{
        "id": "sal-2024", "anno": 2024, "data": "2024-05-01",
        "cedolino_id": "ced-2024", "movimenti_bancari_ids": ["ec-stip-2024"],
    }]
    db["estratto_conto_movimenti"].docs = [
        {"id": "ec-stip-2024", "data": "2024-05-27", "tipo": "uscita"},
        {"id": "ec-altro-2024", "data": "2024-05-28", "tipo": "uscita"},
    ]
    db["prima_nota_banca"].docs = [
        {"id": "pn-stip-2023", "data": "2023-06-27", "categoria": "Stipendi"},
        {"id": "pn-altro-2023", "data": "2023-06-28", "categoria": "Fatture"},
    ]

    esito = _run(mod.pulizia_dati_pre_anno(
        anno_da_mantenere=2026, dry_run=False, crea_backup=False, _admin={}
    ))

    assert {d["id"] for d in db["cedolini"].docs} == {"ced-2024"}
    assert {d["id"] for d in db["prima_nota_salari"].docs} == {"sal-2024"}
    assert {d["id"] for d in db["estratto_conto_movimenti"].docs} == {"ec-stip-2024"}
    assert {d["id"] for d in db["prima_nota_banca"].docs} == {"pn-stip-2023"}
    assert esito["cedolini_preservati"] is True
    assert esito["prima_nota_salari_preservata"] is True
    assert esito["collections"]["estratto_conto_movimenti"]["preservati_cedolini_bonifici"] == 1
