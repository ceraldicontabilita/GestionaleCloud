"""
Handler Prima Nota — reagisce a cedolino.importato (event bus unico).
Scrive automaticamente il movimento stipendio in prima_nota_salari.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)


async def handler_prima_nota_cedolino(payload: Dict[str, Any], db) -> Dict[str, Any]:
    """
    Quando arriva un cedolino, scrive automaticamente il movimento in prima_nota_salari.
    """
    if db is None:
        return {"skipped": True, "reason": "db non disponibile"}

    cedolino_id   = payload.get("cedolino_id") or payload.get("id")
    dipendente_id = payload.get("dipendente_id")
    nome          = payload.get("nome_dipendente") or payload.get("nome", "")
    cf            = payload.get("codice_fiscale", "")
    netto         = float(payload.get("netto") or payload.get("netto_in_busta") or 0)
    mese          = payload.get("mese")
    anno          = payload.get("anno")
    periodo       = f"{mese:02d}/{anno}" if mese and anno else ""

    if netto <= 0:
        return {"skipped": True, "reason": "netto zero o negativo"}

    # Anti-duplicato. Senza la chiave completa (dipendente+mese+anno) non e'
    # possibile riconoscere un replay dello stesso cedolino: meglio saltare
    # che rischiare movimenti stipendio duplicati (l'handler ora scatta per
    # TUTTI i canali di import, inclusa la pipeline email dove il dipendente
    # puo' non essere ancora in anagrafica).
    #
    # Bug corretto 15/07/2026 (audit funzionale): il filtro includeva anche
    # source="cedolino_auto", ma salari_unificati_v2.py::processa_cedolino_v2
    # (canale cedolini_manager/Drive/email "v2") scrive DIRETTAMENTE un
    # movimento in prima_nota_salari per lo stesso dipendente+mese+anno PRIMA
    # di propagare questo stesso evento, con source="cedolino_v2" (non
    # "cedolino_auto"): l'anti-duplicato non lo trovava mai e questo handler
    # inseriva un SECONDO movimento (doppio conteggio reale dello stipendio
    # in cassa/bilancio). Un qualsiasi movimento già presente per lo stesso
    # dipendente+mese+anno in prima_nota_salari, da qualunque canale sia
    # nato, e' comunque "lo stipendio di quel mese": basta a bloccare il
    # doppione, senza serve il match esatto sul source.
    if not (dipendente_id and mese and anno):
        return {"skipped": True, "reason": "chiave anti-duplicato incompleta (dipendente/mese/anno)"}
    anti_dup = {"dipendente_id": dipendente_id, "mese": mese, "anno": anno}
    esistente = await db["prima_nota_salari"].find_one(anti_dup)
    if esistente:
        return {"skipped": True, "reason": "movimento già presente", "movimento_id": esistente["id"]}

    movimento = {
        "id":             str(uuid.uuid4()),
        "cedolino_id":    cedolino_id,
        "dipendente_id":  dipendente_id,
        "nome_dipendente": nome,
        "codice_fiscale": cf,
        "data":           f"{anno}-{mese:02d}-01" if anno and mese else "",
        "tipo":           "uscita",
        "importo":        netto,
        "descrizione":    f"Stipendio {nome} {periodo}".strip(),
        "categoria":      "Stipendi",
        "mese":           mese,
        "anno":           anno,
        "periodo":        periodo,
        "source":         "cedolino_auto",
        "created_at":     datetime.now(timezone.utc).isoformat(),
    }

    await db["prima_nota_salari"].insert_one(movimento.copy())
    logger.info(f"[HandlerPrimaNota] Cedolino {nome} {periodo} → prima_nota_salari €{netto}")
    return {"movimento_id": movimento["id"], "netto": netto, "periodo": periodo}
