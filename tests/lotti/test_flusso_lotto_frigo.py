"""Invarianti del ciclo produzione -> conservazione -> prelievo."""

import asyncio
from datetime import date, timedelta

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

from app.lotti.routers import anomalie, attrezzature, lotti_produzione
from app.lotti.servizi import lotti_service, movimenti_lotto_service, prelievo_lotto_service


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def archivio(monkeypatch):
    db = AsyncMongoMockClient()["flusso_lotto_frigo_test"]
    for modulo in (anomalie, attrezzature, lotti_produzione, lotti_service, movimenti_lotto_service,
                   prelievo_lotto_service):
        monkeypatch.setattr(modulo, "db", db)
    import app.lotti.eventi as eventi

    async def pubblica(*_args, **_kwargs):
        return None

    monkeypatch.setattr(eventi, "publish", pubblica)
    return db


def test_elenco_attrezzature_non_inventa_frigo(archivio):
    assert run(attrezzature.get_attrezzature()) == {
        "frigoriferi": [], "congelatori": [], "tutti": [],
    }


def test_destinazione_deve_essere_censita_e_coerente(archivio):
    run(archivio.attrezzature_config.insert_many([
        {"tipo": "frigo", "numero": 2, "nome": "Frigo laboratorio", "attivo": True},
        {"tipo": "congelatore", "numero": 1, "nome": "Abbattitore", "attivo": True},
    ]))

    frigo = run(lotti_produzione._posizione_produzione(
        "frigo", "Frigo laboratorio", "pasticceria", "op-1", "Mario", 12))
    assert frigo["tipo"] == "frigo"
    assert frigo["numero"] == "2"
    assert frigo["nome"] == "Frigo laboratorio"

    abbattitore = run(lotti_produzione._posizione_produzione(
        "abbattitore", "Abbattitore", "pasticceria", "op-1", "Mario", 12))
    assert abbattitore["tipo"] == "abbattitore"

    with pytest.raises(HTTPException) as errore:
        run(lotti_produzione._posizione_produzione(
            "frigo", "Frigo scritto a mano", "pasticceria", "op-1", "Mario", 12))
    assert errore.value.status_code == 422


def test_prelievo_parziale_aggiorna_anche_quantita_della_posizione(archivio):
    scadenza = (date.today() + timedelta(days=2)).strftime("%d/%m/%Y")
    run(archivio.lotti.insert_one({
        "id": "lotto-1", "numero_lotto": "TEST-1", "quantita": 10,
        "data_scadenza": scadenza, "frigo_numero": "Frigo laboratorio",
        "posizione": {"tipo": "frigo", "numero": "2", "nome": "Frigo laboratorio",
                      "quantita": 10},
    }))
    risultato = run(prelievo_lotto_service.preleva_lotto(
        "lotto-1", 4, "banco", "op-parziale",
        posizione_a={"tipo": "banco", "nome": "Banco", "quantita": 4},
    ))
    assert risultato["residua"] == 6
    lotto = run(archivio.lotti.find_one({"id": "lotto-1"}))
    assert lotto["quantita"] == lotto["posizione"]["quantita"] == 6
    assert lotto["posizione"]["tipo"] == "frigo"


def test_prelievo_totale_non_lascia_il_lotto_anche_nel_frigo(archivio):
    scadenza = (date.today() + timedelta(days=2)).strftime("%d/%m/%Y")
    run(archivio.lotti.insert_one({
        "id": "lotto-2", "numero_lotto": "TEST-2", "quantita": 5,
        "data_scadenza": scadenza, "frigo_numero": "Frigo laboratorio",
        "posizione": {"tipo": "frigo", "numero": "2", "nome": "Frigo laboratorio",
                      "quantita": 5},
    }))
    run(prelievo_lotto_service.preleva_lotto(
        "lotto-2", 5, "banco", "op-totale",
        posizione_a={"tipo": "banco", "nome": "Banco", "quantita": 5},
    ))
    lotto = run(archivio.lotti.find_one({"id": "lotto-2"}))
    assert lotto["quantita"] == 0
    assert lotto["consumato"] is True
    assert lotto["frigo_numero"] == ""
    assert lotto["posizione"]["tipo"] == "banco"
    assert lotto["posizione"]["quantita"] == 0


def test_creazione_senza_movimento_blocca_il_lotto(archivio, monkeypatch):
    async def registro_non_disponibile(*_args, **_kwargs):
        raise RuntimeError("registro non disponibile")

    monkeypatch.setattr(movimenti_lotto_service, "registra_movimento", registro_non_disponibile)
    with pytest.raises(RuntimeError):
        run(lotti_service.crea_lotto({
            "id": "lotto-audit", "numero_lotto": "AUDIT-1", "prodotto": "Crema",
            "quantita": 2,
        }, origine="produzione"))
    lotto = run(archivio.lotti.find_one({"id": "lotto-audit"}))
    assert lotto["stato"] == "bloccato_audit"
    assert lotto["audit_incompleto"] is True


def test_spostamento_non_puo_bypassare_il_flusso_banco(archivio):
    run(archivio.lotti.insert_one({
        "id": "lotto-sposta", "quantita": 2, "stato": "attivo",
        "posizione": {"tipo": "frigo", "nome": "Frigo 1", "quantita": 2},
    }))
    with pytest.raises(HTTPException) as errore:
        run(lotti_produzione.sposta_posizione_lotto(
            "lotto-sposta", tipo="banco", numero="", nome="", reparto="pasticceria",
            motivo="", operatore_id="op-1", operatore_nome="Mario", operation_id="sposta-1"))
    assert errore.value.status_code == 422


def test_spostamento_senza_audit_viene_annullato(archivio, monkeypatch):
    run(archivio.attrezzature_config.insert_one({
        "tipo": "frigo", "numero": 2, "nome": "Frigo 2", "attivo": True,
    }))
    posizione_prima = {"tipo": "frigo", "numero": "1", "nome": "Frigo 1", "quantita": 2}
    run(archivio.lotti.insert_one({
        "id": "lotto-rollback", "numero_lotto": "ROLL-1", "quantita": 2,
        "stato": "attivo", "frigo_numero": "Frigo 1", "posizione": posizione_prima,
    }))

    async def registro_non_disponibile(*_args, **_kwargs):
        raise RuntimeError("registro non disponibile")

    monkeypatch.setattr(movimenti_lotto_service, "registra_movimento", registro_non_disponibile)
    with pytest.raises(HTTPException) as errore:
        run(lotti_produzione.sposta_posizione_lotto(
            "lotto-rollback", tipo="frigo", numero="Frigo 2", nome="",
            reparto="pasticceria", motivo="Guasto", operatore_id="op-1",
            operatore_nome="Mario", operation_id="sposta-rollback"))
    assert errore.value.status_code == 503
    lotto = run(archivio.lotti.find_one({"id": "lotto-rollback"}))
    assert lotto["frigo_numero"] == "Frigo 1"
    assert lotto["posizione"] == posizione_prima


def test_anomalia_usa_identita_apparecchio_e_non_un_prefisso(archivio):
    run(archivio.attrezzature_config.insert_many([
        {"tipo": "frigo", "numero": 2, "nome": "Frigorifero N°2", "attivo": True},
        {"tipo": "frigo", "numero": 9, "nome": "Frigorifero N°9", "attivo": True},
    ]))
    run(archivio.lotti.insert_many([
        {"id": "nel-2", "quantita": 2, "stato": "attivo", "frigo_numero": "Frigorifero N°2",
         "posizione": {"tipo": "frigo", "numero": "2", "nome": "Frigorifero N°2"}},
        {"id": "nel-9", "quantita": 2, "stato": "attivo", "frigo_numero": "Frigorifero N°9",
         "posizione": {"tipo": "frigo", "numero": "9", "nome": "Frigorifero N°9"}},
    ]))
    esito = run(anomalie.registra_anomalia(anomalie.NuovaAnomaliaRequest(
        attrezzatura="Frigorifero N°2", categoria="Frigorifero",
        tipo="Temperatura fuori soglia", descrizione="Prova",
    )))
    coinvolti = esito["anomalia"]["lotti_coinvolti"]
    assert [lotto["id"] for lotto in coinvolti] == ["nel-2"]
    assert esito["anomalia"]["attrezzatura_ref"]["numero"] == 2


def test_anomalia_del_freddo_rifiuta_un_nome_non_censito(archivio):
    with pytest.raises(HTTPException) as errore:
        run(anomalie.registra_anomalia(anomalie.NuovaAnomaliaRequest(
            attrezzatura="Frigo inventato", categoria="Frigorifero",
            tipo="Temperatura fuori soglia", descrizione="Prova",
        )))
    assert errore.value.status_code == 422
    assert run(archivio.anomalie.count_documents({})) == 0
