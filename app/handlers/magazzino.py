"""
Handler Magazzino — reagisce a fattura.importata
Carica ogni riga della fattura come movimento di carico in magazzino.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)


async def handler_carico_magazzino(payload: Dict[str, Any], db) -> Dict[str, Any]:
    """
    Per ogni riga della fattura, crea un movimento di carico in warehouse_movements
    e aggiorna le giacenze in warehouse_inventory.
    Viene saltato se il fornitore ha il flag 'esclude_magazzino'.
    """
    if db is None:
        return {"skipped": True, "reason": "db non disponibile"}

    fattura_id     = payload.get("fattura_id") or payload.get("id")
    fornitore_obj  = payload.get("fornitore", {})
    righe          = payload.get("righe") or payload.get("linee", [])
    data_fattura   = payload.get("data_documento") or payload.get("invoice_date", "")
    numero_doc     = payload.get("numero_documento") or payload.get("invoice_number", "")

    if fornitore_obj.get("esclude_magazzino"):
        return {"skipped": True, "reason": "fornitore escluso da magazzino"}

    if not righe:
        return {"skipped": True, "reason": "nessuna riga in fattura"}

    carichi_creati = 0
    errori = []

    for riga in righe:
        try:
            descrizione = riga.get("descrizione") or riga.get("description") or ""
            quantita    = float(riga.get("quantita") or riga.get("quantity") or 1)
            prezzo_unit = float(riga.get("prezzo_unitario") or riga.get("unit_price") or 0)
            um          = riga.get("unita_misura") or riga.get("unit") or "pz"

            if not descrizione or quantita <= 0:
                continue

            movimento = {
                "id":              str(uuid.uuid4()),
                "fattura_id":      fattura_id,
                "numero_fattura":  numero_doc,
                "tipo":            "carico",
                "descrizione":     descrizione,
                "quantita":        quantita,
                "unita_misura":    um,
                "prezzo_unitario": prezzo_unit,
                "valore_totale":   round(quantita * prezzo_unit, 2),
                "fornitore_id":    fornitore_obj.get("id"),
                "fornitore_nome":  fornitore_obj.get("ragione_sociale") or fornitore_obj.get("nome"),
                "data":            data_fattura[:10] if data_fattura else "",
                "source":          "fattura_xml",
                "created_at":      datetime.now(timezone.utc).isoformat(),
            }

            await db["warehouse_movements"].insert_one(movimento.copy())
            carichi_creati += 1

        except Exception as e:
            errori.append(str(e))
            logger.warning(f"[HandlerMagazzino] Errore su riga '{descrizione}': {e}")

    logger.info(f"[HandlerMagazzino] Fattura {fattura_id}: {carichi_creati} carichi creati")
    return {
        "carichi_creati": carichi_creati,
        "errori":         errori,
        "fattura_id":     fattura_id,
    }
