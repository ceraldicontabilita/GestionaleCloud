"""Giro automatico PayPal: dati dall'API, banca, fatture e posta senza click.

Prima la sincronizzazione partiva all'apertura della pagina PayPal (lenta, e
con un 404 dell'API restava tutto fermo); ora gira di notte e a meta' giornata
e la pagina si limita a leggere. Ogni passo e' indipendente: il guasto di uno
non ferma gli altri e si scrive nel log col tipo di errore.
"""
import logging
from typing import Any, Dict

from app.config import settings

logger = logging.getLogger(__name__)

LIMITE_RICERCHE_POSTA = 40


async def giro_paypal(db) -> Dict[str, Any]:
    esito: Dict[str, Any] = {}

    if settings.PAYPAL_CLIENT_ID and settings.PAYPAL_CLIENT_SECRET:
        try:
            from datetime import datetime

            from app.services.paypal_api_sync import sync_paypal_incremental
            sync = await sync_paypal_incremental(db)
            esito["sync"] = sync.get("status")
            if sync.get("status") == "updated" and sync.get("period_start") and sync.get("period_end"):
                from app.services.paypal_reconciliation_pipeline import riconcilia_paypal_importato
                inizio = datetime.fromisoformat(sync["period_start"]).date().isoformat()
                fine = datetime.fromisoformat(sync["period_end"]).date().isoformat()
                await riconcilia_paypal_importato(db, start_date=inizio, end_date=fine)
        except Exception as exc:
            esito["sync"] = "errore"
            logger.error("[PAYPAL-AUTO] sync API: %s: %s", type(exc).__name__, exc)
    else:
        esito["sync"] = "non_configurata"

    try:
        from app.routers.paypal_statements import _auto_riconcilia
        banca = await _auto_riconcilia(db, applica=True)
        esito["banca"] = {"riconciliati": banca.get("riconciliati"), "ambigui": banca.get("ambigui")}
    except Exception as exc:
        logger.error("[PAYPAL-AUTO] banca: %s: %s", type(exc).__name__, exc)

    try:
        from app.services.paypal_reconciliation_links import riprocessa_collegamenti_paypal
        fatture = await riprocessa_collegamenti_paypal(db)
        esito["fatture"] = {"associate": fatture.get("associate"), "ambigue": fatture.get("ambigue")}
    except Exception as exc:
        logger.error("[PAYPAL-AUTO] fatture: %s: %s", type(exc).__name__, exc)

    try:
        from app.routers.paypal_statements import auto_cerca_gmail
        posta = await auto_cerca_gmail(limit=LIMITE_RICERCHE_POSTA)
        esito["posta"] = {"cercate": posta.get("cercate"), "associate": posta.get("associate_gmail")}
    except Exception as exc:
        logger.error("[PAYPAL-AUTO] posta: %s: %s", type(exc).__name__, exc)

    logger.info("[PAYPAL-AUTO] %s", esito)
    return esito
