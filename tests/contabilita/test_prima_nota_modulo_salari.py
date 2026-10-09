"""Le rotte salari del modulo Prima Nota leggono i campi veri delle righe.

Sommavano ``$importo`` e filtravano ``nome_dipendente``, due campi che le
righe salari non hanno: totali sempre zero e filtro che non trovava nessuno.
Contavano anche le righe eliminate, e l'eliminazione cancellava davvero.
"""
import asyncio

import pytest

from app.database import Database
from app.routers.prima_nota_module import salari
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def _run(awaitable):
    return asyncio.run(awaitable)


@pytest.fixture()
def db(monkeypatch):
    database = ClientArchivioMemoria()["test_modulo_salari"]
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: database))
    _run(database["prima_nota_salari"].insert_many([
        {"id": "s1", "data": "2026-03-27", "anno": 2026, "dipendente": "ROSSI MARIO",
         "dipendente_nome": "Rossi Mario", "importo_busta": 1400.0, "importo_bonifico": 1400.0},
        {"id": "s2", "data": "2026-03-27", "anno": 2026, "dipendente": "BIANCHI LUCA",
         "importo_busta": 1200.0, "importo_bonifico": 1000.0},
        {"id": "s3", "data": "2026-03-27", "anno": 2026, "dipendente": "ROSSI MARIO",
         "importo_busta": 1400.0, "importo_bonifico": 1400.0, "status": "deleted"},
        {"id": "s4", "data": "2026-03-27", "anno": 2026, "dipendente": "ROSSI MARIO",
         "importo_busta": 1400.0, "entity_status": "deleted", "duplicate_of": "s1"},
    ]))
    return database


def _lista(**filtri):
    parametri = {"data_da": None, "data_a": None, "dipendente": None, "anno": None,
                 "skip": 0, "limit": 100, **filtri}
    return _run(salari.get_prima_nota_salari(**parametri))


def test_la_lista_somma_buste_e_bonifici_delle_sole_righe_attive(db):
    esito = _lista(anno=2026)
    assert sorted(m["id"] for m in esito["movimenti"]) == ["s1", "s2"]
    assert esito["totale_buste"] == 2600.0
    assert esito["totale_bonifici"] == 2400.0
    assert esito["count"] == 2


def test_il_filtro_per_dipendente_legge_i_campi_veri(db):
    assert [m["id"] for m in _lista(dipendente="bianchi")["movimenti"]] == ["s2"]
    assert [m["id"] for m in _lista(dipendente="rossi", anno=2026)["movimenti"]] == ["s1"]


def test_le_statistiche_per_dipendente(db):
    esito = _run(salari.get_salari_stats(data_da=None, data_a=None))
    assert esito["totale_buste"] == 2600.0
    assert {d["nome"]: d["totale_buste"] for d in esito["by_dipendente"]} == {
        "Rossi Mario": 1400.0, "BIANCHI LUCA": 1200.0,
    }


def test_l_eliminazione_e_un_soft_delete(db):
    _run(salari.delete_prima_nota_salari("s2"))
    riga = _run(db["prima_nota_salari"].find_one({"id": "s2"}))
    assert riga["status"] == "deleted" and riga["deleted_reason"]
    assert [m["id"] for m in _lista()["movimenti"]] == ["s1"]
    with pytest.raises(Exception):
        _run(salari.delete_prima_nota_salari("s2"))
