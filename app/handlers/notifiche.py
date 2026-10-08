"""
Handler Notifiche — reagisce a tutti gli eventi
Invia notifiche WebSocket in tempo reale all'interfaccia.
"""
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


async def handler_notifica_fattura(payload: Dict[str, Any], db) -> Dict[str, Any]:
    """Notifica WebSocket quando arriva una fattura."""
    try:
        from app.services.websocket_manager import notify_data_change
        numero   = payload.get("numero_documento") or payload.get("invoice_number", "")
        forn     = payload.get("fornitore", {})
        fornitore_nome = forn.get("ragione_sociale") or forn.get("nome", "")
        importo  = payload.get("importo_totale") or payload.get("total_amount", 0)
        await notify_data_change("fattura_importata", {
            "numero":   numero,
            "fornitore": fornitore_nome,
            "importo":  importo,
        }, "notifications")
        return {"notifica_inviata": True}
    except Exception as e:
        logger.debug(f"[HandlerNotifiche] WebSocket non disponibile: {e}")
        return {"notifica_inviata": False, "reason": str(e)}


async def handler_notifica_cedolino(payload: Dict[str, Any], db) -> Dict[str, Any]:
    """Notifica WebSocket quando arriva un cedolino."""
    try:
        from app.services.websocket_manager import notify_data_change
        nome  = payload.get("nome_dipendente") or payload.get("nome", "")
        mese  = payload.get("mese", "")
        anno  = payload.get("anno", "")
        netto = payload.get("netto") or payload.get("netto_in_busta", 0)
        await notify_data_change("cedolino_importato", {
            "dipendente": nome,
            "periodo":    f"{mese}/{anno}",
            "netto":      netto,
        }, "notifications")
        return {"notifica_inviata": True}
    except Exception as e:
        logger.debug(f"[HandlerNotifiche] WebSocket non disponibile: {e}")
        return {"notifica_inviata": False}
