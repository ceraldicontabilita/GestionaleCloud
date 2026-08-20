import uuid
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


async def crea_segnalazione(
    db,
    agente: str,
    tipo: str,
    titolo: str,
    descrizione: str,
    azione: str = None,
    dati: dict = None,
    scadenza: str = None
):
    segnalazione = {
        "id": str(uuid.uuid4()),
        "agente": agente,
        "tipo": tipo,
        "titolo": titolo,
        "descrizione": descrizione,
        "azione_suggerita": azione,
        "dati_riferimento": dati or {},
        "letta": False,
        "risolta": False,
        "scadenza": scadenza,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db["agenti_segnalazioni"].insert_one(segnalazione)

    # Ogni segnalazione alimenta anche il registro decisionale. Il registro
    # non esegue azioni di business: produce soltanto osservazioni o proposte
    # sottoposte alla policy L0-L4 e, quando necessario, all'approvazione umana.
    try:
        from app.agents.decision_engine import crea_decisione
        from app.agents.models import (
            DecisioneInput,
            LivelloAutonomia,
            LivelloRischio,
            Reversibilita,
        )

        dati_riferimento = dati or {}
        importo_raw = dati_riferimento.get("importo", 0)
        try:
            impatto = float(str(importo_raw).replace(".", "").replace(",", ".")) \
                if isinstance(importo_raw, str) and "," in importo_raw \
                else float(importo_raw or 0)
        except (TypeError, ValueError):
            impatto = 0.0

        sensibile = tipo in ["urgente", "anomalia"] or abs(impatto) > 0
        decisione = await crea_decisione(db, DecisioneInput(
            agent=agente,
            objective=titolo,
            input_sources=[{"type": "agent_signal", "signal_id": segnalazione["id"]}],
            facts=[{"description": descrizione}],
            assumptions=[],
            rule_ids=["AI-SHADOW-001", "HUMAN-APPROVAL-001"] if sensibile else ["AI-SHADOW-001"],
            alternatives=[],
            recommended_action={
                "type": "human_review" if sensibile else "recommendation",
                "description": azione or "Valutare la segnalazione",
            },
            confidence=0.5,
            financial_impact=impatto,
            risk_level=LivelloRischio.HIGH if tipo in ["urgente", "anomalia"] else (
                LivelloRischio.MEDIUM if abs(impatto) > 0 else LivelloRischio.LOW
            ),
            reversibility=Reversibilita.FULL,
            autonomy_level=LivelloAutonomia.L3 if sensibile else LivelloAutonomia.L1,
            approver_role="admin",
            explanation=descrizione,
            metadata={"signal_type": tipo, "shadow_mode": True},
        ))
        await db["agenti_segnalazioni"].update_one(
            {"id": segnalazione["id"]},
            {"$set": {"decision_id": decisione["decision_id"]}},
        )
        segnalazione["decision_id"] = decisione["decision_id"]
    except Exception as exc:
        # Una difficolta' nel registro non deve cancellare la segnalazione
        # originale. L'errore resta osservabile nei log senza dati segreti.
        logger.warning("Registro decisionale non aggiornato per la segnalazione %s: %s", segnalazione["id"], exc)

    # Telegram se urgente. Prima di questa correzione importava
    # invia_messaggio, funzione mai esistita in telegram_notifications.py
    # (la funzione reale è send_notification): l'ImportError veniva
    # inghiottito dal except sotto, quindi le notifiche Telegram per gli
    # avvisi urgenti degli agenti non hanno mai funzionato, silenziosamente.
    if tipo in ["urgente", "anomalia"]:
        try:
            from app.services.telegram_notifications import send_notification
            await send_notification(f"🚨 {titolo}\n{descrizione[:200]}")
        except Exception as exc:
            logger.warning(
                "Segnalazione %s salvata, ma notifica Telegram non inviata: %s",
                segnalazione["id"],
                exc,
            )

    return segnalazione["id"]
