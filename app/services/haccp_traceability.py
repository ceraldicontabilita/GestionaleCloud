"""Tracciabilita HACCP derivata dalle fatture canoniche di GestionaleCloud.

La fattura resta l'unica fonte dell'acquisto. Questo servizio materializza
soltanto le righe merce utili alla ricezione e permette poi all'operatore di
registrare lotto e scadenza realmente osservati. Non inventa mai questi dati.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from app.db_collections import (
    COLL_HACCP_LOTS,
    COLL_HACCP_LOT_MOVEMENTS,
    COLL_HACCP_PURCHASE_LINES,
    COLL_INVOICES,
)

PARSER_VERSION = "haccp-invoice-lines/1.0"
PAYLOAD_SCHEMA_VERSION = "1"
OPEN_STATES = {"ATTESO", "DA_VERIFICARE", "IN_ELABORAZIONE", "ERRORE"}

_SERVICE_WORDS = (
    "ABBONAMENTO", "AFFITTO", "ASSICURAZIONE", "CANONE", "COMMISSIONE",
    "CONSEGNA", "CONSULENZA", "MANUTENZIONE", "NOLEGGIO", "SERVIZIO",
    "SPESE DI TRASPORTO", "TRASPORTO",
)
_LOT_KEYS = {"LOT", "LOTTO", "NLOTTO", "NUMEROLOTTO", "BATCH"}
_EXPIRY_KEYS = {"SCADENZA", "DATASCADENZA", "EXPIRY", "EXP"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_key(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", _text(value).upper())


def decimal_string(value: Any, default: str = "0") -> str:
    """Normalizza un numero senza passare da float."""
    raw = _text(value)
    if not raw:
        raw = default
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    else:
        raw = raw.replace(",", ".")
    try:
        result = Decimal(raw)
    except (InvalidOperation, ValueError):
        result = Decimal(default)
    return format(result.normalize(), "f") if result else "0"


def invoice_year(invoice: dict[str, Any]) -> int | None:
    raw = invoice.get("anno")
    try:
        if raw not in (None, ""):
            return int(raw)
    except (TypeError, ValueError):
        pass
    raw_date = _text(invoice.get("invoice_date") or invoice.get("data_documento") or invoice.get("data"))
    return int(raw_date[:4]) if len(raw_date) >= 4 and raw_date[:4].isdigit() else None


def is_service_line(line: dict[str, Any]) -> bool:
    description = _text(line.get("descrizione") or line.get("description")).upper()
    return not description or any(word in description for word in _SERVICE_WORDS)


def _explicit_lot_data(line: dict[str, Any]) -> tuple[str, str]:
    """Legge solo campi strutturati dell'XML; nessuna inferenza dal nome."""
    lot_number = ""
    expiry = ""
    for item in line.get("altri_dati_gestionali") or []:
        key = _normalized_key(item.get("tipo_dato"))
        value = _text(item.get("riferimento_testo") or item.get("riferimento_data"))
        if key in _LOT_KEYS and value:
            lot_number = value
        elif key in _EXPIRY_KEYS and value:
            expiry = value
    return lot_number, expiry


def _invoice_identity(invoice: dict[str, Any]) -> str:
    identity = _text(invoice.get("id") or invoice.get("invoice_key"))
    if identity:
        return identity
    raw = "|".join((
        _text(invoice.get("supplier_vat")),
        _text(invoice.get("invoice_number")),
        _text(invoice.get("invoice_date")),
    ))
    return sha256(raw.encode("utf-8")).hexdigest()


def build_purchase_lines(invoice: dict[str, Any]) -> list[dict[str, Any]]:
    """Crea candidati deterministici dalle righe merce di una fattura."""
    identity = _invoice_identity(invoice)
    invoice_date = _text(invoice.get("invoice_date") or invoice.get("data_documento") or invoice.get("data"))[:10]
    supplier = invoice.get("fornitore") if isinstance(invoice.get("fornitore"), dict) else {}
    supplier_name = _text(invoice.get("supplier_name") or supplier.get("denominazione"))
    supplier_vat = _text(invoice.get("supplier_vat") or supplier.get("partita_iva"))
    source_lines = invoice.get("linee") or invoice.get("righe") or []
    results: list[dict[str, Any]] = []

    for index, line in enumerate(source_lines):
        if not isinstance(line, dict) or is_service_line(line):
            continue
        description = _text(line.get("descrizione") or line.get("description"))
        number = _text(line.get("numero_linea")) or str(index + 1)
        fingerprint_payload = {
            "description": description,
            "quantity": decimal_string(line.get("quantita"), "1"),
            "unit": _text(line.get("unita_misura") or line.get("unita")),
            "unit_price": decimal_string(line.get("prezzo_unitario")),
            "line_total": decimal_string(line.get("prezzo_totale")),
        }
        digest = sha256(json.dumps(fingerprint_payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]
        canonical_id = f"haccp_purchase_line:{identity}:{number}:{digest}"
        lot_number, expiry_date = _explicit_lot_data(line)
        missing = [name for name, value in (
            ("lot_number", lot_number), ("expiry_date", expiry_date)
        ) if not value]
        now = datetime.now(timezone.utc).isoformat()
        results.append({
            "id": canonical_id,
            "canonical_id": canonical_id,
            "operation_id": str(uuid5(NAMESPACE_URL, canonical_id)),
            "anno": invoice_year(invoice),
            "data": invoice_date,
            "invoice_id": _text(invoice.get("id")),
            "invoice_key": _text(invoice.get("invoice_key")),
            "invoice_number": _text(invoice.get("invoice_number")),
            "invoice_date": invoice_date,
            "supplier_id": _text(invoice.get("supplier_id") or invoice.get("fornitore_id")),
            "supplier_name": supplier_name,
            "supplier_vat": supplier_vat,
            "line_number": number,
            "description": description,
            "quantity": fingerprint_payload["quantity"],
            "unit": fingerprint_payload["unit"],
            "unit_price": fingerprint_payload["unit_price"],
            "line_total": fingerprint_payload["line_total"],
            "document_lot_number": lot_number,
            "document_expiry_date": expiry_date,
            "missing_fields": missing,
            "status": "DA_VERIFICARE" if missing else "ATTESO",
            "source": "invoices",
            "source_external_id": identity,
            "documento_id": _text(invoice.get("documento_inbox_id") or invoice.get("drive_file_id")),
            "fattura_id": _text(invoice.get("id")),
            "file_hash": _text(invoice.get("file_hash") or invoice.get("sha256")),
            "parser_version": PARSER_VERSION,
            "payload_schema_version": PAYLOAD_SCHEMA_VERSION,
            "created_at": now,
            "updated_at": now,
        })
    return results


async def invoices_for_year(db, year: int) -> list[dict[str, Any]]:
    query = {"$or": [
        {"anno": year},
        {"anno": str(year)},
        {"invoice_date": {"$regex": f"^{year}-"}},
    ]}
    return await db[COLL_INVOICES].find(query, {"_id": 0}).limit(20000).to_list(20000)


async def preview_invoice_sync(db, year: int) -> dict[str, Any]:
    invoices = await invoices_for_year(db, year)
    candidates = [candidate for invoice in invoices for candidate in build_purchase_lines(invoice)]
    existing_ids = set(await db[COLL_HACCP_PURCHASE_LINES].distinct(
        "canonical_id", {"anno": year}
    ))
    new_items = [item for item in candidates if item["canonical_id"] not in existing_ids]
    return {
        "year": year,
        "invoices": len(invoices),
        "merchandise_lines": len(candidates),
        "new_lines": len(new_items),
        "unchanged_lines": len(candidates) - len(new_items),
        "requiring_review": sum(item["status"] == "DA_VERIFICARE" for item in candidates),
        "sample": new_items[:25],
        "_new_items": new_items,
    }


async def sync_invoice_lines(db, year: int, *, dry_run: bool = True) -> dict[str, Any]:
    preview = await preview_invoice_sync(db, year)
    new_items = preview.pop("_new_items")
    if not dry_run:
        for item in new_items:
            await db[COLL_HACCP_PURCHASE_LINES].update_one(
                {"canonical_id": item["canonical_id"]},
                {"$setOnInsert": item},
                upsert=True,
            )
    return {**preview, "dry_run": dry_run, "written": 0 if dry_run else len(new_items)}


def validate_iso_date(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError) as exc:
        raise ValueError("La data deve essere nel formato YYYY-MM-DD") from exc


async def create_lot_from_purchase_line(
    db,
    *,
    purchase_line_id: str,
    lot_number: str,
    expiry_date: str,
    quantity_received: Any,
    received_date: str,
    user_id: str,
) -> tuple[dict[str, Any], bool]:
    purchase = await db[COLL_HACCP_PURCHASE_LINES].find_one(
        {"canonical_id": purchase_line_id}, {"_id": 0}
    )
    if not purchase:
        raise LookupError("Riga di acquisto non trovata")
    lot_number = _text(lot_number)
    if not lot_number:
        raise ValueError("Il numero di lotto e obbligatorio")
    expiry_date = validate_iso_date(expiry_date)
    received_date = validate_iso_date(received_date)
    quantity = Decimal(decimal_string(quantity_received))
    if quantity <= 0:
        raise ValueError("La quantita ricevuta deve essere maggiore di zero")

    canonical_id = "haccp_lot:" + sha256(
        f"{purchase_line_id}|{lot_number.upper()}".encode("utf-8")
    ).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    lot = {
        "id": canonical_id,
        "canonical_id": canonical_id,
        "operation_id": str(uuid5(NAMESPACE_URL, canonical_id)),
        "purchase_line_id": purchase_line_id,
        "invoice_id": purchase.get("invoice_id", ""),
        "fattura_id": purchase.get("fattura_id", ""),
        "invoice_number": purchase.get("invoice_number", ""),
        "supplier_id": purchase.get("supplier_id", ""),
        "supplier_name": purchase.get("supplier_name", ""),
        "supplier_vat": purchase.get("supplier_vat", ""),
        "product_description": purchase.get("description", ""),
        "lot_number": lot_number,
        "expiry_date": expiry_date,
        "received_date": received_date,
        "quantity_received": format(quantity.normalize(), "f"),
        "quantity_available": format(quantity.normalize(), "f"),
        "unit": purchase.get("unit", ""),
        "status": "ATTIVO",
        "source": "manual_receipt_from_invoice",
        "source_external_id": purchase_line_id,
        "documento_id": purchase.get("documento_id", ""),
        "file_hash": purchase.get("file_hash", ""),
        "parser_version": PARSER_VERSION,
        "payload_schema_version": PAYLOAD_SCHEMA_VERSION,
        "created_by": user_id,
        "created_at": now,
        "updated_at": now,
    }
    result = await db[COLL_HACCP_LOTS].update_one(
        {"canonical_id": canonical_id},
        {"$setOnInsert": lot},
        upsert=True,
    )
    created = bool(result.upserted_id)
    stored = await db[COLL_HACCP_LOTS].find_one({"canonical_id": canonical_id}, {"_id": 0})
    if not created:
        return stored, False

    related_lots = await db[COLL_HACCP_LOTS].find(
        {"purchase_line_id": purchase_line_id}, {"_id": 0, "quantity_received": 1}
    ).limit(1000).to_list(1000)
    received_total = sum(
        (Decimal(decimal_string(item.get("quantity_received"))) for item in related_lots),
        Decimal("0"),
    )
    expected_total = Decimal(decimal_string(purchase.get("quantity"), "1"))
    if received_total == expected_total:
        purchase_status = "SODDISFATTO"
    elif received_total < expected_total:
        purchase_status = "IN_ELABORAZIONE"
    else:
        # Una consegna superiore alla quantita fatturata e possibile, ma non
        # viene chiusa automaticamente: richiede verifica umana.
        purchase_status = "DA_VERIFICARE"
    remaining = max(expected_total - received_total, Decimal("0"))
    await db[COLL_HACCP_PURCHASE_LINES].update_one(
        {"canonical_id": purchase_line_id},
        {"$set": {
            "status": purchase_status,
            "lot_id": canonical_id,
            "quantity_received_total": format(received_total.normalize(), "f") if received_total else "0",
            "quantity_remaining": format(remaining.normalize(), "f") if remaining else "0",
            "updated_at": now,
        }},
    )
    return stored, True


async def haccp_overview(db, year: int) -> dict[str, Any]:
    today = date.today().isoformat()
    lines = await db[COLL_HACCP_PURCHASE_LINES].find({"anno": year}, {"_id": 0}).limit(20000).to_list(20000)
    lots = await db[COLL_HACCP_LOTS].find({}, {"_id": 0}).limit(20000).to_list(20000)
    year_lots = [lot for lot in lots if _text(lot.get("received_date")).startswith(str(year))]
    return {
        "year": year,
        "purchase_lines": len(lines),
        "requiring_review": sum(item.get("status") in OPEN_STATES for item in lines),
        "lots": len(year_lots),
        "expired_lots": sum(
            bool(lot.get("expiry_date")) and lot["expiry_date"] < today and lot.get("status") == "ATTIVO"
            for lot in year_lots
        ),
        "source": "GestionaleCloud invoices -> Drive/Sheets",
    }


async def record_lot_movement(
    db,
    *,
    lot_id: str,
    movement_type: str,
    quantity: Any,
    reason: str,
    client_operation_id: str,
    user_id: str,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    """Registra uno scarico append-only e aggiorna la disponibilita del lotto."""
    movement_type = _text(movement_type).upper()
    if movement_type not in {"CONSUMO", "SCARTO"}:
        raise ValueError("Tipo movimento non valido")
    client_operation_id = _text(client_operation_id)
    if not client_operation_id:
        raise ValueError("client_operation_id e obbligatorio")
    amount = Decimal(decimal_string(quantity))
    if amount <= 0:
        raise ValueError("La quantita deve essere maggiore di zero")

    lot = await db[COLL_HACCP_LOTS].find_one({"canonical_id": lot_id}, {"_id": 0})
    if not lot:
        raise LookupError("Lotto non trovato")
    movement_id = "haccp_movement:" + sha256(client_operation_id.encode("utf-8")).hexdigest()
    existing = await db[COLL_HACCP_LOT_MOVEMENTS].find_one(
        {"canonical_id": movement_id}, {"_id": 0}
    )
    if existing:
        return existing, lot, False

    available = Decimal(decimal_string(lot.get("quantity_available")))
    if amount > available:
        raise ValueError(
            f"Quantita non disponibile: massimo {format(available.normalize(), 'f')} {lot.get('unit', '')}".strip()
        )
    remaining = available - amount
    now = datetime.now(timezone.utc).isoformat()
    movement = {
        "id": movement_id,
        "canonical_id": movement_id,
        "operation_id": client_operation_id,
        "lot_id": lot_id,
        "purchase_line_id": lot.get("purchase_line_id", ""),
        "fattura_id": lot.get("fattura_id", ""),
        "movement_type": movement_type,
        "direction": "OUT",
        "quantity": format(amount.normalize(), "f"),
        "unit": lot.get("unit", ""),
        "balance_after": format(remaining.normalize(), "f") if remaining else "0",
        "reason": _text(reason),
        "source": "manual_lot_movement",
        "source_external_id": client_operation_id,
        "created_by": user_id,
        "created_at": now,
        "payload_schema_version": PAYLOAD_SCHEMA_VERSION,
    }
    result = await db[COLL_HACCP_LOT_MOVEMENTS].update_one(
        {"canonical_id": movement_id}, {"$setOnInsert": movement}, upsert=True
    )
    created = bool(result.upserted_id)
    stored = await db[COLL_HACCP_LOT_MOVEMENTS].find_one(
        {"canonical_id": movement_id}, {"_id": 0}
    )
    if created:
        await db[COLL_HACCP_LOTS].update_one(
            {"canonical_id": lot_id},
            {"$set": {
                "quantity_available": movement["balance_after"],
                "status": "ESAURITO" if remaining == 0 else "ATTIVO",
                "updated_at": now,
            }},
        )
    updated_lot = await db[COLL_HACCP_LOTS].find_one({"canonical_id": lot_id}, {"_id": 0})
    return stored, updated_lot, created


async def lot_trace(db, lot_id: str) -> dict[str, Any]:
    lot = await db[COLL_HACCP_LOTS].find_one({"canonical_id": lot_id}, {"_id": 0})
    if not lot:
        raise LookupError("Lotto non trovato")
    movements = await db[COLL_HACCP_LOT_MOVEMENTS].find(
        {"lot_id": lot_id}, {"_id": 0}
    ).sort("created_at", -1).limit(1000).to_list(1000)
    return {"lot": lot, "movements": movements}
