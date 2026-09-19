"""Regressioni per la risoluzione tracciata delle anomalie dalla card."""

import asyncio
import os
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "Gestionale_Test")


def run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@pytest.fixture()
def contesto(monkeypatch):
    import app.lotti.routers.anomalie as modulo
    db = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(modulo, "db", db)
    run(db.anomalie.insert_one({
        "id": "anomalia-1",
        "attrezzatura": "Affettatrice principale",
        "stato": "Aperta",
        "azione_correttiva": "",
        "esito_verifica": "",
    }))
    request = SimpleNamespace(state=SimpleNamespace(user={
        "sub": "valerio-id",
        "nome": "Ceraldi Valerio",
        "ruolo": "amministratore",
    }))
    return modulo, db, request


def test_non_si_puo_chiudere_senza_intervento_e_verifica(contesto):
    modulo, _, request = contesto

    with pytest.raises(HTTPException) as exc:
        run(modulo.aggiorna_anomalia(
            "anomalia-1",
            modulo.AggiornaAnomaliaRequest(stato="Risolta"),
            request,
        ))

    assert exc.value.status_code == 400
    assert "azione correttiva" in exc.value.detail
    assert "verifica finale" in exc.value.detail


def test_risoluzione_usa_identita_del_token_e_scrive_evento(contesto):
    modulo, db, request = contesto

    esito = run(modulo.aggiorna_anomalia(
        "anomalia-1",
        modulo.AggiornaAnomaliaRequest(
            stato="Risolta",
            azione_correttiva="Sostituita lama e verificata la protezione",
            esito_verifica="Funzionamento ripristinato e verificato",
            operatore_risoluzione="Nome non autorizzato",
            note="Rapporto tecnico 42",
        ),
        request,
    ))

    assert esito["success"] is True
    doc = run(db.anomalie.find_one({"id": "anomalia-1"}))
    assert doc["stato"] == "Risolta"
    assert doc["operatore_risoluzione"] == "Ceraldi Valerio"
    assert doc["azione_correttiva"] == "Sostituita lama e verificata la protezione"
    assert doc["esito_verifica"] == "Funzionamento ripristinato e verificato"
    assert doc["data_risoluzione"]
    assert doc["data_verifica"]

    evento = run(db.anomalie_eventi.find_one({"anomalia_id": "anomalia-1"}))
    assert evento["evento"] == "risoluzione"
    assert evento["operatore"] == "Ceraldi Valerio"
    assert evento["stato_precedente"] == "Aperta"
    assert evento["stato_nuovo"] == "Risolta"


def test_presa_in_carico_registra_operatore_e_data(contesto):
    modulo, db, request = contesto

    run(modulo.aggiorna_anomalia(
        "anomalia-1",
        modulo.AggiornaAnomaliaRequest(stato="In corso"),
        request,
    ))

    doc = run(db.anomalie.find_one({"id": "anomalia-1"}))
    assert doc["operatore_presa_in_carico"] == "Ceraldi Valerio"
    assert doc["data_presa_in_carico"]
    assert not doc.get("operatore_risoluzione")
    evento = run(db.anomalie_eventi.find_one({"anomalia_id": "anomalia-1"}))
    assert evento["evento"] == "presa_in_carico"
