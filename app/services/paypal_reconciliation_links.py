"""Collegamenti canonici PayPal -> fattura -> estratto conto -> Prima Nota.

La transazione PayPal prova quale fattura e' stata pagata; il movimento
bancario prova invece che il denaro e' realmente uscito.  Le due evidenze
possono arrivare in qualunque ordine e vengono conservate su entrambi i lati.
Nessuna fattura viene marcata pagata in assenza del riscontro bancario.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional

from app.services.paypal_invoice_matching import (
    evaluate_paypal_invoice_match,
    invoice_amount,
    invoice_number,
    transaction_amount,
)
from app.services.accounting_relation_writers import (
    record_paypal_bank_chain,
    record_paypal_invoice_link,
)


COLL_TRANSACTIONS = "paypal_transactions"
COLL_INVOICES = "invoices"
COLL_SUPPLIERS = "fornitori"
COLL_BANK = "estratto_conto_movimenti"
logger = logging.getLogger(__name__)


def _tx_id(transaction: Dict[str, Any]) -> str:
    return str(transaction.get("transaction_id") or transaction.get("id") or "").strip()


def _invoice_id(invoice: Dict[str, Any]) -> str:
    return str(invoice.get("id") or invoice.get("_id") or "").strip()


def is_successful_paypal_payment(transaction: Dict[str, Any]) -> bool:
    """Scarta righe tecniche, pending, negate e stornate.

    I vecchi import non hanno lo stato: restano processabili per
    retrocompatibilita'. I codici T02 sono conversioni valuta e non fatture.
    """
    status = str(
        transaction.get("transaction_status")
        or transaction.get("status")
        or ""
    ).strip().upper()
    if status in {"P", "V", "D", "PENDING", "REVERSED", "DENIED"}:
        return False
    balance_affecting = transaction.get("balance_affecting")
    if balance_affecting is False or str(balance_affecting or "").strip().upper() in {
        "N", "NO", "FALSE",
    }:
        return False
    event_code = str(
        transaction.get("transaction_event_code")
        or transaction.get("event_code")
        or transaction.get("tipo")
        or ""
    ).strip().upper()
    if event_code.startswith("T02"):
        return False
    raw_amount = transaction.get("importo")
    if raw_amount is None:
        raw_amount = transaction.get("lordo")
    if raw_amount is None:
        raw_amount = transaction.get("amount")
    try:
        return float(raw_amount or 0) < 0 and transaction_amount(transaction) > 0
    except (TypeError, ValueError):
        return False


async def supplier_mapping_for_transaction(db, transaction: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    account_id = transaction.get("paypal_account_id") or transaction.get("account_id")
    if not account_id:
        return None
    supplier = await db[COLL_SUPPLIERS].find_one(
        {"paypal_account_id": account_id}, {"_id": 0}
    )
    if not supplier:
        return None
    registry = supplier.get("anagrafica") if isinstance(supplier.get("anagrafica"), dict) else {}
    return {
        "fornitore_id": supplier.get("id"),
        "fornitore_piva": (
            supplier.get("piva") or supplier.get("partita_iva")
            or registry.get("piva") or registry.get("partita_iva")
        ),
        "codice_fiscale": supplier.get("codice_fiscale") or registry.get("codice_fiscale"),
        "fornitore_nome": supplier.get("nome") or registry.get("nome"),
        "fornitore_ragione_sociale": (
            supplier.get("ragione_sociale") or registry.get("ragione_sociale")
        ),
    }


async def _invoice_is_available(db, invoice_id: str, transaction_id: str) -> bool:
    invoice = await db[COLL_INVOICES].find_one({"id": invoice_id}, {"_id": 0})
    if not invoice:
        return False
    linked_ids = {
        str(value) for value in (invoice.get("paypal_transaction_ids") or []) if value
    }
    if invoice.get("paypal_transaction_id"):
        linked_ids.add(str(invoice["paypal_transaction_id"]))
    if linked_ids - {transaction_id}:
        return False
    if (
        invoice.get("pagato") is True
        or str(invoice.get("stato_pagamento") or "").lower() in {"pagata", "paid"}
    ) and transaction_id not in linked_ids:
        return False
    other = await db[COLL_TRANSACTIONS].find_one({
        "fattura_associata.fattura_id": invoice_id,
        "transaction_id": {"$ne": transaction_id},
    }, {"_id": 0, "transaction_id": 1})
    return other is None


async def finalizza_transazione_paypal_se_completa(
    db, transaction_id: str,
) -> Dict[str, Any]:
    """Chiude la fattura solo quando PayPal, fattura e banca sono tutti legati."""
    transaction = await db[COLL_TRANSACTIONS].find_one(
        {"$or": [{"transaction_id": transaction_id}, {"id": transaction_id}]},
        {"_id": 0},
    )
    if not transaction:
        return {"finalizzata": False, "motivo": "transazione_non_trovata"}
    association = transaction.get("fattura_associata") or {}
    invoice_id = association.get("fattura_id")
    if not invoice_id:
        return {"finalizzata": False, "motivo": "fattura_non_collegata"}
    movement_id = (
        transaction.get("movimento_banca_id")
        or transaction.get("estratto_conto_movimento_id")
    )
    if not movement_id:
        return {"finalizzata": False, "motivo": "estratto_conto_non_collegato"}
    movement = await db[COLL_BANK].find_one(
        {"id": movement_id}, {"_id": 0}
    )
    if not movement or not (
        movement.get("riconciliato")
        and str(movement.get("paypal_transaction_id") or "") == transaction_id
    ):
        return {"finalizzata": False, "motivo": "riscontro_bancario_non_confermato"}
    invoice = await db[COLL_INVOICES].find_one({"id": invoice_id})
    if not invoice:
        return {"finalizzata": False, "motivo": "fattura_non_trovata"}

    from app.services.riconciliazione_bancaria import _applica_pagamento_banca

    now = datetime.now(timezone.utc).isoformat()
    # Un solo identificativo attraversa fattura, pagamento PayPal, estratto
    # conto e Prima Nota. Consente il deep-link tra le sezioni senza usare
    # importo/data come identita' dell'operazione.
    operation_id = str(
        transaction.get("payment_operation_id") or f"paypal:{transaction_id}"
    )
    payment_date = str(
        movement.get("data") or movement.get("data_contabile")
        or transaction.get("data_banca") or transaction.get("data") or ""
    )[:10]
    await _applica_pagamento_banca(
        db, invoice, "PayPal", payment_date, movement_id,
        int(transaction.get("riconciliazione_banca_score") or 20), now,
        source="riconciliazione_paypal_end_to_end",
        importo_pagamento=transaction_amount(transaction),
    )
    await db[COLL_INVOICES].update_one({"id": invoice_id}, {"$set": {
        "riconciliato_paypal": True,
        "paypal_riconciliato_banca": True,
        "paypal_transaction_id": transaction_id,
        "paypal_movimento_banca_id": movement_id,
        "payment_operation_id": operation_id,
        "stato_finanziario": "riconciliato",
        "updated_at": now,
    }})
    await db[COLL_TRANSACTIONS].update_one(
        {"$or": [{"transaction_id": transaction_id}, {"id": transaction_id}]},
        {"$set": {
            "payment_operation_id": operation_id,
            "fattura_pagamento_finalizzato": True,
            "fattura_pagamento_finalizzato_at": now,
        }},
    )
    await db[COLL_BANK].update_one({"id": movement_id}, {"$set": {
        "payment_operation_id": operation_id,
        "invoice_id": invoice_id,
        "paypal_transaction_id": transaction_id,
    }})
    await db["prima_nota_banca"].update_many({"$or": [
        {"id": movement_id}, {"movimento_bancario_id": movement_id},
        {"fattura_id": invoice_id},
    ]}, {"$set": {"payment_operation_id": operation_id}})
    try:
        await record_paypal_bank_chain(
            db,
            transaction=transaction,
            invoice=invoice,
            movement=movement,
            amount=transaction_amount(transaction),
        )
    except Exception:
        logger.exception(
            "Errore registrazione catena PayPal/banca %s", transaction_id
        )
    return {
        "finalizzata": True,
        "transaction_id": transaction_id,
        "fattura_id": invoice_id,
        "movimento_banca_id": movement_id,
        "payment_operation_id": operation_id,
    }


async def collega_transazione_a_fattura(
    db,
    transaction: Dict[str, Any],
    invoice: Dict[str, Any],
    evaluation: Dict[str, Any],
    *,
    automatic: bool,
) -> Dict[str, Any]:
    """Scrive il link su entrambi i documenti e prova a chiudere la catena."""
    transaction_id = _tx_id(transaction)
    invoice_id = _invoice_id(invoice)
    if not transaction_id or not invoice_id:
        return {"collegata": False, "motivo": "identificativo_mancante"}
    if not evaluation.get("associabile"):
        return {"collegata": False, "motivo": evaluation.get("scarto") or "evidenze_insufficienti"}

    current = transaction.get("fattura_associata") or {}
    if current.get("fattura_id") and str(current["fattura_id"]) != invoice_id:
        return {"collegata": False, "motivo": "transazione_gia_collegata_ad_altra_fattura"}
    if not await _invoice_is_available(db, invoice_id, transaction_id):
        return {"collegata": False, "motivo": "fattura_gia_collegata_ad_altra_transazione"}

    now = datetime.now(timezone.utc).isoformat()
    link = {
        "fattura_id": invoice_id,
        "numero": invoice_number(invoice),
        "data": invoice.get("invoice_date") or invoice.get("data_fattura"),
        "fornitore": invoice.get("supplier_name") or invoice.get("cedente_denominazione"),
        "importo": invoice_amount(invoice),
        "view_url": f"/api/fatture-ricevute/fattura/{invoice_id}/view-assoinvoice",
        "auto": automatic,
        "match": "fornitore_numero_importo_esatti" if automatic else "manuale_validato",
        "evidenze": evaluation.get("evidenze") or [],
        "collegata_at": now,
    }
    await db[COLL_TRANSACTIONS].update_one(
        {"$or": [{"transaction_id": transaction_id}, {"id": transaction_id}]},
        {"$set": {
            "fattura_associata": link,
            "payment_operation_id": str(transaction.get("payment_operation_id") or f"paypal:{transaction_id}"),
        }},
    )
    await db[COLL_INVOICES].update_one({"id": invoice_id}, {
        "$set": {
            "paypal_transaction_id": transaction_id,
            "payment_operation_id": str(transaction.get("payment_operation_id") or f"paypal:{transaction_id}"),
            "paypal_fattura_collegata": True,
            "paypal_fattura_collegata_at": now,
            "metodo_pagamento_rilevato": "PayPal",
            "stato_finanziario": "in_attesa_estratto_conto",
            "updated_at": now,
        },
        "$addToSet": {"paypal_transaction_ids": transaction_id},
    })
    try:
        relation_evidence = []
        for item in evaluation.get("evidenze") or []:
            if isinstance(item, dict):
                relation_evidence.append(item)
            elif str(item or "").strip():
                relation_evidence.append({
                    "type": "paypal_match",
                    "value": str(item).strip(),
                })
        await record_paypal_invoice_link(
            db,
            transaction=transaction,
            invoice=invoice,
            amount=transaction_amount(transaction),
            evidence=relation_evidence,
        )
    except Exception:
        logger.exception(
            "Errore registrazione relazione PayPal/fattura %s", transaction_id
        )
    finalization = await finalizza_transazione_paypal_se_completa(db, transaction_id)
    return {
        "collegata": True,
        "transaction_id": transaction_id,
        "fattura_id": invoice_id,
        "finalizzazione": finalization,
        "fattura_associata": link,
    }


async def _candidate_invoices(db, transaction: Dict[str, Any], *, invoice_id: Optional[str] = None):
    amount = transaction_amount(transaction)
    query: Dict[str, Any]
    if invoice_id:
        query = {"id": invoice_id}
    else:
        query = {"$or": [
            {"total_amount": {"$gte": amount - 0.004, "$lte": amount + 0.004}},
            {"importo_totale": {"$gte": amount - 0.004, "$lte": amount + 0.004}},
        ]}
    return await db[COLL_INVOICES].find(query, {"_id": 0}).limit(100).to_list(100)


async def associa_transazione_univoca(
    db, transaction: Dict[str, Any], *, invoice_id: Optional[str] = None,
    automatic: bool = True,
) -> Dict[str, Any]:
    if not is_successful_paypal_payment(transaction) or transaction.get("is_pagopa"):
        return {"collegata": False, "motivo": "non_pagamento_commerciale_valido"}
    mapping = await supplier_mapping_for_transaction(db, transaction)
    valid = []
    for invoice in await _candidate_invoices(db, transaction, invoice_id=invoice_id):
        evaluation = evaluate_paypal_invoice_match(transaction, invoice, mapping)
        if evaluation["associabile"]:
            valid.append((evaluation, invoice))
    valid.sort(key=lambda item: item[0]["score"], reverse=True)
    if not valid:
        return {"collegata": False, "motivo": "nessuna_fattura_con_evidenze_complete"}
    if len(valid) > 1 and valid[0][0]["score"] == valid[1][0]["score"]:
        return {"collegata": False, "motivo": "fatture_ambigue", "candidati": len(valid)}
    return await collega_transazione_a_fattura(
        db, transaction, valid[0][1], valid[0][0], automatic=automatic,
    )


async def riprocessa_collegamenti_paypal(
    db, *, start_date: Optional[str] = None, end_date: Optional[str] = None,
    limit: int = 5000,
) -> Dict[str, Any]:
    """Riprocessa lo storico senza dipendere dall'ordine degli import."""
    date_filter: Dict[str, Any] = {}
    if start_date:
        date_filter["$gte"] = start_date
    if end_date:
        date_filter["$lte"] = end_date + ("T23:59:59Z" if "T" not in end_date else "")
    query: Dict[str, Any] = {"$or": [
        {"importo": {"$lt": 0}}, {"lordo": {"$lt": 0}}, {"amount": {"$lt": 0}},
    ]}
    if date_filter:
        query["$and"] = [{"$or": [
            {"initiation_date": date_filter}, {"data": date_filter},
        ]}]
    transactions = await db[COLL_TRANSACTIONS].find(query, {"_id": 0}).limit(limit).to_list(limit)
    result = {
        "analizzate": len(transactions), "associate": 0, "finalizzate": 0,
        "ambigue": 0, "gia_collegate": 0, "non_trovate": 0, "errori": 0,
    }
    for transaction in transactions:
        try:
            association = transaction.get("fattura_associata") or {}
            if association.get("fattura_id"):
                result["gia_collegate"] += 1
                finalization = await finalizza_transazione_paypal_se_completa(db, _tx_id(transaction))
                result["finalizzate"] += int(bool(finalization.get("finalizzata")))
                continue
            outcome = await associa_transazione_univoca(db, transaction)
            if outcome.get("collegata"):
                result["associate"] += 1
                result["finalizzate"] += int(bool(
                    (outcome.get("finalizzazione") or {}).get("finalizzata")
                ))
            elif outcome.get("motivo") == "fatture_ambigue":
                result["ambigue"] += 1
            else:
                result["non_trovate"] += 1
        except Exception:
            logger.exception(
                "Errore nel riprocessamento PayPal transaction_id=%s",
                _tx_id(transaction),
            )
            result["errori"] += 1
    return result


async def collega_fattura_paypal_appena_importata(db, invoice: Dict[str, Any]) -> Dict[str, Any]:
    """Hook fattura-late: cerca la transazione PayPal gia' importata."""
    amount = invoice_amount(invoice)
    if amount <= 0:
        return {"collegata": False, "motivo": "importo_fattura_non_valido"}
    candidates = await db[COLL_TRANSACTIONS].find({"$or": [
        {"importo": {"$gte": -amount - 0.004, "$lte": -amount + 0.004}},
        {"lordo": {"$gte": -amount - 0.004, "$lte": -amount + 0.004}},
        {"amount": {"$gte": -amount - 0.004, "$lte": -amount + 0.004}},
    ]}, {"_id": 0}).limit(100).to_list(100)
    valid = []
    for transaction in candidates:
        if not is_successful_paypal_payment(transaction) or transaction.get("is_pagopa"):
            continue
        mapping = await supplier_mapping_for_transaction(db, transaction)
        evaluation = evaluate_paypal_invoice_match(transaction, invoice, mapping)
        if evaluation["associabile"]:
            valid.append((evaluation, transaction))
    valid.sort(key=lambda item: item[0]["score"], reverse=True)
    if not valid:
        return {"collegata": False, "motivo": "nessuna_transazione_con_evidenze_complete"}
    if len(valid) > 1 and valid[0][0]["score"] == valid[1][0]["score"]:
        return {"collegata": False, "motivo": "transazioni_ambigue", "candidati": len(valid)}
    return await collega_transazione_a_fattura(
        db, valid[0][1], invoice, valid[0][0], automatic=True,
    )
