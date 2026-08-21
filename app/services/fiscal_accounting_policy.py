"""Policy contabile fiscale, senza scritture definitive.

Questo modulo traduce l'evidenza documentale in una *proposta* di bilancio.
Non scrive su Drive/Sheets e non decide da solo la deducibilita': la natura
contabile (stato patrimoniale/conto economico) e la deducibilita' IRES/IRAP
sono assi distinti e restano subordinate a contesto, periodo e approvazione.

Un modello F24 non e' una quietanza. Un avviso PagoPA non e' una ricevuta.
La proposta diventa pronta per l'approvazione solo quando esiste una prova
di pagamento compatibile; la banca resta una prova separata.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


POLICY_VERSION = "fiscal-accounting-policy-2026-08-11"

_AE_CODE_URL = "https://www1.agenziaentrate.gov.it/servizi/codici/ricerca/"
_OIC_25_URL = "https://www.fondazioneoic.eu/wp-content/uploads/2011/02/2024-03-OIC-25-Imposte-sul-reddito.pdf"


# Registro minimo, versionato per decorrenza. Un codice assente non viene
# considerato valido perche' il registro ufficiale deve essere esteso con una
# fonte e una decorrenza prima di abilitare la contabilizzazione.
TAX_CODE_REGISTRY: dict[str, dict[str, Any]] = {
    "1040": {
        "valid_from": "1998-01-01",
        "valid_to": None,
        "status": "VALID",
        "description": "Ritenute su redditi di lavoro autonomo",
        "nature": "TAX_LIABILITY_SETTLEMENT",
        "balance_sheet_account": "D12_DEBITI_TRIBUTARI_RITENUTE",
        "balance_sheet_section": "PASSIVO_D12_DEBITI_TRIBUTARI",
        "income_statement_account": None,
        "income_statement_section": None,
        "deductibility_ires": "NON_APPLICABILE_NON_E_UN_COSTO",
        "deductibility_irap": "NON_APPLICABILE_NON_E_UN_COSTO",
        "source_url": f"{_AE_CODE_URL}SezioneErario.php?CT=1040&Ord=0492&Q1=Tutte&Q2=&Q3=IRPEF&Q4=Tutte",
    },
    "7085": {
        "valid_from": "1998-01-01",
        "valid_to": None,
        "status": "VALID",
        "description": "Tassa annuale vidimazione libri sociali",
        "nature": "TAX_OBLIGATION",
        "balance_sheet_account": "D12_DEBITI_TRIBUTARI",
        "balance_sheet_section": "PASSIVO_D12_DEBITI_TRIBUTARI",
        "income_statement_account": "B14_TASSE_E_ONERI_DIVERSI",
        "income_statement_section": "CONTO_ECONOMICO_B14",
        "deductibility_ires": "DA_VERIFICARE_COMPETENZA_E_REGISTRAZIONE_PRECEDENTE",
        "deductibility_irap": "DA_VERIFICARE_COMPETENZA_E_REGISTRAZIONE_PRECEDENTE",
        "source_url": f"{_AE_CODE_URL}SezioneErario.php?CT=7085&Ord=2487&Q1=&Q2=&Q3=&Q4=Tutte",
    },
    "3918": {
        "valid_from": "2012-01-01",
        "valid_to": None,
        "status": "VALID",
        "description": "IMU altri fabbricati - comune",
        "nature": "LOCAL_TAX_OBLIGATION",
        "balance_sheet_account": "D12_DEBITI_TRIBUTARI_IMU",
        "balance_sheet_section": "PASSIVO_D12_DEBITI_TRIBUTARI",
        "income_statement_account": "B14_IMU_E_TRIBUTI_LOCALI",
        "income_statement_section": "CONTO_ECONOMICO_B14",
        "deductibility_ires": "DA_VERIFICARE_IMMOBILE_E_DESTINAZIONE",
        "deductibility_irap": "DA_VERIFICARE_NON_AUTOMATICA",
        "source_url": _AE_CODE_URL,
    },
    "3813": {
        "valid_from": "2012-01-01",
        "valid_to": None,
        "status": "VALID",
        "description": "IRAP acconto seconda rata o unica soluzione",
        "nature": "TAX_ADVANCE",
        "balance_sheet_account": "D12_CREDITI_O_DEBITI_IRAP",
        "balance_sheet_section": "ATTIVO_CII_CREDITI_TRIBUTARI_O_PASSIVO_D12",
        "income_statement_account": "IMPOSTE_SUL_REDDITO_IRAP",
        "income_statement_section": "CONTO_ECONOMICO_IMPOSTE_SUL_REDDITO",
        "deductibility_ires": "DA_VERIFICARE_LIQUIDAZIONE_IRAP",
        "deductibility_irap": "DA_VERIFICARE_LIQUIDAZIONE_IRAP",
        "source_url": f"{_AE_CODE_URL}MenuQ4.php?Q1=Tutte&Q2=PER+RAVVEDIMENTO+OPEROSO&Q3=IRAP",
    },
    "1993": {
        "valid_from": "2012-01-01",
        "valid_to": None,
        "status": "VALID",
        "description": "Interessi ravvedimento IRAP",
        "nature": "TAX_INTEREST",
        "balance_sheet_account": "D12_DEBITI_TRIBUTARI",
        "balance_sheet_section": "PASSIVO_D12_DEBITI_TRIBUTARI",
        "income_statement_account": "ONERI_FINANZIARI_INTERESSI_RAVVEDIMENTO",
        "income_statement_section": "CONTO_ECONOMICO_C17_O_B14_DA_VERIFICARE",
        "deductibility_ires": "DA_VERIFICARE",
        "deductibility_irap": "DA_VERIFICARE",
        "source_url": f"{_AE_CODE_URL}MenuQ4.php?Q1=Tutte&Q2=PER+RAVVEDIMENTO+OPEROSO&Q3=IRAP",
    },
    "8907": {
        "valid_from": "2012-01-01",
        "valid_to": None,
        "status": "VALID",
        "description": "Sanzione pecuniaria IRAP",
        "nature": "TAX_PENALTY",
        "balance_sheet_account": "D12_DEBITI_TRIBUTARI",
        "balance_sheet_section": "PASSIVO_D12_DEBITI_TRIBUTARI",
        "income_statement_account": "B14_SANZIONI_TRIBUTARIE",
        "income_statement_section": "CONTO_ECONOMICO_B14_SEPARATO_INDEDUCIBILE",
        "deductibility_ires": "INDEDUCIBILE_DA_CONFERMARE",
        "deductibility_irap": "INDEDUCIBILE_DA_CONFERMARE",
        "source_url": f"{_AE_CODE_URL}MenuQ4.php?Q1=Tutte&Q2=PER+RAVVEDIMENTO+OPEROSO&Q3=IRAP",
    },
    "1701": {
        "valid_from": "2020-01-01",
        "valid_to": None,
        "status": "VALID",
        "description": "Credito trattamento integrativo",
        "nature": "TAX_CREDIT",
        "balance_sheet_account": "CREDITI_TRIBUTARI_DA_ORIGINARE",
        "balance_sheet_section": "ATTIVO_CII_CREDITI_TRIBUTARI",
        "income_statement_account": None,
        "income_statement_section": None,
        "deductibility_ires": "NON_APPLICABILE_CREDITO",
        "deductibility_irap": "NON_APPLICABILE_CREDITO",
        "source_url": f"{_AE_CODE_URL}SezioneErario.php?CT=1701",
    },
    "1704": {
        "valid_from": "2020-01-01",
        "valid_to": None,
        "status": "VALID",
        "description": "Credito sostituto d'imposta",
        "nature": "TAX_CREDIT",
        "balance_sheet_account": "CREDITI_TRIBUTARI_DA_ORIGINARE",
        "balance_sheet_section": "ATTIVO_CII_CREDITI_TRIBUTARI",
        "income_statement_account": None,
        "income_statement_section": None,
        "deductibility_ires": "NON_APPLICABILE_CREDITO",
        "deductibility_irap": "NON_APPLICABILE_CREDITO",
        "source_url": f"{_AE_CODE_URL}SezioneErario.php?CT=1704",
    },
    # L'Agenzia restituisce esplicitamente "Codice Tributo inesistente".
    "1075": {
        "valid_from": None,
        "valid_to": None,
        "status": "INVALID_OFFICIAL_REGISTER",
        "description": "Codice tributo non validato dall'archivio ufficiale",
        "nature": "UNVALIDATED_TAX_CODE",
        "balance_sheet_account": None,
        "balance_sheet_section": None,
        "income_statement_account": None,
        "income_statement_section": None,
        "deductibility_ires": "DA_VERIFICARE",
        "deductibility_irap": "DA_VERIFICARE",
        "source_url": f"{_AE_CODE_URL}SezioneErario.php?CT=1075&Ord=0526",
    },
}


def tax_code_rule(code: Any, *, period: Any = None) -> dict[str, Any]:
    """Restituisce la regola applicabile senza inventare una validita'."""
    normalized = str(code or "").strip().upper()
    rule = deepcopy(TAX_CODE_REGISTRY.get(normalized))
    if rule is None:
        return {
            "code": normalized,
            "status": "NOT_IN_LOCAL_VERSIONED_REGISTRY",
            "description": f"Codice {normalized or 'vuoto'} non validato",
            "nature": "UNVALIDATED_TAX_CODE",
            "balance_sheet_account": None,
            "balance_sheet_section": None,
            "income_statement_account": None,
            "income_statement_section": None,
            "deductibility_ires": "DA_VERIFICARE",
            "deductibility_irap": "DA_VERIFICARE",
            "source_url": _AE_CODE_URL,
        }
    rule["code"] = normalized
    rule["period_checked"] = str(period or "") or None
    return rule


def _cents(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            text = str(value).replace(".", "").replace(",", ".")
            return int((Decimal(text) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        except (InvalidOperation, TypeError, ValueError):
            return 0


def _rows(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalizza righe usando il servizio F24 canonico, senza scrivere."""
    try:
        from app.services.f24_canonico import normalizza_righe_tributo

        return normalizza_righe_tributo(document)
    except Exception:
        return []


def _document_kind(document: dict[str, Any], explicit: str | None) -> str:
    return str(
        explicit
        or document.get("document_kind")
        or document.get("tipo_documento")
        or document.get("tipo")
        or "F24_MODELLO"
    ).upper()


def _has_payment_evidence(kind: str, evidence_state: dict[str, Any]) -> bool:
    return bool(
        evidence_state.get("quietanza_validata")
        or evidence_state.get("pagato_documentalmente")
        or kind in {"F24_QUIETANZA", "QUIETANZA_AE", "RICEVUTA_PAGOPA", "RICEVUTA_CBILL"}
    )


def _source(document: dict[str, Any]) -> dict[str, Any]:
    general = document.get("dati_generali") or {}
    return {
        "document_id": document.get("id") or document.get("document_id"),
        "pdf_hash": document.get("pdf_hash") or document.get("file_hash"),
        "filename": document.get("filename") or document.get("file_name"),
        "page": document.get("pagina") or document.get("page_number"),
        "parser_version": (document.get("validazione") or {}).get("parser_version")
        or document.get("parser_version"),
        "taxpayer_id": general.get("taxpayer_id") or general.get("codice_fiscale")
        or document.get("codice_fiscale"),
        "intermediary_id": general.get("intermediary_id")
        or general.get("intermediario_codice_fiscale"),
    }


def _deductibility(rule: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    status = {
        "ires": rule.get("deductibility_ires") or "DA_VERIFICARE",
        "irap": rule.get("deductibility_irap") or "DA_VERIFICARE",
        "basis": "RULE_BASED_BUT_CONTEXT_REQUIRED",
        "approved": bool(context.get("accountant_approved")),
        "rules_version": POLICY_VERSION,
    }
    # La sanzione societaria resta separata e non viene trasformata in costo
    # deducibile. La frase "da confermare" mantiene l'audit trail.
    if rule.get("nature") == "TAX_PENALTY":
        status["basis"] = "PENALTY_SEPARATE_ACCOUNT_NO_AUTOMATIC_DEDUCTION"
    return status


def build_journal_proposal(
    document: dict[str, Any],
    *,
    document_type: str | None = None,
    evidence_state: dict[str, Any] | None = None,
    bank_state: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Produce una proposta bilanciata o un blocco esplicito, mai una scrittura."""
    evidence_state = dict(evidence_state or {})
    bank_state = dict(bank_state or {})
    context = dict(context or {})
    kind = _document_kind(document, document_type)
    rows = _rows(document)
    source = _source(document)
    findings: list[dict[str, Any]] = []
    assumptions: list[str] = []
    blockers: list[str] = []
    lines: list[dict[str, Any]] = []
    net_cents = _cents((document.get("totali") or {}).get("saldo_netto_cents"))
    if not net_cents:
        net_cents = sum(_cents(row.get("debit_cents")) - _cents(row.get("credit_cents")) for row in rows)

    if kind in {"AVVISO_PAGOPA", "AVVISO_PAGOPA/VERBALE", "AVVISO_PAGOPA"}:
        blockers.append("AVVISO_NON_PROVA_PAGAMENTO")
    if kind in {"F24_MODELLO", "F24", "F24_STAMPA_DI_PROVA", "F24_MODELLO_PRESENTATO"}:
        blockers.append("MODELLO_F24_NON_PROVA_PAGAMENTO")
    if kind == "NOTA_RETTIFICA_INPS":
        blockers.append("NOTA_RETTIFICA_E_OBBLIGAZIONE_NON_QUIETANZA")

    for row in rows:
        code = row.get("tax_code") or row.get("codice_tributo") or row.get("causale")
        rule = tax_code_rule(code, period=row.get("reference_period"))
        finding = {
            "code": str(code or "").upper(),
            "rule": rule,
            "debit_cents": _cents(row.get("debit_cents")),
            "credit_cents": _cents(row.get("credit_cents")),
            "page": row.get("page_number") or row.get("pagina"),
            "source_text": row.get("source_text") or row.get("testo_sorgente"),
        }
        findings.append(finding)
        if rule.get("status") != "VALID":
            blockers.append(f"CODICE_TRIBUTO_NON_VALIDATO:{str(code or '').upper()}")
        if rule.get("nature") == "TAX_CREDIT":
            blockers.append(f"ORIGINE_CREDITO_DA_ASSOCIARE:{str(code or '').upper()}")

    payment_evidence = _has_payment_evidence(kind, evidence_state)
    bank_verified = bool(bank_state.get("verified") or bank_state.get("banca_verificata"))
    if not payment_evidence:
        blockers.append("EVIDENZA_PAGAMENTO_MANCANTE")
    if payment_evidence and not bank_verified:
        assumptions.append("Quietanza/ricevuta valida: pagamento documentale provato; banca ancora da verificare")

    # Solo il caso piu' sicuro (1040 gia' riconosciuto come debito) puo' avere
    # una proposta di chiusura senza generare un costo nuovo. Tutti gli altri
    # casi richiedono contabilita' pregressa, dettaglio o approvazione.
    for finding in findings:
        rule = finding["rule"]
        amount = finding["debit_cents"]
        if amount <= 0 or rule.get("status") != "VALID":
            continue
        nature = rule.get("nature")
        if nature == "TAX_LIABILITY_SETTLEMENT" and payment_evidence:
            lines.append({
                "account_code": rule["balance_sheet_account"],
                "account_name": rule["description"],
                "dare_cents": amount,
                "avere_cents": 0,
                "tax_code": finding["code"],
                "phase": "PAYMENT_SETTLEMENT",
            })
        elif nature in {"TAX_OBLIGATION", "LOCAL_TAX_OBLIGATION", "TAX_ADVANCE", "TAX_INTEREST", "TAX_PENALTY"}:
            blockers.append(f"CONTESTO_CONTABILE_RICHIESTO:{finding['code']}")
            assumptions.append(f"Separare obbligazione/costo per {finding['code']} e verificare registrazioni pregresse")

    if lines:
        lines.append({
            "account_code": "BANCA_C_C_DA_RICONCILIARE",
            "account_name": "Banca c/c (evidenza bancaria separata)",
            "dare_cents": 0,
            "avere_cents": sum(line["dare_cents"] for line in lines),
            "phase": "PAYMENT_SETTLEMENT",
        })
    dare_cents = sum(line["dare_cents"] for line in lines)
    avere_cents = sum(line["avere_cents"] for line in lines)
    balanced = dare_cents == avere_cents
    if lines and not balanced:
        blockers.append("PROPOSTA_NON_QUADRATA")

    status = "READY_FOR_ACCOUNTANT_APPROVAL" if lines and balanced and not blockers else "BLOCKED_REVIEW"
    if not rows and kind not in {"NOTA_RETTIFICA_INPS", "AVVISO_PAGOPA"}:
        blockers.append("NESSUNA_RIGA_TRIBUTO_NORMALIZZATA")
    return {
        "policy_version": POLICY_VERSION,
        "document_type": kind,
        "source": source,
        "payment_evidence": {
            "documental": payment_evidence,
            "bank_verified": bank_verified,
            "status": "PAGATO_DOCUMENTALE" if payment_evidence else "NON_PROVATO",
        },
        "tax_code_findings": findings,
        "journal_proposal_status": status,
        "posting_allowed": bool(lines and balanced and not blockers),
        "definitive_posting_created": False,
        "requires_accountant_approval": True,
        "lines": lines,
        "dare_cents": dare_cents,
        "avere_cents": avere_cents,
        "net_document_cents": net_cents,
        "balanced": balanced,
        "balance_sheet_candidates": sorted({
            rule.get("balance_sheet_account")
            for item in findings
            for rule in [item["rule"]]
            if rule.get("balance_sheet_account")
        }),
        "income_statement_candidates": sorted({
            rule.get("income_statement_account")
            for item in findings
            for rule in [item["rule"]]
            if rule.get("income_statement_account")
        }),
        "bilancio_candidates": [
            {
                "tax_code": item["code"],
                "stato_patrimoniale": item["rule"].get("balance_sheet_section"),
                "conto_economico": item["rule"].get("income_statement_section"),
                "accounting_nature": item["rule"].get("nature"),
            }
            for item in findings
        ],
        "deducibilita": [
            {"tax_code": item["code"], **_deductibility(item["rule"], context)}
            for item in findings
        ],
        "blockers": sorted(set(blockers)),
        "assumptions": assumptions,
        "official_sources": sorted({
            rule.get("source_url")
            for item in findings
            for rule in [item["rule"]]
            if rule.get("source_url")
        } | {_OIC_25_URL}),
        "relation_requirements": {
            "obligation": "document_to_obligation_required",
            "payment_evidence": "quietanza_or_receipt_required",
            "bank_movement": "separate_exact_cents_and_identity_match",
            "prima_nota": "proposal_only_until_accountant_approval",
        },
    }
