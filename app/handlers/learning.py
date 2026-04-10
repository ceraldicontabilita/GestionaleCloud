"""
Handler Learning — reagisce a fattura.importata
Classifica la fattura per centro di costo e calcola deducibilità/detraibilità.
"""
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


async def handler_classifica_cdc(payload: Dict[str, Any], db) -> Dict[str, Any]:
    """
    Chiama la Learning Machine per classificare la fattura per centro di costo.
    Aggiorna la fattura con: centro_costo_id, imponibile_deducibile_ires, iva_detraibile.
    """
    if db is None:
        return {"skipped": True, "reason": "db non disponibile"}

    fattura_id = payload.get("fattura_id") or payload.get("id")
    if not fattura_id:
        return {"skipped": True, "reason": "fattura_id mancante"}

    try:
        from app.services.learning_machine_cdc import (
            classifica_fattura_per_centro_costo,
            calcola_importi_fiscali,
        )

        fornitore_nome = payload.get("fornitore", {}).get("ragione_sociale", "")
        descrizione    = payload.get("descrizione", "")
        righe          = payload.get("righe") or payload.get("linee", [])
        imponibile     = float(payload.get("imponibile") or 0)
        iva            = float(payload.get("iva") or 0)

        cdc_id, cdc_config, confidence = classifica_fattura_per_centro_costo(
            fornitore_nome, descrizione, righe
        )

        importi = calcola_importi_fiscali(imponibile, iva, cdc_config)

        update = {
            "centro_costo_id":               cdc_id,
            "centro_costo_nome":             cdc_config.get("nome", ""),
            "classificazione_confidence":    confidence,
            "imponibile_deducibile_ires":    importi.get("imponibile_deducibile_ires", 0),
            "imponibile_indeducibile_ires":  importi.get("imponibile_indeducibile_ires", 0),
            "iva_detraibile":                importi.get("iva_detraibile", 0),
            "iva_indetraibile":              importi.get("iva_indetraibile", 0),
            "classificato_da":               "learning_machine",
        }

        await db["invoices"].update_one({"id": fattura_id}, {"$set": update})

        logger.info(f"[HandlerLearning] Fattura {fattura_id} → CDC: {cdc_config.get('nome')} (conf={confidence:.2f})")
        return {"centro_costo": cdc_config.get("nome"), "confidence": confidence}

    except Exception as e:
        logger.warning(f"[HandlerLearning] Classificazione fallita per {fattura_id}: {e}")
        return {"error": str(e)}
