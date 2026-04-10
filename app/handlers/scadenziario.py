"""
Handler Scadenziario — reagisce a fattura.importata
Crea la scadenza di pagamento nel scadenziario_fornitori.
"""
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Giorni di pagamento default per modalità
GIORNI_PER_MODALITA = {
    "bonifico":  30,
    "sepa":      30,
    "rid":       30,
    "riba":      30,
    "assegno":   0,
    "contanti":  0,
    "cassa":     0,
    "carta":     0,
    "altro":     30,
}


async def handler_crea_scadenza(payload: Dict[str, Any], db) -> Dict[str, Any]:
    """
    Crea una scadenza di pagamento in scadenziario_fornitori.
    Usa la data di scadenza dall'XML se presente, altrimenti la calcola
    dalla data fattura + giorni per metodo di pagamento.
    """
    if db is None:
        return {"skipped": True, "reason": "db non disponibile"}

    fattura_id    = payload.get("fattura_id") or payload.get("id")
    importo       = float(payload.get("importo_totale") or payload.get("total_amount") or 0)
    fornitore_obj = payload.get("fornitore", {})
    data_fattura  = payload.get("data_documento") or payload.get("invoice_date", "")
    metodo_pag    = payload.get("metodo_pagamento") or "da_configurare"
    numero_doc    = payload.get("numero_documento") or payload.get("invoice_number", "")

    if importo <= 0:
        return {"skipped": True, "reason": "importo zero o negativo"}

    # Calcola data scadenza
    data_scadenza = payload.get("data_scadenza_pagamento")
    if not data_scadenza and data_fattura:
        try:
            giorni = GIORNI_PER_MODALITA.get(metodo_pag.lower(), 30)
            data_base = datetime.strptime(data_fattura[:10], "%Y-%m-%d")
            data_scadenza = (data_base + timedelta(days=giorni)).strftime("%Y-%m-%d")
        except Exception:
            data_scadenza = data_fattura[:10] if data_fattura else ""

    # Controlla se esiste già
    esistente = await db["scadenziario_fornitori"].find_one({"fattura_id": fattura_id})
    if esistente:
        return {"skipped": True, "reason": "scadenza già esistente", "scadenza_id": esistente["id"]}

    scadenza = {
        "id":              str(uuid.uuid4()),
        "fattura_id":      fattura_id,
        "numero_fattura":  numero_doc,
        "fornitore_id":    fornitore_obj.get("id"),
        "fornitore_nome":  fornitore_obj.get("ragione_sociale") or fornitore_obj.get("nome", ""),
        "fornitore_piva":  fornitore_obj.get("partita_iva") or fornitore_obj.get("piva", ""),
        "importo":         importo,
        "metodo_pagamento": metodo_pag,
        "data_fattura":    data_fattura[:10] if data_fattura else "",
        "data_scadenza":   data_scadenza or "",
        "stato":           "aperta",
        "pagato":          False,
        "created_at":      datetime.now(timezone.utc).isoformat(),
    }

    await db["scadenziario_fornitori"].insert_one(scadenza.copy())
    logger.info(f"[HandlerScadenziario] Scadenza creata: {fattura_id} → {data_scadenza} €{importo}")
    return {"scadenza_id": scadenza["id"], "data_scadenza": data_scadenza, "importo": importo}
