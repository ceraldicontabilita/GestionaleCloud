"""Lo storico produzione non cancella lotti né restituisce scorte senza prova."""

import asyncio

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

from app.lotti.routers import produzioni
from app.lotti.servizi import annullamento_lotto_service as lotti_service
from app.lotti.servizi import annullamento_produzione_service as service
from app.lotti.servizi import movimenti_lotto_service as movimenti


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def archivio(monkeypatch):
    db = AsyncMongoMockClient()["annullamento_produzione_test"]
    for modulo in (service, lotti_service, movimenti, produzioni):
        monkeypatch.setattr(modulo, "db", db)
    import app.lotti.eventi as eventi
    async def pubblica(*args, **kwargs):
        return None
    monkeypatch.setattr(eventi, "publish", pubblica)
    return db


ACTOR = {"id": "dipendente-1", "nome": "Amministratore"}


def test_annullamento_conserva_registrazione_lotto_e_scorte(archivio):
    run(archivio.produzioni.insert_one({"id": "prod-1", "numero_lotto": "TEST-001", "pezzi": 5}))
    run(archivio.lotti.insert_one({"id": "lotto-1", "numero_lotto": "TEST-001", "quantita": 5}))
    run(archivio.lotti_fornitori.insert_one({"id": "materia-1", "quantita_disponibile": 12}))

    assert run(service.annulla_produzione("prod-1", "Produzione errata", ACTOR))["stato"] == "annullata"
    assert run(service.annulla_produzione("prod-1", "Produzione errata", ACTOR))["stato"] == "annullata"
    produzione = run(archivio.produzioni.find_one({"id": "prod-1"}))
    lotto = run(archivio.lotti.find_one({"id": "lotto-1"}))
    assert produzione["annullata_da_id"] == ACTOR["id"]
    assert produzione["motivo_annullamento"] == "Produzione errata"
    assert lotto["stato"] == "annullato" and lotto["quantita_pre_annullamento"] == 5
    assert run(archivio.lotti_fornitori.find_one({"id": "materia-1"}))["quantita_disponibile"] == 12
    assert run(archivio.movimenti_lotto.count_documents({"tipo_evento": "annullamento"})) == 1


def test_produzione_con_lotto_usato_non_si_annulla(archivio):
    run(archivio.produzioni.insert_one({"id": "prod-2", "numero_lotto": "TEST-002"}))
    run(archivio.lotti.insert_one({"id": "lotto-2", "numero_lotto": "TEST-002", "quantita": 2}))
    run(archivio.vendite_banco.insert_one({"lotto_id": "lotto-2", "pezzi_prodotti": 1}))
    with pytest.raises(HTTPException) as errore:
        run(service.annulla_produzione("prod-2", "Produzione errata", ACTOR))
    assert errore.value.status_code == 409
    assert run(archivio.produzioni.find_one({"id": "prod-2"})).get("stato") != "annullata"


def test_produzione_senza_lotto_verificabile_non_si_annulla(archivio):
    run(archivio.produzioni.insert_one({"id": "prod-3", "ricetta_nome": "Crema"}))
    with pytest.raises(HTTPException) as errore:
        run(service.annulla_produzione("prod-3", "Produzione errata", ACTOR))
    assert errore.value.status_code == 409


def test_router_non_espone_piu_cancellazione_fisica():
    assert not any(r.path == "/produzioni/{produzione_id}" and "DELETE" in r.methods for r in produzioni.router.routes)
    assert any(r.path == "/produzioni/{produzione_id}/annulla" and "POST" in r.methods for r in produzioni.router.routes)
