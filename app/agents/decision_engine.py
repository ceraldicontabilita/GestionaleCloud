"""Policy engine deterministico per gli agenti AI.

Il modulo registra decisioni e transizioni, ma NON esegue azioni di business.
Un futuro executor potra' consumare solo decisioni ``ready_l2`` o approvate,
passando nuovamente dalla policy e da strumenti applicativi tipizzati.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.services.sheets_document_store import DuplicateRecordError

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

# Campi sostanziali della proposta. Sorgenti, timestamp e metadati tecnici non
# devono creare una nuova decisione se il problema e l'azione restano uguali.
CAMPI_FINGERPRINT = (
    "agent", "objective", "facts", "assumptions", "rule_ids", "alternatives",
    "recommended_action", "confidence", "financial_impact", "risk_level",
    "reversibility", "autonomy_level", "approver_role", "explanation",
    "rollback_reference",
)


def _json_canonico(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _normalizza_obiettivo(value: Any) -> str:
    testo = " ".join(str(value or "").lower().split())
    return re.sub(r"\b\d+(?:[.,]\d+)?\b", "#", testo)


def _impronta_semantica(dati: Dict[str, Any]) -> str:
    sostanza = {campo: dati.get(campo) for campo in CAMPI_FINGERPRINT}
    return hashlib.sha256(_json_canonico(sostanza).encode("utf-8")).hexdigest()


def _chiave_semantica_input(dati: Dict[str, Any]) -> str:
    if dati.get("semantic_key"):
        return str(dati["semantic_key"])
    decision_key = str(dati.get("decision_key") or "")
    # Gli agenti shadow terminano le chiavi della fotografia con un digest.
    # Lo rimuoviamo per riconoscere lo stesso problema tra due rilevazioni.
    base = re.sub(r"([:_-])[0-9a-f]{12,64}$", "", decision_key, flags=re.IGNORECASE)
    if base and base != decision_key:
        return base
    stabile = {
        "agent": dati.get("agent"),
        "objective": _normalizza_obiettivo(dati.get("objective")),
        "action_type": (dati.get("recommended_action") or {}).get("type"),
        "rule_ids": dati.get("rule_ids") or [],
    }
    return "semantic:" + hashlib.sha256(_json_canonico(stabile).encode("utf-8")).hexdigest()[:32]


def chiave_semantica_record(record: Dict[str, Any]) -> str:
    """Chiave compatibile anche con decisioni storiche prive dei nuovi campi."""
    decision_key = str(record.get("decision_key") or "")
    if decision_key.startswith("cashflow13w:"):
        return "cashflow13w:previsione"
    return _chiave_semantica_input(record)


def decisioni_correnti(records: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    """Restituisce una sola decisione corrente per problema, senza cancellare lo storico."""
    correnti: list[Dict[str, Any]] = []
    viste: Dict[str, int] = {}
    storiche: Dict[str, int] = {}
    for originale in records:
        record = dict(originale)
        chiave = chiave_semantica_record(record)
        if chiave in viste or record.get("execution_status") == StatoEsecuzione.SUPERSEDED.value:
            storiche[chiave] = storiche.get(chiave, 0) + 1
            continue
        viste[chiave] = len(correnti)
        correnti.append(record)
    for chiave, indice in viste.items():
        correnti[indice]["versioni_storiche"] = storiche.get(chiave, 0)
    return correnti


async def _trova_ultima_semantica(db, semantic_key: str) -> Optional[Dict[str, Any]]:
    righe = await db[COLL_DECISIONI].find(
        {"semantic_key": semantic_key}, {"_id": 0}
    ).sort("timestamp", -1).limit(1).to_list(1)
    if righe:
        return righe[0]
    # Compatibilita' transitoria con il registro creato prima di semantic_key.
    legacy = await db[COLL_DECISIONI].find(
        {"semantic_key": {"$exists": False}}, {"_id": 0}
    ).sort("timestamp", -1).limit(500).to_list(500)
    return next(
        (record for record in legacy if chiave_semantica_record(record) == semantic_key),
        None,
    )


async def _registra_nuova_rilevazione(
    db, decisione: Dict[str, Any], dati: Dict[str, Any], ora: str
) -> Dict[str, Any]:
    semantic_key = decisione.get("semantic_key") or _chiave_semantica_input(dati)
    fingerprint = decisione.get("semantic_fingerprint") or _impronta_semantica(dati)
    aggiornamento = {
        "semantic_key": semantic_key,
        "semantic_fingerprint": fingerprint,
        "version": int(decisione.get("version") or 1),
        "occurrence_count": int(decisione.get("occurrence_count") or 1) + 1,
        "first_seen_at": decisione.get("first_seen_at") or decisione.get("timestamp") or ora,
        "last_seen_at": ora,
        "last_input_sources": dati.get("input_sources") or [],
        "updated_at": ora,
    }
    await db[COLL_DECISIONI].update_one(
        {"decision_id": decisione["decision_id"]}, {"$set": aggiornamento}
    )
    return {**decisione, **aggiornamento}


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
    dati = _dump(proposta)
    semantic_key = _chiave_semantica_input(dati)
    fingerprint = _impronta_semantica(dati)
    decision_key = proposta.decision_key or f"{semantic_key}:{fingerprint[:24]}"
    ora = datetime.now(timezone.utc).isoformat()

    esistente = await db[COLL_DECISIONI].find_one(
        {"decision_key": decision_key}, {"_id": 0}
    )
    if esistente:
        return await _registra_nuova_rilevazione(db, esistente, dati, ora)

    precedente = await _trova_ultima_semantica(db, semantic_key)
    fingerprint_precedente = (
        precedente.get("semantic_fingerprint") if precedente else None
    ) or (_impronta_semantica(precedente) if precedente else None)
    if precedente and fingerprint_precedente == fingerprint:
        return await _registra_nuova_rilevazione(db, precedente, dati, ora)

    policy = await valuta_policy(db, proposta)
    versione = int((precedente or {}).get("version") or 0) + 1
    record = {
        "decision_id": str(uuid.uuid4()),
        "timestamp": ora,
        **dati,
        "decision_key": decision_key,
        "semantic_key": semantic_key,
        "semantic_fingerprint": fingerprint,
        "version": versione,
        "occurrence_count": 1,
        "first_seen_at": ora,
        "last_seen_at": ora,
        "supersedes_decision_id": (precedente or {}).get("decision_id"),
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
    except DuplicateRecordError:
        # Protezione concorrente: due esecuzioni con la stessa fotografia
        # restituiscono la decisione già registrata, senza duplicare eventi.
        esistente = await db[COLL_DECISIONI].find_one(
            {"$or": [
                {"decision_key": decision_key},
                {"semantic_key": semantic_key, "semantic_fingerprint": fingerprint},
            ]},
            {"_id": 0},
        )
        if esistente:
            return await _registra_nuova_rilevazione(db, esistente, dati, ora)
        raise

    if precedente:
        await db[COLL_DECISIONI].update_one(
            {"decision_id": precedente["decision_id"]},
            {"$set": {
                "status_before_supersede": precedente.get("execution_status"),
                "execution_status": StatoEsecuzione.SUPERSEDED.value,
                "superseded_by_decision_id": record["decision_id"],
                "superseded_at": ora,
                "updated_at": ora,
            }},
        )
        await _registra_evento(
            db,
            decision_id=precedente["decision_id"],
            evento="decisione_superata",
            attore=proposta.agent,
            dettaglio={"sostituita_da": record["decision_id"], "versione": versione},
        )
    await _registra_evento(
        db,
        decision_id=record["decision_id"],
        evento="decisione_creata",
        attore=proposta.agent,
        dettaglio={
            "livello": record["autonomy_level"],
            "stato": record["execution_status"],
            "motivi_policy": record["policy_reasons"],
            "versione": versione,
            "sostituisce": record.get("supersedes_decision_id"),
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
    ultima = await _trova_ultima_semantica(db, chiave_semantica_record(decisione))
    if ultima and ultima.get("decision_id") != decision_id:
        raise ValueError("La decisione e' stata superata da una versione piu recente")
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
            "approved_at": ora if approva else None,
            "rejected_at": None if approva else ora,
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
