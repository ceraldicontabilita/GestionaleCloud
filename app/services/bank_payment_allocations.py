"""Allocazioni canoniche movimento bancario -> una o piu' fatture."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List
from uuid import uuid4
import re

from fastapi import HTTPException

from app.services.entity_relations import upsert_entity_relation
from app.services.payment_allocation_validator import (
    existing_invoice_allocations_cents,
    invoice_total_cents,
    to_cents,
    validate_invoice_allocation,
)
from app.services.bank_reconciliation_rules import classify_bank_movement
from app.services.scritture_contabili import scrivi_movimento_se_assente


def _supplier_key(invoice: Dict[str, Any]) -> str:
    vat = str(
        invoice.get("supplier_vat") or invoice.get("fornitore_piva")
        or invoice.get("cedente_piva") or ""
    ).strip().upper()
    name = str(
        invoice.get("supplier_name") or invoice.get("fornitore")
        or invoice.get("cedente_denominazione") or ""
    ).strip().upper()
    return vat or name


def _requested_cents(item: Dict[str, Any], invoice: Dict[str, Any]) -> int:
    if isinstance(item.get("quota_cents"), int):
        return int(item["quota_cents"])
    if item.get("quota") not in (None, ""):
        return to_cents(item["quota"])
    total = invoice_total_cents(invoice)
    return max(0, total - existing_invoice_allocations_cents(invoice))


async def validate_bank_invoice_allocations(
    db, movement: Dict[str, Any], associations: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Valida l'intero prospetto prima di qualunque scrittura."""
    items = list(associations or [])
    if not items:
        raise HTTPException(status_code=409, detail="Selezionare almeno una fattura")
    ids = [str(item.get("id") or item.get("fattura_id") or "").strip() for item in items]
    if any(not invoice_id for invoice_id in ids) or len(set(ids)) != len(ids):
        raise HTTPException(status_code=409, detail="Fatture mancanti o duplicate nel prospetto")

    invoices = await db["invoices"].find({"id": {"$in": ids}}).to_list(len(ids))
    by_id = {str(invoice.get("id")): invoice for invoice in invoices}
    if len(by_id) != len(ids):
        missing = [invoice_id for invoice_id in ids if invoice_id not in by_id]
        raise HTTPException(status_code=404, detail=f"Fatture non trovate: {', '.join(missing)}")

    suppliers = {_supplier_key(by_id[invoice_id]) for invoice_id in ids}
    if "" in suppliers or len(suppliers) != 1:
        raise HTTPException(
            status_code=409,
            detail="Allocazione multipla bloccata: le fatture devono appartenere allo stesso fornitore identificato",
        )

    result: List[Dict[str, Any]] = []
    for item, invoice_id in zip(items, ids):
        invoice = by_id[invoice_id]
        quota_cents = _requested_cents(item, invoice)
        allocation_id = f"bank:{movement.get('id')}:{invoice_id}"
        validation = validate_invoice_allocation(
            invoice, quota_cents, allocation_id=allocation_id,
        )
        if not validation["allowed"]:
            raise HTTPException(
                status_code=409,
                detail=f"Fattura {invoice_id}: {validation['reason']}",
            )
        result.append({
            "allocation_id": allocation_id,
            "fattura_id": invoice_id,
            "fattura_numero": invoice.get("invoice_number") or invoice.get("numero_fattura"),
            "fornitore": invoice.get("supplier_name") or invoice.get("fornitore"),
            "quota_cents": quota_cents,
            "totale_fattura_cents": validation["total_cents"],
            "residuo_precedente_cents": validation["residual_cents"] + quota_cents,
            "residuo_successivo_cents": validation["residual_cents"],
            "invoice": invoice,
        })

    movement_cents = abs(to_cents(movement.get("importo")))
    allocated_cents = sum(item["quota_cents"] for item in result)
    if movement_cents <= 0 or allocated_cents != movement_cents:
        raise HTTPException(
            status_code=409,
            detail=(
                "Quadratura bloccata: quote fatture "
                f"{allocated_cents} centesimi, movimento {movement_cents} centesimi"
            ),
        )
    return result


async def persist_bank_invoice_allocations(
    db, movement: Dict[str, Any], allocations: List[Dict[str, Any]], *, actor: str,
) -> Dict[str, Any]:
    """Persiste quote e collegamenti reciproci in modo idempotente."""
    movement_id = str(movement.get("id") or "")
    now = datetime.now(timezone.utc).isoformat()
    public_allocations = []
    for item in allocations:
        public = {key: value for key, value in item.items() if key != "invoice"}
        public.update({
            "movimento_id": movement_id,
            "status": "confirmed",
            "rule_id": "bank.invoice_allocations.manual.v1",
            "confirmed_by": actor,
            "confirmed_at": now,
        })
        public_allocations.append(public)
        existing = await db["bank_payment_allocations"].find_one({"allocation_id": public["allocation_id"]})
        if existing and int(existing.get("quota_cents") or 0) != public["quota_cents"]:
            raise HTTPException(status_code=409, detail="Allocazione esistente con quota differente")
        await db["bank_payment_allocations"].update_one(
            {"allocation_id": public["allocation_id"]},
            {"$setOnInsert": public},
            upsert=True,
        )

    for item in allocations:
        invoice_id = item["fattura_id"]
        invoice_allocations = await db["bank_payment_allocations"].find(
            {"fattura_id": invoice_id, "status": {"$ne": "reversed"}}, {"_id": 0}
        ).to_list(1000)
        invoice = item["invoice"]
        legacy_without_bank = max(
            0,
            existing_invoice_allocations_cents(invoice)
            - sum(int(link.get("quota_cents") or 0) for link in invoice.get("payment_allocations") or []),
        )
        paid_cents = legacy_without_bank + sum(int(link.get("quota_cents") or 0) for link in invoice_allocations)
        total_cents = invoice_total_cents(invoice)
        paid = total_cents > 0 and paid_cents >= total_cents
        movement_ids = sorted({
            str(link.get("movimento_id"))
            for link in invoice_allocations
            if link.get("movimento_id")
        })
        await db["invoices"].update_one(
            {"id": invoice_id},
            {"$set": {
                "payment_allocations": invoice_allocations,
                "importo_pagato": min(paid_cents, total_cents) / 100,
                "pagato": paid,
                "paid": paid,
                "stato_pagamento": "pagata" if paid else "parzialmente_pagata",
                "payment_allocation_status": "valid",
                "movimento_bancario_id": movement_ids[0] if len(movement_ids) == 1 else None,
                "movimento_bancario_ids": movement_ids,
                "updated_at": now,
            }},
        )
        await upsert_entity_relation(
            db,
            source_type="bank_movement", source_id=movement_id,
            relation_type="allocates_invoice_payment",
            target_type="invoice", target_id=invoice_id,
            status="confirmed", rule="exact_cents+same_supplier+manual_selection",
            evidence=[
                {"type": "bank_movement_id", "value": movement_id},
                {"type": "invoice_id", "value": invoice_id},
                {"type": "allocated_cents", "value": item["quota_cents"]},
            ],
            amount=item["quota_cents"] / 100,
            provenance={"collection": "estratto_conto_movimenti", "document_id": movement_id},
            actor=actor,
        )

    invoice_ids = [item["fattura_id"] for item in allocations]
    movement_update = {
        "riconciliato": True,
        "abbinato": True,
        "tipo_riconciliazione": "manuale_allocazione",
        "fattura_id": invoice_ids[0] if len(invoice_ids) == 1 else None,
        "fattura_ids": invoice_ids,
        "allocazioni_fatture": public_allocations,
        "data_riconciliazione": now,
        "updated_at": now,
    }
    await db["estratto_conto_movimenti"].update_one({"id": movement_id}, {"$set": movement_update})

    pn_query = {"$or": [
        {"estratto_conto_id": movement_id},
        {"movimento_bancario_id": movement_id},
        {"movimento_estratto_conto_id": movement_id},
    ]}
    pn_update = {"$set": {
        "fattura_id": invoice_ids[0] if len(invoice_ids) == 1 else None,
        "fattura_ids": invoice_ids,
        "allocazioni_fatture": public_allocations,
        "riconciliato": True,
        "updated_at": now,
    }}
    updated = await db["prima_nota_banca"].update_many(pn_query, pn_update)
    if updated.matched_count == 0:
        await scrivi_movimento_se_assente(db, "banca", pn_query, {
            "id": str(uuid4()),
            "data": str(movement.get("data") or "")[:10],
            "tipo": "uscita" if to_cents(movement.get("importo")) < 0 else "entrata",
            "importo": abs(to_cents(movement.get("importo"))) / 100,
            "categoria": "Pagamenti fatture",
            "descrizione": movement.get("descrizione_originale") or movement.get("descrizione"),
            "estratto_conto_id": movement_id,
            "movimento_bancario_id": movement_id,
            "source": "riconciliazione_manual_allocations",
            "created_at": now,
            **pn_update["$set"],
        })

    return {
        "success": True,
        "movimento_id": movement_id,
        "fattura_ids": invoice_ids,
        "allocazioni": public_allocations,
        "quadratura": {
            "movimento_cents": abs(to_cents(movement.get("importo"))),
            "allocato_cents": sum(item["quota_cents"] for item in allocations),
            "stato": "verificata",
        },
    }


def _invoice_refs(movement: Dict[str, Any]) -> List[str]:
    text = " ".join(str(movement.get(field) or "") for field in (
        "descrizione_originale", "descrizione", "causale", "numero_fattura",
    ))
    match = re.search(r"saldo\s+fattur[ea]s?\s+([\d\s,;/-]+)", text, re.IGNORECASE)
    source = match.group(1) if match else str(movement.get("numero_fattura") or "")
    refs = re.findall(r"\d{5,12}", source)
    return list(dict.fromkeys(refs))


async def reconcile_deterministic_invoice_allocations(
    db, *, movement_ids=None, anno=None,
) -> Dict[str, Any]:
    """Collega automaticamente solo distinte con riferimenti univoci e quadrati."""
    query: Dict[str, Any] = {"riconciliato": {"$ne": True}}
    if movement_ids:
        query["id"] = {"$in": [str(value) for value in movement_ids if value]}
    if anno:
        query["data"] = {"$regex": f"^{anno}"}
    movements = await db["estratto_conto_movimenti"].find(query, {"_id": 0}).to_list(5000)
    stats = {"esaminati": len(movements), "allocati": 0, "sospesi": 0, "errori": []}
    for movement in movements:
        classification = classify_bank_movement(movement)
        refs = _invoice_refs(movement)
        if not classification or classification["tipo"] != "fattura_sdd" or not refs:
            continue
        associations = []
        ambiguous = False
        for ref in refs:
            candidates = await db["invoices"].find({
                "$or": [
                    {"invoice_number": ref},
                    {"numero_fattura": ref},
                ],
                "pagato": {"$ne": True},
            }, {"_id": 0}).to_list(2)
            if len(candidates) != 1:
                ambiguous = True
                break
            invoice = candidates[0]
            if str(invoice.get("invoice_date") or "")[:10] > str(movement.get("data") or "")[:10]:
                ambiguous = True
                break
            residual = max(
                0, invoice_total_cents(invoice) - existing_invoice_allocations_cents(invoice),
            )
            associations.append({"id": invoice["id"], "quota_cents": residual})
        if ambiguous or len(associations) != len(refs):
            stats["sospesi"] += 1
            continue
        try:
            allocations = await validate_bank_invoice_allocations(db, movement, associations)
            await persist_bank_invoice_allocations(
                db, movement, allocations, actor="automatic_import",
            )
            stats["allocati"] += 1
        except HTTPException as exc:
            stats["sospesi"] += 1
            stats["errori"].append({"movimento_id": movement.get("id"), "motivo": exc.detail})
    return stats
