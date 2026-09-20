"""
Router /api/invoices — lista e dettaglio fatture passive.

Consolidato da invoices_main.py (legacy, basato su un service layer con
schema payment_status/user_id/month_year incompatibile con le fatture
importate da XML) + invoices_main_overlay.py (le route effettivamente in
uso, che leggono lo schema reale coalescendo i campi EN/IT). Il legacy non
aveva chiamanti nel frontend (verificato) ed è stato rimosso insieme al
relativo InvoiceService — vedi memoria/endpoints/03-fatture-fornitori.md
per i dettagli dell'audit che ha portato a questa unificazione.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import Collections, Database
from app.utils.dependencies import get_current_admin_user
from app.services.stato_pagamento_fattura import FILTRO_NON_PAGATE

logger = logging.getLogger(__name__)
router = APIRouter()


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().upper().replace(" ", "")


def _normalize_invoice_number(value: Any) -> str:
    return _normalize_text(value).replace("/", "-")


def _invoice_effective_date(invoice: Dict[str, Any]) -> str:
    return (
        invoice.get("invoice_date")
        or invoice.get("data_documento")
        or invoice.get("data_fattura")
        or ""
    )


def _invoice_total(invoice: Dict[str, Any]) -> float:
    return _as_float(invoice.get("total_amount") or invoice.get("importo_totale"))


def _invoice_score(invoice: Dict[str, Any]) -> int:
    score = 0
    if _as_float(invoice.get("imponibile")) > 0:
        score += 4
    if _as_float(invoice.get("iva")) > 0:
        score += 4
    if invoice.get("riepilogo_iva"):
        score += 3
    if invoice.get("linee"):
        score += 3
    if invoice.get("xml_content"):
        score += 2
    if invoice.get("filename"):
        score += 1
    if invoice.get("supplier_name") or invoice.get("fornitore_ragione_sociale"):
        score += 1
    return score


def _invoice_identity_key(invoice: Dict[str, Any]) -> str:
    number = (
        invoice.get("invoice_number")
        or invoice.get("numero_documento")
        or invoice.get("numero_fattura")
    )
    vat = invoice.get("supplier_vat") or invoice.get("fornitore_partita_iva") or invoice.get("cedente_piva")
    date_value = _invoice_effective_date(invoice)
    total = _invoice_total(invoice)
    if not number or not vat or not date_value:
        return str(invoice.get("id") or "")
    return f"{_normalize_invoice_number(number)}|{_normalize_text(vat)}|{date_value}|{total:.2f}"


def _source_evidence(invoice: Dict[str, Any]) -> tuple[set[str], set[str]]:
    """Restituisce hash e ID degli originali, senza dedurli dai dati contabili."""
    # content_hash_canonico (prefisso "c:"): impronta del CONTENUTO letto
    # dall'XML, uguale fra due copie dello stesso documento anche se i byte
    # differiscono per BOM, a capo o codifica (17/09/2026: 42 coppie
    # legacy↔Drive bloccate come «collisione» per un solo byte).
    hashes = {
        str(invoice.get(name) or "").strip().lower()
        for name in ("content_hash", "file_hash", "source_hash", "sha256", "xml_hash",
                     "content_hash_canonico")
        if invoice.get(name)
    }
    source_ids = {
        str(invoice.get(name) or "").strip()
        for name in ("source_document_id", "drive_file_id", "documents_inbox_id")
        if invoice.get(name)
    }
    for source in invoice.get("source_documents") or []:
        if not isinstance(source, dict):
            continue
        digest = source.get("file_hash") or source.get("sha256")
        source_id = source.get("drive_file_id") or source.get("source_document_id")
        if digest:
            hashes.add(str(digest).strip().lower())
        if source_id:
            source_ids.add(str(source_id).strip())
    return hashes - {""}, source_ids - {""}


def _same_original(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    """Vero solo con prova documentale comune, mai per numero/importo/nome."""
    left_hashes, left_ids = _source_evidence(left)
    right_hashes, right_ids = _source_evidence(right)
    return bool(left_hashes & right_hashes or left_ids & right_ids)


def _dedupe_invoices(invoices: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_key: Dict[str, Dict[str, Any]] = {}
    for invoice in invoices:
        key = _invoice_identity_key(invoice)
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = invoice
            continue
        if not _same_original(existing, invoice):
            # La chiave contabile e' solo un indizio. Mostra entrambe le righe
            # e demandane la verifica, invece di nasconderne una come duplicata.
            existing["duplicate_review_required"] = True
            invoice["duplicate_review_required"] = True
            by_key[f"{key}|review|{invoice.get('id') or len(by_key)}"] = invoice
            continue
        current_rank = (_invoice_score(invoice), invoice.get("updated_at") or invoice.get("created_at") or "")
        existing_rank = (_invoice_score(existing), existing.get("updated_at") or existing.get("created_at") or "")
        if current_rank > existing_rank:
            by_key[key] = invoice
    deduped = list(by_key.values())
    deduped.sort(
        key=lambda invoice: (_invoice_effective_date(invoice), invoice.get("updated_at") or invoice.get("created_at") or ""),
        reverse=True,
    )
    return deduped


async def _load_invoices(query: Dict[str, Any], limit: int, skip: int) -> List[Dict[str, Any]]:
    db = Database.get_db()
    raw_limit = min(max(limit * 10, 1000), 5000)
    invoices = await db[Collections.INVOICES].find(query, {
        "_id": 0,
        "fattura_allegata": 0,
        "document_original_ref": 0,
        "xml_raw": 0,
        "foto": 0,
    }).sort("invoice_date", -1).limit(raw_limit).to_list(raw_limit)
    deduped = _dedupe_invoices(invoices)
    return deduped[skip : skip + limit]


@router.get("")
async def list_invoices(
    supplier_vat: Optional[str] = Query(None, description="Filter by supplier VAT"),
    month_year: Optional[str] = Query(None, description="Filter by month (MM-YYYY)"),
    status: Optional[str] = Query(None, description="Filter by status"),
    anno: Optional[int] = Query(None, description="Filter by year (YYYY)"),
    limit: int = Query(100, description="Limit results", le=1000),
    skip: int = Query(0, description="Skip results"),
) -> List[Dict[str, Any]]:
    # Le soft-delete non devono mai comparire nell'elenco (bug segnalato
    # 18/07/2026: le fatture 2024 eliminate restavano visibili), a meno che
    # non si chieda esplicitamente status=deleted.
    query: Dict[str, Any] = {}
    if status != "deleted":
        query["status"] = {"$nin": ["deleted", "archived"]}

    if anno is not None:
        start = f"{anno}-01-01"
        end = f"{anno}-12-31"
        query["$or"] = [
            {"invoice_date": {"$gte": start, "$lte": end}},
            {"data_documento": {"$gte": start, "$lte": end}},
            {"data_fattura": {"$gte": start, "$lte": end}},
        ]

    if supplier_vat:
        supplier_query = {
            "$or": [
                {"supplier_vat": supplier_vat},
                {"fornitore_partita_iva": supplier_vat},
                {"cedente_piva": supplier_vat},
            ]
        }
        query = {"$and": [query, supplier_query]} if query else supplier_query

    if month_year:
        month_query = {
            "$or": [
                {"month_year": month_year},
                {"invoice_date": {"$regex": f"-{month_year[:2]}-"}} if len(month_year) == 7 else {},
            ]
        }
        month_query["$or"] = [item for item in month_query["$or"] if item]
        query = {"$and": [query, month_query]} if query else month_query

    if status:
        status_query = {"$or": [{"status": status}, {"stato": status}, {"stato_pagamento": status}]}
        query = {"$and": [query, status_query]} if query else status_query

    return await _load_invoices(query, limit=limit, skip=skip)


@router.post("/bonifica-identita")
async def bonifica_identita_fatture_endpoint(
    dry_run: bool = Query(False, description="Solo conteggi, nessuna scrittura"),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Identita' canonica dall'XML per le fatture che ne sono prive, dedup
    provata per hash (archivio reversibile + storno della scrittura doppia),
    storno delle registrazioni non ammesse (archivio storico). Stesso giro
    del job periodico ogni 30 minuti; qui si lancia subito. Il giro reale
    parte in background: esito in `GET .../bonifica-identita/stato`."""
    from app.services import fatture_identita

    db = Database.get_db()
    if dry_run:
        return await fatture_identita.bonifica_identita_fatture(db, dry_run=True)
    if fatture_identita.avvia_bonifica_in_background(db):
        return {"status": "started", "message": "Bonifica identita' fatture avviata"}
    return {"status": "running", "message": "Bonifica gia' in corso",
            **await fatture_identita.stato_bonifica(db)}


@router.get("/bonifica-identita/stato")
async def stato_bonifica_identita_fatture(
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    from app.services import fatture_identita

    return await fatture_identita.stato_bonifica(Database.get_db())


@router.get("/bank-pending")
async def get_bank_pending_invoices() -> Dict[str, Any]:
    db = Database.get_db()
    query = {
        "metodo_pagamento": {"$in": ["banca", "bonifico", "riba", "sdd"]},
        "$or": [
            {"payment_status": {"$ne": "paid"}},
            {"stato_pagamento": {"$ne": "pagata"}},
            {**FILTRO_NON_PAGATE,},
        ],
        "status": {"$ne": "deleted"},
    }
    invoices = await db[Collections.INVOICES].find(query, {"_id": 0}).sort("invoice_date", 1).limit(300).to_list(300)
    deduped = _dedupe_invoices(invoices)
    results = [
        {
            "id": str(invoice.get("id", "")),
            "invoice_number": invoice.get("invoice_number") or invoice.get("numero_documento"),
            "supplier_name": invoice.get("supplier_name") or invoice.get("fornitore_ragione_sociale"),
            "supplier_vat": invoice.get("supplier_vat") or invoice.get("fornitore_partita_iva"),
            "invoice_date": _invoice_effective_date(invoice),
            "due_date": invoice.get("due_date") or invoice.get("data_scadenza"),
            "total_amount": _invoice_total(invoice),
            "payment_method": invoice.get("payment_method") or invoice.get("metodo_pagamento"),
            "alert_level": "normal",
        }
        for invoice in deduped
    ]
    return {"success": True, "count": len(results), "invoices": results}


@router.get("/by-month/{year}/{month}")
async def get_invoices_by_month(year: int, month: int) -> Dict[str, Any]:
    if year < 2000 or year > 2100 or month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="Anno o mese non validi")

    month_year_variants = [f"{year}-{month:02d}", f"{month:02d}-{year}"]
    prefix = f"{year}-{month:02d}"
    query = {
        "$or": [
            {"month_year": {"$in": month_year_variants}},
            {"invoice_date": {"$regex": f"^{prefix}"}},
            {"data_documento": {"$regex": f"^{prefix}"}},
            {"data_fattura": {"$regex": f"^{prefix}"}},
        ]
    }
    invoices = await _load_invoices(query, limit=1000, skip=0)
    total_amount = sum(_invoice_total(invoice) for invoice in invoices)
    total_paid = sum(_as_float(invoice.get("amount_paid")) for invoice in invoices)
    paid_count = sum(
        1
        for invoice in invoices
        if invoice.get("payment_status") == "paid"
        or invoice.get("stato_pagamento") == "pagata"
        or invoice.get("pagato") is True
    )
    result = [
        {
            "id": str(invoice.get("id", "")),
            "invoice_number": invoice.get("invoice_number") or invoice.get("numero_documento"),
            "invoice_date": _invoice_effective_date(invoice),
            "supplier_name": invoice.get("supplier_name") or invoice.get("fornitore_ragione_sociale"),
            "total_amount": _invoice_total(invoice),
            "payment_status": invoice.get("payment_status") or invoice.get("stato_pagamento") or ("paid" if invoice.get("pagato") else "unpaid"),
        }
        for invoice in invoices
    ]
    return {
        "invoices": result,
        "total_count": len(result),
        "year": year,
        "month": month,
        "month_year": f"{year}-{month:02d}",
        "stats": {
            "total_amount": total_amount,
            "total_paid": total_paid,
            "total_unpaid": total_amount - total_paid,
            "paid_count": paid_count,
            "unpaid_count": len(result) - paid_count,
        },
    }


@router.get("/{invoice_id}")
async def get_invoice(invoice_id: str) -> Dict[str, Any]:
    db = Database.get_db()
    invoice = await db[Collections.INVOICES].find_one({"id": invoice_id}, {"_id": 0})
    if invoice:
        return invoice
    try:
        invoice = await db[Collections.INVOICES].find_one({"_id": invoice_id})
        if invoice:
            invoice.pop("_id", None)
            return invoice
    except Exception as exc:  # noqa: BLE001
        logger.debug("[Fatture] ricerca per _id storico non riuscita: %s", exc)
    raise HTTPException(status_code=404, detail="Fattura non trovata")
