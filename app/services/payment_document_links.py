"""Collegamenti canonici fra bonifici PDF, fatture e movimenti bancari.

Il PDF originale resta esclusivamente in ``bonifici_transfers``. Le altre
entita' conservano solo ID, hash e metadati: in questo modo lo stesso file non
viene copiato in piu' collection e rimane sempre possibile risalire alla prova.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List

from app.services.identity_matching import identita_coincide, nome_presente_nel_testo
from app.services.payment_invoice_matching import amounts_equal_to_cent, invoice_reference_in_text


def _invoice_amount(invoice: Dict[str, Any]) -> float:
    for field in ("total_amount", "totale", "importo_totale"):
        value = invoice.get(field)
        if value not in (None, ""):
            try:
                return abs(float(value))
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def _invoice_supplier(invoice: Dict[str, Any]) -> str:
    return str(
        invoice.get("supplier_name")
        or invoice.get("fornitore_denominazione")
        or invoice.get("fornitore")
        or invoice.get("cedente_denominazione")
        or ""
    ).strip()


def _invoice_number(invoice: Dict[str, Any]) -> str:
    return str(invoice.get("invoice_number") or invoice.get("numero_fattura") or "").strip()


def valuta_fattura_bonifico(transfer: Dict[str, Any], invoice: Dict[str, Any]) -> Dict[str, Any]:
    """Una fattura singola e' certa solo con numero, centesimi e fornitore."""
    causale = str(transfer.get("causale") or "")
    beneficiary = transfer.get("beneficiario") or {}
    beneficiary_name = (
        beneficiary.get("nome") if isinstance(beneficiary, dict) else str(beneficiary)
    ) or ""
    supplier = _invoice_supplier(invoice)
    number = _invoice_number(invoice)
    amount_exact = amounts_equal_to_cent(
        abs(float(transfer.get("importo") or 0)), _invoice_amount(invoice)
    )
    supplier_identity = bool(
        beneficiary_name and supplier and identita_coincide(beneficiary_name, supplier)
    )
    supplier_in_text = bool(supplier and nome_presente_nel_testo(supplier, causale))
    invoice_in_text = invoice_reference_in_text(number, causale)
    evidence = []
    if amount_exact:
        evidence.append("importo_esatto")
    if invoice_in_text:
        evidence.append("numero_fattura_in_causale")
    if supplier_identity:
        evidence.append("identita_fornitore")
    if supplier_in_text:
        evidence.append("fornitore_in_causale")
    return {
        "compatibile": amount_exact and invoice_in_text and (supplier_identity or supplier_in_text),
        "evidenze": evidence,
        "score": 100 if amount_exact and invoice_in_text and (supplier_identity or supplier_in_text) else 0,
        "importo_fattura": _invoice_amount(invoice),
    }


def seleziona_fatture_bonifico(transfer: Dict[str, Any], invoices: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Seleziona una fattura o una distinta multi-fattura non ambigua.

    Per una distinta ogni numero deve essere scritto nella causale, tutte le
    fatture devono appartenere allo stesso fornitore coerente col beneficiario e
    la somma deve coincidere al centesimo. Numeri duplicati restano sospesi.
    """
    items = list(invoices)
    singles = [inv for inv in items if valuta_fattura_bonifico(transfer, inv)["compatibile"]]
    if len(singles) == 1:
        return singles
    if len(singles) > 1:
        return []

    causale = str(transfer.get("causale") or "")
    beneficiary = transfer.get("beneficiario") or {}
    beneficiary_name = beneficiary.get("nome") if isinstance(beneficiary, dict) else str(beneficiary)
    referenced = []
    seen_numbers = set()
    for inv in items:
        number = _invoice_number(inv)
        supplier = _invoice_supplier(inv)
        if not number or not invoice_reference_in_text(number, causale):
            continue
        if not supplier or not (
            identita_coincide(beneficiary_name or "", supplier)
            or nome_presente_nel_testo(supplier, causale)
        ):
            continue
        normalized = "".join(ch for ch in number.upper() if ch.isalnum())
        if normalized in seen_numbers:
            return []
        seen_numbers.add(normalized)
        referenced.append(inv)
    if len(referenced) < 2:
        return []
    suppliers = {_invoice_supplier(inv).upper() for inv in referenced}
    if len(suppliers) != 1:
        return []
    total = round(sum(_invoice_amount(inv) for inv in referenced), 2)
    if not amounts_equal_to_cent(abs(float(transfer.get("importo") or 0)), total):
        return []
    return referenced


def payment_document_ref(transfer: Dict[str, Any]) -> Dict[str, Any]:
    transfer_id = str(transfer.get("id") or "")
    return {
        "id": transfer_id,
        "tipo": "bonifico_pdf",
        "nome_file": transfer.get("source_file") or transfer.get("filename") or "bonifico.pdf",
        "sha256": transfer.get("document_hash") or transfer.get("sha256"),
        "data": str(transfer.get("data") or "")[:10],
        "importo": abs(float(transfer.get("importo") or 0)),
        "view_url": f"/api/archivio-bonifici/transfers/{transfer_id}/pdf",
    }


async def collega_bonifico_fatture(db, transfer: Dict[str, Any], invoices: List[Dict[str, Any]], *, auto: bool) -> None:
    """Scrive gli stessi ID su entrambi i lati, in modo idempotente."""
    if not invoices:
        return
    now = datetime.now(timezone.utc).isoformat()
    transfer_id = str(transfer.get("id") or "")
    invoice_ids = [str(inv.get("id")) for inv in invoices if inv.get("id")]
    if not transfer_id or not invoice_ids:
        return
    evidence = ["numero_fattura_in_causale", "importo_esatto_al_centesimo", "identita_fornitore"]
    await db.bonifici_transfers.update_one(
        {"id": transfer_id},
        {"$set": {
            "fattura_associata": True,
            "fattura_id": invoice_ids[0] if len(invoice_ids) == 1 else None,
            "fattura_ids": invoice_ids,
            "fattura_associata_id": invoice_ids[0] if len(invoice_ids) == 1 else None,
            "fattura_associazione_evidenze": evidence,
            "auto_associated": bool(auto),
            "updated_at": now,
        }},
    )
    for invoice_id in invoice_ids:
        await db.invoices.update_one(
            {"id": invoice_id},
            {"$set": {
                "bonifico_associato": True,
                "bonifico_id": transfer_id,
                "updated_at": now,
            }, "$addToSet": {"bonifico_ids": transfer_id, "payment_document_ids": transfer_id}},
        )
    movement_id = transfer.get("movimento_estratto_conto_id")
    if movement_id:
        await propaga_documento_pagamento(db, movement_id, transfer_id, invoice_ids)


async def propaga_documento_pagamento(db, movement_id: str, transfer_id: str, invoice_ids: List[str]) -> None:
    """Collega la prova al movimento EC e alle eventuali righe di Prima Nota."""
    update = {
        "$set": {"bonifico_transfer_id": transfer_id},
        "$addToSet": {"payment_document_ids": transfer_id},
    }
    await db.estratto_conto_movimenti.update_one({"id": movement_id}, update)
    query = {"$or": [
        {"id": movement_id},
        {"estratto_conto_id": movement_id},
        {"movimento_bancario_id": movement_id},
        {"fattura_id": {"$in": invoice_ids}},
    ]}
    await db.prima_nota_banca.update_many(query, update)


async def documenti_pagamento_fattura(db, invoice_id: str) -> List[Dict[str, Any]]:
    invoice = await db.invoices.find_one(
        {"$or": [{"id": invoice_id}, {"invoice_key": invoice_id}]},
        {"_id": 0, "id": 1, "bonifico_id": 1, "bonifico_ids": 1, "payment_document_ids": 1},
    )
    if not invoice:
        return []
    ids = set(invoice.get("bonifico_ids") or []) | set(invoice.get("payment_document_ids") or [])
    if invoice.get("bonifico_id"):
        ids.add(invoice["bonifico_id"])
    query = {"$or": [
        {"id": {"$in": list(ids)}},
        {"fattura_ids": invoice.get("id") or invoice_id},
        {"fattura_id": invoice.get("id") or invoice_id},
        {"fattura_associata_id": invoice.get("id") or invoice_id},
    ]}
    transfers = await db.bonifici_transfers.find(query, {"_id": 0, "pdf_data": 0}).to_list(100)
    return [payment_document_ref(transfer) for transfer in transfers]
