"""Migra fornitori dal DB storico al DB configurato, senza cancellazioni.

La modalita predefinita e dry-run. Usare ``--apply`` solo dopo aver verificato
il riepilogo. Il report contiene esclusivamente conteggi e nessun dato fiscale.
"""
from __future__ import annotations

import argparse
import os
import re
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from pymongo import MongoClient


SOURCE_DB_DEFAULT = "Gestionale"
TARGET_COLLECTION = "fornitori"
VALID_METHODS = {"cassa", "banca", "paypal", "bonifico", "assegno", "misto"}


def normalized_key(value: Any) -> str:
    normalized = re.sub(r"[^A-Z0-9]", "", str(value or "").upper())
    if normalized.startswith("IT") and normalized[2:].isdigit():
        return normalized[2:]
    return normalized


def first_value(document: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = document.get(key)
        if value not in (None, "", []):
            return value
    return None


def normalize_payment_method(value: Any) -> str | None:
    token = re.sub(r"[^a-z0-9]", "", str(value or "").casefold())
    if not token:
        return None
    if token in {"cassa", "contanti", "contante", "cash", "mp01"}:
        return "cassa"
    if "paypal" in token:
        return "paypal"
    if "assegn" in token:
        return "assegno"
    if "misto" in token:
        return "misto"
    if "bonific" in token or token in {"sepa", "sdd", "rid", "riba", "mp05"}:
        return "bonifico"
    if token in {"banca", "bancario", "domiciliazione"}:
        return "banca"
    return token if token in VALID_METHODS else None


def payment_area(method: str | None) -> str | None:
    if method == "cassa":
        return "cassa"
    if method in {"banca", "bonifico", "assegno"}:
        return "banca"
    if method == "paypal":
        return "paypal"
    if method == "misto":
        return "provvisoria"
    return None


def invoice_year(value: Any) -> int | None:
    match = re.search(r"(20\d{2})", str(value or ""))
    return int(match.group(1)) if match else None


def canonical_source(document: dict[str, Any]) -> dict[str, Any] | None:
    raw_vat = first_value(document, "partita_iva", "piva", "vat_number", "supplier_vat")
    key = normalized_key(raw_vat)
    name = str(first_value(document, "ragione_sociale", "denominazione", "nome", "name") or "").strip()
    if len(key) < 8 or len(name) < 2:
        return None
    explicit_method = first_value(document, "metodo_pagamento_predefinito", "metodo_pagamento", "payment_method")
    method = normalize_payment_method(explicit_method)
    locality = first_value(document, "locality", "comune", "citta")
    province = first_value(document, "provincia")
    if locality and province and str(province).casefold() not in str(locality).casefold():
        locality = f"{locality} ({province})"
    count = first_value(document, "source_invoice_count", "fatture_count", "num_fatture", "fatture_totali") or 0
    try:
        count = max(0, int(count))
    except (TypeError, ValueError):
        count = 0
    days = first_value(document, "payment_days", "giorni_pagamento") or 30
    try:
        days = min(365, max(0, int(days)))
    except (TypeError, ValueError):
        days = 30
    return {
        "match_key": key,
        "name": name,
        "vat": f"IT{key}" if len(key) == 11 and key.isdigit() else str(raw_vat).upper(),
        "iban": first_value(document, "iban"),
        "email": first_value(document, "email"),
        "locality": locality,
        "default_payment_method": method,
        "payment_area": payment_area(method),
        "payment_days": days,
        "inventory_enabled": not bool(document.get("esclude_magazzino", False)),
        "source_invoice_count": count,
        "source_last_invoice_year": invoice_year(first_value(document, "ultima_fattura", "ultima_fattura_data")),
    }


def merged_values(source: dict[str, Any], target: dict[str, Any] | None) -> dict[str, Any]:
    if target is None:
        return {**source, "source": "migrazione_db_storico"}
    values = dict(target)
    for field in ("iban", "email", "locality", "default_payment_method", "payment_area"):
        if not values.get(field) and source.get(field):
            values[field] = source[field]
    values["source_invoice_count"] = max(
        int(values.get("source_invoice_count") or 0),
        int(source.get("source_invoice_count") or 0),
    )
    if not values.get("source_last_invoice_year") and source.get("source_last_invoice_year"):
        values["source_last_invoice_year"] = source["source_last_invoice_year"]
    return {key: values.get(key) for key in (
        "match_key", "name", "vat", "iban", "email", "locality",
        "default_payment_method", "payment_area", "payment_days",
        "inventory_enabled", "source_invoice_count", "source_last_invoice_year", "source",
    )}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--source-db", default=SOURCE_DB_DEFAULT)
    args = parser.parse_args()
    mongo_url = os.environ.get("MONGO_URL") or os.environ.get("MONGODB_URI")
    target_name = os.environ.get("DB_NAME")
    if not mongo_url or not target_name:
        raise SystemExit("MONGO_URL/MONGODB_URI e DB_NAME sono obbligatori")
    if args.source_db == target_name:
        raise SystemExit("Database sorgente e destinazione coincidono")

    client = MongoClient(mongo_url)
    source_db = client[args.source_db]
    target_db = client[target_name]
    consolidated: dict[str, dict[str, Any]] = {}
    invalid = duplicates = 0
    for collection_name in ("fornitori", "suppliers"):
        for document in source_db[collection_name].find({}):
            candidate = canonical_source(document)
            if candidate is None:
                invalid += 1
                continue
            key = candidate["match_key"]
            if key in consolidated:
                duplicates += 1
                # La raccolta canonica viene letta per prima e ha precedenza;
                # il legacy secondario completa soltanto campi mancanti.
                consolidated[key] = merged_values(candidate, consolidated[key])
            else:
                consolidated[key] = candidate

    target_collection = target_db[TARGET_COLLECTION]
    policy_collection = target_db["regole_pagamento_fornitori"]
    known_policy_keys = {
        normalized_key(document.get("supplier_vat"))
        for document in policy_collection.find({}, {"supplier_vat": 1})
        if normalized_key(document.get("supplier_vat"))
    }
    created = updated = unchanged = policies_created = 0
    now = datetime.now(timezone.utc)
    for key, source in consolidated.items():
        current = target_collection.find_one({"match_key": key})
        desired = merged_values(source, current)
        comparable = {k: v for k, v in desired.items() if k != "source"}
        if current is None:
            created += 1
            if args.apply:
                target_collection.insert_one({"_id": ObjectId(), **desired, "created_at": now, "updated_at": now})
        elif any(current.get(k) != v for k, v in comparable.items()):
            updated += 1
            if args.apply:
                target_collection.update_one({"_id": current["_id"]}, {"$set": {**comparable, "updated_at": now}})
        else:
            unchanged += 1

        method = desired.get("default_payment_method")
        if not method:
            continue
        policy_vat = desired["vat"]
        if key in known_policy_keys:
            continue
        policies_created += 1
        known_policy_keys.add(key)
        if args.apply:
            policy_collection.insert_one({
                "_id": ObjectId(), "supplier_vat": policy_vat,
                "method": method, "area": payment_area(method),
                "effective_from": now.date().isoformat(),
                "reason": "Migrazione anagrafica dal database storico",
                "created_at": now,
            })

    report = {
        "mode": "apply" if args.apply else "dry-run",
        "source_documents": sum(source_db[name].count_documents({}) for name in ("fornitori", "suppliers")),
        "valid_unique_suppliers": len(consolidated),
        "invalid_without_strong_key": invalid,
        "duplicate_strong_keys": duplicates,
        "target_before": target_collection.count_documents({}) - (created if args.apply else 0),
        "created": created, "updated": updated, "unchanged": unchanged,
        "payment_policies_created": policies_created,
        "deletions": 0,
    }
    if args.apply:
        target_db["migration_audit"].insert_one({**report, "kind": "suppliers_from_legacy", "created_at": now})
        report["target_after"] = target_collection.count_documents({})
    print(report)


if __name__ == "__main__":
    main()
