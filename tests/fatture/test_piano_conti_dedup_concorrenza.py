"""Regressioni sul Piano dei Conti.

Storia: il frontend caricava elenco e bilancio in parallelo e, con la
collezione ``piano_conti`` vuota, entrambi gli endpoint la inizializzavano
producendo due copie per codice (saldi sommati due volte). Dall'audit del
commercialista 03/09/2026 (PR 7) la collezione e' DISMESSA: il piano e' il
CEE ufficiale in codice, nessun endpoint scrive piu' conti, quindi la
concorrenza non puo' produrre copie e ogni codice compare una sola volta.
"""

import asyncio
from copy import deepcopy

import pytest
from fastapi import HTTPException

import app.routers.accounting.piano_conti as pc
import app.routers.accounting.contabilita_avanzata as ca
from app.services.mapping_piano_conti import CODICI_PIANO


class _Cursor:
    def __init__(self, docs, projection=None):
        self._docs = [deepcopy(doc) for doc in docs]
        self._projection = projection or {}

    def sort(self, key, direction):
        self._docs.sort(key=lambda doc: doc.get(key, ""), reverse=direction < 0)
        return self

    async def to_list(self, length):
        docs = self._docs[:length]
        if self._projection.get("_id") == 0:
            for doc in docs:
                doc.pop("_id", None)
        return docs


class _Collection:
    def __init__(self, docs=None):
        self.docs = [deepcopy(doc) for doc in (docs or [])]
        self.scritture = 0

    def find(self, query=None, projection=None):
        return _Cursor(self.docs, projection)

    async def insert_many(self, docs):
        self.scritture += 1
        raise AssertionError("la collezione piano_conti e' dismessa: nessuna scrittura")

    async def insert_one(self, doc):
        self.scritture += 1
        raise AssertionError("la collezione piano_conti e' dismessa: nessuna scrittura")

    async def update_one(self, query, update, upsert=False):
        self.scritture += 1
        raise AssertionError("la collezione piano_conti e' dismessa: nessuna scrittura")


class _Db:
    def __init__(self, conti=None):
        self.collection = _Collection(conti)

    def __getitem__(self, name):
        assert name == "piano_conti"
        return self.collection


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _conto(codice, nome, categoria):
    return {
        "id": f"id-{codice}-{nome}",
        "codice": codice,
        "nome": nome,
        "categoria": categoria,
        "natura": "finanziario",
        "attivo": True,
        "created_at": "2026-08-04T13:41:54+00:00",
    }


def test_get_piano_conti_restituisce_un_solo_record_per_codice(monkeypatch):
    conti = [
        _conto("01.01.01", "Cassa", "attivo"),
        _conto("01.01.01", "Cassa", "attivo"),
        _conto("04.01.01", "Ricavi", "ricavi"),
        _conto("04.01.01", "Ricavi", "ricavi"),
    ]
    db = _Db(conti)
    monkeypatch.setattr(pc.Database, "get_db", staticmethod(lambda: db))

    async def _saldi(_db, anno=None):
        return {"01.01.01": 100.0, "04.01.01": 50.0}

    monkeypatch.setattr(pc, "_calcola_saldi_piano_conti", _saldi)

    result = _run(pc.get_piano_conti(anno="2026"))

    codici = [row["codice"] for row in result["conti"]]
    assert len(codici) == len(set(codici)) == len(CODICI_PIANO)
    assert result["totale"] == len(CODICI_PIANO)
    per_codice = {row["codice"]: row for row in result["conti"]}
    assert per_codice["19.03.03"]["saldo"] == 100.0      # 01.01.01 Cassa → Cassa contanti
    assert per_codice["47.01.03"]["saldo"] == 50.0       # 04.01.01 Ricavi → Vendita merci
    assert sum(1 for c in result["grouped"]["attivo"] if c["codice"] == "19.03.03") == 1
    assert result["conti_operativi_non_mappati"] == []
    assert db.collection.scritture == 0


def test_bilancio_non_somma_due_volte_un_codice_duplicato(monkeypatch):
    conti = [
        _conto("01.01.01", "Cassa", "attivo"),
        _conto("01.01.01", "Cassa", "attivo"),
        _conto("05.01.01", "Acquisti", "costi"),
        _conto("05.01.01", "Acquisti", "costi"),
    ]
    db = _Db(conti)
    monkeypatch.setattr(pc.Database, "get_db", staticmethod(lambda: db))

    async def _saldi(_db, anno=None):
        return {"01.01.01": 100.0, "05.01.01": 25.0}

    monkeypatch.setattr(pc, "_calcola_saldi_piano_conti", _saldi)

    result = _run(pc.get_bilancio(anno="2026"))

    assert result["stato_patrimoniale"]["attivo"]["totale"] == 100.0
    assert result["conto_economico"]["costi"]["totale"] == 25.0
    attivo = result["stato_patrimoniale"]["attivo"]["conti"]
    assert len({c["codice"] for c in attivo}) == len(attivo)
    assert sum(1 for c in attivo if c["codice"] == "19.03.03") == 1
    assert db.collection.scritture == 0


def test_inizializzazione_concorrente_non_scrive_e_restituisce_il_cee():
    db = _Db()

    async def _inizializza_due_endpoint():
        return await asyncio.gather(
            pc.inizializza_piano_conti_base(db),
            pc.inizializza_piano_conti_base(db),
        )

    primo, secondo = _run(_inizializza_due_endpoint())

    assert db.collection.docs == [] and db.collection.scritture == 0
    assert [c["codice"] for c in primo] == CODICI_PIANO
    assert primo == secondo
    codici_base = {
        conto["codice"]
        for gruppo in pc.STRUTTURA_BASE.values()
        for conto in gruppo["conti_tipici"]
    }
    alias = {a for c in primo for a in c["alias_operativi"]}
    assert codici_base <= alias


def test_creazione_manuale_restituisce_conflitto_e_indica_il_conto_cee(monkeypatch):
    db = _Db()
    monkeypatch.setattr(pc.Database, "get_db", staticmethod(lambda: db))

    with pytest.raises(HTTPException) as exc_info:
        _run(pc.create_conto({
            "codice": " 05.02.03 ",
            "nome": " Spese telefoniche ",
            "categoria": " costi ",
        }))

    assert exc_info.value.status_code == 409
    assert "05.02.03" in exc_info.value.detail and "65" in exc_info.value.detail
    assert db.collection.scritture == 0


def test_inizializzazione_piano_esteso_non_scrive(monkeypatch):
    db = _Db()
    monkeypatch.setattr(ca.Database, "get_db", staticmethod(lambda: db))
    monkeypatch.setattr(ca, "PIANO_CONTI_ESTESO", {
        "05.02.03": {
            "nome": "Spese telefoniche",
            "categoria": "costi",
            "natura": "economico",
        }
    })

    async def _inizializza_due_endpoint():
        return await asyncio.gather(
            ca.inizializza_piano_conti_esteso(),
            ca.inizializza_piano_conti_esteso(),
        )

    risultati = _run(_inizializza_due_endpoint())

    assert db.collection.docs == [] and db.collection.scritture == 0
    assert all(r["conti_aggiunti"] == 0 for r in risultati)
    assert all(r["totale_piano_conti"] == len(CODICI_PIANO) for r in risultati)
    assert all(r["alias_operativi"] == 1 for r in risultati)
