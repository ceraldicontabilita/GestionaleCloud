"""Regole deterministiche del sottosistema fiscale evidence-bound.

Questo modulo non decide mai che un importo e' pagato dal nome di un file,
dal residuo zero o da un F24 predisposto. Le funzioni pure sono condivise da
router, job di import e test, cosi' la semantica resta versionabile.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import StrEnum
from typing import Any, Iterable

from app.services.fiscal_evidence import now_iso as utc_now, stable_id


CENT = Decimal("0.01")


class DocumentType(StrEnum):
    F24 = "F24"
    QUIETANZA_F24 = "QUIETANZA_F24"
    RICEVUTA_F24 = "RICEVUTA_F24"
    DICHIARAZIONE_IVA = "DICHIARAZIONE_IVA"
    LIPE = "LIPE"
    MODELLO_770 = "MODELLO_770"
    CU = "CU"
    AVVISO_BONARIO = "AVVISO_BONARIO"
    COMUNICAZIONE_IRREGOLARITA = "COMUNICAZIONE_IRREGOLARITA"
    CARTELLA_ADE_R = "CARTELLA_ADE_R"
    AVVISO_ADDEBITO_INPS = "AVVISO_ADDEBITO_INPS"
    QUIETANZA_ADE_R = "QUIETANZA_ADE_R"
    RICEVUTA_PAGOPA = "RICEVUTA_PAGOPA"
    RICEVUTA_CBILL = "RICEVUTA_CBILL"
    PIANO_RATEIZZAZIONE = "PIANO_RATEIZZAZIONE"
    RATA_RATEIZZAZIONE = "RATA_RATEIZZAZIONE"
    DEFINIZIONE_AGEVOLATA = "DEFINIZIONE_AGEVOLATA"
    SGRAVIO = "SGRAVIO"
    SOSPENSIONE = "SOSPENSIONE"
    AUTOTUTELA = "AUTOTUTELA"
    SENTENZA = "SENTENZA"
    ATTO_GIUDIZIARIO = "ATTO_GIUDIZIARIO"
    DIRITTO_CAMERA_COMMERCIO = "DIRITTO_CAMERA_COMMERCIO"
    VERBALE_CODICE_STRADA = "VERBALE_CODICE_STRADA"
    MOVIMENTO_BANCARIO_DOCUMENTO = "MOVIMENTO_BANCARIO_DOCUMENTO"
    ALTRO_FISCALE = "ALTRO_FISCALE"


class PaymentStatus(StrEnum):
    DUE = "DUE"
    PAID_ON_TIME = "PAID_ON_TIME"
    PAID_LATE = "PAID_LATE"
    PAID_LATE_WITH_COMPLETE_RAVVEDIMENTO = "PAID_LATE_WITH_COMPLETE_RAVVEDIMENTO"
    PAID_LATE_WITH_INCOMPLETE_RAVVEDIMENTO = "PAID_LATE_WITH_INCOMPLETE_RAVVEDIMENTO"
    PAID_LATE_WITHOUT_RAVVEDIMENTO = "PAID_LATE_WITHOUT_RAVVEDIMENTO"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    OFFSET_BY_CREDIT = "OFFSET_BY_CREDIT"
    PAID_AFTER_NOTICE = "PAID_AFTER_NOTICE"
    PAID_AFTER_ROLE = "PAID_AFTER_ROLE"
    PAID_AFTER_CARTELLA = "PAID_AFTER_CARTELLA"
    SUSPENDED = "SUSPENDED"
    RELIEVED = "RELIEVED"
    TO_VERIFY = "TO_VERIFY"


class RavvedimentoStatus(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"
    NOT_DETERMINABLE = "NOT_DETERMINABLE"


PAYMENT_EVIDENCE_TYPES = {
    DocumentType.QUIETANZA_F24.value,
    DocumentType.RICEVUTA_F24.value,
    DocumentType.QUIETANZA_ADE_R.value,
    DocumentType.RICEVUTA_PAGOPA.value,
    DocumentType.RICEVUTA_CBILL.value,
    "BANK_MOVEMENT",
}


def money(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Importo non valido: {value!r}") from exc


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def normalize_cartella_number(value: str) -> str:
    """Normalizza per il matching preservando sempre l'originale nel record."""
    return re.sub(r"[^0-9A-Z]", "", (value or "").upper())


_CLASSIFIERS: tuple[tuple[DocumentType, tuple[str, ...]], ...] = (
    (DocumentType.QUIETANZA_ADE_R, ("quietanza ader", "quietanza ade-r", "ricevuta pagamento riscossione")),
    (DocumentType.CARTELLA_ADE_R, ("cartella di pagamento", "cartella esattoriale", "agenzia entrate riscossione")),
    (DocumentType.AVVISO_BONARIO, ("avviso bonario", "comunicazione di irregolarita")),
    (DocumentType.PIANO_RATEIZZAZIONE, ("piano di ammortamento", "piano rateizzazione")),
    (DocumentType.DEFINIZIONE_AGEVOLATA, ("definizione agevolata", "rottamazione")),
    (DocumentType.SOSPENSIONE, ("sospensione della riscossione", "provvedimento di sospensione")),
    (DocumentType.SGRAVIO, ("provvedimento di sgravio", "sgravio")),
    (DocumentType.QUIETANZA_F24, ("quietanza f24", "esito delega", "protocollo telematico")),
    (DocumentType.LIPE, ("liquidazioni periodiche iva", "comunicazione liquidazioni")),
    (DocumentType.MODELLO_770, ("modello 770", "770/")),
    (DocumentType.DICHIARAZIONE_IVA, ("dichiarazione iva", "modello iva")),
    (DocumentType.F24, ("modello f24", "f24")),
    (DocumentType.RICEVUTA_PAGOPA, ("pagopa", "iuv")),
    (DocumentType.RICEVUTA_CBILL, ("cbill",)),
)


def classify_document(filename: str, text: str = "") -> dict[str, Any]:
    haystack = f"{filename} {text[:12000]}".casefold()
    for doc_type, markers in _CLASSIFIERS:
        matched = [marker for marker in markers if marker in haystack]
        if matched:
            return {
                "document_type": doc_type.value,
                "confidence": 0.95 if text else 0.65,
                "reasons": [f"marker:{marker}" for marker in matched],
                "requires_review": not bool(text),
            }
    return {
        "document_type": DocumentType.ALTRO_FISCALE.value,
        "confidence": 0.0,
        "reasons": ["nessun_marcatore_deterministico"],
        "requires_review": True,
    }


def classify_f24_line(tax_code: str, amount: Any, *, is_credit: bool = False) -> dict[str, Any]:
    """Scompone la riga F24 senza registrare un secondo costo contabile."""
    code = str(tax_code or "").strip().upper()
    return {"tax_code": code, "amount": str(money(amount)),
            "kind": "credit" if is_credit else "debit",
            "vat_cycle": {"6012": "monthly_december", "6013": "annual_advance",
                          "6099": "annual_balance"}.get(code),
            "is_accounting_cost": False}


def fiscal_control_findings(obligations: Iterable[dict[str, Any]],
                            claims: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for claim in claims:
        if money(claim.get("current_due")) == 0 and not claim.get("payment_evidence_ids"):
            findings.append({"code": "ZERO_WITHOUT_PAYMENT_EVIDENCE", "severity": "warning",
                             "entity_id": claim.get("id"),
                             "message": "Residuo zero senza prova documentale di pagamento."})
        if claim.get("substantive_validity_status", "NOT_REVIEWED") == "NOT_REVIEWED":
            findings.append({"code": "ORIGINAL_CLAIM_NOT_REVIEWED", "severity": "warning",
                             "entity_id": claim.get("id"),
                             "message": "Il pagamento non dimostra la correttezza della pretesa originaria."})
    for obligation in obligations:
        if not obligation.get("evidence_ids"):
            findings.append({"code": "OBLIGATION_WITHOUT_EVIDENCE", "severity": "warning",
                             "entity_id": obligation.get("id"),
                             "message": "Obbligo privo di prova documentale collegata."})
    return findings


def build_evidence(
    *, document_id: str, version_id: str, page_number: int,
    field_name: str, raw_value: Any, normalized_value: Any,
    parser_version: str, confidence: float, reason: str,
) -> dict[str, Any]:
    if page_number < 1:
        raise ValueError("page_number deve essere >= 1")
    if not 0 <= confidence <= 1:
        raise ValueError("confidence deve essere compresa tra 0 e 1")
    evidence_id = stable_id(
        "evidence", document_id, version_id, page_number, field_name,
        json.dumps(raw_value, sort_keys=True, default=str), parser_version,
    )
    return {
        "id": evidence_id,
        "document_id": document_id,
        "version_id": version_id,
        "page_number": page_number,
        "field_name": field_name,
        "raw_value": raw_value,
        "normalized_value": normalized_value,
        "confidence": confidence,
        "parser_version": parser_version,
        "reason": reason,
        "created_at": utc_now(),
    }


def evaluate_payment_status(
    *, due_amount: Any, allocations: Iterable[dict[str, Any]],
    due_date: date | None = None, suspended: bool = False,
    relieved: bool = False, zero_balance_cause: str | None = None,
) -> dict[str, Any]:
    due = money(due_amount)
    proven = []
    rejected = []
    for allocation in allocations:
        evidence_types = set(allocation.get("evidence_types") or [])
        if not evidence_types.intersection(PAYMENT_EVIDENCE_TYPES):
            rejected.append({"id": allocation.get("id"), "reason": "payment_evidence_missing"})
            continue
        proven.append(allocation)
    paid = sum((money(item.get("amount")) for item in proven), Decimal("0.00"))
    residual = max(Decimal("0.00"), due - paid)
    reasons: list[str] = []
    if suspended:
        status = PaymentStatus.SUSPENDED
        reasons.append("sospensione documentata: non equivale a pagamento")
    elif relieved:
        status = PaymentStatus.RELIEVED
        reasons.append("sgravio documentato: non equivale a pagamento")
    elif due == 0 and not zero_balance_cause:
        status = PaymentStatus.TO_VERIFY
        reasons.append("residuo_zero_senza_causa_probatoria")
    elif paid <= 0:
        status = PaymentStatus.DUE
        reasons.append("nessuna_allocazione_con_prova_di_pagamento")
    elif paid < due:
        status = PaymentStatus.PARTIALLY_PAID
        reasons.append("pagamento_probatorio_inferiore_al_dovuto")
    else:
        payment_dates = [item.get("payment_date") for item in proven if item.get("payment_date")]
        latest = max(payment_dates) if payment_dates else None
        if due_date and latest:
            latest_date = date.fromisoformat(str(latest)[:10])
            status = PaymentStatus.PAID_ON_TIME if latest_date <= due_date else PaymentStatus.PAID_LATE
        else:
            status = PaymentStatus.TO_VERIFY
            reasons.append("data_scadenza_o_pagamento_mancante")
    return {
        "payment_status": status.value,
        "due_amount": str(due),
        "proven_paid_amount": str(paid),
        "residual_amount": str(residual),
        "accepted_allocation_ids": [item.get("id") for item in proven],
        "rejected_allocations": rejected,
        "reasons": reasons,
    }


def match_ader_payment(claim: dict[str, Any], payment: dict[str, Any]) -> dict[str, Any]:
    claim_number = normalize_cartella_number(claim.get("cartella_number_original") or claim.get("cartella_number"))
    payment_number = normalize_cartella_number(payment.get("cartella_number"))
    claim_amount = money(claim.get("amount"))
    payment_amount = money(payment.get("amount"))
    same_amount = claim_amount == payment_amount
    same_module = bool(claim.get("payment_module_code")) and claim.get("payment_module_code") == payment.get("payment_module_code")
    same_iuv = bool(claim.get("iuv")) and claim.get("iuv") == payment.get("iuv")
    same_cartella = bool(claim_number) and claim_number == payment_number
    if same_module or (same_cartella and same_iuv and same_amount):
        confidence, reasons = 100, ["identificativo_pagamento_forte", "importo_coerente"]
    elif same_cartella and same_amount and payment.get("psp"):
        confidence, reasons = 98, ["cartella_importo_psp"]
    elif same_amount and claim.get("cbill_code") and claim.get("cbill_code") == payment.get("cbill_code"):
        confidence, reasons = 95, ["cbill_importo"]
    else:
        confidence, reasons = 0, ["nessuna_identita_forte_univoca"]
    return {
        "matched": confidence >= 95,
        "confidence_score": confidence,
        "reasons": reasons,
        "requires_human_review": confidence < 100,
    }


def reconstruct_collection_state(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(events, key=lambda event: (event.get("effective_at") or "", event.get("id") or ""))
    collection_status = "OPEN"
    total_paid = Decimal("0.00")
    total_relief = Decimal("0.00")
    causes: list[str] = []
    for event in ordered:
        event_type = event.get("event_type")
        amount = money(event.get("amount"))
        if event_type in {"PAYMENT", "PARTIAL_PAYMENT", "INSTALLMENT_PAYMENT", "SETTLEMENT_PAYMENT"}:
            total_paid += amount
        elif event_type in {"RELIEF", "PARTIAL_RELIEF"}:
            total_relief += amount
        elif event_type == "SUSPENSION_START":
            collection_status = "SUSPENDED"
            causes.append("SUSPENSION")
        elif event_type == "SUSPENSION_END":
            collection_status = "OPEN"
        elif event_type == "RATE_PLAN_GRANTED":
            collection_status = "RATE_PLAN_ACTIVE"
        elif event_type == "SETTLEMENT_ACCEPTED":
            collection_status = "SETTLEMENT_ACTIVE"
        elif event_type == "CLOSURE":
            cause = event.get("closure_cause")
            if cause not in {"PAYMENT", "SUSPENSION", "RELIEF", "SETTLEMENT", "OFFSET", "COURT_ORDER", "OTHER"}:
                collection_status = "TO_VERIFY"
                causes.append("closure_cause_missing")
            else:
                collection_status = "CLOSED"
                causes.append(cause)
    return {
        "collection_status": collection_status,
        "total_paid": str(total_paid.quantize(CENT)),
        "total_relief": str(total_relief.quantize(CENT)),
        "event_count": len(ordered),
        "closure_causes": causes,
    }


def evaluate_ravvedimento(
    *, due_date: date, payment_date: date, tax_amount: Any,
    penalty_paid: Any, interest_paid: Any, rule: dict[str, Any] | None,
) -> dict[str, Any]:
    if payment_date <= due_date:
        return {"status": RavvedimentoStatus.NOT_REQUIRED.value, "days_late": 0}
    days_late = (payment_date - due_date).days
    if not rule or not rule.get("valid_from") or not rule.get("source_hash"):
        return {
            "status": RavvedimentoStatus.NOT_DETERMINABLE.value,
            "days_late": days_late,
            "reason": "regola_versionata_e_fonte_ufficiale_mancanti",
        }
    try:
        penalty_rate = Decimal(str(rule["penalty_rate"]))
        annual_interest_rate = Decimal(str(rule["annual_interest_rate"]))
    except (KeyError, InvalidOperation):
        return {"status": RavvedimentoStatus.NOT_DETERMINABLE.value, "days_late": days_late, "reason": "parametri_regola_incompleti"}
    tax = money(tax_amount)
    expected_penalty = (tax * penalty_rate).quantize(CENT)
    expected_interest = (tax * annual_interest_rate * Decimal(days_late) / Decimal(365)).quantize(CENT)
    actual_penalty, actual_interest = money(penalty_paid), money(interest_paid)
    if actual_penalty >= expected_penalty and actual_interest >= expected_interest:
        status = RavvedimentoStatus.COMPLETE
    elif actual_penalty == 0 and actual_interest == 0:
        status = RavvedimentoStatus.MISSING
    else:
        status = RavvedimentoStatus.PARTIAL
    return {
        "status": status.value,
        "days_late": days_late,
        "expected_penalty": str(expected_penalty),
        "expected_interest": str(expected_interest),
        "rule_version_id": rule.get("id"),
        "rule_source_hash": rule.get("source_hash"),
    }


def rebuild_vat_credit_chain(movements: Iterable[dict[str, Any]], start_year: int, end_year: int) -> dict[str, Any]:
    balance = Decimal("0.00")
    errors: list[dict[str, Any]] = []
    lineage: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    ordered = sorted(movements, key=lambda item: (item.get("year", 0), item.get("effective_at", ""), item.get("id", "")))
    for movement in ordered:
        year = int(movement.get("year") or 0)
        if year < start_year or year > end_year:
            continue
        movement_id = movement.get("id")
        if not movement_id or not movement.get("evidence_ids"):
            errors.append({"code": "CREDIT_LINEAGE_BREAK", "movement_id": movement_id})
            continue
        if movement_id in used_ids:
            errors.append({"code": "CREDIT_USED_TWICE", "movement_id": movement_id})
            continue
        used_ids.add(movement_id)
        amount = money(movement.get("amount"))
        if movement.get("movement_type") in {"ORIGIN", "ADJUSTMENT_IN", "REFUND_REVERSED"}:
            balance += amount
        elif movement.get("movement_type") in {"OFFSET", "REFUND", "ADJUSTMENT_OUT"}:
            balance -= amount
            if balance < 0:
                errors.append({"code": "F24_OFFSET_MISMATCH", "movement_id": movement_id, "balance": str(balance)})
        lineage.append({"movement_id": movement_id, "year": year, "balance_after": str(balance.quantize(CENT))})
    return {"balance": str(balance.quantize(CENT)), "lineage": lineage, "errors": errors}


def rebuildVatCreditChain(company_id: str, start_year: int, end_year: int,
                          movements: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """API di dominio esplicita; company_id resta obbligatorio e tracciato."""
    if not company_id:
        raise ValueError("company_id obbligatorio")
    result = rebuild_vat_credit_chain(movements, start_year, end_year)
    return {"company_id": company_id, "start_year": start_year, "end_year": end_year, **result}


def build_advisor_brief(claim: dict[str, Any], state: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    missing: list[str] = []
    if not evidence:
        missing.append("documenti_probatori")
    if not claim.get("cartella_number_original"):
        missing.append("numero_cartella")
    return {
        "subject": f"Verifica posizione {claim.get('cartella_number_original') or claim.get('id')}",
        "period": claim.get("tax_period"),
        "amounts": {
            "original": claim.get("original_amount"),
            "current_due": claim.get("current_due"),
            "paid": state.get("total_paid"),
            "relieved": state.get("total_relief"),
        },
        "multidimensional_status": {
            "payment_status": claim.get("payment_status", PaymentStatus.TO_VERIFY.value),
            "collection_status": state.get("collection_status", "TO_VERIFY"),
            "substantive_validity_status": claim.get("substantive_validity_status", "NOT_REVIEWED"),
            "procedural_status": claim.get("procedural_status", "TO_VERIFY"),
        },
        "evidence_ids": [item.get("id") for item in evidence],
        "missing_evidence": missing,
        "questions": ["La pretesa originaria e' documentata?", "Il pagamento e' provato da quietanza o banca?", "Esistono sgravi, sospensioni o definizioni?"],
        "proposed_action": "REVISIONE_UMANA",
        "automatic_submission": False,
    }


def build_review_dossier_pdf(claim: dict[str, Any], brief: dict[str, Any], events: list[dict[str, Any]]) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table

    output = io.BytesIO()
    document = SimpleDocTemplate(output, pagesize=A4)
    styles = getSampleStyleSheet()
    story = [Paragraph("Dossier fiscale - revisione umana", styles["Title"]), Spacer(1, 12)]
    story.append(Paragraph(str(brief.get("subject") or claim.get("id")), styles["Heading2"]))
    status = brief.get("multidimensional_status") or {}
    story.append(Table([["Dimensione", "Stato"], *[[key, value] for key, value in status.items()]], repeatRows=1))
    story.append(Spacer(1, 12))
    story.append(Paragraph("Timeline eventi", styles["Heading2"]))
    timeline = [["Data", "Evento", "Importo", "Prova"]]
    for event in sorted(events, key=lambda item: item.get("effective_at") or ""):
        timeline.append([event.get("effective_at", ""), event.get("event_type", ""), event.get("amount", ""), ", ".join(event.get("evidence_ids") or [])])
    story.append(Table(timeline, repeatRows=1))
    story.append(Spacer(1, 12))
    story.append(Paragraph("Documento preparatorio: nessun invio automatico e nessuna conclusione priva di prova.", styles["BodyText"]))
    document.build(story)
    return output.getvalue()


def build_evidence_package_zip(*, claim: dict[str, Any], dossier_pdf: bytes, originals: Iterable[dict[str, Any]]) -> bytes:
    output = io.BytesIO()
    claim_number = normalize_cartella_number(claim.get("cartella_number_original") or claim.get("id")) or "DA_VERIFICARE"
    manifest: list[dict[str, Any]] = []
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        dossier_name = f"DOSSIER_FISCALE_{claim_number}.pdf"
        archive.writestr(dossier_name, dossier_pdf)
        manifest.append({"name": dossier_name, "sha256": sha256_bytes(dossier_pdf), "kind": "generated_dossier"})
        for original in originals:
            content = original["content"]
            filename = re.sub(r"[^A-Za-z0-9._-]", "_", original.get("filename") or "documento.pdf")
            archive.writestr(f"originali/{filename}", content)
            manifest.append({"name": f"originali/{filename}", "sha256": sha256_bytes(content), "kind": "original_unmodified"})
        draft = "BOZZA NON INVIATA - richiesta di riesame da completare e approvare manualmente.\n"
        archive.writestr("BOZZA_RICHIESTA_RIESAME.txt", draft.encode("utf-8"))
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8"))
    return output.getvalue()
