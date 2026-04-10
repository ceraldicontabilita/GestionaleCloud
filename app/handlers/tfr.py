"""
Handler TFR — reagisce a cedolino.importato
Aggiorna automaticamente l'accantonamento TFR.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)

DIVISORE_TFR = 13.5          # art. 2120 c.c.
RIVALUTAZIONE_FISSA = 0.015  # 1.5% fisso


async def handler_aggiorna_tfr(payload: Dict[str, Any], db) -> Dict[str, Any]:
    """
    Quando arriva un cedolino, aggiorna l'accantonamento TFR per quell'anno.
    Calcola quota: paga_lorda / 13.5 (art. 2120 c.c.)
    """
    if db is None:
        return {"skipped": True, "reason": "db non disponibile"}

    dipendente_id = payload.get("dipendente_id")
    mese          = payload.get("mese")
    anno          = payload.get("anno")
    lordo         = float(payload.get("lordo") or payload.get("retribuzione_lorda") or 0)
    tfr_da_pdf    = float(payload.get("tfr_quota_mese") or 0)

    if not dipendente_id or not anno or not mese:
        return {"skipped": True, "reason": "dati insufficienti"}

    # Anti-duplicato: un accantonamento per mese/anno/dipendente
    esistente = await db["tfr_accantonamenti"].find_one({
        "dipendente_id": dipendente_id,
        "anno": anno,
        "mese": mese,
    })
    if esistente:
        return {"skipped": True, "reason": "accantonamento già registrato", "id": esistente["id"]}

    # Quota TFR: usa quella dal PDF se disponibile, altrimenti calcola
    quota = tfr_da_pdf if tfr_da_pdf > 0 else (lordo / DIVISORE_TFR if lordo > 0 else 0)

    if quota <= 0:
        return {"skipped": True, "reason": "quota TFR zero"}

    accantonamento = {
        "id":             str(uuid.uuid4()),
        "dipendente_id":  dipendente_id,
        "anno":           anno,
        "mese":           mese,
        "quota":          round(quota, 2),
        "lordo_base":     lordo,
        "rivalutazione":  0,  # calcolata a fine anno
        "source":         "cedolino_auto",
        "created_at":     datetime.now(timezone.utc).isoformat(),
    }

    await db["tfr_accantonamenti"].insert_one(accantonamento.copy())

    # Aggiorna il totale TFR sul dipendente
    await db["dipendenti"].update_one(
        {"id": dipendente_id},
        {"$inc": {"tfr_maturato": quota},
         "$set": {"tfr_ultimo_aggiornamento": datetime.now(timezone.utc).isoformat()}}
    )

    logger.info(f"[HandlerTFR] Dipendente {dipendente_id} anno {anno}/{mese}: quota TFR €{quota:.2f}")
    return {"accantonamento_id": accantonamento["id"], "quota": quota, "anno": anno, "mese": mese}
