"""Policy engine deterministico per gli agenti AI.

Il modulo registra decisioni e transizioni, ma NON esegue azioni di business.
Un futuro executor potra' consumare solo decisioni ``ready_l2`` o approvate,
passando nuovamente dalla policy e da strumenti applicativi tipizzati.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pymongo.errors import DuplicateKeyError

from app.agents.models import (
    DecisioneInput,
    LivelloAutonomia,
    LivelloRischio,
    Reversibilita,
    StatoEsecuzione,
)


COLL_DECISIONI = "ai_decisions"
COLL_EVENTI = "ai_decision_events"
COLL_STATO = "sistema_stato"
STATO_KEY = "ai_automazioni"

SOGLIA_CONFIDENZA_L2 = float(os.getenv("AI_L2_MIN_CONFIDENCE", "0.95"))
IMPATTO_MASSIMO_L2 = float(os.getenv("AI_L2_MAX_FINANCIAL_IMPACT", "100"))

# Queste azioni non possono essere rese autonome nemmeno con confidenza 1.0.
AZIONI_VIETATE = {
    "approve_own_decision",
    "alter_audit_log",
    "bypass_permissions",
    "invent_document",
    "delete_audit_log",
}

AZIONI_SEMPRE_L3 = {
    "payment",
    "tax_submission",
    "fiscal_document_issue",
    "accounting_posting",
    "delete",
    "bulk_update",
    "purchase",
    "user_permission_change",
    "bank_account_change",
    "external_legal_communication",
    "human_review",
}


def _dump(model: DecisioneInput) -> Dict[str, Any]:
    return (
        model.model_dump(mode="json", exclude_none=True)
        if hasattr(model, "model_dump")
        else model.dict(exclude_none=True)
    )


async def automazioni_sospese(db) -> bool:
    stato = await db[COLL_STATO].find_one({"chiave": STATO_KEY}, {"_id": 0})
    return bool(stato and stato.get("sospese"))


async def imposta_automazioni(db, sospese: bool, utente: str) -> Dict[str, Any]:
    ora = datetime.now(timezone.utc).isoformat()
    await db[COLL_STATO].update_one(
        {"chiave": STATO_KEY},
        {"$set": {
            "chiave": STATO_KEY,
            "sospese": sospese,
            "updated_at": ora,
            "updated_by": utente,
        }},
        upsert=True,
    )
    await _registra_evento(
        db,
        decision_id=None,
        evento="automazioni_fermate" if sospese else "automazioni_riprese",
        attore=utente,
        dettaglio={},
    )
    return {"sospese": sospese, "updated_at": ora, "updated_by": utente}


async def valuta_policy(db, proposta: DecisioneInput) -> Dict[str, Any]:
    livello = proposta.autonomy_level
    motivi = []
    tipo_azione = str(proposta.recommended_action.get("type") or "").strip().lower()

    if tipo_azione in AZIONI_VIETATE:
        return {
            "effective_level": LivelloAutonomia.L4,
            "approval_required": False,
            "execution_status": StatoEsecuzione.BLOCKED,
            "policy_reasons": ["azione_vietata_dalla_policy"],
        }

    if tipo_azione in AZIONI_SEMPRE_L3:
        livello = LivelloAutonomia.L3
        motivi.append("azione_con_approvazione_umana_obbligatoria")

    if livello == LivelloAutonomia.L0:
        stato = StatoEsecuzione.OBSERVED
        approvazione = False
    elif livello == LivelloAutonomia.L1:
        stato = StatoEsecuzione.PROPOSED
        approvazione = False
    elif livello == LivelloAutonomia.L3:
        stato = StatoEsecuzione.PENDING_APPROVAL
        approvazione = True
    elif livello == LivelloAutonomia.L4:
        stato = StatoEsecuzione.BLOCKED
        approvazione = False
        motivi.append("livello_l4_vietato")
    else:
        # L2 e' fail-closed: qualunque requisito mancante lo porta a L3.
        if proposta.risk_level != LivelloRischio.LOW:
            motivi.append("rischio_non_basso")
        if proposta.reversibility != Reversibilita.FULL:
            motivi.append("azione_non_completamente_reversibile")
        if proposta.confidence < SOGLIA_CONFIDENZA_L2:
            motivi.append("confidenza_sotto_soglia")
        if abs(proposta.financial_impact) > IMPATTO_MASSIMO_L2:
            motivi.append("impatto_economico_oltre_soglia")
        if await automazioni_sospese(db):
            return {
                "effective_level": LivelloAutonomia.L2,
                "approval_required": False,
                "execution_status": StatoEsecuzione.SUSPENDED,
                "policy_reasons": ["automazioni_fermate_globalmente"],
            }
        if motivi:
            livello = LivelloAutonomia.L3
            stato = StatoEsecuzione.PENDING_APPROVAL
            approvazione = True
        else:
            stato = StatoEsecuzione.READY_L2
            approvazione = False

    return {
        "effective_level": livello,
        "approval_required": approvazione,
        "execution_status": stato,
        "policy_reasons": motivi,
    }


async def crea_decisione(db, proposta: DecisioneInput) -> Dict[str, Any]:
    if proposta.decision_key:
        esistente = await db[COLL_DECISIONI].find_one(
            {"decision_key": proposta.decision_key}, {"_id": 0}
        )
        if esistente:
            return esistente

    policy = await valuta_policy(db, proposta)
    ora = datetime.now(timezone.utc).isoformat()
    record = {
        "decision_id": str(uuid.uuid4()),
        "timestamp": ora,
        **_dump(proposta),
        "requested_autonomy_level": proposta.autonomy_level.value,
        "autonomy_level": policy["effective_level"].value,
        "approval_required": policy["approval_required"],
        "execution_status": policy["execution_status"].value,
        "policy_reasons": policy["policy_reasons"],
        "created_at": ora,
        "updated_at": ora,
    }
    try:
        await db[COLL_DECISIONI].insert_one(dict(record))
    except DuplicateKeyError:
        # Protezione concorrente: due esecuzioni con la stessa fotografia
        # restituiscono la decisione già registrata, senza duplicare eventi.
        esistente = await db[COLL_DECISIONI].find_one(
            {"decision_key": proposta.decision_key}, {"_id": 0}
        )
        if esistente:
            return esistente
        raise
    await _registra_evento(
        db,
        decision_id=record["decision_id"],
        evento="decisione_creata",
        attore=proposta.agent,
        dettaglio={
            "livello": record["autonomy_level"],
            "stato": record["execution_status"],
            "motivi_policy": record["policy_reasons"],
        },
    )
    record.pop("_id", None)
    return record


async def _registra_evento(
    db,
    decision_id: Optional[str],
    evento: str,
    attore: str,
    dettaglio: Dict[str, Any],
) -> None:
    await db[COLL_EVENTI].insert_one({
        "event_id": str(uuid.uuid4()),
        "decision_id": decision_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": evento,
        "actor": attore,
        "detail": dettaglio,
    })


async def cambia_stato_decisione(
    db,
    decision_id: str,
    approva: bool,
    utente: str,
    nota: str = "",
) -> Optional[Dict[str, Any]]:
    decisione = await db[COLL_DECISIONI].find_one({"decision_id": decision_id})
    if not decisione:
        return None
    if decisione.get("execution_status") != StatoEsecuzione.PENDING_APPROVAL.value:
        raise ValueError("La decisione non e' in attesa di approvazione")
    # Un agente non puo' approvare la propria proposta.
    if utente == decisione.get("agent"):
        raise ValueError("Un agente non puo' approvare la propria decisione")

    nuovo_stato = (
        StatoEsecuzione.APPROVED_PENDING_EXECUTION
        if approva
        else StatoEsecuzione.REJECTED
    )
    ora = datetime.now(timezone.utc).isoformat()
    esito = await db[COLL_DECISIONI].update_one(
        {"decision_id": decision_id, "execution_status": StatoEsecuzione.PENDING_APPROVAL.value},
        {"$set": {
            "execution_status": nuovo_stato.value,
            "approval_required": False,
            "approved_by": utente if approva else None,
            "rejected_by": None if approva else utente,
            "approval_note": nota,
            "updated_at": ora,
        }},
    )
    if not esito.modified_count:
        raise ValueError("La decisione e' gia' stata gestita da un altro utente")
    await _registra_evento(
        db,
        decision_id=decision_id,
        evento="decisione_approvata" if approva else "decisione_rifiutata",
        attore=utente,
        dettaglio={"nota": nota},
    )
    aggiornata = await db[COLL_DECISIONI].find_one({"decision_id": decision_id}, {"_id": 0})
    return aggiornata
