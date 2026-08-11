"""Indice manuale delle operazioni bancarie.

Il movimento importato dall'estratto conto e' una fonte immutabile. Questo
modulo registra esclusivamente la decisione esplicita dell'operatore e una
relazione bidirezionale di indice; non crea scritture, non marca fatture come
pagate e non esegue riconciliazioni automatiche.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field
from bson import ObjectId

from app.database import Database
from app.db_collections import (
    COLL_BANK_OPERATION_INDEX,
    COLL_CEDOLINI,
    COLL_CORRISPETTIVI,
    COLL_ESTRATTO_CONTO,
    COLL_F24,
    COLL_INVOICES,
    COLL_SUPPLIERS,
    COLL_VEICOLI_NOLEGGIO,
    COLL_VERBALI_NOLEGGIO,
)
from app.services.entity_relations import revoke_entity_relation, upsert_entity_relation
from app.services.payment_invoice_matching import money_cents
from app.utils.dependencies import get_current_user


INDEX_RULE = "manual_operation_index.v1"

CATEGORIES: Dict[str, Dict[str, Any]] = {
    "fornitore": {
        "label": "Fornitore (senza fattura)",
        "target_type": "supplier",
        "collection": COLL_SUPPLIERS,
        "requires_target": True,
        "help": "Scegli il fornitore quando non esiste una fattura precisa.",
        "date_field": "updated_at",
        "search_fields": ["ragione_sociale", "denominazione", "nome", "partita_iva", "codice_fiscale"],
    },
    "fattura": {
        "label": "Fornitore / fattura",
        "target_type": "invoice",
        "collection": COLL_INVOICES,
        "requires_target": True,
        "help": "Scegli la fattura esatta del fornitore.",
        "date_field": "invoice_date",
        "search_fields": ["supplier_name", "fornitore", "numero_documento", "numero_fattura", "invoice_number"],
    },
    "cedolino": {
        "label": "Cedolino / dipendente",
        "target_type": "payslip",
        "collection": COLL_CEDOLINI,
        "requires_target": True,
        "help": "Scegli il cedolino e il dipendente esatti.",
        "date_field": "data",
        "search_fields": ["dipendente_nome", "nome_dipendente", "employee_name", "nominativo", "codice_fiscale", "periodo"],
    },
    "f24": {
        "label": "F24",
        "target_type": "f24_model",
        "collection": COLL_F24,
        "requires_target": True,
        "help": "Scegli il modello F24; quietanza e banca restano prove separate.",
        "date_field": "data_compilazione",
        "search_fields": ["periodo", "codice_fiscale", "taxpayer_id", "nome_contribuente"],
    },
    "noleggio": {
        "label": "Noleggio / veicolo",
        "target_type": "rental_vehicle",
        "collection": COLL_VEICOLI_NOLEGGIO,
        "requires_target": True,
        "help": "Scegli targa, veicolo e driver dall'anagrafica.",
        "date_field": "updated_at",
        "search_fields": ["targa", "marca", "modello", "driver_nome", "dipendente_nome", "contratto"],
    },
    "verbale": {
        "label": "Verbale",
        "target_type": "fine",
        "collection": COLL_VERBALI_NOLEGGIO,
        "requires_target": True,
        "help": "Scegli il verbale esatto; un avviso non prova il pagamento.",
        "date_field": "data_verbale",
        "search_fields": ["numero_verbale", "numero", "veicolo_targa", "targa", "driver_nome"],
    },
    "corrispettivo_pos": {
        "label": "Corrispettivo / POS",
        "target_type": "daily_receipt",
        "collection": COLL_CORRISPETTIVI,
        "requires_target": True,
        "help": "Scegli la chiusura giornaliera o il corrispettivo esatto.",
        "date_field": "data",
        "search_fields": ["data", "numero_documento", "matricola_dispositivo"],
    },
    "commissione_bancaria": {
        "label": "Commissione bancaria",
        "target_type": None,
        "collection": None,
        "requires_target": False,
        "help": "Classificazione manuale senza documento da collegare.",
    },
    "trasferimento": {
        "label": "Trasferimento interno",
        "target_type": None,
        "collection": None,
        "requires_target": False,
        "help": "Giroconto o trasferimento tra conti, da verificare manualmente.",
    },
    "altro": {
        "label": "Altro",
        "target_type": None,
        "collection": None,
        "requires_target": False,
        "help": "Usa la nota per descrivere la natura dell'operazione.",
    },
}


class ManualIndexDecisionIn(BaseModel):
    category: str
    target_id: Optional[str] = None
    note: str = Field(default="", max_length=500)
    expected_version: Optional[int] = Field(default=None, ge=0)


def _actor(user: Dict[str, Any]) -> str:
    return str(user.get("user_id") or user.get("email") or "utente")


def _date(doc: Dict[str, Any]) -> str:
    return str(
        doc.get("data")
        or doc.get("data_documento")
        or doc.get("data_emissione")
        or doc.get("data_verbale")
        or doc.get("periodo")
        or ""
    )[:10]


def _first(doc: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = doc.get(key)
        if value not in (None, "", []):
            return value
    return None


def _target_label(category: str, doc: Dict[str, Any]) -> str:
    if category == "fornitore":
        name = _first(doc, "ragione_sociale", "denominazione", "nome") or "Fornitore"
        vat = _first(doc, "partita_iva", "piva", "codice_fiscale")
        return f"{name} - {vat}" if vat else str(name)
    if category == "fattura":
        supplier = _first(doc, "supplier_name", "fornitore", "cedente_nome", "denominazione_fornitore") or "Fornitore"
        number = _first(doc, "numero_documento", "numero_fattura", "invoice_number", "numero") or "senza numero"
        return f"{supplier} - fattura {number}"
    if category == "cedolino":
        employee = _first(doc, "dipendente_nome", "nome_dipendente", "employee_name", "nominativo", "nome") or "Dipendente"
        period = _first(doc, "periodo", "mese_competenza") or "periodo non indicato"
        return f"{employee} - {period}"
    if category == "f24":
        codes = doc.get("codici_tributo") or doc.get("tributi") or []
        if isinstance(codes, list):
            codes = ", ".join(str(x.get("codice") if isinstance(x, dict) else x) for x in codes[:4])
        return f"F24 {_first(doc, 'periodo', 'data_compilazione', 'data') or ''} {codes or ''}".strip()
    if category == "noleggio":
        plate = _first(doc, "targa") or "senza targa"
        vehicle = " ".join(str(x) for x in (_first(doc, "marca"), _first(doc, "modello")) if x)
        driver = _first(doc, "driver_nome", "dipendente_nome", "driver")
        return " - ".join(x for x in (str(plate), vehicle, str(driver or "")) if x)
    if category == "verbale":
        number = _first(doc, "numero_verbale", "numero") or "senza numero"
        plate = _first(doc, "veicolo_targa", "targa") or "targa non indicata"
        return f"Verbale {number} - {plate}"
    if category == "corrispettivo_pos":
        return f"Corrispettivo {_date(doc) or 'senza data'}"
    return str(doc.get("id") or "")


def _target_amount(category: str, doc: Dict[str, Any]) -> Any:
    keys = {
        "fattura": ("importo_totale", "total_amount", "totale_documento", "totale"),
        "cedolino": ("netto", "netto_pagare", "importo_netto", "importo"),
        "f24": ("saldo_finale", "importo_totale", "totale", "importo"),
        "verbale": ("importo_verificato", "importo", "totale"),
        "corrispettivo_pos": ("pagato_pos", "pagato_elettronico", "totale", "importo"),
    }.get(category, ("importo", "totale"))
    return _first(doc, *keys)


def _candidate(category: str, doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(doc.get("id") or doc.get("_id") or ""),
        "label": _target_label(category, doc),
        "date": _date(doc),
        "amount_cents": money_cents(_target_amount(category, doc)),
        "details": {
            "supplier": _first(doc, "supplier_name", "fornitore", "cedente_nome"),
            "invoice_number": _first(doc, "numero_documento", "numero_fattura", "invoice_number"),
            "employee": _first(doc, "dipendente_nome", "nome_dipendente", "employee_name", "nominativo"),
            "tax_code": _first(doc, "codice_fiscale", "employee_cf", "taxpayer_id"),
            "plate": _first(doc, "targa", "veicolo_targa"),
            "driver": _first(doc, "driver_nome", "dipendente_nome", "driver"),
            "period": _first(doc, "periodo", "mese_competenza", "anno"),
        },
    }


def _target_query(target_id: str) -> Dict[str, Any]:
    choices: List[Dict[str, Any]] = [{"id": target_id}]
    try:
        choices.append({"_id": ObjectId(target_id)})
    except Exception:
        choices.append({"_id": target_id})
    return {"$or": choices}


def _movement_query(movement_id: str) -> Dict[str, Any]:
    """Trova anche gli import storici che non hanno ancora il campo ``id``."""
    return _target_query(movement_id)


def _searchable(candidate: Dict[str, Any]) -> str:
    values = [candidate.get("label"), candidate.get("date")]
    values.extend((candidate.get("details") or {}).values())
    return " ".join(str(value or "") for value in values).upper()


async def list_manual_operation_index(
    anno: int = Query(..., ge=2000, le=2100),
    tipo: Optional[str] = Query(None),
    stato: Optional[str] = Query(None),
    search: str = Query("", max_length=120),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    db = Database.get_db()
    query: Dict[str, Any] = {"data": {"$gte": f"{anno}-01-01", "$lte": f"{anno}-12-31"}}
    if tipo in {"entrata", "uscita"}:
        query["tipo"] = tipo
    if search.strip():
        query["descrizione"] = {"$regex": re.escape(search.strip()), "$options": "i"}

    total = await db[COLL_ESTRATTO_CONTO].count_documents(query)
    movements = await db[COLL_ESTRATTO_CONTO].find(query).sort("data", -1).skip(offset).limit(limit).to_list(limit)
    ids = [str(item.get("id") or item.get("_id") or "") for item in movements]
    ids = [movement_id for movement_id in ids if movement_id]
    decisions = await db[COLL_BANK_OPERATION_INDEX].find(
        {"movement_id": {"$in": ids}, "status": {"$ne": "revoked"}}, {"_id": 0, "history": 0}
    ).to_list(len(ids) or 1)
    by_movement = {str(item.get("movement_id")): item for item in decisions}

    rows: List[Dict[str, Any]] = []
    for movement in movements:
        movement_id = str(movement.get("id") or movement.get("_id") or "")
        decision = by_movement.get(movement_id)
        row_status = "collegato_indice" if decision and decision.get("target_id") else "classificato" if decision else "da_classificare"
        if stato and stato != row_status:
            continue
        rows.append({
            "id": movement_id,
            "date": _date(movement),
            "type": movement.get("tipo"),
            "description": movement.get("descrizione") or "",
            "amount_cents": money_cents(movement.get("importo")),
            "source_fingerprint": movement.get("fingerprint"),
            "bank_reconciled": bool(movement.get("riconciliato")),
            "index_status": row_status,
            "decision": decision,
        })

    return {
        "year": anno,
        "total_rows": total,
        "loaded_rows": len(rows),
        "offset": offset,
        "limit": limit,
        "categories": [
            {
                "id": key,
                "label": config["label"],
                "target_type": config["target_type"],
                "requires_target": config["requires_target"],
                "help": config["help"],
            }
            for key, config in CATEGORIES.items()
        ],
        "rows": rows,
        "automation": "disabled_for_manual_index",
    }


async def list_manual_operation_candidates(
    movement_id: str,
    category: str = Query(...),
    search: str = Query("", max_length=120),
    limit: int = Query(50, ge=1, le=100),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    config = CATEGORIES.get(category)
    if not config:
        raise HTTPException(status_code=400, detail="Categoria non valida")
    db = Database.get_db()
    movement = await db[COLL_ESTRATTO_CONTO].find_one(_movement_query(movement_id))
    if not movement:
        raise HTTPException(status_code=404, detail="Movimento bancario non trovato")
    if not config["requires_target"]:
        return {"movement_id": movement_id, "category": category, "candidates": []}

    search_text = search.strip()
    candidate_query: Dict[str, Any] = {}
    if search_text:
        expression = {"$regex": re.escape(search_text), "$options": "i"}
        candidate_query["$or"] = [{field: expression} for field in config.get("search_fields", [])]
    documents = await db[config["collection"]].find(candidate_query).sort(
        config.get("date_field") or "data", -1
    ).limit(500).to_list(500)
    candidates = [_candidate(category, item) for item in documents]
    candidates = [item for item in candidates if item["id"]]
    query_text = search_text.upper()
    if query_text:
        candidates = [item for item in candidates if query_text in _searchable(item)]
    return {
        "movement_id": movement_id,
        "category": category,
        "movement_amount_cents": money_cents(movement.get("importo")),
        "candidates": candidates[:limit],
        "matching": "manual_only",
    }


async def save_manual_operation_decision(
    movement_id: str,
    body: ManualIndexDecisionIn,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    config = CATEGORIES.get(body.category)
    if not config:
        raise HTTPException(status_code=400, detail="Categoria non valida")
    db = Database.get_db()
    movement = await db[COLL_ESTRATTO_CONTO].find_one(_movement_query(movement_id))
    if not movement:
        raise HTTPException(status_code=404, detail="Movimento bancario non trovato")

    target_id = str(body.target_id or "").strip() or None
    if config["requires_target"] and not target_id:
        raise HTTPException(status_code=400, detail="Seleziona il dato esatto da collegare")
    target = None
    if target_id:
        target = await db[config["collection"]].find_one(_target_query(target_id))
        if not target:
            raise HTTPException(status_code=404, detail="Dato selezionato non trovato")

    previous = await db[COLL_BANK_OPERATION_INDEX].find_one({"movement_id": movement_id}, {"_id": 0})
    previous_version = int((previous or {}).get("version") or 0)
    if body.expected_version is not None and body.expected_version != previous_version:
        raise HTTPException(status_code=409, detail="La scelta e' stata modificata: ricarica la riga")

    actor = _actor(current_user)
    now = datetime.now(timezone.utc).isoformat()
    target_type = config.get("target_type") if target_id else None
    if previous and previous.get("target_id") and (
        previous.get("target_id") != target_id or previous.get("target_type") != target_type
    ):
        await revoke_entity_relation(
            db,
            source_type="bank_movement",
            source_id=movement_id,
            relation_type="manually_indexed_as",
            target_type=str(previous["target_type"]),
            target_id=str(previous["target_id"]),
            actor=actor,
        )

    decision = {
        "id": f"bank-operation-index:{movement_id}",
        "movement_id": movement_id,
        "category": body.category,
        "category_label": config["label"],
        "target_type": target_type,
        "target_id": target_id,
        "target_label": _target_label(body.category, target) if target else None,
        "note": body.note.strip(),
        "amount_cents": money_cents(movement.get("importo")),
        "source_fingerprint": movement.get("fingerprint"),
        "status": "linked_index" if target_id else "classified",
        "version": previous_version + 1,
        "updated_at": now,
        "updated_by": actor,
    }
    update: Dict[str, Any] = {"$set": decision, "$setOnInsert": {"created_at": now, "created_by": actor}}
    if previous:
        history_item = {k: v for k, v in previous.items() if k not in {"history", "_id"}}
        update["$push"] = {"history": history_item}
    await db[COLL_BANK_OPERATION_INDEX].update_one({"movement_id": movement_id}, update, upsert=True)

    relation_key = None
    if target_id:
        relation_key = await upsert_entity_relation(
            db,
            source_type="bank_movement",
            source_id=movement_id,
            relation_type="manually_indexed_as",
            target_type=str(target_type),
            target_id=target_id,
            status="confirmed",
            rule=INDEX_RULE,
            evidence=[
                {"type": "bank_movement_id", "value": movement_id},
                {"type": "operator_selection", "value": body.category},
            ],
            amount=movement.get("importo"),
            provenance={"source_collection": COLL_ESTRATTO_CONTO, "fingerprint": movement.get("fingerprint")},
            actor=actor,
        )

    return {
        "saved": True,
        "decision": decision,
        "relation_key": relation_key,
        "source_unchanged": True,
        "payment_status_changed": False,
    }
