"""Policy L0-L4, approvazioni umane e interruttore globale.

I test usano un database MongoDB esclusivamente in memoria: nessuna rete,
credenziale o collection reale viene letta o modificata.
"""

import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.agents.decision_engine import (
    cambia_stato_decisione,
    crea_decisione,
    imposta_automazioni,
)
from app.agents.models import (
    DecisioneInput,
    LivelloAutonomia,
    LivelloRischio,
    Reversibilita,
)
from app.agents.notifier import crea_segnalazione
from app.agents.orchestrator import run_agenti


def _db():
    return AsyncMongoMockClient()["gestionale_ai_test"]


def _proposta(**override):
    dati = {
        "agent": "TestAgent",
        "objective": "Controllare una anomalia sintetica",
        "input_sources": [{"type": "fixture"}],
        "facts": [{"description": "Dato fittizio"}],
        "recommended_action": {"type": "recommendation", "description": "Verificare"},
        "confidence": 0.99,
        "financial_impact": 0,
        "risk_level": LivelloRischio.LOW,
        "reversibility": Reversibilita.FULL,
        "autonomy_level": LivelloAutonomia.L1,
    }
    dati.update(override)
    return DecisioneInput(**dati)


def test_l1_registra_una_proposta_senza_esecuzione():
    db = _db()
    decisione = asyncio.run(crea_decisione(db, _proposta()))
    assert decisione["autonomy_level"] == "L1"
    assert decisione["execution_status"] == "proposed"
    assert decisione["approval_required"] is False


def test_l2_sicuro_diventa_pronto_ma_non_viene_eseguito():
    db = _db()
    decisione = asyncio.run(crea_decisione(
        db, _proposta(autonomy_level=LivelloAutonomia.L2, financial_impact=10)
    ))
    assert decisione["execution_status"] == "ready_l2"
    assert "executed_at" not in decisione


@pytest.mark.parametrize("override,motivo", [
    ({"risk_level": LivelloRischio.MEDIUM}, "rischio_non_basso"),
    ({"confidence": 0.40}, "confidenza_sotto_soglia"),
    ({"financial_impact": 101}, "impatto_economico_oltre_soglia"),
    ({"reversibility": Reversibilita.PARTIAL}, "azione_non_completamente_reversibile"),
])
def test_l2_fail_closed_richiede_approvazione(override, motivo):
    db = _db()
    decisione = asyncio.run(crea_decisione(
        db, _proposta(autonomy_level=LivelloAutonomia.L2, **override)
    ))
    assert decisione["autonomy_level"] == "L3"
    assert decisione["execution_status"] == "pending_approval"
    assert motivo in decisione["policy_reasons"]


def test_pagamento_e_sempre_l3_anche_se_richiesto_l2():
    db = _db()
    decisione = asyncio.run(crea_decisione(db, _proposta(
        autonomy_level=LivelloAutonomia.L2,
        recommended_action={"type": "payment", "description": "Pagamento fittizio"},
    )))
    assert decisione["autonomy_level"] == "L3"
    assert decisione["execution_status"] == "pending_approval"


def test_azione_l4_viene_bloccata():
    db = _db()
    decisione = asyncio.run(crea_decisione(db, _proposta(
        autonomy_level=LivelloAutonomia.L2,
        recommended_action={"type": "alter_audit_log"},
    )))
    assert decisione["autonomy_level"] == "L4"
    assert decisione["execution_status"] == "blocked"


def test_interruttore_globale_sospende_l2_e_blocca_orchestratore():
    db = _db()
    asyncio.run(imposta_automazioni(db, True, "admin@example.test"))
    decisione = asyncio.run(crea_decisione(
        db, _proposta(autonomy_level=LivelloAutonomia.L2)
    ))
    assert decisione["execution_status"] == "suspended"
    with pytest.raises(RuntimeError, match="interruttore globale"):
        asyncio.run(run_agenti(db))


def test_approvazione_umana_non_esegue_e_registra_evento():
    db = _db()
    decisione = asyncio.run(crea_decisione(db, _proposta(
        autonomy_level=LivelloAutonomia.L3,
        recommended_action={"type": "payment"},
    )))
    aggiornata = asyncio.run(cambia_stato_decisione(
        db, decisione["decision_id"], True, "admin@example.test", "Verificata"
    ))
    assert aggiornata["execution_status"] == "approved_pending_execution"
    assert "executed_at" not in aggiornata
    eventi = asyncio.run(db["ai_decision_events"].find(
        {"decision_id": decisione["decision_id"]}
    ).to_list(10))
    assert [evento["event"] for evento in eventi] == ["decisione_creata", "decisione_approvata"]


def test_agente_non_puo_approvare_la_propria_decisione():
    db = _db()
    decisione = asyncio.run(crea_decisione(db, _proposta(
        autonomy_level=LivelloAutonomia.L3,
        recommended_action={"type": "payment"},
    )))
    with pytest.raises(ValueError, match="propria decisione"):
        asyncio.run(cambia_stato_decisione(
            db, decisione["decision_id"], True, "TestAgent"
        ))


def test_una_decisione_non_puo_essere_approvata_due_volte():
    db = _db()
    decisione = asyncio.run(crea_decisione(db, _proposta(
        autonomy_level=LivelloAutonomia.L3,
        recommended_action={"type": "payment"},
    )))
    asyncio.run(cambia_stato_decisione(
        db, decisione["decision_id"], True, "admin-one@example.test"
    ))
    with pytest.raises(ValueError, match="attesa di approvazione"):
        asyncio.run(cambia_stato_decisione(
            db, decisione["decision_id"], True, "admin-two@example.test"
        ))


def test_notifier_collega_segnalazione_e_decisione_shadow():
    db = _db()
    segnalazione_id = asyncio.run(crea_segnalazione(
        db,
        agente="TestAgent",
        tipo="info",
        titolo="Controllo sintetico",
        descrizione="Nessun dato reale",
        azione="Verificare",
    ))
    segnalazione = asyncio.run(db["agenti_segnalazioni"].find_one({"id": segnalazione_id}))
    decisione = asyncio.run(db["ai_decisions"].find_one({"decision_id": segnalazione["decision_id"]}))
    assert decisione["execution_status"] == "proposed"
    assert decisione["metadata"]["shadow_mode"] is True
