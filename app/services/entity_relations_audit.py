"""Audit storico, esclusivamente in lettura, del registro relazionale.

L'audit ricostruisce soltanto relazioni gia' dimostrate dai campi canonici
delle collection operative. Non crea collegamenti, non corregge record e non
promuove proposte o documenti a prova di pagamento.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List

from app.db_collections import COLL_ENTITY_RELATIONS
from app.services.entity_relations import relation_key
from app.services.f24_payment_evidence import (
    ha_evidenza_bancaria,
    riferimento_bancario,
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _document_id(document: Dict[str, Any], *fields: str) -> str:
    for field in fields:
        value = _text(document.get(field))
        if value:
            return value
    return ""


def _movement_ids(value: Any) -> List[str]:
    values = value if isinstance(value, list) else [value]
    return list(dict.fromkeys(_text(item) for item in values if _text(item)))


async def _read_limited(
    db,
    collection: str,
    query: Dict[str, Any],
    projection: Dict[str, int],
    limit: int,
) -> List[Dict[str, Any]]:
    cursor = db[collection].find(query, projection).limit(limit)
    return await cursor.to_list(length=limit)


def _add_expected(
    expected: Dict[str, Dict[str, Any]],
    *,
    domain: str,
    source_type: str,
    source_id: str,
    relation_type: str,
    target_type: str,
    target_id: str,
    source_collection: str,
) -> None:
    if not source_id or not target_id:
        return
    key = relation_key(
        source_type, source_id, relation_type, target_type, target_id
    )
    expected[key] = {
        "relation_key": key,
        "domain": domain,
        "source_collection": source_collection,
        "source": {"type": source_type, "id": source_id},
        "target": {"type": target_type, "id": target_id},
        "relation_type": relation_type,
    }


async def _existing_relation_keys(db, keys: Iterable[str]) -> set[str]:
    result: set[str] = set()
    ordered = list(keys)
    for start in range(0, len(ordered), 500):
        chunk = ordered[start:start + 500]
        rows = await db[COLL_ENTITY_RELATIONS].find(
            {"relation_key": {"$in": chunk}, "status": "confirmed"},
            {"_id": 0, "relation_key": 1},
        ).to_list(length=len(chunk))
        result.update(_text(row.get("relation_key")) for row in rows)
    return result


async def audit_legacy_entity_relations(
    db,
    *,
    limit_per_collection: int = 5000,
    sample_limit: int = 100,
) -> Dict[str, Any]:
    """Confronta prove storiche e registro senza effettuare scritture."""
    limit = max(1, min(int(limit_per_collection), 50000))
    expected: Dict[str, Dict[str, Any]] = {}
    scanned: Dict[str, int] = {}

    cheques = await _read_limited(
        db,
        "assegni",
        {"$or": [
            {"movimento_estratto_conto_id": {"$nin": [None, ""]}},
            {"movimento_bancario_id": {"$nin": [None, ""]}},
        ]},
        {
            "_id": 0, "id": 1, "movimento_estratto_conto_id": 1,
            "movimento_bancario_id": 1, "fatture_collegate": 1,
            "incassato_confermato_banca": 1,
        },
        limit,
    )
    scanned["assegni"] = len(cheques)
    for cheque in cheques:
        cheque_id = _document_id(cheque, "id")
        movement_id = _document_id(
            cheque, "movimento_estratto_conto_id", "movimento_bancario_id"
        )
        if not cheque_id or not movement_id:
            continue
        _add_expected(
            expected, domain="assegni", source_type="bank_movement",
            source_id=movement_id, relation_type="proves_check_debit",
            target_type="cheque", target_id=cheque_id,
            source_collection="assegni",
        )
        for link in cheque.get("fatture_collegate") or []:
            if not isinstance(link, dict):
                continue
            invoice_id = _text(link.get("fattura_id"))
            bank_confirmed = bool(
                link.get("banca_confermata")
                or cheque.get("incassato_confermato_banca")
            )
            if not invoice_id or not bank_confirmed:
                continue
            _add_expected(
                expected, domain="assegni", source_type="cheque",
                source_id=cheque_id, relation_type="allocated_to_invoice",
                target_type="invoice", target_id=invoice_id,
                source_collection="assegni",
            )
            _add_expected(
                expected, domain="assegni", source_type="bank_movement",
                source_id=movement_id, relation_type="proves_invoice_payment",
                target_type="invoice", target_id=invoice_id,
                source_collection="assegni",
            )

    salaries = await _read_limited(
        db,
        "prima_nota_salari",
        {"$or": [
            {"movimenti_bancari_ids.0": {"$exists": True}},
            {"movimento_bancario_id": {"$nin": [None, ""]}},
        ]},
        {
            "_id": 0, "id": 1, "cedolino_id": 1, "payslip_id": 1,
            "movimenti_bancari_ids": 1, "movimento_bancario_id": 1,
        },
        limit,
    )
    scanned["prima_nota_salari"] = len(salaries)
    for salary in salaries:
        salary_id = _document_id(salary, "id")
        payslip_id = _document_id(salary, "cedolino_id", "payslip_id")
        ids = _movement_ids(salary.get("movimenti_bancari_ids"))
        ids += [item for item in _movement_ids(
            salary.get("movimento_bancario_id")
        ) if item not in ids]
        for movement_id in ids:
            _add_expected(
                expected, domain="salari", source_type="bank_movement",
                source_id=movement_id, relation_type="allocates_salary_payment",
                target_type="salary_entry", target_id=salary_id,
                source_collection="prima_nota_salari",
            )
            if payslip_id:
                _add_expected(
                    expected, domain="salari", source_type="bank_movement",
                    source_id=movement_id, relation_type="proves_payslip_payment",
                    target_type="payslip", target_id=payslip_id,
                    source_collection="prima_nota_salari",
                )
        if salary_id and payslip_id:
            _add_expected(
                expected, domain="salari", source_type="salary_entry",
                source_id=salary_id, relation_type="accounts_for_payslip",
                target_type="payslip", target_id=payslip_id,
                source_collection="prima_nota_salari",
            )

    payslips = await _read_limited(
        db,
        "cedolini",
        {"pagata": True, "movimento_bancario_id": {"$nin": [None, ""]}},
        {"_id": 0, "id": 1, "movimento_bancario_id": 1},
        limit,
    )
    scanned["cedolini"] = len(payslips)
    for payslip in payslips:
        _add_expected(
            expected, domain="salari", source_type="bank_movement",
            source_id=_document_id(payslip, "movimento_bancario_id"),
            relation_type="proves_payslip_payment", target_type="payslip",
            target_id=_document_id(payslip, "id"), source_collection="cedolini",
        )

    f24_rows = await _read_limited(
        db,
        "f24_unificato",
        {"$or": [
            {"quietanza_id": {"$nin": [None, ""]}},
            {"allocazioni_banca.0": {"$exists": True}},
            {"movimento_bancario_id": {"$nin": [None, ""]}},
            {"bank_movement_id": {"$nin": [None, ""]}},
            {"estratto_conto_id": {"$nin": [None, ""]}},
            {"movimento_bancario_ref": {"$nin": [None, ""]}},
            {"evidenza_bancaria_id": {"$nin": [None, ""]}},
            {"movimento_bancario.id": {"$nin": [None, ""]}},
            {"movimento_bancario.movimento_id": {"$nin": [None, ""]}},
        ]},
        {
            "_id": 0, "id": 1, "quietanza_id": 1,
            "allocazioni_banca": 1, "movimento_bancario_id": 1,
            "bank_movement_id": 1, "estratto_conto_id": 1,
            "movimento_bancario_ref": 1, "evidenza_bancaria_id": 1,
            "movimento_bancario": 1, "data_pagamento_effettivo": 1,
            "data_addebito_banca": 1, "bank_paid_date": 1,
        },
        limit,
    )
    scanned["f24_unificato"] = len(f24_rows)
    for f24 in f24_rows:
        f24_id = _document_id(f24, "id")
        receipt_id = _document_id(f24, "quietanza_id")
        if receipt_id:
            _add_expected(
                expected, domain="f24", source_type="f24_receipt",
                source_id=receipt_id, relation_type="documents_f24_model",
                target_type="f24_model", target_id=f24_id,
                source_collection="f24_unificato",
            )
        allocation_ids = []
        for allocation in f24.get("allocazioni_banca") or []:
            if isinstance(allocation, dict):
                movement_id = _document_id(
                    allocation, "movimento_id", "id", "fingerprint"
                )
                if movement_id and movement_id not in allocation_ids:
                    allocation_ids.append(movement_id)
        # I flag legacy ``pagato``/``riconciliato`` e la quietanza non sono
        # prova bancaria. Il fallback e' ammesso soltanto quando il record
        # conserva sia un riferimento identificabile sia la data di addebito.
        if not allocation_ids and ha_evidenza_bancaria(f24):
            allocation_ids = _movement_ids(riferimento_bancario(f24))
        for movement_id in allocation_ids:
            _add_expected(
                expected, domain="f24", source_type="bank_movement",
                source_id=movement_id, relation_type="settles_f24_model",
                target_type="f24_model", target_id=f24_id,
                source_collection="f24_unificato",
            )

    paypal_rows = await _read_limited(
        db,
        "paypal_transactions",
        {"fattura_associata.fattura_id": {"$nin": [None, ""]}},
        {
            "_id": 0, "id": 1, "transaction_id": 1,
            "fattura_associata": 1, "movimento_banca_id": 1,
            "estratto_conto_movimento_id": 1,
            "fattura_pagamento_finalizzato": 1,
        },
        limit,
    )
    scanned["paypal_transactions"] = len(paypal_rows)
    for transaction in paypal_rows:
        transaction_id = _document_id(transaction, "transaction_id", "id")
        linked = transaction.get("fattura_associata") or {}
        invoice_id = _text(linked.get("fattura_id")) if isinstance(linked, dict) else ""
        _add_expected(
            expected, domain="paypal", source_type="paypal_transaction",
            source_id=transaction_id, relation_type="allocates_paypal_payment",
            target_type="invoice", target_id=invoice_id,
            source_collection="paypal_transactions",
        )
        if transaction.get("fattura_pagamento_finalizzato") is True:
            movement_id = _document_id(
                transaction, "movimento_banca_id", "estratto_conto_movimento_id"
            )
            _add_expected(
                expected, domain="paypal", source_type="bank_movement",
                source_id=movement_id, relation_type="settles_paypal_transaction",
                target_type="paypal_transaction", target_id=transaction_id,
                source_collection="paypal_transactions",
            )
            _add_expected(
                expected, domain="paypal", source_type="bank_movement",
                source_id=movement_id, relation_type="proves_invoice_payment",
                target_type="invoice", target_id=invoice_id,
                source_collection="paypal_transactions",
            )

    present_keys = await _existing_relation_keys(db, expected.keys())
    domain_totals: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"expected": 0, "present": 0, "missing": 0}
    )
    missing: List[Dict[str, Any]] = []
    for key, specification in expected.items():
        domain = specification["domain"]
        domain_totals[domain]["expected"] += 1
        if key in present_keys:
            domain_totals[domain]["present"] += 1
        else:
            domain_totals[domain]["missing"] += 1
            if len(missing) < max(0, int(sample_limit)):
                missing.append(specification)

    return {
        "read_only": True,
        "collections_scanned": scanned,
        "expected": len(expected),
        "present": len(present_keys),
        "missing": len(expected) - len(present_keys),
        "by_domain": dict(domain_totals),
        "sample_missing": missing,
        "sample_truncated": len(expected) - len(present_keys) > len(missing),
        "writes_performed": 0,
    }
