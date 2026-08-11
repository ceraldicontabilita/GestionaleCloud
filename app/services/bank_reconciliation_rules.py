"""Regole deterministiche e auditabili per le causali bancarie.

La classificazione della natura del movimento e il collegamento a un documento
sono due decisioni diverse.  Questo modulo si limita alla prima: non scrive dati
e non considera mai l'uguaglianza dell'importo come identita' sufficiente.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from app.services.payment_allocation_validator import to_cents


RULE_VERSION = "2026.08.11.1"


def _text(movement: Dict[str, Any]) -> str:
    return " ".join(
        str(movement.get(field) or "")
        for field in (
            "descrizione_originale", "descrizione", "causale",
            "beneficiario", "ordinante",
        )
        if movement.get(field)
    ).strip()


def _evidence(movement: Dict[str, Any], raw_text: str) -> list[Dict[str, Any]]:
    return [
        {"tipo": "movimento_bancario", "id": str(movement.get("id") or "")},
        {"tipo": "causale", "testo": raw_text},
        {"tipo": "importo_centesimi", "valore": abs(to_cents(movement.get("importo")))},
        {"tipo": "data", "valore": str(movement.get("data") or "")[:10]},
    ]


def _result(
    movement: Dict[str, Any], *, rule_id: str, tipo: str, categoria: str,
    extracted: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    text = _text(movement)
    return {
        "rule_id": rule_id,
        "rule_version": RULE_VERSION,
        "tipo": tipo,
        "categoria": categoria,
        "campi_estratti": extracted or {},
        "evidenze": _evidence(movement, text),
        "classificazione_certa": True,
    }


def classify_bank_movement(movement: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Classifica una causale solo quando esiste un pattern deterministico."""
    text = _text(movement)
    upper = text.upper()
    if not upper:
        return None

    if re.search(r"\bINC\.?\s*POS\b|\bINCASSO\s+POS\b|\bACCREDITO\s+POS\b|\bNUMIA[-\s]", upper):
        circuit_match = re.search(r"\b(AMEX|INTER|BNCMT|BANCOMAT|PAGOBANCOMAT)\b", upper)
        date_match = re.search(r"\bDEL\s+(\d{2}[/-]\d{2}(?:[/-]\d{2,4})?)", upper)
        terminal_match = re.search(r"\b(?:PDV|TERM(?:INALE)?)\s*[:.-]?\s*([A-Z0-9]+)", upper)
        return _result(
            movement, rule_id="bank.pos_credit.v1", tipo="incasso_pos",
            categoria="Incasso POS",
            extracted={
                "circuito": circuit_match.group(1) if circuit_match else None,
                "giorno_vendita": date_match.group(1) if date_match else None,
                "terminale": terminal_match.group(1) if terminal_match else None,
            },
        )

    if re.search(r"\bVERS\.?\s+CONTANTI\b|\bVERSAMENTO\s+CONTANTI\b", upper):
        return _result(
            movement, rule_id="bank.cash_deposit.v1", tipo="versamento_contanti",
            categoria="Versamento contanti",
        )

    if re.search(r"\bSPESE\s*-?\s*RILASCIO\s+CARNET\s+ASSEGNI\b", upper):
        return _result(
            movement, rule_id="bank.cheque_book_fee.v1", tipo="commissione_bancaria",
            categoria="Spese carnet assegni",
        )

    if re.search(r"\bINT\.?\s+E\s+COMP\.?\s*-?\s*COMPETENZE\b", upper):
        return _result(
            movement, rule_id="bank.account_fee.v1", tipo="commissione_bancaria",
            categoria="Competenze bancarie",
        )

    if re.search(r"\bCOMMISSION(?:E|I)\b|\bCOMM\.?\s+SU\s+BONIFICI\b", upper):
        return _result(
            movement, rule_id="bank.generic_fee.v1", tipo="commissione_bancaria",
            categoria="Commissioni bancarie",
        )

    if re.search(r"\b(?:ADDEBITO\s+DIRETTO\s+)?SDD\b", upper):
        mandate = re.search(r"\b(?:MANDATO|MANDATE)\s*[:.-]?\s*([A-Z0-9-]+)", upper)
        creditor = re.search(r"\b(?:CREDITORE|CREDITOR)\s*[:.-]?\s*([^;|]+)", text, re.IGNORECASE)
        return _result(
            movement, rule_id="bank.sdd_debit.v1", tipo="fattura_sdd",
            categoria="Addebito diretto SDD",
            extracted={
                "mandato": mandate.group(1) if mandate else None,
                "creditore": creditor.group(1).strip() if creditor else None,
            },
        )

    if re.search(r"\bI24\s+AGENZIA\s+ENTRATE\b|\bPAG\.?TO\s+TELEMATICO\b", upper):
        return _result(
            movement, rule_id="bank.f24_debit.v1", tipo="f24",
            categoria="Pagamento F24",
        )

    return None
