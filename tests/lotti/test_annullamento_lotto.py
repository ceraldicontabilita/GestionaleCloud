"""L'annullamento di un lotto conserva la tracciabilità ed è reversibile."""

import asyncio
from datetime import date, timedelta

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

from app.lotti.routers import lotti
from app.lotti.servizi import annullamento_lotto_service as rettifiche
from app.lotti.servizi import movimenti_lotto_service as movimenti


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def archivio(monkeypatch):
    db = AsyncMongoMockClient()["rettifica_lotti_test"]
    monkeypatch.setattr(rettifiche, "db", db)
    monkeypatch.setattr(movimenti, "db", db)
    monkeypatch.setattr(lotti, "db", db)
    import app.lotti.eventi as eventi
    async def pubblica(*args, **kwargs):
        return None
    monkeypatch.setattr(eventi, "publish", pubblica)
    return db


ACTOR = {"id": "dipendente-admin-1", "nome": "Amministratore"}


def test_annulla_e_ripristina_preservano_lotto_e_movimenti(archivio):
    run(archivio.lotti.insert_one({
        "id": "lotto-1", "numero_lotto": "BISC-001", "prodotto": "Biscotti",
        "quantita": 4, "data_scadenza": (date.today() + timedelta(days=2)).isoformat(),
    }))
    assert run(rettifiche.annulla_lotto("lotto-1", "Produzione registrata per errore", ACTOR))["stato"] == "annullato"
    assert run(rettifiche.annulla_lotto("lotto-1", "Produzione registrata per errore", ACTOR))["stato"] == "annullato"
    salvato = run(archivio.lotti.find_one({"id": "lotto-1"}))
    assert salvato["quantita"] == 0 and salvato["quantita_pre_annullamento"] == 4
    assert salvato["annullato_da_id"] == ACTOR["id"]
    assert run(archivio.movimenti_lotto.count_documents({"tipo_evento": "annullamento"})) == 1
    assert run(lotti.cosa_usare_oggi(limit=200))["totale"] == 0

    assert run(rettifiche.ripristina_lotto("lotto-1", "Registrazione corretta", ACTOR))["stato"] == "attivo"
    assert run(rettifiche.ripristina_lotto("lotto-1", "Registrazione corretta", ACTOR))["stato"] == "attivo"
    salvato = run(archivio.lotti.find_one({"id": "lotto-1"}))
    assert salvato["quantita"] == 4 and salvato["esaurito"] is False
    assert run(archivio.movimenti_lotto.count_documents({"tipo_evento": "ripristino"})) == 1
    assert run(lotti.cosa_usare_oggi(limit=200))["totale"] == 1


def test_lotto_gia_inviato_al_banco_non_si_annulla(archivio):
    run(archivio.lotti.insert_one({"id": "lotto-usato", "prodotto": "Babà", "quantita": 2}))
    run(archivio.vendite_banco.insert_one({"lotto_id": "lotto-usato", "pezzi_prodotti": 1}))
    with pytest.raises(HTTPException) as errore:
        run(rettifiche.annulla_lotto("lotto-usato", "Non serviva la produzione", ACTOR))
    assert errore.value.status_code == 409
    assert run(archivio.lotti.find_one({"id": "lotto-usato"}))["quantita"] == 2


def test_lotto_componente_di_altra_produzione_non_si_annulla(archivio):
    run(archivio.lotti.insert_many([
        {"id": "base", "numero_lotto": "BASE-001", "prodotto": "Base", "quantita": 2},
        {"id": "finale", "prodotto": "Prodotto finale", "quantita": 1,
         "lotti_componenti": [{"numero_lotto": "BASE-001"}]},
    ]))
    with pytest.raises(HTTPException) as errore:
        run(rettifiche.annulla_lotto("base", "Produzione da correggere", ACTOR))
    assert errore.value.status_code == 409
    assert run(archivio.lotti.find_one({"id": "base"}))["quantita"] == 2


def test_router_non_espone_piu_delete_lotto():
    assert not any(r.path == "/lotti/{lotto_id}" and "DELETE" in r.methods for r in lotti.router.routes)
    assert any(r.path == "/lotti/{lotto_id}/annulla" and "POST" in r.methods for r in lotti.router.routes)
