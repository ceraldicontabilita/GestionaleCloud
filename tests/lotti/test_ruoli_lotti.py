"""Ruoli di Lotti (titolare 26/09/2026): responsabile HACCP e caporeparto.

- ogni ruolo passa solo sulle sue API, gli altri ricevono 403 con codice;
- il ruolo si rilegge dalla scheda HR a ogni operazione: tolto, vale subito;
- il caporeparto modifica solo le ricette del proprio reparto;
- il ruolo si assegna sulla scheda HR e arriva al tablet col login.

Database finti (mongomock), token firmati con un segreto di prova.
"""
import os
os.environ.setdefault("AUTH_SECRET", "test-secret-non-usare-in-prod")

import asyncio

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def ambiente(monkeypatch):
    import app.lotti.db as lotti_db
    import app.lotti.routers.tablet_operatori as t
    from app.hr.database import Database as DatabaseHR

    db = AsyncMongoMockClient()["ruoli_test"]
    hr = AsyncMongoMockClient()["ruoli_hr"]
    monkeypatch.setattr(lotti_db, "database", db)
    monkeypatch.setattr(t, "db", db)
    monkeypatch.setattr(DatabaseHR, "get_db", classmethod(lambda cls: hr))
    run(hr.dipendenti.insert_many([
        {"id": "hr-op", "stato": "attivo", "lotti_ruolo": "operatore"},
        {"id": "hr-haccp", "stato": "attivo", "lotti_ruolo": "haccp"},
        {"id": "hr-capo", "stato": "attivo", "lotti_ruolo": "caporeparto",
         "lotti_reparti": ["pasticceria"]},
        {"id": "hr-cessato", "stato": "cessato", "lotti_ruolo": "haccp"},
    ]))
    run(db.tablet_operatori.insert_many([
        {"id": "op-1", "hr_id": "hr-op", "gestionale_dipendente_id": "hr-op", "nome": "Operatore", "attivo": True},
        {"id": "op-2", "hr_id": "hr-haccp", "gestionale_dipendente_id": "hr-haccp", "nome": "Responsabile",
         "attivo": True, "ruolo_lotti": "haccp"},
        {"id": "op-3", "hr_id": "hr-capo", "gestionale_dipendente_id": "hr-capo", "nome": "Capo",
         "attivo": True, "ruolo_lotti": "caporeparto", "reparti_lotti": ["pasticceria"]},
        {"id": "op-4", "hr_id": "hr-cessato", "gestionale_dipendente_id": "hr-cessato", "nome": "Cessato",
         "attivo": False, "ruolo_lotti": "haccp"},
    ]))
    run(db.ricette.insert_many([
        {"id": "r-dolce", "nome": "Babà", "reparto": "pasticceria"},
        {"id": "r-salato", "nome": "Casatiello", "reparto": "rosticceria"},
    ]))
    return t, db, hr


def _token(sub):
    from app.lotti.auth import make_token
    return {"Authorization": f"Bearer {make_token(sub=sub, nome=sub, ruolo='operatore', via='pin')}"}


def _app():
    from app.lotti.auth import require_permesso, verifica_reparto_ricetta

    app = FastAPI()

    @app.post("/registri")
    async def registri(_r=Depends(require_permesso("haccp_registri"))):
        return {"ok": True}

    @app.post("/smalti")
    async def smalti(_r=Depends(require_permesso("smaltimento"))):
        return {"ok": True}

    @app.put("/ricette/{ricetta_id}")
    async def ricetta(ricetta_id: str, _r=Depends(require_permesso("ricette"))):
        await verifica_reparto_ricetta(_r, ricetta_id)
        return {"ok": True}

    return TestClient(app)


def test_matrice_dei_permessi():
    from app.lotti.servizi import ruoli

    assert ruoli.permessi_di("operatore") == []
    assert ruoli.permessi_di("haccp") == ["frigoriferi", "haccp_anomalie", "haccp_conformita", "haccp_registri", "smaltimento"]
    assert ruoli.permessi_di("caporeparto") == ["produzione", "ricette", "smaltimento"]
    assert ruoli.permessi_di("amministratore") == sorted(ruoli.PERMESSI)
    # un ruolo sconosciuto non promuove nessuno
    assert ruoli.normalizza_ruolo("admin") == "operatore"
    assert ruoli.normalizza_reparti(["Pasticceria", "cucina", "pasticceria"]) == ["pasticceria"]


def test_ogni_ruolo_passa_solo_sulle_sue_api(ambiente):
    client = _app()
    op, haccp, capo = _token("hr-op"), _token("hr-haccp"), _token("hr-capo")

    risposta = client.post("/registri", headers=op)
    assert risposta.status_code == 403 and risposta.headers["x-error-code"] == "RUOLO_NON_AUTORIZZATO"
    assert client.post("/smalti", headers=op).status_code == 403
    assert client.put("/ricette/r-dolce", headers=op).status_code == 403

    assert client.post("/registri", headers=haccp).status_code == 200
    assert client.post("/smalti", headers=haccp).status_code == 200
    assert client.put("/ricette/r-dolce", headers=haccp).status_code == 403

    assert client.post("/registri", headers=capo).status_code == 403
    assert client.post("/smalti", headers=capo).status_code == 200
    assert client.put("/ricette/r-dolce", headers=capo).status_code == 200
    fuori = client.put("/ricette/r-salato", headers=capo)
    assert fuori.status_code == 403 and fuori.headers["x-error-code"] == "REPARTO_NON_AUTORIZZATO"

    assert client.post("/registri").status_code == 401


def test_ruolo_tolto_vale_subito_e_il_cessato_non_passa(ambiente):
    _t, _db, hr = ambiente
    client = _app()
    haccp = _token("hr-haccp")
    assert client.post("/registri", headers=haccp).status_code == 200
    run(hr.dipendenti.update_one({"id": "hr-haccp"}, {"$set": {"lotti_ruolo": "operatore"}}))
    assert client.post("/registri", headers=haccp).status_code == 403  # stesso token
    assert client.post("/registri", headers=_token("hr-cessato")).status_code == 403
    assert client.post("/registri", headers=_token("hr-inesistente")).status_code == 403


def test_revoca_hr_ignora_proiezione_tablet_non_ancora_aggiornata(ambiente):
    from app.lotti.auth import profilo_da_token

    _t, db, hr = ambiente
    token = {"sub": "hr-haccp", "ruolo": "operatore"}
    assert run(profilo_da_token(token))["ruolo"] == "haccp"
    run(hr.dipendenti.update_one({"id": "hr-haccp"}, {"$set": {"lotti_ruolo": "operatore"}}))
    assert run(db.tablet_operatori.find_one({"hr_id": "hr-haccp"}))["ruolo_lotti"] == "haccp"
    assert run(profilo_da_token(token))["ruolo"] == "operatore"


@pytest.mark.parametrize("revoca", [
    {"stato": "cessato"}, {"attivo": False}, {"in_carico": False},
    {"merged_into": "altra-scheda"}, {"lotti_operatore": False},
])
def test_cessazione_o_esclusione_hr_revoca_il_profilo_esistente(ambiente, revoca):
    from app.lotti.auth import profilo_da_token

    _t, db, hr = ambiente
    run(hr.dipendenti.update_one({"id": "hr-haccp"}, {"$set": revoca}))
    assert run(db.tablet_operatori.find_one({"hr_id": "hr-haccp"}))["attivo"] is True
    assert run(profilo_da_token({"sub": "hr-haccp", "ruolo": "operatore"})) is None


def test_reparto_riletto_da_hr_senza_attendere_sync(ambiente):
    from app.lotti.auth import profilo_da_token

    _t, _db, hr = ambiente
    run(hr.dipendenti.update_one({"id": "hr-capo"}, {"$set": {"lotti_reparti": ["bar"]}}))
    assert run(profilo_da_token({"sub": "hr-capo", "ruolo": "operatore"}))["reparti"] == ["bar"]


def test_hr_indisponibile_non_usa_ruoli_tablet_obsoleti(ambiente, monkeypatch):
    from app.hr.database import Database as DatabaseHR
    from app.lotti.auth import profilo_da_token
    from fastapi import HTTPException

    monkeypatch.setattr(DatabaseHR, "get_db", classmethod(lambda cls: None))
    with pytest.raises(HTTPException) as errore:
        run(profilo_da_token({"sub": "hr-haccp", "ruolo": "operatore"}))
    assert errore.value.status_code == 503
    # La sessione ERP amministratore non dipende dalla proiezione HR.
    assert run(profilo_da_token({"sub": "erp:1", "ruolo": "amministratore"}))["ruolo"] == "amministratore"


def test_il_titolare_passa_ovunque():
    from app.lotti.auth import profilo_da_token
    from app.lotti.servizi import ruoli

    profilo = run(profilo_da_token({"sub": "erp:1", "ruolo": "amministratore"}))
    assert profilo["ruolo"] == "amministratore"
    assert all(ruoli.ha_permesso(profilo["ruolo"], p) for p in ruoli.PERMESSI)
    assert ruoli.reparto_ammesso("amministratore", [], "rosticceria")


def test_ruolo_si_assegna_sulla_scheda_hr_e_arriva_al_login(ambiente):
    from fastapi import HTTPException
    from starlette.requests import Request

    t, db, hr = ambiente
    run(hr.dipendenti.insert_many([
        {"id": "hr-capo2", "nome": "Francesco", "cognome": "Prova", "stato": "attivo", "attivo": True,
         "lotti_operatore": False},
    ]))
    richiesta = Request({"type": "http", "headers": [], "state": {}})
    richiesta.state.user = {"nome": "Titolare"}

    with pytest.raises(HTTPException) as errore:
        run(t.imposta_ruolo_operatore("hr-capo2", t.RuoloOperatore(ruolo="admin"), richiesta))
    assert errore.value.status_code == 400
    with pytest.raises(HTTPException):
        run(t.imposta_ruolo_operatore("hr-capo2", t.RuoloOperatore(ruolo="caporeparto", reparti=["cucina"]), richiesta))

    esito = run(t.imposta_ruolo_operatore("hr-capo2", t.RuoloOperatore(ruolo="caporeparto"), richiesta))
    assert esito["avviso"] and esito["permessi"] == ["produzione", "ricette", "smaltimento"]

    esito = run(t.imposta_ruolo_operatore(
        "hr-capo2", t.RuoloOperatore(ruolo="caporeparto", reparti=["Pasticceria"]), richiesta))
    assert esito["avviso"] is None and esito["reparti"] == ["pasticceria"]

    scheda = run(hr.dipendenti.find_one({"id": "hr-capo2"}))
    assert scheda["lotti_ruolo"] == "caporeparto" and scheda["lotti_reparti"] == ["pasticceria"]
    assert scheda["lotti_operatore"] is True  # un caporeparto deve poter entrare
    proiezione = run(db.tablet_operatori.find_one({"hr_id": "hr-capo2"}))
    assert proiezione["attivo"] is True and proiezione["ruolo_lotti"] == "caporeparto"

    risposta = t._op_response({"dipendente_id": "hr-capo2", "nome": "Prova Francesco", "ruolo": "operatore",
                               "ruolo_lotti": proiezione["ruolo_lotti"], "reparti_lotti": proiezione["reparti_lotti"]})
    assert risposta["operatore"]["profilo"]["ruolo"] == "caporeparto"
    assert risposta["operatore"]["profilo"]["reparti"] == ["pasticceria"]
    # il token resta da operatore: il ruolo di Lotti non si porta nel token
    from app.lotti.auth import verify_token
    assert verify_token(risposta["token"])["ruolo"] == "operatore"
