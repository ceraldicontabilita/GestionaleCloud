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

    # Telegram se urgente. Prima di questa correzione importava
    # invia_messaggio, funzione mai esistita in telegram_notifications.py
    # (la funzione reale è send_notification): l'ImportError veniva
    # inghiottito dal except sotto, quindi le notifiche Telegram per gli
    # avvisi urgenti degli agenti non hanno mai funzionato, silenziosamente.
    if tipo in ["urgente", "anomalia"]:
        try:
            from app.services.telegram_notifications import send_notification
            await send_notification(f"🚨 {titolo}\n{descrizione[:200]}")
        except Exception:
            pass

    return segnalazione["id"]
