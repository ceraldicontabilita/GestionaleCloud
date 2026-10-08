"""Relazioni canoniche fra fatture di noleggio e veicoli.

La fattura e il veicolo restano entita distinte. Questa collection conserva
soltanto il collegamento esplicito, la sua provenienza e la regola applicata.
La riconciliazione del pagamento bancario non appartiene a questo dominio.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import HTTPException

from .constants import COLLECTION, FORNITORI_NOLEGGIO


COLLECTION_FATTURA_VEICOLO_LINKS = "noleggio_fattura_veicolo_links"
MANUAL_RULE_ID = "NOLEGGIO_FATTURA_VEICOLO_MANUALE_V1"


def normalize_company_id(value: Any) -> str:
    """Normalizza P.IVA/CF aziendale senza dipendere da prefissi o spazi."""

    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper()).removeprefix("IT")


def normalize_contract_reference(value: Any) -> str:
    """Normalizza il riferimento contrattuale conservando tutte le cifre."""

    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def invoice_lookup_query(invoice_id: str) -> Dict[str, Any]:
    """Cerca una fattura tramite gli identificativi stringa del registro."""

    candidates: list[Dict[str, Any]] = [
        {"id": invoice_id},
        {"invoice_id": invoice_id},
    ]
    candidates.insert(0, {"_id": invoice_id})
    return {"$or": candidates}


async def load_manual_vehicle_links(db) -> Dict[str, Dict[str, Any]]:
    """Restituisce i collegamenti manuali indicizzati per id fattura."""

    result: Dict[str, Dict[str, Any]] = {}
    cursor = db[COLLECTION_FATTURA_VEICOLO_LINKS].find({}, {"_id": 0})
    async for link in cursor:
        invoice_id = str(link.get("invoice_id") or "")
        if invoice_id:
            result[invoice_id] = link
    return result


async def associate_invoice_to_vehicle(
    db,
    *,
    invoice_id: str,
    targa: str,
    actor: str = "operatore",
) -> Dict[str, Any]:
    """Crea o aggiorna in modo idempotente una relazione fattura-veicolo."""

    invoice_id = str(invoice_id or "").strip()
    targa = str(targa or "").strip().upper()
    if not invoice_id or not targa:
        raise HTTPException(status_code=400, detail="Fattura e targa sono obbligatorie")

    invoice = await db["invoices"].find_one(
        invoice_lookup_query(invoice_id),
        {
            "_id": 1,
            "id": 1,
            "invoice_id": 1,
            "invoice_number": 1,
            "invoice_date": 1,
            "supplier_name": 1,
            "supplier_vat": 1,
        },
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Fattura non trovata")

    vehicle = await db[COLLECTION].find_one(
        {"targa": targa},
        {"_id": 0, "targa": 1, "fornitore_piva": 1, "contratto": 1},
    )
    if not vehicle:
        raise HTTPException(status_code=404, detail=f"Veicolo {targa} non trovato")

    invoice_vat = normalize_company_id(invoice.get("supplier_vat"))
    vehicle_vat = normalize_company_id(vehicle.get("fornitore_piva"))
    rental_vats = {normalize_company_id(value) for value in FORNITORI_NOLEGGIO.values()}
    if invoice_vat not in rental_vats:
        raise HTTPException(status_code=400, detail="La fattura non appartiene a un fornitore di noleggio")
    if invoice_vat and vehicle_vat and invoice_vat != vehicle_vat:
        raise HTTPException(
            status_code=409,
            detail="Il fornitore della fattura non coincide con quello del veicolo",
        )

    canonical_invoice_id = str(invoice.get("_id") or invoice.get("id") or invoice_id)
    now = datetime.now(timezone.utc)
    link = {
        "invoice_id": canonical_invoice_id,
        "invoice_number": invoice.get("invoice_number"),
        "invoice_date": invoice.get("invoice_date"),
        "supplier_name": invoice.get("supplier_name"),
        "supplier_vat": invoice.get("supplier_vat"),
        "targa": targa,
        "contratto_veicolo": vehicle.get("contratto"),
        "source": "manuale",
        "rule_id": MANUAL_RULE_ID,
        "confirmed_by": actor,
        "updated_at": now,
    }
    await db[COLLECTION_FATTURA_VEICOLO_LINKS].update_one(
        {"invoice_id": canonical_invoice_id},
        {
            "$set": link,
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    return link
