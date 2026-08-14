"""Regole amministrative per riconoscere fornitori nelle causali bancarie."""
from datetime import datetime, timezone
import re
import uuid

from fastapi import HTTPException

from app.services.invoice_payments import InvoiceBankReconciliationRequest, reconcile_invoice_bank_movement

COLLECTION = "bank_supplier_rules"

def normalize(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())

def invoice_supplier(invoice: dict) -> str:
    return str(invoice.get("supplier_name") or invoice.get("fornitore_ragione_sociale") or invoice.get("cedente_nome") or "")

def invoice_total(invoice: dict) -> float:
    return abs(float(invoice.get("total_amount") or invoice.get("importo_totale") or 0))

async def save_rule(db, payload: dict) -> dict:
    reference = str(payload.get("reference_text") or "").strip()
    supplier = str(payload.get("supplier_name") or "").strip()
    if len(reference) < 8 or len(supplier) < 2:
        raise HTTPException(status_code=422, detail="Riferimento bancario e fornitore sono obbligatori")
    normalized = normalize(reference)
    now = datetime.now(timezone.utc).isoformat()
    existing = await db[COLLECTION].find_one({"reference_normalized": normalized})
    doc = {
        "id": (existing or {}).get("id") or str(uuid.uuid4()),
        "reference_text": reference, "reference_normalized": normalized,
        "supplier_name": supplier, "supplier_normalized": normalize(supplier),
        "supplier_vat": str(payload.get("supplier_vat") or "").strip(),
        "active": payload.get("active", True) is not False, "updated_at": now,
    }
    if not existing:
        doc["created_at"] = now
    await db[COLLECTION].update_one({"reference_normalized": normalized}, {"$set": doc}, upsert=True)
    return doc

async def reprocess_rules(db, year: int) -> dict:
    rules = await db[COLLECTION].find({"active": True}, {"_id": 0}).to_list(1000)
    movements = await db["estratto_conto_movimenti"].find({
        "data": {"$regex": f"^{int(year)}"}, "tipo": "uscita", "riconciliato": {"$ne": True},
    }, {"_id": 0}).to_list(50000)
    invoices = await db["invoices"].find({
        "$or": [{"invoice_date": {"$regex": f"^{int(year)}"}}, {"data_fattura": {"$regex": f"^{int(year)}"}}],
        "pagato": {"$ne": True},
    }, {"_id": 0}).to_list(50000)
    linked, ambiguous, no_invoice = [], [], []
    for movement in movements:
        description = " ".join(str(movement.get(k) or "") for k in ("descrizione_originale", "descrizione", "causale"))
        normalized_description = normalize(description)
        rule = next((r for r in rules if r["reference_normalized"] in normalized_description), None)
        if not rule:
            continue
        amount = abs(float(movement.get("importo") or 0))
        movement_date = str(movement.get("data") or "")[:10]
        candidates = []
        for invoice in invoices:
            supplier_ok = rule["supplier_normalized"] in normalize(invoice_supplier(invoice))
            if rule.get("supplier_vat"):
                invoice_vat = str(invoice.get("supplier_vat") or invoice.get("fornitore_partita_iva") or "")
                supplier_ok = supplier_ok or normalize(rule["supplier_vat"]) == normalize(invoice_vat)
            invoice_date = str(invoice.get("invoice_date") or invoice.get("data_fattura") or "")[:10]
            if supplier_ok and abs(invoice_total(invoice) - amount) <= 0.005 and invoice_date <= movement_date:
                candidates.append(invoice)
        candidates.sort(key=lambda i: str(i.get("invoice_date") or i.get("data_fattura") or ""), reverse=True)
        if not candidates:
            no_invoice.append({"movimento_id": movement.get("id"), "importo": amount, "regola_id": rule["id"]})
            continue
        if len(candidates) > 1:
            first_date = str(candidates[0].get("invoice_date") or candidates[0].get("data_fattura") or "")[:10]
            second_date = str(candidates[1].get("invoice_date") or candidates[1].get("data_fattura") or "")[:10]
            if first_date == second_date:
                ambiguous.append({"movimento_id": movement.get("id"), "importo": amount, "fattura_ids": [c.get("id") for c in candidates], "regola_id": rule["id"]})
                continue
        invoice = candidates[0]
        await reconcile_invoice_bank_movement(db, InvoiceBankReconciliationRequest(
            fattura_id=invoice["id"], movimento_id=movement["id"],
            override_reason=f"Regola Admin SDD {rule['id']}: riferimento confermato per {rule['supplier_name']}; importo esatto e fattura precedente piu recente.",
        ))
        invoices = [item for item in invoices if item.get("id") != invoice.get("id")]
        linked.append({"movimento_id": movement["id"], "fattura_id": invoice["id"], "numero_fattura": invoice.get("invoice_number") or invoice.get("numero_documento"), "fornitore": invoice_supplier(invoice), "importo": amount})
    return {"year": int(year), "rules": len(rules), "linked": linked, "linked_count": len(linked), "ambiguous": ambiguous, "ambiguous_count": len(ambiguous), "no_invoice": no_invoice, "no_invoice_count": len(no_invoice)}
