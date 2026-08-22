"""Recupero conservativo dei metodi di pagamento dei fornitori.

Le sole fonti ammesse sono lo storico esplicito dell'anagrafica e il
dizionario persistente. Fatture, importi e descrizioni non vengono usati per
dedurre un metodo.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


VALID_METHODS = {
    "cassa", "banca", "misto", "contanti", "assegno", "bonifico", "rid", "carta"
}
MISSING_METHODS = {"", "da_configurare", "altro", "n/d", "sospesa"}


def _vat(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isalnum()).upper()


def _method(value: Any) -> str:
    method = str(value or "").strip().lower()
    return method if method in VALID_METHODS else ""


def _dated_candidate(method: Any, timestamp: Any, source: str) -> dict[str, str] | None:
    normalized = _method(method)
    if not normalized:
        return None
    return {"metodo": normalized, "timestamp": str(timestamp or ""), "fonte": source}


def _choose_candidate(candidates: list[dict[str, str]]) -> tuple[dict[str, str] | None, str]:
    if not candidates:
        return None, "nessuna_fonte_storica"
    dated = [candidate for candidate in candidates if candidate["timestamp"]]
    if dated:
        latest_timestamp = max(candidate["timestamp"] for candidate in dated)
        latest = [candidate for candidate in dated if candidate["timestamp"] == latest_timestamp]
        methods = {candidate["metodo"] for candidate in latest}
        if len(methods) == 1:
            return latest[0], ""
        return None, "conflitto_alla_stessa_data"
    methods = {candidate["metodo"] for candidate in candidates}
    if len(methods) == 1:
        return candidates[0], ""
    return None, "conflitto_senza_data"


async def recover_supplier_payment_methods(db, *, apply: bool = False) -> dict[str, Any]:
    suppliers = await db["fornitori"].find({}, {"_id": 0}).to_list(5000)
    dictionary = await db["supplier_payment_methods"].find({}, {"_id": 0}).to_list(5000)
    history = await db["supplier_payment_history"].find({}, {"_id": 0}).to_list(20000)

    dictionary_by_vat: dict[str, list[dict[str, Any]]] = {}
    history_by_vat: dict[str, list[dict[str, Any]]] = {}
    for row in dictionary:
        dictionary_by_vat.setdefault(_vat(row.get("supplier_vat")), []).append(row)
    for row in history:
        history_by_vat.setdefault(_vat(row.get("supplier_vat")), []).append(row)

    result: dict[str, Any] = {
        "dry_run": not apply,
        "fornitori": len(suppliers),
        "gia_configurati": 0,
        "recuperabili": 0,
        "ripristinati": 0,
        "senza_fonte": 0,
        "conflitti": 0,
        "dettaglio": [],
    }
    now = datetime.now(timezone.utc).isoformat()

    for supplier in suppliers:
        current = str(supplier.get("metodo_pagamento") or "").strip().lower()
        if _method(current) and current not in MISSING_METHODS:
            result["gia_configurati"] += 1
            continue
        vat = _vat(supplier.get("partita_iva") or supplier.get("piva") or supplier.get("vat_number"))
        candidates: list[dict[str, str]] = []
        for event in supplier.get("storico_metodi_pagamento") or []:
            candidate = _dated_candidate(
                event.get("metodo"), event.get("registrato_il") or event.get("dal"), "storico_fornitore"
            )
            if candidate:
                candidates.append(candidate)
        for row in dictionary_by_vat.get(vat, []):
            candidate = _dated_candidate(
                row.get("payment_method"), row.get("updated_at") or row.get("created_at"), "dizionario"
            )
            if candidate:
                candidates.append(candidate)
        for event in history_by_vat.get(vat, []):
            candidate = _dated_candidate(event.get("payment_method"), event.get("changed_at"), "storico_dizionario")
            if candidate:
                candidates.append(candidate)

        chosen, reason = _choose_candidate(candidates)
        if not chosen:
            bucket = "conflitti" if reason.startswith("conflitto") else "senza_fonte"
            result[bucket] += 1
            result["dettaglio"].append({"partita_iva": vat, "esito": reason})
            continue

        result["recuperabili"] += 1
        detail = {"partita_iva": vat, "metodo": chosen["metodo"], "fonte": chosen["fonte"]}
        result["dettaglio"].append(detail)
        if not apply:
            continue

        supplier_id = str(supplier.get("id") or supplier.get("_record_id") or vat)
        await db["supplier_payment_method_recovery_backup"].insert_one({
            "id": f"supplier-method-backup:{supplier_id}:{now}",
            "supplier_id": supplier_id,
            "partita_iva": vat,
            "documento_originale": supplier,
            "metodo_ripristinato": chosen["metodo"],
            "fonte_ripristino": chosen["fonte"],
            "created_at": now,
        })
        supplier_filter = ({"id": supplier["id"]} if supplier.get("id") else {
            "$or": [
                {"partita_iva": supplier.get("partita_iva")},
                {"piva": supplier.get("piva")},
                {"vat_number": supplier.get("vat_number")},
            ]
        })
        await db["fornitori"].update_one(
            supplier_filter,
            {"$set": {
                "metodo_pagamento": chosen["metodo"],
                "metodo_pagamento_ripristinato_il": now,
                "metodo_pagamento_ripristinato_da": chosen["fonte"],
                "updated_at": now,
            }},
        )
        result["ripristinati"] += 1

    return result
