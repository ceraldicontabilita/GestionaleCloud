"""Merge dipendenti duplicati (audit 19/09/2026): il cedolino duplicato
cancellato dal merge non deve lasciare orfano il bonifico che lo referenzia
via `cedolino_id`, e `bonifici.dipendente_id` va migrata come le altre
collezioni collegate al dipendente."""
import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.hr.services import dipendenti_dedupe as dedupe


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def hr(monkeypatch):
    from app.hr.database import Database as DatabaseHR

    db = AsyncMongoMockClient()["hr_test"]
    monkeypatch.setattr(DatabaseHR, "get_db", classmethod(lambda cls: db))
    return db


def test_merge_ripunta_bonifico_sul_cedolino_sopravvissuto_e_migra_bonifici(hr):
    """Due dipendenti con un cedolino ciascuno per lo stesso anno/mese: il
    merge cancella il cedolino del duplicato come ridondante. Un bonifico che
    puntava a quel cedolino (`cedolino_id`) deve ripuntare al cedolino
    sopravvissuto del target, non restare orfano. `bonifici.dipendente_id`
    deve migrare come `estratto_conto_movimenti.dipendente_id`."""
    _run(hr.dipendenti.insert_many([
        {"id": "dip-target", "nome": "Vincenzo", "cognome": "Vespa",
         "nome_completo": "Vespa Vincenzo", "codice_fiscale": "VSPVCN80A01F839X"},
        {"id": "dip-dup", "nome": "Vincenzo", "cognome": "Vespa",
         "nome_completo": "Vespa Vincenzo", "codice_fiscale": ""},
    ]))
    _run(hr.cedolini.insert_many([
        {"id": "ced-target", "dipendente_id": "dip-target", "anno": 2026, "mese": 3,
         "codice_fiscale": "VSPVCN80A01F839X", "netto": 1300.0},
        {"id": "ced-dup", "dipendente_id": "dip-dup", "anno": 2026, "mese": 3,
         "codice_fiscale": "", "netto": 1300.0},
    ]))
    _run(hr.bonifici.insert_many([
        {"id": "bon-1", "dipendente_id": "dip-dup", "cedolino_id": "ced-dup",
         "importo": 1300.0, "data": "2026-03-27"},
        {"id": "bon-2", "dipendente_id": "dip-dup", "cedolino_id": None,
         "importo": 200.0, "data": "2026-03-28"},
    ]))

    esito = _run(dedupe.merge_dipendenti("dip-target", "dip-dup", soft=True))

    assert esito["success"] is True
    stats = esito["stats_migrazione"]
    assert stats["cedolini_skippati_duplicati"] == 1
    assert stats["bonifici_cedolino_ripuntati"] == 1
    assert stats["bonifici_migrati"] == 2

    # Il cedolino duplicato e' sparito, quello del target e' l'unico rimasto.
    assert _run(hr.cedolini.find_one({"id": "ced-dup"})) is None
    ced_target = _run(hr.cedolini.find_one({"id": "ced-target"}, {"_id": 0}))
    assert ced_target is not None

    # Il bonifico che puntava al cedolino cancellato ora punta al superstite:
    # nessun cedolino_id orfano.
    bon1 = _run(hr.bonifici.find_one({"id": "bon-1"}, {"_id": 0}))
    assert bon1["cedolino_id"] == "ced-target"
    assert bon1["dipendente_id"] == "dip-target"

    # Anche il bonifico senza cedolino_id migra il dipendente_id.
    bon2 = _run(hr.bonifici.find_one({"id": "bon-2"}, {"_id": 0}))
    assert bon2["dipendente_id"] == "dip-target"

    # Il duplicato resta soft-merged, non cancellato.
    dup = _run(hr.dipendenti.find_one({"id": "dip-dup"}, {"_id": 0}))
    assert dup["merged_into"] == "dip-target"


def test_merge_migra_estratto_conto_movimenti_dipendente_id(hr):
    """Comportamento gia' esistente, non deve regredire: le righe banca
    seguono lo stesso pattern di `bonifici`."""
    _run(hr.dipendenti.insert_many([
        {"id": "dip-target", "nome": "Luigi", "cognome": "Taiano",
         "nome_completo": "Taiano Luigi", "codice_fiscale": "TNALGU85B02F839Y"},
        {"id": "dip-dup", "nome": "Luigi", "cognome": "Taiano",
         "nome_completo": "Taiano Luigi", "codice_fiscale": ""},
    ]))
    _run(hr.estratto_conto_movimenti.insert_one(
        {"id": "ecm-1", "dipendente_id": "dip-dup", "importo": -900.0, "data": "2026-04-03"}))

    esito = _run(dedupe.merge_dipendenti("dip-target", "dip-dup", soft=True))

    assert esito["stats_migrazione"]["estratto_conto_movimenti_migrati"] == 1
    riga = _run(hr.estratto_conto_movimenti.find_one({"id": "ecm-1"}, {"_id": 0}))
    assert riga["dipendente_id"] == "dip-target"
