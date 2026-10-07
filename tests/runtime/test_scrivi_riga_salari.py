"""Motore stipendi: unico INSERT in prima_nota_salari, mai uno zero inventato."""
import asyncio

import pytest

from app.services.scritture_contabili import (
    ScritturaNonValida, scrivi_riga_salari, scrivi_righe_salari,
)


class _Coll:
    def __init__(self):
        self.docs = []

    async def find_one(self, filtro):
        for d in self.docs:
            if all(d.get(k) == v for k, v in filtro.items()):
                return d
        return None

    async def insert_one(self, doc):
        self.docs.append(doc)

    async def insert_many(self, docs):
        self.docs.extend(docs)


class _Db(dict):
    def __getitem__(self, k):
        return self.setdefault(k, _Coll())


def _riga(**kw):
    base = {"dipendente": "ROSSI MARIO", "anno": 2026, "mese": 3,
            "importo_busta": 1200.0, "source": "test"}
    base.update(kw)
    return base


def run(c):
    return asyncio.run(c)


def test_scrive_e_assegna_id():
    db = _Db()
    r = run(scrivi_riga_salari(db, _riga()))
    assert r["creata"] and r["id"]
    assert db["prima_nota_salari"].docs[0]["id"] == r["id"]


def test_importo_assente_resta_assente():
    db = _Db()
    riga = _riga()
    del riga["importo_busta"]
    run(scrivi_riga_salari(db, riga))
    assert "importo_busta" not in db["prima_nota_salari"].docs[0]


def test_anti_duplicato_non_scrive_il_secondo():
    db = _Db()
    chiave = {"dipendente": "ROSSI MARIO", "mese": 3, "anno": 2026}
    a = run(scrivi_riga_salari(db, _riga(), anti_duplicato=chiave))
    b = run(scrivi_riga_salari(db, _riga(), anti_duplicato=chiave))
    assert a["creata"] and not b["creata"] and a["id"] == b["id"]
    assert len(db["prima_nota_salari"].docs) == 1


@pytest.mark.parametrize("rotto", [
    {"source": None}, {"dipendente": None}, {"anno": None, "mese": None},
])
def test_righe_incomplete_rifiutate(rotto):
    with pytest.raises(ScritturaNonValida):
        run(scrivi_riga_salari(_Db(), _riga(**rotto)))


def test_lotto_scrive_le_valide_e_riporta_le_rifiutate():
    db = _Db()
    esito = run(scrivi_righe_salari(db, [_riga(), _riga(source=None, id="x")]))
    assert esito["scritte"] == 1
    assert esito["rifiutate"][0]["id"] == "x"
    assert len(db["prima_nota_salari"].docs) == 1
