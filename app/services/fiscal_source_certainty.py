"""Confronto probatorio tra fonti fiscali senza inferenze per solo importo."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable


CERTAIN = "CONCORDANTE"
DIFFERENT = "DIFFERENZA"
MISSING_ACCOUNTANT = "MANCANTE_COMMERCIALISTA"
MISSING_OFFICIAL = "MANCANTE_QUIETANZA"
AMBIGUOUS = "AMBIGUO"
NOTHING_DUE_DOCUMENTED = "NULLA_DOVUTO_ERARIO_DOCUMENTATO"
WAITING_RECEIPT = "F24_COMMERCIALISTA_IN_ATTESA_QUIETANZA"
SOURCE_REVIEW = "PROVE_F24_DA_VERIFICARE"
DECLARATION_READY = "PRONTO_PER_VERIFICA_CAMPI"
DECLARATION_VERSION_REVIEW = "IDENTITA_DICHIARANTE_E_VERSIONE_DA_VERIFICARE"
SUPPORTED_DECLARATIONS = {
    "MODELLO_770", "LIPE", "DICHIARAZIONE_IVA", "REDDITI_SC", "DICHIARAZIONE_IRAP",
}
VERSION_SENSITIVE_DECLARATIONS = SUPPORTED_DECLARATIONS - {"LIPE"}


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().upper().split())


def _cents(value: Any) -> int:
    if value in (None, ""):
        return 0
    text = str(value).strip().replace("€", "").replace(" ", "")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return int((Decimal(text) * 100).quantize(Decimal("1")))
    except (InvalidOperation, TypeError, ValueError):
        return 0


def _row_signature(row: dict[str, Any]) -> tuple[str, str, str, str, int, int]:
    """Identita' fiscale di riga: mai il solo importo."""
    return (
        _text(row.get("tax_code") or row.get("Codice tributo") or row.get("codice_tributo")),
        _text(row.get("reference_period") or row.get("Periodo tributo") or row.get("periodo_riferimento")),
        _text(row.get("section") or row.get("Sezione") or row.get("sezione")),
        _text(row.get("entity") or row.get("Ente") or row.get("entity_code") or row.get("codice_ente")),
        _cents(row.get("debit_amount") if "debit_amount" in row else row.get("Debito", row.get("importo_debito"))),
        _cents(row.get("credit_amount") if "credit_amount" in row else row.get("Credito", row.get("importo_credito"))),
    )


def _document(rows: Iterable[dict[str, Any]], *, source: str, document_id: str,
              filename: str | None = None, protocol: str | None = None) -> dict[str, Any]:
    signatures = sorted(_row_signature(row) for row in rows)
    payload = json.dumps(signatures, ensure_ascii=True, separators=(",", ":"))
    return {
        "source": source,
        "document_id": document_id,
        "filename": filename,
        "protocol": protocol,
        "row_signatures": signatures,
        "row_count": len(signatures),
        "total_debit_cents": sum(row[-2] for row in signatures),
        "total_credit_cents": sum(row[-1] for row in signatures),
        "fiscal_fingerprint": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    }


def group_drive_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        document_id = str(row.get("document_id") or row.get("ID documento") or "").strip()
        if document_id:
            grouped[document_id].append(row)
    return [
        _document(
            values, source="QUIETANZA_DRIVE", document_id=document_id,
            filename=str(values[0].get("filename") or values[0].get("Nome file") or "") or None,
            protocol=str(values[0].get("protocol") or values[0].get("Protocollo") or "") or None,
        )
        for document_id, values in grouped.items()
    ]


def normalize_accountant_documents(documents: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    from app.services.f24_fiscal_evidence import normalize_f24_evidence_rows

    normalized = []
    for index, source in enumerate(documents):
        rows = source.get("normalized_tax_rows") or source.get("righe_tributo")
        if not isinstance(rows, list):
            rows = normalize_f24_evidence_rows(source)
        document_id = str(source.get("id") or source.get("f24_dedup_key") or f"commercialista-{index}")
        general = source.get("dati_generali") or {}
        normalized.append(_document(
            rows, source="F24_COMMERCIALISTA", document_id=document_id,
            filename=str(source.get("file_name") or source.get("filename") or "") or None,
            protocol=str(source.get("protocollo") or source.get("protocollo_telematico")
                         or general.get("protocollo_telematico") or "") or None,
        ))
    return normalized


def group_model_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Converte i modelli F24 indicizzati in Drive in documenti commercialista.

    La funzione non promuove mai un modello a quietanza: conserva soltanto le
    righe fiscali necessarie al confronto bidirezionale con la prova ufficiale.
    """
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        document_id = str(row.get("document_id") or row.get("ID documento") or "").strip()
        if document_id:
            grouped[document_id].append(row)
    return [{
        "id": document_id,
        "filename": values[0].get("filename") or values[0].get("Nome file"),
        "protocollo": values[0].get("protocol") or values[0].get("Protocollo"),
        "normalized_tax_rows": values,
        "source": "MODELLO_F24_DRIVE",
    } for document_id, values in grouped.items()]


def annotate_declaration_certainty(
    declarations: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Blocca il doppio conteggio quando identita' o versione non sono provate.

    Il solo tipo dichiarazione e anno d'imposta non permettono di stabilire se
    due PDF appartengano a soggetti diversi, siano invii separati oppure una
    dichiarazione integrativa. Finche' il PDF non fornisce tale identita',
    nessuna delle versioni concorrenti entra nel registro automatico dovuto.
    """
    items = [dict(item) for item in declarations]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        document_type = str(item.get("document_type") or "")
        tax_year = str(item.get("tax_year") or "")
        if document_type in VERSION_SENSITIVE_DECLARATIONS and tax_year:
            grouped[(document_type, tax_year)].append(item)

    for item in items:
        supported = item.get("document_type") in SUPPORTED_DECLARATIONS
        identity_confirmed = (
            item.get("relation_state") == "CONFERMATA_NOME_UNIVOCO_E_INDICE_VERIFICATO"
        )
        siblings = grouped.get((
            str(item.get("document_type") or ""), str(item.get("tax_year") or ""),
        ), [])
        if supported and identity_confirmed and len(siblings) <= 1:
            item["field_check_status"] = DECLARATION_READY
            item["declaration_set_status"] = "UNICA_PER_TIPO_E_ANNO_IMPOSTA"
            item["related_document_ids"] = []
        elif supported and identity_confirmed and len(siblings) > 1:
            item["field_check_status"] = DECLARATION_VERSION_REVIEW
            item["declaration_set_status"] = "PIU_DICHIARAZIONI_STESSO_TIPO_E_ANNO_IMPOSTA"
            item["related_document_ids"] = sorted(
                str(sibling.get("document_id") or "")
                for sibling in siblings
                if sibling.get("document_id") != item.get("document_id")
            )
        else:
            item["field_check_status"] = "PARSER_SPECIFICO_NON_DISPONIBILE"
            item["declaration_set_status"] = "IDENTITA_O_PARSER_NON_DISPONIBILE"
            item["related_document_ids"] = []
    return items


def reconcile_f24_sources(drive_rows: Iterable[dict[str, Any]],
                          accountant_documents: Iterable[dict[str, Any]]) -> dict[str, Any]:
    official = group_drive_rows(drive_rows)
    accountant = normalize_accountant_documents(accountant_documents)
    official_by_fingerprint: dict[str, list[dict[str, Any]]] = defaultdict(list)
    accountant_by_fingerprint: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in official:
        official_by_fingerprint[item["fiscal_fingerprint"]].append(item)
    for item in accountant:
        accountant_by_fingerprint[item["fiscal_fingerprint"]].append(item)

    results = []
    matched_official: set[str] = set()
    for model in accountant:
        candidates = official_by_fingerprint.get(model["fiscal_fingerprint"], [])
        reverse_candidates = accountant_by_fingerprint.get(model["fiscal_fingerprint"], [])
        if len(candidates) == 1 and len(reverse_candidates) == 1:
            receipt = candidates[0]
            matched_official.add(receipt["document_id"])
            status = CERTAIN
        elif candidates:
            receipt = None
            status = AMBIGUOUS
        else:
            receipt = None
            same_totals = [item for item in official if (
                item["total_debit_cents"] == model["total_debit_cents"]
                and item["total_credit_cents"] == model["total_credit_cents"]
            )]
            status = DIFFERENT if same_totals else MISSING_OFFICIAL
        results.append({
            "id": f"certainty:{model['document_id']}",
            "status": status,
            "requires_review": status != CERTAIN,
            "accountant_document": {key: value for key, value in model.items() if key != "row_signatures"},
            "official_document": (
                {key: value for key, value in receipt.items() if key != "row_signatures"}
                if receipt else None
            ),
            "candidate_count": len(candidates),
            "erario_state": (
                NOTHING_DUE_DOCUMENTED if status == CERTAIN
                else WAITING_RECEIPT if status == MISSING_OFFICIAL
                else SOURCE_REVIEW
            ),
            "rule": "codice+periodo+sezione+ente+debito_cents+credito_cents",
        })

    for receipt in official:
        if receipt["document_id"] in matched_official:
            continue
        candidates = accountant_by_fingerprint.get(receipt["fiscal_fingerprint"], [])
        if candidates:
            continue
        results.append({
            "id": f"certainty:{receipt['document_id']}",
            "status": MISSING_ACCOUNTANT,
            "requires_review": True,
            "accountant_document": None,
            "official_document": {key: value for key, value in receipt.items() if key != "row_signatures"},
            "candidate_count": 0,
            "erario_state": NOTHING_DUE_DOCUMENTED,
            "rule": "codice+periodo+sezione+ente+debito_cents+credito_cents",
        })

    counts = Counter(item["status"] for item in results)
    return {
        "items": results,
        "counts": dict(sorted(counts.items())),
        "total": len(results),
        "certain": counts[CERTAIN],
        "requires_review": sum(item["requires_review"] for item in results),
        "all_certain": bool(results) and all(not item["requires_review"] for item in results),
        "semantics": {
            "amount_only_match_allowed": False,
            "bank_payment_proven": False,
            "bidirectional": True,
            "exact_cents": True,
        },
    }
