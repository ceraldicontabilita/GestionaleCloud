"""POS reale manuale: fonte operativa separata dall'elettronico XML."""
import asyncio
import pytest
from fastapi import HTTPException

from app.services.scritture_contabili import (
    chiusura_pos_del_giorno,
    registra_chiusura_pos_reale,
)
from app.routers import pos_corrispettivi_check as pos_router


def _valore(doc, chiave):
    valore = doc
    for parte in chiave.split("."):
        if not isinstance(valore, dict):
            return None
        valore = valore.get(parte)
    return valore


def _match(doc, query):
    for chiave, atteso in (query or {}).items():
        if chiave == "$or":
            if not any(_match(doc, q) for q in atteso):
                return False
            continue
        reale = _valore(doc, chiave)
        if isinstance(atteso, dict):
            if "$in" in atteso and reale not in atteso["$in"]:
                return False
            if "$nin" in atteso and reale in atteso["$nin"]:
                return False
            if "$ne" in atteso and reale == atteso["$ne"]:
                return False
        elif reale != atteso:
            return False
    return True


def _set(doc, chiave, valore):
    parti = chiave.split(".")
    target = doc
    for parte in parti[:-1]:
        target = target.setdefault(parte, {})
    target[parti[-1]] = valore


class _Result:
    def __init__(self, matched=0):
        self.matched_count = matched


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, n=None):
        return [dict(d) for d in (self.docs[:n] if n else self.docs)]


class _Collection:
    def __init__(self, docs=None):
        self.docs = [dict(d) for d in (docs or [])]

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _match(doc, query):
                return dict(doc)
        return None

    def find(self, query=None, projection=None):
        return _Cursor([d for d in self.docs if _match(d, query or {})])

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if _match(doc, query):
                for chiave, valore in update.get("$set", {}).items():
                    _set(doc, chiave, valore)
                return _Result(1)
        if upsert:
            nuovo = {k: v for k, v in query.items() if not k.startswith("$")}
            for chiave, valore in update.get("$setOnInsert", {}).items():
                _set(nuovo, chiave, valore)
            for chiave, valore in update.get("$set", {}).items():
                _set(nuovo, chiave, valore)
            self.docs.append(nuovo)
            return _Result(1)
        return _Result(0)

    async def find_one_and_update(self, query, update, upsert=False):
        for doc in self.docs:
            if _match(doc, query):
                precedente = dict(doc)
                for chiave, valore in update.get("$set", {}).items():
                    _set(doc, chiave, valore)
                return precedente
        if upsert:
            nuovo = {k: v for k, v in query.items() if not k.startswith("$")}
            for chiave, valore in update.get("$setOnInsert", {}).items():
                _set(nuovo, chiave, valore)
            for chiave, valore in update.get("$set", {}).items():
                _set(nuovo, chiave, valore)
            self.docs.append(nuovo)
        return None


class _Db(dict):
    def __getitem__(self, nome):
        return self.setdefault(nome, _Collection())


def _run(coro):
    return asyncio.run(coro)


def _db_esistente():
    db = _Db()
    db["corrispettivi"].docs = [{
        "id": "corr-1", "data": "2026-07-05", "totale": 1200.0,
        "pagato_elettronico": 1152.70,
    }]
    db["prima_nota_cassa"].docs = [
        {
            "id": "cassa-entrata", "data": "2026-07-05", "tipo": "entrata",
            "categoria": "Corrispettivi", "importo": 1200.0,
            "pagato_elettronico": 1152.70, "pagato_contanti": 47.30,
            "dettaglio": {"elettronico": 1152.70, "contanti": 47.30},
        },
        {
            "id": "cassa-pos", "data": "2026-07-05", "tipo": "uscita",
            "categoria": "POS Verso Banca", "importo": 1152.70,
            "source": "corrispettivo_import", "trasferimento_id": "tr-1",
            "quota_pos_fonte": "xml",
        },
    ]
    db["prima_nota_banca"].docs = [{
        "id": "banca-pos", "data": "2026-07-05", "tipo": "entrata",
        "categoria": "Corrispettivi POS", "importo": 1152.70,
        "source": "trasferimento_pos", "trasferimento_id": "tr-1",
        "quota_pos_fonte": "xml", "accreditato_ec": 1098.40,
        "riconciliato": True,
    }]
    return db


def test_pos_manuale_sostituisce_xml_solo_in_prima_nota():
    db = _db_esistente()
    esito = _run(registra_chiusura_pos_reale(db, "2026-07-05", 1000.0))

    assert esito["action"] == "created"
    assert db["chiusure_pos_manuali"].docs[0]["importo"] == 1000.0
    corr = db["corrispettivi"].docs[0]
    assert corr["pagato_elettronico"] == 1152.70  # XML intatto
    assert corr["pos_reale_serale"] == 1000.0

    entrata, uscita = db["prima_nota_cassa"].docs
    assert entrata["importo"] == 1200.0
    assert entrata["pagato_elettronico"] == 1000.0
    assert entrata["pagato_contanti"] == 200.0
    assert entrata["dettaglio"]["elettronico"] == 1000.0
    assert uscita["importo"] == 1000.0
    assert uscita["quota_pos_fonte"] == "chiusura_manuale"

    banca = db["prima_nota_banca"].docs[0]
    assert banca["importo"] == 1000.0
    assert banca["source"] == "trasferimento_pos"
    assert banca["quota_pos_fonte"] == "chiusura_manuale"
    assert banca["riconciliato"] is False  # accredito 1098,40 non quadra


def test_salvataggio_esatto_riconcilia_e_non_duplica():
    db = _db_esistente()
    _run(registra_chiusura_pos_reale(db, "2026-07-05", 1098.40))
    esito2 = _run(registra_chiusura_pos_reale(db, "2026-07-05", 1098.40))

    assert esito2["action"] == "noop"
    assert len(db["chiusure_pos_manuali"].docs) == 1
    assert len(db["prima_nota_cassa"].docs) == 2
    assert len(db["prima_nota_banca"].docs) == 1
    assert db["prima_nota_banca"].docs[0]["riconciliato"] is True


def test_crea_trasferimento_speculare_se_manca():
    db = _Db()
    db["corrispettivi"].docs = [{
        "id": "corr-2", "data": "2026-07-08", "totale": 1500.0,
        "pagato_elettronico": 1000.0,
    }]

    _run(registra_chiusura_pos_reale(db, "2026-07-08", 875.50))

    uscita = db["prima_nota_cassa"].docs[0]
    banca = db["prima_nota_banca"].docs[0]
    assert uscita["tipo"] == "uscita" and uscita["importo"] == 875.50
    assert banca["tipo"] == "entrata" and banca["importo"] == 875.50
    assert uscita["trasferimento_id"] == banca["trasferimento_id"]
    assert banca["riconciliato"] is False


def test_zero_manualizzato_non_riprende_il_valore_xml():
    db = _db_esistente()
    _run(registra_chiusura_pos_reale(db, "2026-07-05", 0))

    assert _run(chiusura_pos_del_giorno(db, "2026-07-05")) == 0.0
    assert db["corrispettivi"].docs[0]["pagato_elettronico"] == 1152.70
    assert db["prima_nota_cassa"].docs[1]["status"] == "deleted"
    assert db["prima_nota_banca"].docs[0]["status"] == "deleted"


def test_importazione_batch_salva_tutte_le_giornate(monkeypatch):
    db = _Db()
    db["corrispettivi"].docs = [
        {"id": "corr-1", "data": "2026-07-01", "totale": 2000.0,
         "pagato_elettronico": 1700.0},
        {"id": "corr-2", "data": "2026-07-02", "totale": 2100.0,
         "pagato_elettronico": 1800.0},
    ]
    monkeypatch.setattr(pos_router.Database, "get_db", staticmethod(lambda: db))

    esito = _run(pos_router.upsert_chiusure_giornaliere_batch(
        payload={
            "righe": [
                {"data": "2026-07-01", "importo": 1685.80},
                {"data": "2026-07-02", "importo": 1666.90},
            ],
            "note": "solo acquisti approvati",
        },
        current_user={"sub": "tester"},
    ))

    assert esito["success"] is True
    assert esito["salvati"] == 2
    assert esito["errori"] == 0
    assert esito["totale"] == 3352.70
    assert len(db["chiusure_pos_manuali"].docs) == 2
    assert len(db["prima_nota_cassa"].docs) == 2
    assert len(db["prima_nota_banca"].docs) == 2


def test_importazione_batch_rifiuta_date_duplicate_prima_di_scrivere(monkeypatch):
    db = _Db()
    monkeypatch.setattr(pos_router.Database, "get_db", staticmethod(lambda: db))

    with pytest.raises(HTTPException) as exc:
        _run(pos_router.upsert_chiusure_giornaliere_batch(
            payload={"righe": [
                {"data": "2026-07-01", "importo": 10},
                {"data": "2026-07-01", "importo": 20},
            ]},
            current_user={"sub": "tester"},
        ))

    assert exc.value.status_code == 400
    assert "Data duplicata" in exc.value.detail
    assert db["chiusure_pos_manuali"].docs == []
