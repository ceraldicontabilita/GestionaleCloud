"""Dominio operativo HACCP nativo di GestionaleCloud.

I registri sono append-only, le ricette sono versionate e le produzioni
consumano lotti esplicitamente selezionati. Tutto persiste nei fogli del
registro Drive/Sheets; fatture, fornitori e prodotti restano quelli canonici.
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
    COLL_HACCP_EQUIPMENT,
    COLL_HACCP_EXPECTATIONS,
    COLL_HACCP_LOTS,
    COLL_HACCP_LOT_MOVEMENTS,
    COLL_HACCP_PRODUCTIONS,
    COLL_HACCP_RECIPES,
    COLL_HACCP_REGISTER_ENTRIES,
)
from app.services.haccp_traceability import decimal_string, record_lot_movement, validate_iso_date

SCHEMA_VERSION = "haccp-domain/1.0"
OPEN_STATES = {"ATTESO", "DA_VERIFICARE", "IN_ELABORAZIONE", "ERRORE"}
REGISTER_TYPES = {
    "TEMPERATURA_POSITIVA": {"label": "Temperature positive", "unit": "°C", "min": "0", "max": "4"},
    "TEMPERATURA_NEGATIVA": {"label": "Temperature negative", "unit": "°C", "min": "-22", "max": "-18"},
    "TEMPERATURA_COTTURA": {"label": "Temperature cottura", "unit": "°C", "min": "75", "max": ""},
    "SANIFICAZIONE": {"label": "Sanificazione", "unit": "", "min": "", "max": ""},
    "DISINFESTAZIONE": {"label": "Disinfestazione", "unit": "", "min": "", "max": ""},
    "CONTROLLO_OLIO": {"label": "Controllo olio frittura", "unit": "°C", "min": "", "max": "175"},
    "RICEZIONE_MERCE": {"label": "Controllo ricezione merce", "unit": "°C", "min": "", "max": ""},
    "ANOMALIA": {"label": "Anomalia", "unit": "", "min": "", "max": ""},
    "ALLERGENI": {"label": "Controllo allergeni", "unit": "", "min": "", "max": ""},
    "SCHEDA_TECNICA": {"label": "Scheda tecnica", "unit": "", "min": "", "max": ""},
    "FORMAZIONE_PERSONALE": {"label": "Formazione personale", "unit": "", "min": "", "max": ""},
    "MANUTENZIONE_ATTREZZATURA": {"label": "Manutenzione attrezzatura", "unit": "", "min": "", "max": ""},
    "CHIUSURA_GIORNALIERA": {"label": "Chiusura giornaliera", "unit": "", "min": "", "max": ""},
    "COLLAUDO": {"label": "Collaudo", "unit": "", "min": "", "max": ""},
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", _text(value)).casefold()


def _decimal(value: Any, *, required: bool = False) -> Decimal | None:
    raw = _text(value)
    if not raw:
        if required:
            raise ValueError("Il valore numerico e obbligatorio")
        return None
    normalized = decimal_string(raw, "0")
    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError("Valore numerico non valido") from exc


def _decimal_out(value: Decimal | None) -> str:
    if value is None:
        return ""
    return format(value.normalize(), "f") if value else "0"


def _canonical(prefix: str, key: str) -> str:
    return f"{prefix}:" + sha256(key.encode("utf-8")).hexdigest()


def _operation_id(canonical_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, canonical_id))


def _payload_hash(payload: dict[str, Any]) -> str:
    return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def register_catalog() -> list[dict[str, str]]:
    return [{"id": key, **value} for key, value in REGISTER_TYPES.items()]


async def _equipment_thresholds(db, equipment_id: str) -> tuple[str, str, str]:
    if not equipment_id:
        return "", "", "catalogo"
    item = await db[COLL_HACCP_EQUIPMENT].find_one(
        {"canonical_id": equipment_id, "active": {"$ne": False}}, {"_id": 0}
    )
    if not item:
        return "", "", "catalogo"
    return _text(item.get("threshold_min")), _text(item.get("threshold_max")), "attrezzatura"


def _evaluate_control(
    register_type: str,
    value: Decimal | None,
    threshold_min: Decimal | None,
    threshold_max: Decimal | None,
    declared_compliant: bool | None,
    extra: dict[str, Any],
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    compliant = True if declared_compliant is None else declared_compliant
    if value is not None and threshold_min is not None and value < threshold_min:
        compliant = False
        reasons.append(f"valore inferiore alla soglia minima {_decimal_out(threshold_min)}")
    if value is not None and threshold_max is not None and value > threshold_max:
        compliant = False
        reasons.append(f"valore superiore alla soglia massima {_decimal_out(threshold_max)}")
    if register_type == "CONTROLLO_OLIO":
        polarity = _decimal(extra.get("polarita"))
        if polarity is not None and polarity >= Decimal("25"):
            compliant = False
            reasons.append("polarita uguale o superiore al 25%")
        if extra.get("odore_ok") is False:
            compliant = False
            reasons.append("odore non conforme")
        color = _decimal(extra.get("colore"))
        if color is not None and color >= Decimal("4"):
            compliant = False
            reasons.append("colore olio non conforme")
    return compliant, reasons


async def create_register_entry(
    db,
    *,
    register_type: str,
    event_date: str,
    subject: str,
    operator: str,
    client_operation_id: str,
    value: Any = None,
    unit: str = "",
    threshold_min: Any = None,
    threshold_max: Any = None,
    equipment_id: str = "",
    compliant: bool | None = None,
    corrective_action: str = "",
    notes: str = "",
    extra: dict[str, Any] | None = None,
    user_id: str,
) -> tuple[dict[str, Any], bool]:
    register_type = _text(register_type).upper()
    if register_type not in REGISTER_TYPES:
        raise ValueError("Tipo registro HACCP non valido")
    event_date = validate_iso_date(event_date)
    subject = _text(subject)
    if not subject:
        raise ValueError("Oggetto del controllo obbligatorio")
    client_operation_id = _text(client_operation_id)
    if len(client_operation_id) < 8:
        raise ValueError("client_operation_id deve contenere almeno 8 caratteri")

    catalog = REGISTER_TYPES[register_type]
    equipment_min, equipment_max, threshold_source = await _equipment_thresholds(db, equipment_id)
    min_raw = _text(threshold_min) or equipment_min or catalog["min"]
    max_raw = _text(threshold_max) or equipment_max or catalog["max"]
    numeric_value = _decimal(value)
    minimum = _decimal(min_raw)
    maximum = _decimal(max_raw)
    extra = dict(extra or {})
    is_compliant, reasons = _evaluate_control(
        register_type, numeric_value, minimum, maximum, compliant, extra
    )

    canonical_id = _canonical("haccp_register", client_operation_id)
    existing = await db[COLL_HACCP_REGISTER_ENTRIES].find_one(
        {"canonical_id": canonical_id}, {"_id": 0}
    )
    if existing:
        return existing, False

    timestamp = _now()
    operation_id = _operation_id(canonical_id)
    entry = {
        "id": canonical_id,
        "canonical_id": canonical_id,
        "operation_id": operation_id,
        "anno": int(event_date[:4]),
        "data": event_date,
        "event_date": event_date,
        "register_type": register_type,
        "register_label": catalog["label"],
        "subject": subject,
        "equipment_id": _text(equipment_id),
        "operator": _text(operator) or user_id,
        "value": _decimal_out(numeric_value),
        "unit": _text(unit) or catalog["unit"],
        "threshold_min": _decimal_out(minimum),
        "threshold_max": _decimal_out(maximum),
        "threshold_source": threshold_source,
        "compliant": is_compliant,
        "non_conformity_reasons": reasons,
        "corrective_action": _text(corrective_action),
        "notes": _text(notes),
        "extra": extra,
        "status": "SODDISFATTO" if is_compliant else "DA_VERIFICARE",
        "source": "haccp_manual_control",
        "source_external_id": client_operation_id,
        "payload_schema_version": SCHEMA_VERSION,
        "created_by": user_id,
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    entry["payload_hash"] = _payload_hash(entry)
    result = await db[COLL_HACCP_REGISTER_ENTRIES].update_one(
        {"canonical_id": canonical_id}, {"$setOnInsert": entry}, upsert=True
    )
    created = bool(result.upserted_id)
    stored = await db[COLL_HACCP_REGISTER_ENTRIES].find_one(
        {"canonical_id": canonical_id}, {"_id": 0}
    )
    if created and not is_compliant:
        expectation_id = _canonical("haccp_expectation", f"{canonical_id}|corrective_action")
        expectation = {
            "id": expectation_id,
            "canonical_id": expectation_id,
            "operation_id": operation_id,
            "anno": int(event_date[:4]),
            "data": event_date,
            "expectation_type": "AZIONE_CORRETTIVA_HACCP",
            "owner_type": "haccp_register_entry",
            "source_fact_id": canonical_id,
            "status": "IN_ELABORAZIONE" if corrective_action else "ATTESO",
            "evidence_ids": [],
            "reason": "; ".join(reasons) or "Controllo dichiarato non conforme",
            "proposed_action": _text(corrective_action),
            "created_at": timestamp,
            "updated_at": timestamp,
            "payload_schema_version": SCHEMA_VERSION,
        }
        await db[COLL_HACCP_EXPECTATIONS].update_one(
            {"canonical_id": expectation_id}, {"$setOnInsert": expectation}, upsert=True
        )
    return stored, created


async def resolve_register_entry(
    db,
    *,
    entry_id: str,
    corrective_action: str,
    verification_notes: str,
    user_id: str,
) -> dict[str, Any]:
    entry = await db[COLL_HACCP_REGISTER_ENTRIES].find_one(
        {"canonical_id": entry_id}, {"_id": 0}
    )
    if not entry:
        raise LookupError("Registrazione HACCP non trovata")
    corrective_action = _text(corrective_action)
    if not corrective_action:
        raise ValueError("L'azione correttiva e obbligatoria")
    if entry.get("compliant"):
        raise ValueError("Il controllo e gia conforme e non richiede un'azione correttiva")
    if entry.get("status") == "SODDISFATTO":
        if entry.get("corrective_action") == corrective_action:
            return entry
        raise ValueError("La non conformita e gia stata chiusa")
    timestamp = _now()
    evidence_id = _canonical("haccp_corrective_evidence", f"{entry_id}|{corrective_action}|{timestamp}")
    await db[COLL_HACCP_REGISTER_ENTRIES].update_one(
        {"canonical_id": entry_id},
        {"$set": {
            "corrective_action": corrective_action,
            "verification_notes": _text(verification_notes),
            "corrective_evidence_id": evidence_id,
            "status": "SODDISFATTO",
            "verified_by": user_id,
            "verified_at": timestamp,
            "updated_at": timestamp,
        }},
    )
    expectation = await db[COLL_HACCP_EXPECTATIONS].find_one(
        {"source_fact_id": entry_id}, {"_id": 0}
    )
    if expectation:
        await db[COLL_HACCP_EXPECTATIONS].update_one(
            {"canonical_id": expectation["canonical_id"]},
            {"$set": {
                "status": "SODDISFATTO",
                "evidence_ids": [evidence_id],
                "resolved_by": user_id,
                "resolved_at": timestamp,
                "updated_at": timestamp,
            }},
        )
    return await db[COLL_HACCP_REGISTER_ENTRIES].find_one(
        {"canonical_id": entry_id}, {"_id": 0}
    )


async def list_register_entries(
    db, *, year: int, register_type: str = "", limit: int = 500
) -> list[dict[str, Any]]:
    query: dict[str, Any] = {"anno": year}
    if register_type:
        normalized = _text(register_type).upper()
        if normalized not in REGISTER_TYPES:
            raise ValueError("Tipo registro HACCP non valido")
        query["register_type"] = normalized
    return await db[COLL_HACCP_REGISTER_ENTRIES].find(
        query, {"_id": 0}
    ).sort("event_date", -1).limit(limit).to_list(limit)


async def save_equipment(
    db,
    *,
    name: str,
    equipment_type: str,
    threshold_min: Any,
    threshold_max: Any,
    location: str,
    client_operation_id: str,
    user_id: str,
) -> tuple[dict[str, Any], bool]:
    name = _text(name)
    equipment_type = _text(equipment_type).upper()
    if not name or not equipment_type:
        raise ValueError("Nome e tipo attrezzatura sono obbligatori")
    client_operation_id = _text(client_operation_id)
    if len(client_operation_id) < 8:
        raise ValueError("client_operation_id deve contenere almeno 8 caratteri")
    canonical_id = _canonical("haccp_equipment", client_operation_id)
    timestamp = _now()
    item = {
        "id": canonical_id,
        "canonical_id": canonical_id,
        "operation_id": _operation_id(canonical_id),
        "name": name,
        "name_normalized": _normalize(name),
        "equipment_type": equipment_type,
        "threshold_min": _decimal_out(_decimal(threshold_min)),
        "threshold_max": _decimal_out(_decimal(threshold_max)),
        "location": _text(location),
        "active": True,
        "source": "haccp_equipment_config",
        "source_external_id": client_operation_id,
        "payload_schema_version": SCHEMA_VERSION,
        "created_by": user_id,
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    result = await db[COLL_HACCP_EQUIPMENT].update_one(
        {"canonical_id": canonical_id}, {"$setOnInsert": item}, upsert=True
    )
    stored = await db[COLL_HACCP_EQUIPMENT].find_one({"canonical_id": canonical_id}, {"_id": 0})
    return stored, bool(result.upserted_id)


async def update_equipment(
    db,
    *,
    equipment_id: str,
    name: str | None,
    threshold_min: Any,
    threshold_max: Any,
    location: str | None,
    active: bool | None,
    user_id: str,
) -> dict[str, Any]:
    existing = await db[COLL_HACCP_EQUIPMENT].find_one(
        {"canonical_id": equipment_id}, {"_id": 0}
    )
    if not existing:
        raise LookupError("Attrezzatura non trovata")
    changes: dict[str, Any] = {"updated_by": user_id, "updated_at": _now()}
    if name is not None:
        cleaned = _text(name)
        if not cleaned:
            raise ValueError("Il nome attrezzatura non puo essere vuoto")
        changes.update({"name": cleaned, "name_normalized": _normalize(cleaned)})
    if threshold_min is not None:
        changes["threshold_min"] = _decimal_out(_decimal(threshold_min))
    if threshold_max is not None:
        changes["threshold_max"] = _decimal_out(_decimal(threshold_max))
    if location is not None:
        changes["location"] = _text(location)
    if active is not None:
        changes["active"] = active
    await db[COLL_HACCP_EQUIPMENT].update_one(
        {"canonical_id": equipment_id}, {"$set": changes}
    )
    return await db[COLL_HACCP_EQUIPMENT].find_one(
        {"canonical_id": equipment_id}, {"_id": 0}
    )


async def save_recipe(
    db,
    *,
    name: str,
    department: str,
    yield_quantity: Any,
    yield_unit: str,
    ingredients: list[dict[str, Any]],
    instructions: str,
    allergens: list[str],
    shelf_life_days: int | None,
    storage: str,
    client_operation_id: str,
    user_id: str,
    recipe_id: str = "",
) -> tuple[dict[str, Any], bool]:
    name = _text(name)
    if not name:
        raise ValueError("Il nome ricetta e obbligatorio")
    if not ingredients:
        raise ValueError("Inserire almeno un ingrediente")
    normalized_ingredients: list[dict[str, Any]] = []
    for index, ingredient in enumerate(ingredients, start=1):
        ingredient_name = _text(ingredient.get("name"))
        quantity = _decimal(ingredient.get("quantity"), required=True)
        if not ingredient_name or quantity is None or quantity <= 0:
            raise ValueError(f"Ingrediente {index} non valido")
        normalized_ingredients.append({
            "product_id": _text(ingredient.get("product_id")),
            "name": ingredient_name,
            "quantity": _decimal_out(quantity),
            "unit": _text(ingredient.get("unit")) or "g",
            "allergens": sorted({_text(value).upper() for value in ingredient.get("allergens", []) if _text(value)}),
        })
    timestamp = _now()
    if recipe_id:
        existing = await db[COLL_HACCP_RECIPES].find_one({"canonical_id": recipe_id}, {"_id": 0})
        if not existing:
            raise LookupError("Ricetta non trovata")
        canonical_id = recipe_id
        created = False
        version = int(existing.get("version") or 1) + 1
        operation_id = existing.get("operation_id") or _operation_id(canonical_id)
        created_at = existing.get("created_at") or timestamp
    else:
        client_operation_id = _text(client_operation_id)
        if len(client_operation_id) < 8:
            raise ValueError("client_operation_id deve contenere almeno 8 caratteri")
        canonical_id = _canonical("haccp_recipe", client_operation_id)
        existing = await db[COLL_HACCP_RECIPES].find_one({"canonical_id": canonical_id}, {"_id": 0})
        if existing:
            return existing, False
        created = True
        version = 1
        operation_id = _operation_id(canonical_id)
        created_at = timestamp
    explicit_allergens = {_text(value).upper() for value in allergens if _text(value)}
    ingredient_allergens = {
        allergen for ingredient in normalized_ingredients for allergen in ingredient["allergens"]
    }
    item = {
        "id": canonical_id,
        "canonical_id": canonical_id,
        "operation_id": operation_id,
        "name": name,
        "name_normalized": _normalize(name),
        "department": _text(department) or "GENERALE",
        "yield_quantity": _decimal_out(_decimal(yield_quantity, required=True)),
        "yield_unit": _text(yield_unit) or "pezzi",
        "ingredients": normalized_ingredients,
        "instructions": _text(instructions),
        "allergens": sorted(explicit_allergens | ingredient_allergens),
        "allergens_verified": bool(explicit_allergens or ingredient_allergens),
        "shelf_life_days": shelf_life_days,
        "storage": _text(storage),
        "status": "ATTIVA",
        "version": version,
        "source": "haccp_recipe_manual",
        "source_external_id": _text(client_operation_id) or canonical_id,
        "payload_schema_version": SCHEMA_VERSION,
        "created_by": existing.get("created_by", user_id) if existing else user_id,
        "created_at": created_at,
        "updated_by": user_id,
        "updated_at": timestamp,
    }
    item["payload_hash"] = _payload_hash(item)
    if created:
        await db[COLL_HACCP_RECIPES].update_one(
            {"canonical_id": canonical_id}, {"$setOnInsert": item}, upsert=True
        )
    else:
        await db[COLL_HACCP_RECIPES].update_one({"canonical_id": canonical_id}, {"$set": item})
    return await db[COLL_HACCP_RECIPES].find_one({"canonical_id": canonical_id}, {"_id": 0}), created


async def register_production(
    db,
    *,
    recipe_id: str,
    production_date: str,
    quantity: Any,
    unit: str,
    lot_number: str,
    ingredient_lots: list[dict[str, Any]],
    operator: str,
    notes: str,
    production_kind: str,
    recovery_from_id: str,
    client_operation_id: str,
    user_id: str,
) -> tuple[dict[str, Any], bool]:
    recipe = await db[COLL_HACCP_RECIPES].find_one({"canonical_id": recipe_id}, {"_id": 0})
    if not recipe:
        raise LookupError("Ricetta non trovata")
    production_date = validate_iso_date(production_date)
    amount = _decimal(quantity, required=True)
    if amount is None or amount <= 0:
        raise ValueError("La quantita prodotta deve essere maggiore di zero")
    client_operation_id = _text(client_operation_id)
    if len(client_operation_id) < 8:
        raise ValueError("client_operation_id deve contenere almeno 8 caratteri")
    canonical_id = _canonical("haccp_production", client_operation_id)
    operation_id = _operation_id(canonical_id)
    existing = await db[COLL_HACCP_PRODUCTIONS].find_one({"canonical_id": canonical_id}, {"_id": 0})
    if existing and existing.get("status") == "SODDISFATTO":
        return existing, False

    if recipe.get("ingredients") and not ingredient_lots:
        raise ValueError("Selezionare almeno un lotto ingrediente per garantire la tracciabilita")

    validated_lots: list[tuple[dict[str, Any], Decimal, str]] = []
    for index, allocation in enumerate(ingredient_lots, start=1):
        lot_id = _text(allocation.get("lot_id"))
        used = _decimal(allocation.get("quantity"), required=True)
        lot = await db[COLL_HACCP_LOTS].find_one({"canonical_id": lot_id}, {"_id": 0})
        if not lot:
            raise LookupError(f"Lotto ingrediente {index} non trovato")
        movement_operation_id = f"{operation_id}:ingredient:{index}"
        prior_movement = await db[COLL_HACCP_LOT_MOVEMENTS].find_one(
            {"source_external_id": movement_operation_id}, {"_id": 0}
        )
        available = _decimal(lot.get("quantity_available")) or Decimal("0")
        if used is None or used <= 0 or (not prior_movement and used > available):
            raise ValueError(f"Quantita non disponibile per il lotto {lot.get('lot_number', lot_id)}")
        validated_lots.append((lot, used, movement_operation_id))

    timestamp = _now()
    output_lot_number = _text(lot_number) or f"PROD-{production_date.replace('-', '')}-{client_operation_id[-6:].upper()}"
    item = {
        "id": canonical_id,
        "canonical_id": canonical_id,
        "operation_id": operation_id,
        "anno": int(production_date[:4]),
        "data": production_date,
        "production_date": production_date,
        "recipe_id": recipe_id,
        "recipe_version": recipe.get("version", 1),
        "recipe_name": recipe.get("name", ""),
        "production_kind": _text(production_kind).upper() or "STANDARD",
        "quantity": _decimal_out(amount),
        "unit": _text(unit) or recipe.get("yield_unit", "pezzi"),
        "lot_number": output_lot_number,
        "ingredient_lots": [
            {"lot_id": lot["canonical_id"], "lot_number": lot.get("lot_number", ""), "quantity": _decimal_out(used), "unit": lot.get("unit", "")}
            for lot, used, _movement_operation_id in validated_lots
        ],
        "recovery_from_id": _text(recovery_from_id),
        "operator": _text(operator) or user_id,
        "notes": _text(notes),
        "status": "IN_ELABORAZIONE",
        "source": "haccp_production",
        "source_external_id": client_operation_id,
        "payload_schema_version": SCHEMA_VERSION,
        "created_by": user_id,
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    await db[COLL_HACCP_PRODUCTIONS].update_one(
        {"canonical_id": canonical_id}, {"$setOnInsert": item}, upsert=True
    )
    for lot, used, movement_operation_id in validated_lots:
        await record_lot_movement(
            db,
            lot_id=lot["canonical_id"],
            movement_type="CONSUMO",
            quantity=_decimal_out(used),
            reason=f"Produzione {recipe.get('name', '')} - lotto {output_lot_number}",
            client_operation_id=movement_operation_id,
            user_id=user_id,
        )
    output_lot_id = _canonical("haccp_lot", f"production|{canonical_id}|{output_lot_number.upper()}")
    output_lot = {
        "id": output_lot_id,
        "canonical_id": output_lot_id,
        "operation_id": operation_id,
        "production_id": canonical_id,
        "recipe_id": recipe_id,
        "product_description": recipe.get("name", ""),
        "lot_number": output_lot_number,
        "expiry_date": "",
        "received_date": production_date,
        "quantity_received": _decimal_out(amount),
        "quantity_available": _decimal_out(amount),
        "unit": item["unit"],
        "status": "ATTIVO",
        "source": "haccp_production",
        "source_external_id": canonical_id,
        "payload_schema_version": SCHEMA_VERSION,
        "created_by": user_id,
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    await db[COLL_HACCP_LOTS].update_one(
        {"canonical_id": output_lot_id}, {"$setOnInsert": output_lot}, upsert=True
    )
    await db[COLL_HACCP_PRODUCTIONS].update_one(
        {"canonical_id": canonical_id},
        {"$set": {"output_lot_id": output_lot_id, "status": "SODDISFATTO", "updated_at": _now()}},
    )
    return await db[COLL_HACCP_PRODUCTIONS].find_one({"canonical_id": canonical_id}, {"_id": 0}), not bool(existing)


async def domain_overview(db, year: int) -> dict[str, Any]:
    registers = await db[COLL_HACCP_REGISTER_ENTRIES].find({"anno": year}, {"_id": 0}).limit(20000).to_list(20000)
    expectations = await db[COLL_HACCP_EXPECTATIONS].find({"anno": year}, {"_id": 0}).limit(20000).to_list(20000)
    return {
        "register_entries": len(registers),
        "non_compliant": sum(not item.get("compliant", True) for item in registers),
        "open_expectations": sum(item.get("status") in OPEN_STATES for item in expectations),
        "recipes": await db[COLL_HACCP_RECIPES].count_documents({"status": {"$ne": "ARCHIVIATA"}}),
        "productions": await db[COLL_HACCP_PRODUCTIONS].count_documents({"anno": year}),
        "equipment": await db[COLL_HACCP_EQUIPMENT].count_documents({"active": {"$ne": False}}),
    }
