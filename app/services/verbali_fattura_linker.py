"""
Collega i verbali alle fatture del fornitore di noleggio.
Trigger B: chiamato dopo insert di una fattura XML ARVAL/Leasys/ALD/etc.
"""
import re
import logging
from typing import Dict, Any, Optional
from app.services.archivio_documenti_memoria import ArchivioDocumenti

logger = logging.getLogger(__name__)
FORNITORI_NOLEGGIO = ["ARVAL", "LEASYS", "ALD AUTOMOTIVE", "ALPHABET", "ATHLON", "LEASEPLAN"]


async def cerca_fattura_per_verbale(db: ArchivioDocumenti, numero_verbale: str) -> Optional[Dict[str, Any]]:
    """Cerca una fattura di noleggio che contenga il numero verbale in una delle linee."""
    if not numero_verbale:
        return None
    from app.services.noleggio.processors import FILTRO_FATTURA_ATTIVA

    pattern_regex = re.escape(numero_verbale)
    # Solo fatture attive: una copia archiviata o cancellata non e' una prova.
    q = {**FILTRO_FATTURA_ATTIVA, "$or": [
        {"fornitore_denominazione": {"$regex": "|".join(FORNITORI_NOLEGGIO), "$options": "i"}},
        {"supplier_name": {"$regex": "|".join(FORNITORI_NOLEGGIO), "$options": "i"}},
    ]}
    cursor = db["invoices"].find(q)
    async for f in cursor:
        for linea in f.get("linee", []) or f.get("items", []) or []:
            desc = linea.get("descrizione") or linea.get("description") or ""
            if re.search(pattern_regex, desc, re.IGNORECASE):
                return {
                    "fattura_id": f.get("id") or str(f.get("_id")),
                    "numero_fattura": f.get("numero") or f.get("invoice_number") or f.get("numero_documento"),
                    "data_fattura": f.get("data_documento") or f.get("invoice_date"),
                    "fornitore": f.get("fornitore_denominazione") or f.get("supplier_name"),
                    "importo_fattura": f.get("importo_totale") or f.get("total_amount"),
                    "linea_matchata": desc[:200],
                }
    return None


async def collega_verbali_a_fatture(db: ArchivioDocumenti) -> Dict[str, int]:
    """Giro di rete: collega i verbali senza fattura a quella che ne cita il numero."""
    from app.services.verbali_collegamento_fattura import collega_verbale, fattura_id_del_verbale

    stats = {"processati": 0, "collegati": 0}
    cursor = db["verbali_noleggio"].find(
        {"numero_verbale": {"$exists": True, "$ne": None}},
        {"pdf_data": 0, "quietanza_pdf": 0},
    )
    async for v in cursor:
        # «Senza fattura» si decide in Python: `$in: [None]` non prende il campo assente.
        if fattura_id_del_verbale(v):
            continue
        stats["processati"] += 1
        m = await cerca_fattura_per_verbale(db, v["numero_verbale"])
        if m:
            filtro = {"id": v["id"]} if v.get("id") else {"_id": v["_id"]}
            await collega_verbale(
                db, filtro, m["fattura_id"], m["numero_fattura"], regola="numero_in_riga_fattura",
            )
            stats["collegati"] += 1
    return stats
