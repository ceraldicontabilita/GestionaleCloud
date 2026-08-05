"""P1 §5.3 — Consolidamento cedolini: chiave naturale (contribuente+anno+mese)
robusta a schemi diversi (campi espliciti o `periodo`), salva_cedolino idempotente.
`buste_paga` NON è toccata (sottosistema vivo)."""
import asyncio

from app.services.cedolini_canonico import chiave_cedolino, salva_cedolino, COLL


class _Coll:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, proj=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                return {k: v for k, v in d.items() if k != "_id"}
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))


class _Db:
    def __init__(self):
        self.c = _Coll()

    def __getitem__(self, name):
        assert name == COLL
        return self.c


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def test_chiave_stabile_tra_schemi():
    valori = {"netto": 1500, "lordo": 2000}
    espliciti = {"codice_fiscale": "RSSMRA80A01H501U", "anno": 2026, "mese": 3, **valori}
    periodo_iso = {"codice_fiscale": "rssmra80a01h501u", "periodo": "2026-03", **valori}
    periodo_slash = {"employee_id": "RSSMRA80A01H501U", "periodo": "03/2026", **valori}
    k = chiave_cedolino(espliciti)
    assert chiave_cedolino(periodo_iso) == k
    assert chiave_cedolino(periodo_slash) == k


def test_chiave_diversa_per_mese_o_persona():
    base = {"codice_fiscale": "CF1", "anno": 2026, "mese": 3}
    assert chiave_cedolino(base) != chiave_cedolino({**base, "mese": 4})
    assert chiave_cedolino(base) != chiave_cedolino({**base, "anno": 2025})
    assert chiave_cedolino(base) != chiave_cedolino({**base, "codice_fiscale": "CF2"})


def test_salva_idempotente():
    db = _Db()
    doc = {"codice_fiscale": "CF1", "anno": 2026, "mese": 3, "netto": 1500}
    id1 = _run(salva_cedolino(db, doc, source="mig"))
    id2 = _run(salva_cedolino(db, dict(doc), source="mig"))
    assert id1 == id2
    assert len(db.c.docs) == 1


def test_stesso_dipendente_mese_ma_importi_diversi_non_viene_perso():
    db = _Db()
    base = {"codice_fiscale": "CF1", "anno": 2026, "mese": 3, "lordo": 2000}
    id1 = _run(salva_cedolino(db, {**base, "netto": 1500}, source="mig"))
    id2 = _run(salva_cedolino(db, {**base, "netto": 900}, source="mig"))
    assert id1 != id2
    assert len(db.c.docs) == 2


def test_tipo_e_hash_documento_separano_identita():
    base = {"codice_fiscale": "CF1", "anno": 2026, "mese": 12, "netto": 1000}
    assert chiave_cedolino({**base, "tipo_cedolino": "mensile"}) != chiave_cedolino(
        {**base, "tipo_cedolino": "tredicesima"}
    )
    assert chiave_cedolino({**base, "file_hash": "a" * 32}) != chiave_cedolino(
        {**base, "file_hash": "b" * 32}
    )


def test_salta_dati_insufficienti():
    db = _Db()
    assert _run(salva_cedolino(db, {"anno": 2026, "mese": 3})) is None  # niente contribuente
    assert _run(salva_cedolino(db, {"codice_fiscale": "CF1"})) is None  # niente periodo
    assert len(db.c.docs) == 0
