"""Scrittori canonici delle relazioni contabili operative.

Le funzioni di questo modulo non cambiano lo stato economico delle entita':
registrano soltanto, in modo idempotente, le prove gia' validate dai motori
operativi.  In questo modo assegni, paghe, F24 e PayPal usano lo stesso
vocabolario e la stessa provenienza verificabile.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from app.services.entity_relations import upsert_entity_relation


def _text(value: Any) -> str:
    return str(value or "").strip()


def _entity_id(document: Dict[str, Any], *fields: str) -> str:
    for field in fields:
        value = _text(document.get(field))
        if value:
            return value
    return ""


async def _write(db, specifications: Iterable[Dict[str, Any]]) -> List[str]:
    keys: List[str] = []
    for specification in specifications:
        keys.append(await upsert_entity_relation(db, **specification))
    return keys


async def record_check_reconciliation(
    db,
    *,
    cheque: Dict[str, Any],
    movement: Dict[str, Any],
    invoice_links: Iterable[Dict[str, Any]],
) -> List[str]:
    """Registra la catena assegno -> banca -> fatture gia' confermata."""
    cheque_id = _entity_id(cheque, "id")
    movement_id = _entity_id(movement, "id", "fingerprint")
    if not cheque_id or not movement_id:
        return []
    number = _text(cheque.get("numero"))
    base_evidence = [
        {"type": "cheque_number", "value": number},
        {"type": "bank_movement_id", "value": movement_id},
    ]
    specifications: List[Dict[str, Any]] = [{
        "source_type": "bank_movement",
        "source_id": movement_id,
        "relation_type": "proves_check_debit",
        "target_type": "cheque",
        "target_id": cheque_id,
        "status": "confirmed",
        "rule": "numero_assegno_e_movimento_bancario_ufficiale",
        "evidence": base_evidence,
        "amount": cheque.get("importo"),
        "provenance": {
            "source_collection": "estratto_conto_movimenti",
            "target_collection": "assegni",
        },
    }]
    for link in invoice_links:
        invoice_id = _text(link.get("fattura_id"))
        if not invoice_id:
            continue
        evidence = base_evidence + [
            {"type": "invoice_number", "value": link.get("numero_fattura")},
            {"type": "match_level", "value": link.get("match_livello")},
        ]
        common = {
            "target_type": "invoice",
            "target_id": invoice_id,
            "status": "confirmed",
            "evidence": evidence,
            "amount": link.get("quota"),
            "provenance": {
                "cheque_id": cheque_id,
                "bank_movement_id": movement_id,
                "source_collection": "assegni",
                "target_collection": "invoices",
            },
        }
        specifications.extend((
            {
                **common,
                "source_type": "cheque",
                "source_id": cheque_id,
                "relation_type": "allocated_to_invoice",
                "rule": "assegno_ripartito_su_fattura_con_quota_esatta",
            },
            {
                **common,
                "source_type": "bank_movement",
                "source_id": movement_id,
                "relation_type": "proves_invoice_payment",
                "rule": "movimento_bancario_prova_assegno_e_quota_fattura",
            },
        ))
    return await _write(db, specifications)


async def record_salary_reconciliation(
    db,
    *,
    salary_entry: Dict[str, Any],
    movement: Dict[str, Any],
    amount: Any,
    employee_name: str,
) -> List[str]:
    """Registra un bonifico stipendio identificato in modo univoco."""
    salary_id = _entity_id(salary_entry, "id")
    movement_id = _entity_id(movement, "id", "fingerprint")
    if not salary_id or not movement_id:
        return []
    evidence = [
        {"type": "employee_full_identity", "value": employee_name},
        {"type": "bank_movement_id", "value": movement_id},
        {"type": "salary_period", "value": salary_entry.get("periodo") or (
            f"{salary_entry.get('mese')}/{salary_entry.get('anno')}"
        )},
    ]
    specifications: List[Dict[str, Any]] = [{
        "source_type": "bank_movement",
        "source_id": movement_id,
        "relation_type": "allocates_salary_payment",
        "target_type": "salary_entry",
        "target_id": salary_id,
        "status": "confirmed",
        "rule": "identita_dipendente_univoca_e_importo_entro_residuo",
        "evidence": evidence,
        "amount": amount,
        "provenance": {
            "source_collection": "estratto_conto_movimenti",
            "target_collection": "prima_nota_salari",
        },
    }]
    payslip_id = _entity_id(salary_entry, "cedolino_id", "payslip_id")
    if payslip_id:
        specifications.extend((
            {
                "source_type": "bank_movement",
                "source_id": movement_id,
                "relation_type": "proves_payslip_payment",
                "target_type": "payslip",
                "target_id": payslip_id,
                "status": "confirmed",
                "rule": "movimento_bancario_allocato_alla_riga_salario_del_cedolino",
                "evidence": evidence,
                "amount": amount,
                "provenance": {"salary_entry_id": salary_id},
            },
            {
                "source_type": "salary_entry",
                "source_id": salary_id,
                "relation_type": "accounts_for_payslip",
                "target_type": "payslip",
                "target_id": payslip_id,
                "status": "confirmed",
                "rule": "riga_prima_nota_salario_generata_dal_cedolino",
                "evidence": evidence,
                "amount": salary_entry.get("netto") or salary_entry.get("importo_netto"),
                "provenance": {
                    "source_collection": "prima_nota_salari",
                    "target_collection": "cedolini",
                },
            },
        ))
    return await _write(db, specifications)


async def record_f24_receipt_link(
    db,
    *,
    f24: Dict[str, Any],
    receipt_id: str,
    protocol: str,
    amount: Any,
    matched_tributes: int,
    total_tributes: int,
) -> List[str]:
    f24_id = _entity_id(f24, "id")
    if not f24_id or not _text(receipt_id):
        return []
    return await _write(db, [{
        "source_type": "f24_receipt",
        "source_id": _text(receipt_id),
        "relation_type": "documents_f24_model",
        "target_type": "f24_model",
        "target_id": f24_id,
        "status": "confirmed",
        "rule": "codici_periodi_e_importi_tributi_coincidenti",
        "evidence": [
            {"type": "receipt_protocol", "value": protocol},
            {"type": "matched_tributes", "value": f"{matched_tributes}/{total_tributes}"},
        ],
        "amount": amount,
        "provenance": {
            "source_collection": "quietanze_f24",
            "target_collection": "f24_unificato",
        },
    }])


async def record_f24_bank_allocations(
    db,
    *,
    f24: Dict[str, Any],
    allocations: Iterable[Dict[str, Any]],
) -> List[str]:
    f24_id = _entity_id(f24, "id")
    specifications: List[Dict[str, Any]] = []
    for allocation in allocations:
        movement_id = _entity_id(allocation, "movimento_id", "id", "fingerprint")
        if not f24_id or not movement_id:
            continue
        codes = allocation.get("codici_tributo") or []
        specifications.append({
            "source_type": "bank_movement",
            "source_id": movement_id,
            "relation_type": "settles_f24_model",
            "target_type": "f24_model",
            "target_id": f24_id,
            "status": "confirmed",
            "rule": "movimento_bancario_allocato_a_totale_o_righe_tributo_f24",
            "evidence": [
                {"type": "tax_codes", "value": ",".join(map(str, codes))},
                {"type": "bank_movement_id", "value": movement_id},
            ],
            "amount": allocation.get("importo") or allocation.get("amount"),
            "provenance": {
                "source_collection": "estratto_conto_movimenti",
                "target_collection": "f24_unificato",
                "tributo_ids": allocation.get("tributo_ids") or [],
            },
        })
    return await _write(db, specifications)


async def record_paypal_invoice_link(
    db,
    *,
    transaction: Dict[str, Any],
    invoice: Dict[str, Any],
    amount: Any,
    evidence: Optional[Iterable[Dict[str, Any]]] = None,
) -> List[str]:
    transaction_id = _entity_id(transaction, "transaction_id", "id")
    invoice_id = _entity_id(invoice, "id")
    if not transaction_id or not invoice_id:
        return []
    return await _write(db, [{
        "source_type": "paypal_transaction",
        "source_id": transaction_id,
        "relation_type": "allocates_paypal_payment",
        "target_type": "invoice",
        "target_id": invoice_id,
        "status": "confirmed",
        "rule": "paypal_fornitore_numero_fattura_e_importo_validati",
        "evidence": list(evidence or []),
        "amount": amount,
        "provenance": {
            "source_collection": "paypal_transactions",
            "target_collection": "invoices",
        },
    }])


async def record_paypal_bank_chain(
    db,
    *,
    transaction: Dict[str, Any],
    invoice: Dict[str, Any],
    movement: Dict[str, Any],
    amount: Any,
) -> List[str]:
    transaction_id = _entity_id(transaction, "transaction_id", "id")
    invoice_id = _entity_id(invoice, "id")
    movement_id = _entity_id(movement, "id", "fingerprint")
    if not transaction_id or not invoice_id or not movement_id:
        return []
    evidence = [
        {"type": "paypal_transaction_id", "value": transaction_id},
        {"type": "bank_movement_id", "value": movement_id},
    ]
    common = {
        "source_type": "bank_movement",
        "source_id": movement_id,
        "status": "confirmed",
        "evidence": evidence,
        "amount": amount,
        "provenance": {"source_collection": "estratto_conto_movimenti"},
    }
    return await _write(db, [
        {
            **common,
            "relation_type": "settles_paypal_transaction",
            "target_type": "paypal_transaction",
            "target_id": transaction_id,
            "rule": "movimento_bancario_con_transazione_paypal_confermata",
        },
        {
            **common,
            "relation_type": "proves_invoice_payment",
            "target_type": "invoice",
            "target_id": invoice_id,
            "rule": "catena_paypal_fattura_movimento_bancario_completa",
            "provenance": {
                "source_collection": "estratto_conto_movimenti",
                "paypal_transaction_id": transaction_id,
            },
        },
    ])
