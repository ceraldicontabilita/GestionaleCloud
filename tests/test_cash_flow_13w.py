"""Cash flow 13 settimane: calcolo deterministico, copertura e shadow mode."""

import asyncio
import inspect
from datetime import date

from app.services.sheets_document_store import MemorySheetsClient

import app.agents.cash_flow_shadow as agent_mod
import app.services.cash_flow_13w_service as service_mod
from app.agents.cash_flow_shadow import CashFlow13WShadow
from app.services.cash_flow_13w_service import calcola_cash_flow_13_settimane


def _db():
    return MemorySheetsClient()["cash_flow_13w_test"]


async def _saldo_fisso(db, collection, query, anno=None):
    saldo = 1000 if collection == "prima_nota_cassa" else 2000
    return {"saldo": saldo}


async def _semina(db):
    await db["scadenziario_fornitori"].insert_many([
        {"id": "arretrata", "data_scadenza": "2026-07-10", "importo_rata": "100.00", "stato": "aperta", "pagato": False},
        {"id": "settimana-1", "data_scadenza": "2026-07-24", "importo_residuo": "200.00", "stato": "parziale", "pagato": False},
        {"id": "settimana-2", "data_scadenza": "2026-07-28", "importo": 300, "stato": "aperta", "pagato": False},
        {"id": "pagata", "data_scadenza": "2026-07-22", "importo": 999, "stato": "pagata", "pagato": True},
    ])
    await db["partite_aperte"].insert_many([
        {"id": "f24", "tipo": "f24", "data_scadenza": "2026-07-30", "residuo": 50, "stato": "aperta"},
        {"id": "stipendio-senza-data", "tipo": "stipendio", "residuo": 400, "stato": "aperta"},
        {"id": "duplicato-fattura", "tipo": "fattura_fornitore", "data_scadenza": "2026-07-24", "residuo": 200, "stato": "aperta"},
    ])
    await db["fatture_emesse"].insert_many([
        {"id": "credito", "data_scadenza": "2026-07-23", "importo_residuo": 500, "status": "open", "pagato": False},
        {"id": "credito-senza-data", "totale": 700, "status": "open", "pagato": False},
        {"id": "credito-pagato", "data_scadenza": "2026-07-23", "totale": 900, "status": "paid", "pagato": True},
    ])


def test_calcolo_settimanale_senza_duplicati_e_con_scenari(monkeypatch):
    db = _db()
    asyncio.run(_semina(db))
    monkeypatch.setattr(service_mod, "aggrega_saldo_prima_nota", _saldo_fisso)

    result = asyncio.run(calcola_cash_flow_13_settimane(db, date(2026, 7, 20)))
    base = next(s for s in result["scenari"] if s["nome"] == "base")
    prudente = next(s for s in result["scenari"] if s["nome"] == "prudente")
    stress = next(s for s in result["scenari"] if s["nome"] == "stress")

    assert result["liquidita_iniziale"] == 3000.0
    assert len(base["settimane"]) == 13
    assert base["settimane"][0] == {
        "settimana": 1, "dal": "2026-07-20", "al": "2026-07-26",
        "scaduti_riportati": 1, "entrate": 500.0, "uscite": 300.0, "saldo_finale": 3200.0,
    }
    assert base["settimane"][1]["uscite"] == 350.0
    assert base["saldo_finale"] == 2850.0
    assert prudente["settimane"][0]["entrate"] == 350.0
    assert stress["settimane"][0]["uscite"] == 330.0
    assert result["qualita_dati"]["scadenze_fornitori_incluse"] == 3
    assert result["qualita_dati"]["obblighi_inclusi"] == 1
    assert result["qualita_dati"]["crediti_inclusi"] == 1
    assert result["qualita_dati"]["senza_data_esclusi"] == 2
    assert result["versione_regole"] == "CF13W-002"
    assert {a["codice"] for a in result["anomalie"]} == {
        "DATI_INCOMPLETI", "SCADENZE_ARRETRATE"
    }
    assert result["sola_lettura"] is True


def test_servizio_non_scrive_collezioni_di_business(monkeypatch):
    db = _db()
    asyncio.run(_semina(db))
    monkeypatch.setattr(service_mod, "aggrega_saldo_prima_nota", _saldo_fisso)
    prima = {
        nome: asyncio.run(db[nome].count_documents({}))
        for nome in ("scadenziario_fornitori", "partite_aperte", "fatture_emesse")
    }

    asyncio.run(calcola_cash_flow_13_settimane(db, date(2026, 7, 20)))

    dopo = {nome: asyncio.run(db[nome].count_documents({})) for nome in prima}
    assert dopo == prima
    assert asyncio.run(db["prima_nota_banca"].count_documents({})) == 0


def test_anomalia_liquidita_indica_scenario_e_prima_settimana(monkeypatch):
    db = _db()
    asyncio.run(db["scadenziario_fornitori"].insert_one({
        "id": "uscita-grande",
        "data_scadenza": "2026-07-21",
        "importo": 4000,
        "stato": "aperta",
        "pagato": False,
    }))
    monkeypatch.setattr(service_mod, "aggrega_saldo_prima_nota", _saldo_fisso)
    result = asyncio.run(calcola_cash_flow_13_settimane(db, date(2026, 7, 20)))
    anomalia = next(a for a in result["anomalie"] if a["codice"] == "LIQUIDITA_BASE_NEGATIVA")
    assert anomalia["scenario"] == "base"
    assert anomalia["settimana"] == 1
    assert anomalia["saldo_minimo"] == -1000.0


def test_tensione_di_cassa_crea_proposta_l3_idempotente(monkeypatch):
    db = _db()
    previsione = {
        "versione_regole": "CF13W-001",
        "data_riferimento": "2026-07-20",
        "liquidita_iniziale": 100.0,
        "scenari": [
            {"nome": "base", "saldo_minimo": -400.0, "saldo_finale": -200.0, "settimane": []},
            {"nome": "prudente", "saldo_minimo": -450.0, "saldo_finale": -250.0, "settimane": []},
            {"nome": "stress", "saldo_minimo": -500.0, "saldo_finale": -300.0, "settimane": []},
        ],
        "qualita_dati": {"record_esclusi": 0, "copertura_percentuale": 100.0},
        "assunzioni": ["fixture sintetica"],
        "sola_lettura": True,
    }

    async def previsione_fissa(database):
        return previsione

    monkeypatch.setattr(agent_mod, "calcola_cash_flow_13_settimane", previsione_fissa)
    asyncio.run(CashFlow13WShadow().run(db))
    asyncio.run(CashFlow13WShadow().run(db))

    decisioni = asyncio.run(db["ai_decisions"].find({}, {"_id": 0}).to_list(10))
    assert len(decisioni) == 1
    assert decisioni[0]["autonomy_level"] == "L3"
    assert decisioni[0]["execution_status"] == "pending_approval"
    assert decisioni[0]["financial_impact"] == 500.0
    assert decisioni[0]["metadata"]["shadow_mode"] is True
    assert asyncio.run(db["prima_nota_banca"].count_documents({})) == 0


def test_previsione_positiva_resta_raccomandazione_l1(monkeypatch):
    db = _db()
    previsione = {
        "versione_regole": "CF13W-001",
        "data_riferimento": "2026-07-20",
        "liquidita_iniziale": 1000.0,
        "scenari": [
            {"nome": "base", "saldo_minimo": 800.0, "saldo_finale": 900.0, "settimane": []},
            {"nome": "prudente", "saldo_minimo": 700.0, "saldo_finale": 800.0, "settimane": []},
            {"nome": "stress", "saldo_minimo": 600.0, "saldo_finale": 700.0, "settimane": []},
        ],
        "qualita_dati": {"record_esclusi": 1, "copertura_percentuale": 90.0},
        "assunzioni": [],
        "sola_lettura": True,
    }

    async def previsione_fissa(database):
        return previsione

    monkeypatch.setattr(agent_mod, "calcola_cash_flow_13_settimane", previsione_fissa)
    asyncio.run(CashFlow13WShadow().run(db))
    doc = asyncio.run(db["ai_decisions"].find_one({}, {"_id": 0}))
    assert doc["autonomy_level"] == "L1"
    assert doc["execution_status"] == "proposed"
    assert doc["confidence"] == 0.8


def test_orchestratore_conosce_agente_cash_flow():
    from app.agents.orchestrator import SCHEDULE

    assert SCHEDULE["CashFlow13WShadow"] == 21600


def test_endpoint_cash_flow_richiede_utente_autenticato():
    from app.routers.agenti import get_cash_flow_13_settimane
    from app.utils.dependencies import get_current_user

    parametro = inspect.signature(get_cash_flow_13_settimane).parameters["current_user"]
    assert parametro.default.dependency is get_current_user
