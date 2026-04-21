"""
Collega i verbali alle fatture del fornitore di noleggio.
Trigger B: chiamato dopo insert di una fattura XML ARVAL/Leasys/ALD/etc.
"""
import re
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)
FORNITORI_NOLEGGIO = ["ARVAL", "LEASYS", "ALD AUTOMOTIVE", "ALPHABET", "ATHLON", "LEASEPLAN"]


async def cerca_fattura_per_verbale(db: AsyncIOMotorDatabase, numero_verbale: str) -> Optional[Dict[str, Any]]:
    """Cerca una fattura di noleggio che contenga il numero verbale in una delle linee."""
    if not numero_verbale:
        return None
    pattern_regex = re.escape(numero_verbale)
    q = {"$or": [
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


async def collega_verbali_a_fatture(db: AsyncIOMotorDatabase) -> Dict[str, int]:
    stats = {"processati": 0, "collegati": 0}
    cursor = db["verbali_noleggio"].find({
        "numero_verbale": {"$exists": True, "$ne": None},
        "fattura_associata_id": {"$exists": False},
    })
    async for v in cursor:
        stats["processati"] += 1
        m = await cerca_fattura_per_verbale(db, v["numero_verbale"])
        if m:
            await db["verbali_noleggio"].update_one(
                {"_id": v["_id"]},
                {"$set": {
                    "fattura_associata_id": m["fattura_id"],
                    "fattura_associata_numero": m["numero_fattura"],
                    "fattura_associata_data": m["data_fattura"],
                    "fattura_associata_fornitore": m["fornitore"],
                    "fattura_associata_importo": m["importo_fattura"],
                    "updated_at": datetime.utcnow().isoformat(),
                }}
            )
            await db["invoices"].update_one(
                {"$or": [{"id": m["fattura_id"]}, {"_id": m["fattura_id"]}]},
                {"$addToSet": {"verbali_collegati": v.get("numero_verbale")}}
            )
            stats["collegati"] += 1
    return stats
