"""Proiezione read-only delle prove di pagamento collegate a una fattura."""
from __future__ import annotations

from typing import Any, Dict, List

from app.services.payment_allocation_validator import allocation_status, to_cents


async def project_invoice_payment_evidence(db, invoice: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Restituisce prove navigabili senza creare o modificare record."""
    invoice_id = str(invoice.get("id") or "")
    status = allocation_status(invoice)
    result: List[Dict[str, Any]] = []

    for raw in invoice.get("payment_evidence") or []:
        if not isinstance(raw, dict):
            continue
        result.append({
            "type": raw.get("type") or raw.get("tipo") or "payment_document",
            "status": raw.get("status") or "documented",
            "amount_cents": raw.get("amount_cents", to_cents(raw.get("amount") or raw.get("importo"))),
            "date": raw.get("date") or raw.get("data"),
            "reference": raw.get("reference") or raw.get("riferimento"),
            "bank_movement_id": raw.get("bank_movement_id") or raw.get("movimento_bancario_id"),
            "document_id": raw.get("document_id") or raw.get("id"),
            "source_hash": raw.get("source_hash") or raw.get("sha256"),
            "allocation_id": raw.get("allocation_id"),
            "rule": raw.get("rule") or "stored_evidence",
            "confidence": raw.get("confidence", 1.0),
            "conflict_reason": raw.get("conflict_reason") if status == "conflicting" else None,
        })

    assegni = invoice.get("assegni_collegati") or []
    check_ids = [str(x.get("assegno_id")) for x in assegni if isinstance(x, dict) and x.get("assegno_id")]
    checks = {}
    if check_ids:
        checks_raw = await db["assegni"].find({"id": {"$in": check_ids}}, {"_id": 0}).to_list(500)
        checks = {str(x.get("id")): x for x in checks_raw if x.get("id")}
    for link in assegni:
        if not isinstance(link, dict):
            continue
        aid = str(link.get("assegno_id") or "")
        check = checks.get(aid, {})
        result.append({
            "type": "assegno",
            "status": "confirmed" if link.get("banca_confermata") else "pending_bank",
            "amount_cents": to_cents(link.get("quota")),
            "date": link.get("data_collegamento") or check.get("data_incasso") or check.get("data"),
            "reference": link.get("numero") or check.get("numero"),
            "bank_movement_id": check.get("movimento_estratto_conto_id") or check.get("movimento_id"),
            "document_id": aid or None,
            "source_hash": check.get("document_hash") or check.get("sha256"),
            "allocation_id": f"assegno:{aid}:{invoice_id}" if aid else None,
            "rule": link.get("match_livello") or "assegno_allocation",
            "confidence": 1.0 if link.get("banca_confermata") else 0.5,
            "conflict_reason": "quota_supera_totale_fattura" if status == "conflicting" else None,
        })

    transfer_ids = [str(x) for x in (invoice.get("payment_document_ids") or invoice.get("bonifico_ids") or []) if x]
    if transfer_ids:
        transfers = await db["bonifici_transfers"].find({"id": {"$in": transfer_ids}}, {"_id": 0}).to_list(500)
        for transfer in transfers:
            tid = str(transfer.get("id"))
            result.append({
                "type": "bonifico_pdf",
                "status": "confirmed" if transfer.get("movimento_estratto_conto_id") else "documented",
                "amount_cents": abs(to_cents(transfer.get("importo") or 0)),
                "date": str(transfer.get("data") or "")[:10],
                "reference": transfer.get("causale") or transfer.get("transaction_code"),
                "bank_movement_id": transfer.get("movimento_estratto_conto_id"),
                "document_id": tid,
                "source_hash": transfer.get("document_hash") or transfer.get("sha256"),
                "allocation_id": f"bonifico:{tid}:{invoice_id}",
                "rule": transfer.get("match_rule") or "payment_document_link",
                "confidence": 1.0 if transfer.get("movimento_estratto_conto_id") else 0.7,
                "conflict_reason": None,
            })

    if invoice.get("movimento_bancario_id"):
        movement_id = str(invoice["movimento_bancario_id"])
        movement = await db["estratto_conto_movimenti"].find_one({"id": movement_id}, {"_id": 0})
        result.append({
            "type": "bank_movement",
            "status": "confirmed" if movement else "missing",
            "amount_cents": abs(to_cents((movement or {}).get("importo") or 0)),
            "date": (movement or {}).get("data"),
            "reference": (movement or {}).get("descrizione") or movement_id,
            "bank_movement_id": movement_id,
            "document_id": movement_id,
            "source_hash": (movement or {}).get("document_hash") or (movement or {}).get("sha256"),
            "allocation_id": f"bank:{movement_id}:{invoice_id}",
            "rule": "invoice_bank_movement_link",
            "confidence": 1.0 if movement else 0.0,
            "conflict_reason": "movimento_non_trovato" if not movement else None,
        })
    return result
