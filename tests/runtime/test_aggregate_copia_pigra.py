"""`aggregate` dell'archivio in memoria non copia la collezione prima di filtrare.

Caso reale 07/10/2026: la campana degli alert aggregava 18.084 documenti
copiandoli tutti due volte a ogni apertura di pagina: centinaia di MB di
copie, event loop fermo 2-5 s, picco a 1,8 GB e OOM del servizio (2 GB).
"""
import asyncio

from app.services import archivio_documenti_memoria as adm
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def _run(coro):
    return asyncio.run(coro)


def _collezione(n=1000):
    db = ClientArchivioMemoria()["copia_pigra"]
    coll = db["alerts"]
    coll._documents = [
        {"_id": f"a{i}", "id": f"a{i}", "stato": "aperto" if i % 100 == 0 else "risolto",
         "severita": "critical" if i % 200 == 0 else "warning", "extra": {"n": i}}
        for i in range(n)
    ]
    return coll


def _conta_copie(monkeypatch):
    chiamate = {"n": 0}
    originale = adm._clone

    def contata(valore):
        chiamate["n"] += 1
        return originale(valore)

    monkeypatch.setattr(adm, "_clone", contata)
    return chiamate


def test_match_e_group_non_copiano_la_collezione(monkeypatch):
    coll = _collezione()
    copie = _conta_copie(monkeypatch)
    righe = _run(coll.aggregate([
        {"$match": {"stato": "aperto"}},
        {"$group": {"_id": "$severita", "count": {"$sum": 1}}},
    ]).to_list(None))
    assert sorted((r["_id"], r["count"]) for r in righe) == [("critical", 5), ("warning", 5)]
    # Copiati solo gli id dei gruppi e le due righe in uscita, non i 1.000 documenti.
    assert copie["n"] < 20


def test_unset_dopo_il_match_copia_solo_i_sopravvissuti_e_non_tocca_gli_originali(monkeypatch):
    coll = _collezione()
    copie = _conta_copie(monkeypatch)
    righe = _run(coll.aggregate([{"$match": {"stato": "aperto"}}, {"$unset": "extra"}]).to_list(None))
    assert len(righe) == 10 and all("extra" not in r for r in righe)
    assert all("extra" in d for d in coll._documents), "gli originali restano interi"
    assert copie["n"] < 50, "copie dei 10 sopravvissuti (prima di scrivere e in uscita), non dei 1.000"


def test_group_poi_unset_non_scrive_dentro_gli_originali():
    coll = _collezione(50)
    righe = _run(coll.aggregate([
        {"$group": {"_id": "$stato", "primo": {"$first": "$extra"}}},
        {"$unset": "primo.n"},
    ]).to_list(None))
    assert all(r["primo"] == {} for r in righe)
    assert all(d["extra"] == {"n": int(d["id"][1:])} for d in coll._documents)


def test_sort_project_e_limit_danno_lo_stesso_risultato_di_prima():
    coll = _collezione(30)
    righe = _run(coll.aggregate([
        {"$match": {"stato": "aperto"}},
        {"$sort": {"id": -1}},
        {"$project": {"_id": 0, "id": 1}},
        {"$limit": 1},
    ]).to_list(None))
    assert righe == [{"id": "a0"}] or righe == [{"id": "a0"}]  # un solo aperto fra 30: a0
