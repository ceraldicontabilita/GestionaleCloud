"""
Trigger B: subito dopo insert di una fattura passiva (XML SDI).
Se il fornitore è noleggio, estrae numeri verbale dalle linee e crea/aggiorna
verbali parziali (anche prima che arrivi la PEC ufficiale).
"""
import re
import uuid
import logging
from datetime import datetime
from typing import Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)
FORNITORI_NOLEGGIO = ["ARVAL", "LEASYS", "ALD", "ALPHABET", "ATHLON", "LEASEPLAN"]
VERBALE_PATTERNS = [
    re.compile(r'\b([A-Z]\d{10,12})\b'),
    re.compile(r'Verbale\s*N?\.?\s*([A-Z0-9]{8,15})', re.IGNORECASE),
    re.compile(r'Multa\s*N?\.?\s*([A-Z0-9]{8,15})', re.IGNORECASE),
]
TARGA_PATTERN = re.compile(r'\b([A-Z]{2}\d{3}[A-Z]{2})\b', re.IGNORECASE)
DATA_INFR_PATTERN = re.compile(r'(?:del|data)[:\s]*(\d{2}/\d{2}/\d{2,4})', re.IGNORECASE)


def _is_fornitore_noleggio(fattura: Dict[str, Any]) -> bool:
    n = (
        (fattura.get("fornitore_denominazione") or "")
        + " "
        + (fattura.get("supplier_name") or "")
    ).upper()
    return any(f in n for f in FORNITORI_NOLEGGIO)


async def processa_fattura_per_verbali(db: AsyncIOMotorDatabase, fattura: Dict[str, Any]) -> Dict[str, Any]:
    if not _is_fornitore_noleggio(fattura):
        return {"skip": True}
    result = {"verbali_trovati": [], "verbali_creati": 0, "verbali_aggiornati": 0}
    fornitore_full = (fattura.get("fornitore_denominazione") or fattura.get("supplier_name") or "").upper()
    fornitore = fornitore_full.split()[0] if fornitore_full else "ARVAL"
    fattura_id = fattura.get("id") or str(fattura.get("_id"))
    visti = set()
    linee = fattura.get("linee") or fattura.get("items") or []
    for linea in linee:
        desc = linea.get("descrizione") or linea.get("description") or ""
        numeri = set()
        for pat in VERBALE_PATTERNS:
            for m in pat.finditer(desc):
                numeri.add(m.group(1).upper())
        for nv in numeri:
            if nv in visti:
                continue
            visti.add(nv)
            tm = TARGA_PATTERN.search(desc)
            dm = DATA_INFR_PATTERN.search(desc)
            importo_linea = linea.get("prezzo_unitario") or linea.get("importo_linea") or linea.get("price") or 0
            existing = await db["verbali_noleggio"].find_one({"numero_verbale": nv})
            if existing:
                fields = {
                    "fattura_associata_id": fattura_id,
                    "fattura_associata_numero": fattura.get("numero") or fattura.get("invoice_number"),
                    "fattura_associata_data": fattura.get("data_documento") or fattura.get("invoice_date"),
                    "fattura_associata_fornitore": fornitore,
                    "fattura_associata_importo": fattura.get("importo_totale") or fattura.get("total_amount"),
                    "updated_at": datetime.utcnow().isoformat(),
                }
                if not existing.get("targa") and tm:
                    fields["targa"] = tm.group(1).upper()
                if not existing.get("data_violazione") and dm:
                    fields["data_violazione"] = dm.group(1)
                if not existing.get("importo") and importo_linea:
                    try:
                        fields["importo_addebitato_fornitore"] = float(importo_linea)
                    except (ValueError, TypeError):
                        pass
                await db["verbali_noleggio"].update_one({"_id": existing["_id"]}, {"$set": fields})
                result["verbali_aggiornati"] += 1
                result["verbali_trovati"].append({"numero_verbale": nv, "azione": "aggiornato"})
            else:
                new_doc = {
                    "id": str(uuid.uuid4()),
                    "numero_verbale": nv,
                    "targa": tm.group(1).upper() if tm else None,
                    "data_violazione": dm.group(1) if dm else None,
                    "importo_addebitato_fornitore": float(importo_linea) if importo_linea else None,
                    "descrizione_da_fattura": desc[:300],
                    "fattura_associata_id": fattura_id,
                    "fattura_associata_numero": fattura.get("numero") or fattura.get("invoice_number"),
                    "fattura_associata_data": fattura.get("data_documento") or fattura.get("invoice_date"),
                    "fattura_associata_fornitore": fornitore,
                    "fattura_associata_importo": fattura.get("importo_totale") or fattura.get("total_amount"),
                    "stato": "notifica_attesa",
                    "source": "fattura_xml_trigger",
                    "creato_il": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                }
                new_doc = {k: v for k, v in new_doc.items() if v is not None}
                await db["verbali_noleggio"].insert_one(new_doc)
                result["verbali_creati"] += 1
                result["verbali_trovati"].append({"numero_verbale": nv, "azione": "creato"})
    return result
