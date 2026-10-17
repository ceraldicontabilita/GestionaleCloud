"""Read-only chronology of one collection claim and its exact documentary links.

Missing stages remain missing. A model, a portal balance, an application and a
bank debit retain distinct meanings; this reader never reconciles or writes.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from zoneinfo import ZoneInfo

from app.db_collections import (
    COLL_ADER_POSITION_SNAPSHOTS, COLL_DOCUMENTS_INBOX, COLL_ESTRATTO_CONTO,
    COLL_F24, COLL_FISCAL_DOCUMENTS, COLL_FISCAL_EVIDENCE, COLL_FISCAL_LINKS,
    COLL_QUIETANZE_F24, COLL_TAX_ALLOCATIONS, COLL_TAX_COLLECTION_CLAIMS,
    COLL_TAX_COLLECTION_DOCUMENTS, COLL_TAX_COLLECTION_EVENTS, COLL_TAX_LEGAL_EVENTS,
    COLL_TAX_NOTIFICATION_EVENTS, COLL_TAX_PAYMENTS, COLL_TAX_RATE_INSTALLMENTS,
    COLL_TAX_RATE_PLAN_CLAIM_ALLOCATIONS, COLL_TAX_RATE_PLANS,
    COLL_TAX_SETTLEMENT_APPLICATIONS, COLL_TAX_SETTLEMENT_CLAIMS,
    COLL_TAX_SETTLEMENT_INSTALLMENTS,
)
from app.services.f24_controllo_incrociato import modello_attivo
from app.services.fiscal_claim_source_reconciliation import (
    match_f24_models_for_obligation, match_quietanza_for_obligation,
    parse_inps_notice_lines, partial_quietanza_candidates_for_obligation,
)
from app.services.fiscal_domain import PAYMENT_EVIDENCE_TYPES
from app.services.originale_documento import url_originale


_PROJECTION = {"_id": 0, "pdf_data": 0, "contenuto_b64": 0, "content_base64": 0}
_PAYMENT_EVENTS = {"PAYMENT", "PARTIAL_PAYMENT", "DIRECT_CLAIM_PAYMENT",
                   "INSTALLMENT_PAYMENT", "SETTLEMENT_PAYMENT"}
_EVENT_LABELS = {
    "RELIEF_REQUEST": "Istanza di sgravio: presentazione documentata",
    "AUTOTUTELA_REQUEST": "Istanza di autotutela: presentazione documentata",
    "RELIEF": "Provvedimento di sgravio", "PARTIAL_RELIEF": "Sgravio parziale",
    "SUSPENSION_REQUEST": "Istanza di sospensione: presentazione documentata",
    "SUSPENSION_START": "Sospensione disposta", "SUSPENSION_END": "Fine sospensione",
    "RATE_PLAN_REQUEST": "Domanda di rateizzazione", "RATE_PLAN_GRANTED": "Rateizzazione accolta",
    "SETTLEMENT_REQUEST": "Domanda di definizione agevolata",
    "SETTLEMENT_ACCEPTED": "Definizione agevolata accolta",
    "ROLE_FORMATION": "Formazione del ruolo", "ROLE_EXECUTIVITY": "Esecutività del ruolo",
    "ROLE_DELIVERY": "Consegna del ruolo alla riscossione",
    "COLLECTION_NOTIFICATION": "Notifica dell'atto di riscossione",
    "NOTICE_NOTIFICATION": "Notifica dell'avviso originario",
    "CLOSURE": "Chiusura registrata: verificare la causa documentale",
}


def _day(value: Any) -> str | None:
    """An upload timestamp is never passed here as a substitute legal date."""
    # Some INPS exports use year 0001 as a documented empty-date sentinel.
    # Keep the document undated rather than fabricating an ancient legal event.
    if isinstance(value, (date, datetime)) and value.year == 1:
        return None
    if isinstance(value, datetime):
        return (value.astimezone(ZoneInfo("Europe/Rome")) if value.tzinfo else value).date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return _day(parsed)
    except ValueError:
        pass
    for pattern in ("%d/%m/%Y", "%d-%m-%Y", "%Y%m%d"):
        try:
            return _day(datetime.strptime(raw, pattern))
        except ValueError:
            continue
    return None


def _first_date(record: dict[str, Any], *fields: str) -> str | None:
    for container in (record, record.get("parsed_metadata") or {},
                      record.get("metadata") or {}, record.get("dati_generali") or {}):
        for field in fields:
            if found := _day(container.get(field)):
                return found
    return None


def _cents(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        raw = str(value).replace("€", "").replace(" ", "")
        if "," in raw:
            raw = raw.replace(".", "").replace(",", ".")
        amount = Decimal(raw).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return int(amount * 100) if amount.is_finite() else None
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        return None


def _ids(record: dict[str, Any]) -> set[str]:
    result = {str(record[field]) for field in (
        "source_document_id", "document_id", "inbox_document_id", "fiscal_document_id",
        "original_document_id", "collection_document_id", "current_document_id",
    ) if record.get(field)}
    result.update(str(value) for value in record.get("source_document_ids") or [] if value)
    return result


def _kind(record: dict[str, Any]) -> str:
    meta = record.get("parsed_metadata") or record.get("metadata") or {}
    kind = str(record.get("document_type") or meta.get("document_type") or "").upper()
    # Il vecchio parser dei dettagli AdeR assegnava AVVISO_ADDEBITO anche
    # all'accertamento o a un generico avviso. La dicitura esplicita prevale:
    # non trasformiamo un titolo non classificato in un avviso INPS.
    label = str(record.get("document_label") or "").strip().lower()
    if kind == "AVVISO_ADDEBITO" and label in {"avviso", "avviso di accertamento"}:
        return "AVVISO" if label == "avviso" else "AVVISO_ACCERTAMENTO"
    return kind


def _reference(value: Any) -> str:
    return "".join(char for char in str(value or "").upper() if char.isalnum())


def _taxpayer_scope(company_id: str) -> dict[str, Any]:
    """Legacy records need an explicit fiscal owner; a conflicting tenant wins."""
    return {"$and": [{"$or": [
        {"company_id": company_id}, {"codice_fiscale": company_id},
        {"dati_generali.codice_fiscale": company_id}, {"dati_generali.taxpayer_id": company_id},
        {"parsed_metadata.codice_fiscale": company_id},
    ]}, {"$or": [
        {"company_id": company_id}, {"company_id": {"$exists": False}}, {"company_id": None},
    ]}]}


def _active_relation(record: dict[str, Any]) -> bool:
    """Do not traverse a revoked, deleted or explicitly unconfirmed edge."""
    if record.get("deleted_at") or record.get("revoked_at") or record.get("entity_status") == "deleted":
        return False
    if str(record.get("status") or "").upper() in {"DELETED", "REVOKED", "INVALID"}:
        return False
    return all(str(record[field]).upper() == "CONFIRMED"
               for field in ("link_status", "relation_status") if record.get(field))


def _source_provenance(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Keep recorded origins, including copies; never derive them from a name."""
    fields = ("source", "channel", "drive_file_id", "drive_document_id", "drive_parent_id",
              "source_path", "drive_path", "sha256", "email_message_id", "gmail_message_id",
              "email_from", "email_to", "email_subject", "email_date", "email_account")
    sources = [record, record.get("source_metadata"), record.get("source_context"),
               *(record.get("source_occurrences") or [])]
    result = []
    for source in sources:
        if isinstance(source, dict):
            origin = {field: source[field] for field in fields if source.get(field) not in (None, "")}
            if origin and origin not in result:
                result.append(origin)
    return result


def _provision_needs_review(record: dict[str, Any]) -> bool:
    classification = record.get("classification") or {}
    # Reimporting identical bytes does not reclassify legacy records. Known
    # old broad markers cannot become a granted outcome merely because the
    # historical automatic classification was saved as CLASSIFIED.
    legacy_markers = {"marker:sgravio", "marker:sospensione legale della riscossione"}
    legacy_automatic = bool(legacy_markers.intersection(classification.get("reasons") or []))
    return legacy_automatic or bool(classification.get("requires_review")) or (
        str(record.get("review_status") or "").upper() == "TO_VERIFY"
    )


def _path(claim: dict[str, Any], documents: list[dict[str, Any]]) -> tuple[str, str, list[tuple[str, str]]]:
    kind = _kind(claim)
    if not kind:
        by_id = {str(doc.get("id")): doc for doc in documents}
        for field in ("current_document_id", "original_document_id", "collection_document_id", "source_document_id"):
            candidate = by_id.get(str(claim.get(field) or ""))
            if candidate and _kind(candidate):
                kind = _kind(candidate)
                break
    # The latest collection title determines the route, rather than its older
    # source documents. A mere INPS creditor name does not prove an executive notice.
    if kind in {"AVVISO_ADDEBITO", "AVVISO_ADDEBITO_INPS"}:
        return "INPS_EXECUTIVE_NOTICE", "INPS: avviso di addebito esecutivo", [
            ("ORIGINAL_NOTICE", "Avviso/invito precedente, se documentato"),
            ("EXECUTIVE_NOTICE", "Avviso di addebito esecutivo"),
            ("COLLECTION_NOTIFICATION", "Notifica dell'avviso"),
        ]
    if kind in {"AVVISO_ACCERTAMENTO_ESECUTIVO", "ACCERTAMENTO_ESECUTIVO"}:
        return "EXECUTIVE_ASSESSMENT", "Accertamento esecutivo", [
            ("EXECUTIVE_ASSESSMENT", "Accertamento esecutivo"),
            ("COLLECTION_NOTIFICATION", "Notifica dell'accertamento"),
            ("ENFORCEMENT_ENTRUSTMENT", "Affidamento alla riscossione"),
        ]
    if kind in {"CARTELLA_ESATTORIALE", "CARTELLA_ADE_R", "CARTELLA"}:
        return "ADE_ROLE_CARTELLA", "Iscrizione a ruolo e cartella", [
            ("ORIGINAL_NOTICE", "Comunicazione/avviso precedente, se previsto e documentato"),
            ("ROLE_FORMATION", "Formazione del ruolo"),
            ("ROLE_EXECUTIVITY", "Esecutività del ruolo"),
            ("ROLE_DELIVERY", "Consegna del ruolo"),
            ("COLLECTION_DOCUMENT", "Cartella di pagamento"),
            ("COLLECTION_NOTIFICATION", "Notifica della cartella"),
        ]
    # The source-only case does not assert that an unknown claim is already a cartella.
    return "UNKNOWN", "Percorso da verificare sull'atto originale", [
        ("ORIGINAL_NOTICE", "Avviso/comunicazione originaria"),
        ("COLLECTION_DOCUMENT", "Atto di riscossione da classificare"),
    ]


async def build_collection_dossier(db, *, company_id: str, claim_id: str) -> dict[str, Any] | None:
    """Return exact, company-scoped documents; never change balances or states."""
    claim = await db[COLL_TAX_COLLECTION_CLAIMS].find_one(
        {"company_id": company_id, "$or": [{"id": claim_id}, {"collection_number": claim_id}]}, _PROJECTION,
    )
    if not claim:
        return None
    ident = str(claim.get("id") or claim_id)
    number = str(claim.get("collection_number") or "")
    events = await db[COLL_TAX_COLLECTION_EVENTS].find(
        {"company_id": company_id, "claim_id": ident}, _PROJECTION,
    ).to_list(5000)
    # The canonical graph contains correspondence attached to a plan rather
    # than directly to each claim. Traverse exact IDs, never similar filenames,
    # periods or amounts. A refusal is a document too, not a revoked relation.
    graph_bound_reached = False

    async def related(collection: str, clauses: list[dict[str, Any]], limit: int = 5000):
        nonlocal graph_bound_reached
        if not clauses:
            return []
        rows = await db[collection].find(
            {"company_id": company_id, "$or": clauses}, _PROJECTION,
        ).to_list(limit)
        graph_bound_reached |= len(rows) >= limit
        return [row for row in rows if _active_relation(row)]

    claim_clauses = [{"claim_id": ident}, {"tax_collection_claim_id": ident}]
    notification_events = await related(COLL_TAX_NOTIFICATION_EVENTS, claim_clauses)
    legal_events = await related(COLL_TAX_LEGAL_EVENTS, claim_clauses)
    events = [event for event in events if _active_relation(event)] + [
        {**event, "_event_store": store}
        for store, records in (("notification", notification_events), ("legal", legal_events))
        for event in records
    ]
    plan_edges = [edge for edge in await related(COLL_TAX_RATE_PLAN_CLAIM_ALLOCATIONS, claim_clauses)
                  if any(str(edge.get(field) or "").upper() == "CONFIRMED"
                         for field in ("link_status", "relation_status"))]
    explicit_plan_ids = sorted({str(edge["rate_plan_id"]) for edge in plan_edges if edge.get("rate_plan_id")})
    plan_clauses = ([{"document_references.document_number": number}] if number else [])
    if explicit_plan_ids:
        plan_clauses.append({"id": {"$in": explicit_plan_ids}})
    plans = await related(COLL_TAX_RATE_PLANS, plan_clauses, 1000)
    plan_ids = sorted({str(plan["id"]) for plan in plans if plan.get("id")})
    installments = await related(COLL_TAX_RATE_INSTALLMENTS,
                                 [{"rate_plan_id": {"$in": plan_ids}}] if plan_ids else [])
    settlement_edges = [edge for edge in await related(COLL_TAX_SETTLEMENT_CLAIMS, claim_clauses)
                        if any(str(edge.get(field) or "").upper() == "CONFIRMED"
                               for field in ("link_status", "relation_status"))]
    settlement_ids = sorted({str(edge["settlement_application_id"]) for edge in settlement_edges
                             if edge.get("settlement_application_id")})
    settlement_clauses = [*claim_clauses]
    if number:
        settlement_clauses.append({"collection_document_number": number})
    if settlement_ids:
        settlement_clauses.append({"id": {"$in": settlement_ids}})
    settlements = await related(COLL_TAX_SETTLEMENT_APPLICATIONS, settlement_clauses, 1000)
    settlement_ids = sorted({str(item["id"]) for item in settlements if item.get("id")})
    settlement_installments = await related(
        COLL_TAX_SETTLEMENT_INSTALLMENTS,
        [{"settlement_application_id": {"$in": settlement_ids}}] if settlement_ids else [],
    )
    correspondence_clauses = [*claim_clauses]
    if plan_ids:
        correspondence_clauses.append({"linked_rate_plan_id": {"$in": plan_ids}, "link_status": "CONFIRMED"})
    if settlement_ids:
        correspondence_clauses.append({"settlement_application_id": {"$in": settlement_ids}, "link_status": "CONFIRMED"})
    correspondence = await related(COLL_TAX_COLLECTION_DOCUMENTS, correspondence_clauses)
    graph_entities: dict[str, list[str]] = {"tax_collection_claim": [ident]}
    for entity_type, records in (("tax_rate_plan", plans), ("tax_rate_installment", installments),
                                 ("tax_collection_document", correspondence),
                                 ("tax_settlement_application", settlements),
                                 ("tax_settlement_installment", settlement_installments)):
        graph_entities[entity_type] = [str(item["id"]) for item in records if item.get("id")]
    fiscal_links = await db[COLL_FISCAL_LINKS].find({
        "company_id": company_id, "status": "confirmed",
        "$or": [{"entity_type": entity_type, "entity_id": {"$in": entity_ids}}
                for entity_type, entity_ids in graph_entities.items() if entity_ids],
    }, _PROJECTION).to_list(5000)
    graph_records = [*events, *plans, *installments, *plan_edges, *settlements, *settlement_edges,
                     *settlement_installments, *correspondence]
    evidence_ids = sorted({str(eid) for item in [*fiscal_links, *graph_records]
                           for eid in item.get("evidence_ids") or []})
    evidence = [] if not evidence_ids else await db[COLL_FISCAL_EVIDENCE].find(
        {"company_id": company_id, "id": {"$in": evidence_ids}}, _PROJECTION,
    ).to_list(5000)
    sources = [link for link in claim.get("source_obligation_links") or []
               if link.get("relation_status") == "CONFIRMED"]
    doc_ids = _ids(claim)
    for item in [*graph_records, *evidence, *sources, *(claim.get("original_notice_sources") or [])]:
        doc_ids.update(_ids(item))
    snapshots = [] if not number else await db[COLL_ADER_POSITION_SNAPSHOTS].find(
        {"company_id": company_id, "document_number": number}, _PROJECTION,
    ).to_list(5000)
    for item in [*snapshots, *plans, *settlements]:
        doc_ids.update(_ids(item))
        for module in item.get("payment_modules") or []:
            doc_ids.update(_ids(module))
    allocations = await db[COLL_TAX_ALLOCATIONS].find({
        "company_id": company_id, "entity_type": "tax_collection_claim", "entity_id": ident,
    }, _PROJECTION).to_list(5000)
    payment_ids = {str(pid) for pid in claim.get("linked_payment_ids") or [] if pid}
    payment_ids.update(str(item["payment_id"]) for item in [*graph_records, *allocations] if item.get("payment_id"))
    payments = [] if not payment_ids else await db[COLL_TAX_PAYMENTS].find(
        {"company_id": company_id, "id": {"$in": sorted(payment_ids)}}, _PROJECTION,
    ).to_list(5000)
    for payment in payments:
        doc_ids.update(_ids(payment))
    documents: list[dict[str, Any]] = []
    document_bound_reached = False
    for collection, original_type in ((COLL_FISCAL_DOCUMENTS, "documento_fiscale"),
                                      (COLL_DOCUMENTS_INBOX, "documento")):
        if doc_ids:
            selected_docs = await db[collection].find(
                {**_taxpayer_scope(company_id), "id": {"$in": sorted(doc_ids)}}, _PROJECTION,
            ).to_list(10000)
            document_bound_reached |= len(selected_docs) >= 10000
            for doc in selected_docs:
                if doc.get("entity_status") != "deleted" and doc.get("status") not in {"eliminato", "deleted"} and not doc.get("deleted_at"):
                    documents.append({**doc, "_original_type": original_type})
    docs_by_id = {str(doc["id"]): doc for doc in documents if doc.get("id")}

    model_ids: set[str] = set()
    receipt_ids: set[str] = set()
    candidate_receipt_ids: set[str] = set()
    source_rows: list[dict[str, Any]] = []
    source_identity_unverified = False
    for source in sources:
        # A persisted reconciliation is a pointer, not a substitute original.
        # Re-check the tenant of each actual record before disclosing it.
        for row in source.get("tax_lines") or []:
            for match in row.get("f24_model_matches") or []:
                if match.get("f24_id"):
                    model_ids.add(str(match["f24_id"]))
            for match in row.get("payment_matches") or []:
                if match.get("quietanza_id"):
                    receipt_ids.add(str(match["quietanza_id"]))
                support = match.get("supporting_f24") or {}
                if support.get("f24_id"):
                    model_ids.add(str(support["f24_id"]))
            for candidate in row.get("partial_payment_candidates") or []:
                if candidate.get("quietanza_id"):
                    candidate_receipt_ids.add(str(candidate["quietanza_id"]))
        own_original = docs_by_id.get(str(source.get("inbox_document_id") or ""))
        if own_original and source.get("source_type") == "AVVISO_ADDEBITO_INPS":
            metadata = own_original.get("parsed_metadata") or {}
            expected = _reference(source.get("document_number") or number)
            if expected and _reference(metadata.get("numero_atto")) == expected:
                source_rows.extend({**row, "matricola_inps": metadata.get("matricola_inps")}
                                   for row in parse_inps_notice_lines(metadata.get("testo_estratto") or ""))
            else:
                source_identity_unverified = True
    taxpayer_scope = _taxpayer_scope(company_id)
    models = [] if not (source_rows or model_ids) else await db[COLL_F24].find(
        {**taxpayer_scope, **({} if source_rows else {"id": {"$in": sorted(model_ids)}})}, _PROJECTION,
    ).to_list(10000)
    model_bound_reached = len(models) >= 10000
    models = [doc for doc in models if doc.get("status") != "eliminato" and modello_attivo(doc)]
    for row in source_rows:
        model_ids.update(str(match["f24_id"]) for match in match_f24_models_for_obligation(row, models))
    for model in models:
        if str(model.get("id")) in model_ids and model.get("quietanza_id"):
            receipt_ids.add(str(model["quietanza_id"]))
    receipts = [] if not (source_rows or receipt_ids or candidate_receipt_ids) else await db[COLL_QUIETANZE_F24].find(
        {**taxpayer_scope, **({} if source_rows else {"id": {"$in": sorted(receipt_ids | candidate_receipt_ids)}})}, _PROJECTION,
    ).to_list(10000)
    receipt_bound_reached = len(receipts) >= 10000
    receipts = [doc for doc in receipts if doc.get("status") != "eliminato" and modello_attivo(doc)]
    exact_receipt_ids: set[str] = set()
    ambiguous_receipt_ids: set[str] = set()
    live_partial_ids: set[str] = set()
    for row in source_rows:
        model_ids.update(str(match["f24_id"]) for match in match_f24_models_for_obligation(row, models))
        row_matches = match_quietanza_for_obligation(row, receipts, models)
        for match in row_matches:
            target_ids = exact_receipt_ids if len(row_matches) == 1 else ambiguous_receipt_ids
            target_ids.add(str(match["quietanza_id"]))
            if support_id := (match.get("supporting_f24") or {}).get("f24_id"):
                model_ids.add(str(support_id))
        live_partial_ids.update(str(match["quietanza_id"])
                                for match in partial_quietanza_candidates_for_obligation(row, receipts))
    models = [model for model in models if str(model.get("id")) in model_ids]
    receipts = [receipt for receipt in receipts if str(receipt.get("id")) in
                receipt_ids | candidate_receipt_ids | exact_receipt_ids | live_partial_ids | ambiguous_receipt_ids]

    entries: dict[str, dict[str, Any]] = {}
    findings: list[dict[str, str]] = []

    def finding(code: str, message: str, severity: str = "warning") -> None:
        if not any(item["code"] == code for item in findings):
            findings.append({"code": code, "severity": severity, "message": message})

    def add(key: str, event_type: str, label: str, when: Any = None, *,
            date_kind: str = "DOCUMENT_DATE", evidence_level: str = "DOCUMENTARY",
            doc: dict[str, Any] | None = None, amount: int | None = None,
            notes: list[str] | None = None) -> None:
        entry: dict[str, Any] = {"id": key, "event_type": event_type, "label": label,
                                 "date": _day(when), "date_kind": date_kind,
                                 "evidence_level": evidence_level}
        if doc and doc.get("id"):
            entry.update({"document_id": str(doc["id"]),
                          "document_type": _kind(doc),
                          "filename": doc.get("filename") or doc.get("file_name") or doc.get("source_filename"),
                          "url": url_originale(doc.get("_original_type") or "documento_fiscale", doc["id"])})
            entry["source_provenance"] = _source_provenance(doc)
            # Registration proves that a reference exists; opening the original
            # is a separate operation and may still fail or return a portal copy.
            entry["original_verified"] = False
            doc_evidence = [item for item in evidence if str(item.get("document_id")) == str(doc["id"])]
            if doc_evidence:
                entry["evidence"] = [{key: item[key] for key in (
                    "id", "version_id", "page_number", "field", "field_name", "reason",
                ) if key in item} for item in doc_evidence]
        if amount is not None:
            entry["amount_cents"] = amount
        if notes:
            entry["notes"] = notes
        entries[key] = entry

    finding("DRIVE_COVERAGE_NOT_VERIFIED", "Il fascicolo legge i collegamenti registrati, inclusi piani e corrispondenza. La presenza di tutti i file Drive e l'accessibilità degli originali richiedono un inventario separato.", "info")
    if doc_ids - set(docs_by_id):
        finding("LINKED_DOCUMENT_UNAVAILABLE", "Alcuni riferimenti documentali del fascicolo non hanno un originale registrato e disponibile per questa società: verificare i documenti mancanti.")
    if (graph_bound_reached or document_bound_reached or model_bound_reached or receipt_bound_reached
            or len(events) >= 5000 or len(fiscal_links) >= 5000 or len(evidence) >= 5000
            or len(snapshots) >= 5000 or len(plans) >= 1000 or len(allocations) >= 5000
            or len(payments) >= 5000):
        finding("DOSSIER_READ_LIMIT_REACHED", "Una lettura ha raggiunto il limite del fascicolo: la cronologia può essere incompleta e richiede una verifica aggiuntiva.")
    if source_identity_unverified:
        finding("SOURCE_DOCUMENT_IDENTITY_UNVERIFIED", "Il riferimento all'avviso non coincide con il numero dell'originale disponibile: l'attribuzione dei versamenti non è confermata.")
    if ambiguous_receipt_ids:
        finding("SOURCE_RECEIPTS_AMBIGUOUS", "Più quietanze corrispondono alla stessa riga originaria: verificare l'attribuzione prima di classificare il versamento.")

    for model in models:
        doc = {**model, "_original_type": "f24"}
        add("f24:" + str(model["id"]), "F24_MODEL", "Modello F24 predisposto: non prova il pagamento",
            _first_date(model, "data_predisposizione", "data_compilazione"),
            date_kind="PREPARATION_DATE", evidence_level="MODEL_ONLY", doc=doc,
            notes=["L'invio del commercialista e il versamento richiedono evidenze distinte."])
        due = _first_date(model, "data_scadenza", "scadenza")
        if due:
            add("f24due:" + str(model["id"]), "F24_DUE_DATE", "Scadenza riportata sul modello F24",
                due, date_kind="EXPLICIT_DUE_DATE", evidence_level="MODEL_ONLY", doc=doc)

    exact_payment_days: set[str] = set()
    documentary_receipt_count = 0
    bank_ids: set[str] = set()
    for receipt in receipts:
        doc = {**receipt, "_original_type": "quietanza"}
        paid_day = _first_date(receipt, "data_pagamento", "data_versamento")
        exact = str(receipt["id"]) in exact_receipt_ids
        provisional = str(receipt["id"]) in live_partial_ids and not exact
        unverified = not exact and not provisional
        if exact:
            documentary_receipt_count += 1
        if exact and paid_day:
            exact_payment_days.add(paid_day)
        add("quietanza:" + str(receipt["id"]),
            "PARTIAL_RECEIPT_CANDIDATE" if provisional else "LINKED_RECEIPT_UNVERIFIED" if unverified else "QUIETANZA_F24",
            "Quietanza parziale da attribuire" if provisional else "Quietanza collegata: attribuzione da verificare"
            if unverified else "Quietanza F24: versamento documentale",
            paid_day, date_kind="PAYMENT_DATE", doc=doc,
            notes=["L'attribuzione alla singola obbligazione è da verificare: non certifica il pagamento della pretesa."
                   if provisional or unverified else "La quietanza ufficiale positiva prova il versamento delle righe attribuite anche senza movimento bancario disponibile. L’eventuale saldo residuo della pretesa resta distinto."])
        if unverified:
            finding("RECEIPT_ATTRIBUTION_UNVERIFIED", "Un riferimento a quietanza è presente, ma i documenti attuali non confermano l'attribuzione esatta alla pretesa.")
        if provisional:
            finding("PARTIAL_SOURCE_RECEIPT_CANDIDATE", "È presente una quietanza di importo parziale con identità e periodo compatibili: verificare l'attribuzione prima di ridurre il debito.")
        bank = receipt.get("riscontro_banca") or {}
        bank_id = bank.get("movimento_id") or receipt.get("movimento_bancario_id") or receipt.get("bank_movement_id")
        if bank_id:
            bank_ids.add(str(bank_id))
    if models and not receipts:
        finding("F24_MODEL_WITHOUT_RECEIPT", "Sono collegati modelli F24, ma non una quietanza: il pagamento non è dimostrato.", "info")

    role_dates: set[str] = set()
    dated_stages = (
        ("ROLE_FORMATION", "Formazione del ruolo", ("role_formation_date", "data_formazione_ruolo", "data_iscrizione_ruolo")),
        ("ROLE_EXECUTIVITY", "Esecutività del ruolo", ("role_executivity_date", "data_esecutivita_ruolo", "data_esecutivita")),
        ("ROLE_DELIVERY", "Consegna del ruolo alla riscossione", ("role_delivery_date", "data_consegna_ruolo")),
    )
    for record in [claim, *documents]:
        record_id = str(record.get("id") or ident)
        for stage, label, fields in dated_stages:
            when = _first_date(record, *fields)
            if when:
                add(stage + ":" + record_id, stage, label, when, date_kind=stage + "_DATE",
                    doc=record if record in documents else None)
                if stage == "ROLE_FORMATION":
                    role_dates.add(when)

    collection_kinds = {"CARTELLA_ESATTORIALE", "CARTELLA_ADE_R", "CARTELLA",
                        "AVVISO_ADDEBITO", "AVVISO_ADDEBITO_INPS",
                        "AVVISO_ACCERTAMENTO_ESECUTIVO", "ACCERTAMENTO_ESECUTIVO"}
    for doc in documents:
        kind = _kind(doc)
        stage = "COLLECTION_DOCUMENT" if kind in collection_kinds else "LINKED_DOCUMENT"
        label = "Documento collegato"
        if kind in {"AVVISO_ADDEBITO", "AVVISO_ADDEBITO_INPS"}:
            stage, label = "EXECUTIVE_NOTICE", "Avviso di addebito INPS esecutivo"
        elif kind in {"AVVISO_ACCERTAMENTO_ESECUTIVO", "ACCERTAMENTO_ESECUTIVO"}:
            stage, label = "EXECUTIVE_ASSESSMENT", "Accertamento esecutivo"
        elif kind in {"AVVISO_BONARIO", "COMUNICAZIONE_IRREGOLARITA", "AVVISO_INPS", "INVITO_REGOLARIZZAZIONE"}:
            stage, label = "ORIGINAL_NOTICE", "Avviso/comunicazione originaria"
        elif kind in {"CARTELLA_ESATTORIALE", "CARTELLA_ADE_R", "CARTELLA"}:
            label = "Cartella di pagamento"
        elif kind in {"SGRAVIO", "PROVVEDIMENTO_SGRAVIO"}:
            stage, label = "RELIEF", "Provvedimento di sgravio"
        elif kind in {"ISTANZA_SGRAVIO", "AUTOTUTELA"}:
            stage, label = "RELIEF_REQUEST", "Istanza di sgravio/autotutela: non è un provvedimento"
        elif kind == "SOSPENSIONE":
            stage, label = "SUSPENSION", "Provvedimento di sospensione"
        elif kind == "ISTANZA_SOSPENSIONE":
            stage, label = "SUSPENSION_REQUEST", "Istanza di sospensione: non è un provvedimento"
        elif kind == "ISTANZA_RATEIZZAZIONE":
            stage, label = "RATE_PLAN_REQUEST", "Domanda di rateizzazione: non è un accoglimento"
        elif kind in {"RIGETTO_SGRAVIO", "RIGETTO_SOSPENSIONE", "RIGETTO_RATEIZZAZIONE"}:
            stage, label = "REQUEST_REJECTED", "Rigetto della richiesta: verificare oggetto e motivazione"
        elif kind == "PREAVVISO_RIGETTO":
            stage, label = "REJECTION_NOTICE", "Preavviso di rigetto: distinto dall'esito definitivo"
        elif kind == "RELATA_NOTIFICA":
            stage, label = "NOTIFICATION_RECORD", "Relata di notifica: verificare destinatario, atto e data"
        elif kind == "CORRISPONDENZA_ADE_R":
            stage, label = "CORRESPONDENCE", "Corrispondenza AdeR: richiesta e risposta da distinguere"
        elif kind == "NOTA_RETTIFICA_INPS":
            stage, label = "CONTRIBUTION_ADJUSTMENT", "Nota di rettifica INPS"
        elif kind == "LETTERA_COMPLIANCE":
            stage, label = "COMPLIANCE_LETTER", "Lettera di compliance: non è una cartella"
        elif kind == "DURC":
            stage, label = "CONTRIBUTION_REGULARITY", "Regolarità contributiva: esito e periodo da verificare"
        elif kind == "COMUNICAZIONE_CIVIS":
            stage, label = "ASSISTANCE_COMMUNICATION", "Comunicazione CIVIS: richiesta ed esito da distinguere"
        elif kind == "SOLLECITO_PAGAMENTO":
            stage, label = "PAYMENT_REMINDER", "Sollecito/intimazione: distinto dalla cartella richiamata"
        elif kind == "RICEVUTA_PEC":
            stage, label = "PEC_TRANSPORT_RECEIPT", "Ricevuta PEC: trasporto del messaggio, non pagamento"
        elif kind == "RICEVUTA_TRASMISSIONE":
            stage, label = "TRANSMISSION_RECEIPT", "Ricevuta di trasmissione: distinta dalla quietanza"
        elif kind == "ESITO_NEGATIVO_F24":
            stage, label = "F24_NEGATIVE_OUTCOME", "Esito negativo F24: non prova un versamento"
        elif kind == "PROSPETTO_ADE_R":
            stage, label = "PORTAL_STATEMENT", "Prospetto informativo AdeR: distinto dagli atti e dalle quietanze"
        elif kind in {"MODULO_PAGAMENTO_ADER", "MODULO_PAGAMENTO"}:
            stage, label = "PAYMENT_MODULE", "Modulo di pagamento predisposto: non prova il versamento"
        if stage in {"RELIEF", "SUSPENSION"} and _provision_needs_review(doc):
            stage, label = "POTENTIAL_PROVISION", "Possibile provvedimento: contenuto ed esito da verificare"
            finding("PROVISION_REVIEW_REQUIRED", "Un documento è classificato come possibile provvedimento, ma la classificazione richiede ancora verifica: nessuno sgravio o sospensione confermato.")
        add("document:" + str(doc["id"]), stage, label,
            _first_date(doc, "document_date", "data_documento", "data_atto", "issue_date"), doc=doc)
        notified = _first_date(doc, "notification_date", "data_notifica")
        if notified:
            add("notification:" + str(doc["id"]),
                "COLLECTION_NOTIFICATION" if kind in collection_kinds else "NOTICE_NOTIFICATION",
                "Notifica dell'atto" if kind in collection_kinds else "Notifica del documento originario",
                notified, date_kind="NOTIFICATION_DATE", doc=doc)
    claim_notification = _first_date(claim, "notification_date", "data_notifica")
    if claim_notification:
        add("claim-notification:" + ident, "COLLECTION_NOTIFICATION", "Notifica dell'atto di riscossione",
            claim_notification, date_kind="NOTIFICATION_DATE", doc=docs_by_id.get(str(claim.get("source_document_id"))))

    valid_allocations: dict[str, int] = {}
    for allocation in allocations:
        if str(allocation.get("status") or "").upper() in {"REVOKED", "REJECTED", "DELETED", "INVALID", "PENDING"} or (
            allocation.get("revoked_at") or allocation.get("deleted_at")
            or allocation.get("entity_status") == "deleted"
        ):
            continue
        if not set(allocation.get("evidence_types") or []).intersection(PAYMENT_EVIDENCE_TYPES):
            continue
        amount = _cents(allocation.get("amount"))
        if amount is not None and amount >= 0:
            pid = str(allocation.get("payment_id") or "")
            valid_allocations[pid] = valid_allocations.get(pid, 0) + amount
    documentary_direct_cents = 0
    for payment in payments:
        if not payment.get("documentary_evidence") or payment.get("source_kind") == "F24_DOCUMENT_EVIDENCE":
            continue
        documentary_receipt_count += 1
        pid = str(payment["id"])
        allocation = valid_allocations.get(pid)
        operation = _cents(payment.get("operation_amount") if payment.get("operation_amount") is not None else payment.get("amount"))
        if allocation is not None and (operation is None or operation < allocation):
            allocation = None
            finding("PAYMENT_ALLOCATION_INVALID", "Le quote non sono verificabili rispetto al totale dell'operazione: nessun importo imputato dal fascicolo.")
        if allocation is not None:
            documentary_direct_cents += allocation
        notes = ["Il totale dell'operazione può coprire più cartelle: vale soltanto la quota documentata di questa pretesa."]
        if allocation is None:
            notes.append("Quota di questa pretesa non disponibile: nessun importo imputato.")
            finding("PAYMENT_ALLOCATION_MISSING", "Una ricevuta è collegata, ma manca la quota probatoria della singola pretesa.")
        doc = docs_by_id.get(str(payment.get("document_id")))
        if doc is None:
            notes.append("Il registro documenta il versamento, ma l'originale della ricevuta non è disponibile nel fascicolo.")
            finding("RECEIPT_ORIGINAL_UNAVAILABLE", "Una prova di pagamento è registrata, ma il documento originale della stessa società non è disponibile nel fascicolo.")
        add("payment:" + pid, "DIRECT_COLLECTION_PAYMENT", "Ricevuta di pagamento della riscossione",
            payment.get("payment_date"), date_kind="PAYMENT_DATE", doc=doc, amount=allocation, notes=notes)
        bank_id = payment.get("bank_movement_id") or payment.get("movimento_id")
        if bank_id:
            bank_ids.add(str(bank_id))
    banks = [] if not bank_ids else await db[COLL_ESTRATTO_CONTO].find(
        {"company_id": company_id, "id": {"$in": sorted(bank_ids)}}, _PROJECTION,
    ).to_list(5000)
    if len(banks) >= 5000:
        finding("DOSSIER_READ_LIMIT_REACHED", "Una lettura ha raggiunto il limite del fascicolo: la cronologia può essere incompleta e richiede una verifica aggiuntiva.")
    for bank in banks:
        add("bank:" + str(bank["id"]), "BANK_MOVEMENT", "Movimento bancario collegato",
            _first_date(bank, "data_contabile", "booking_date", "data"),
            date_kind="BANK_BOOKING_DATE", evidence_level="BANK",
            notes=["Movimento bancario distinto dalla quietanza e dal modello F24."])
    if bank_ids - {str(bank["id"]) for bank in banks}:
        finding("BANK_ORIGINAL_UNAVAILABLE", "È registrato un riferimento bancario, ma il movimento della stessa società non è disponibile in questo fascicolo.")

    payments_by_id = {str(item["id"]): item for item in payments}
    for event in events:
        kind = str(event.get("event_type") or
                   ("COLLECTION_NOTIFICATION" if event.get("_event_store") == "notification" else "EVENT"))
        if kind in _PAYMENT_EVENTS:
            # Imported effective_at can equal the import time when payment_date
            # is missing. A payment event therefore never dates a receipt.
            if str(event.get("payment_id") or event.get("source_reference") or "") in payments_by_id:
                continue
            add("event:" + str(event.get("_event_store") or "collection") + ":" + str(event.get("id")), "PAYMENT_RECORDED_UNVERIFIED",
                "Pagamento registrato: prova e data da verificare", None,
                date_kind="PAYMENT_DATE", evidence_level="EVENT",
                notes=["La data tecnica dell'evento non prova la data del pagamento."])
            continue
        event_has_original = bool(
            _ids(event).intersection(docs_by_id)
            or any(item.get("id") in (event.get("evidence_ids") or [])
                   and str(item.get("document_id")) in docs_by_id for item in evidence)
        )
        if not event_has_original:
            add("event:" + str(event.get("_event_store") or "collection") + ":" + str(event.get("id")), "UNVERIFIED_RECORDED_EVENT",
                "Evento registrato: prova da verificare", None, date_kind="EVENT_EFFECTIVE_DATE", evidence_level="EVENT",
                notes=["Il riferimento all'originale manca o non è disponibile per questa società: la fase non è documentata."])
            finding("EVENT_EVIDENCE_UNAVAILABLE", "Un evento registrato non dispone della relativa prova documentale nel fascicolo.")
            continue
        event_document = next((docs_by_id[doc_id] for doc_id in sorted(_ids(event)) if doc_id in docs_by_id), None)
        if event_document is None:
            event_document = next((docs_by_id[str(item["document_id"])] for item in evidence
                                   if item.get("id") in (event.get("evidence_ids") or [])
                                   and str(item.get("document_id")) in docs_by_id), None)
        required_kinds = {
            "RELIEF": {"SGRAVIO", "PROVVEDIMENTO_SGRAVIO", "SGRAVIO_PARZIALE"},
            "PARTIAL_RELIEF": {"SGRAVIO", "PROVVEDIMENTO_SGRAVIO", "SGRAVIO_PARZIALE"},
            "SUSPENSION_START": {"SOSPENSIONE", "PROVVEDIMENTO_SOSPENSIONE"},
            "RATE_PLAN_GRANTED": {"PIANO_RATEIZZAZIONE", "ACCOGLIMENTO_RATEIZZAZIONE"},
        }
        if kind in required_kinds:
            proving_ids = set(_ids(event))
            proving_ids.update(str(item["document_id"]) for item in evidence
                               if item.get("id") in (event.get("evidence_ids") or []) and item.get("document_id"))
            event_document = next((docs_by_id[doc_id] for doc_id in sorted(proving_ids)
                                   if doc_id in docs_by_id and _kind(docs_by_id[doc_id]) in required_kinds[kind]
                                   and not _provision_needs_review(docs_by_id[doc_id])),
                                  event_document)
        if kind in required_kinds and (_kind(event_document or {}) not in required_kinds[kind]
                                      or _provision_needs_review(event_document or {})):
            add("event:" + str(event.get("_event_store") or "collection") + ":" + str(event.get("id")),
                "UNVERIFIED_RECORDED_EVENT", "Esito registrato: il provvedimento è da verificare", None,
                date_kind="EVENT_EFFECTIVE_DATE", evidence_level="EVENT", doc=event_document,
                notes=["Il documento disponibile non dimostra questo provvedimento; una richiesta, un rigetto e un preavviso sono distinti."])
            finding("EVENT_OUTCOME_NOT_PROVEN", "Un esito registrato non è sostenuto da un documento classificato come relativo provvedimento: nessun accoglimento o sgravio dedotto.")
            continue
        event_day = (_first_date(event, "notification_date", "data_notifica", "effective_at")
                     if event.get("_event_store") == "notification" else event.get("effective_at"))
        add("event:" + str(event.get("_event_store") or "collection") + ":" + str(event.get("id")), kind,
            _EVENT_LABELS.get(kind, "Evento del fascicolo da verificare"),
            event_day, date_kind="NOTIFICATION_DATE" if event.get("_event_store") == "notification"
            else "EVENT_EFFECTIVE_DATE", evidence_level="EVENT", doc=event_document,
            amount=_cents(event.get("amount")),
            notes=["Una richiesta e un provvedimento restano eventi distinti."] if "REQUEST" in kind else None)
        if kind == "ROLE_FORMATION" and event_has_original and (when := _day(event.get("effective_at"))):
            role_dates.add(when)
    for snapshot in snapshots:
        add("portal:" + str(snapshot["id"]), "PORTAL_SNAPSHOT", "Situazione rilevata dal portale AdeR",
            snapshot.get("snapshot_date"), date_kind="PORTAL_CAPTURE_DATE", evidence_level="PORTAL",
            doc=docs_by_id.get(str(snapshot.get("source_document_id"))),
            amount=_cents(snapshot.get("net_payable_amount")),
            notes=["Il residuo del portale non è una quietanza né una prova bancaria."])
        if notified := _day(snapshot.get("notification_date")):
            add("portal-notification:" + str(snapshot["id"]), "COLLECTION_NOTIFICATION",
                "Data di notifica riportata nel prospetto AdeR", notified,
                date_kind="NOTIFICATION_DATE", evidence_level="PORTAL",
                doc=docs_by_id.get(str(snapshot.get("source_document_id"))),
                notes=["Data riportata dal portale: la relata di notifica resta una prova distinta."])
    for plan in plans:
        if plan.get("terms_conflict"):
            finding("RATE_PLAN_TERMS_CONFLICT", "Più documenti dello stesso piano riportano condizioni diverse: tutte le fonti restano nel fascicolo, ma nessuna è scelta come versione definitiva dal nome file o dalla data di caricamento.")
        if plan.get("filename_reference_discrepancy"):
            finding("RATE_PLAN_FILENAME_REFERENCE_DIFFERS", "Il riferimento nel nome del file differisce dall'identificativo stampato nel piano: vale il contenuto; nessun prefisso è ricostruito dal nome.")
        if plan.get("taxpayer_identity_status") != "CONFIRMED" or plan.get("requires_review"):
            finding("RATE_PLAN_REVIEW_REQUIRED", "Un piano collegato richiede verifica dell'identità del contribuente o delle condizioni documentali: il collegamento non conferma una concessione né il pagamento delle rate.")
        add("plan:" + str(plan["id"]), "RATE_PLAN", "Piano di rateizzazione collegato",
            plan.get("application_date"), date_kind="PLAN_APPLICATION_DATE",
            doc=docs_by_id.get(str(plan.get("source_document_id"))),
            notes=["Il piano e i moduli di pagamento non dimostrano il pagamento delle rate."])
    for entity_type, records, parent_field in (
        ("RATE_INSTALLMENT_DUE", installments, "rate_plan_id"),
        ("SETTLEMENT_INSTALLMENT_DUE", settlement_installments, "settlement_application_id"),
    ):
        for installment in records:
            parent = next((item for item in [*plans, *settlements]
                           if str(item.get("id")) == str(installment.get(parent_field))), {})
            doc = docs_by_id.get(str(installment.get("source_document_id") or parent.get("source_document_id")))
            add("installment:" + entity_type + ":" + str(installment.get("id")), entity_type,
                "Scadenza di rata da verificare: documenti del piano discordanti" if parent.get("terms_conflict")
                else "Scadenza di rata registrata: non prova il pagamento", installment.get("due_date"),
                date_kind="DUE_DATE", doc=doc,
                notes=["La rata può coprire più pretese; il suo totale non è imputato a questa cartella."])
    for settlement in settlements:
        add("settlement:" + str(settlement.get("id")), "SETTLEMENT_DOCUMENT",
            "Definizione agevolata collegata: verificare domanda ed esito",
            _first_date(settlement, "document_date", "communication_date", "application_date"),
            doc=docs_by_id.get(str(settlement.get("source_document_id"))),
            notes=["La domanda, la comunicazione delle somme e le ricevute delle rate restano documenti distinti."])
    seen_modules: set[str] = set()
    for parent in [*plans, *settlements]:
        for module in parent.get("payment_modules") or []:
            doc_id = str(module.get("source_document_id") or "")
            module_key = doc_id or str(module.get("id") or "")
            if not module_key or module_key in seen_modules:
                continue
            seen_modules.add(module_key)
            add("module:" + module_key, "PAYMENT_MODULE", "Modulo di pagamento: non prova il versamento",
                _first_date(module, "document_date", "issue_date"), evidence_level="MODEL_ONLY",
                doc=docs_by_id.get(doc_id))

    path_claim = claim
    if not _kind(claim) and snapshots:
        latest = max(snapshots, key=lambda item: _day(item.get("snapshot_date")) or "")
        path_claim = {**claim, "document_type": latest.get("document_type"),
                      "document_label": latest.get("document_label")}
    code, label, stage_specs = _path(path_claim, documents)
    if code == "INPS_EXECUTIVE_NOTICE":
        finding("INPS_DIRECT_EXECUTIVE_NOTICE", "Per l'avviso di addebito INPS esecutivo il percorso non richiede un ruolo e una cartella successivi.", "info")
    if code == "UNKNOWN":
        finding("COLLECTION_PATH_UNKNOWN", "Il tipo dell'atto non consente di stabilire il percorso: verificare l'originale.")
    observed_stages = {entry["event_type"] for entry in entries.values()}
    steps = [{"code": stage, "label": stage_label,
              "status": "DOCUMENTED" if stage in observed_stages else "NOT_DOCUMENTED"}
             for stage, stage_label in stage_specs]
    if code in {"INPS_EXECUTIVE_NOTICE", "EXECUTIVE_ASSESSMENT"}:
        steps.extend({"code": stage, "label": stage_label, "status": "NOT_APPLICABLE"}
                     for stage, stage_label in (("ROLE_FORMATION", "Formazione del ruolo"),
                                                ("COLLECTION_DOCUMENT", "Cartella successiva")))
    if exact_payment_days:
        if code == "ADE_ROLE_CARTELLA":
            if not role_dates:
                finding("ROLE_DATE_REQUIRED", "Una quietanza esatta documenta il versamento originario, ma manca la data di formazione del ruolo: non è determinabile se il versamento sia precedente o successivo.")
            elif len(role_dates) > 1:
                finding("ROLE_DATE_CONFLICT", "Sono presenti date diverse di formazione del ruolo: verificare l'originale prima di classificare il versamento.")
            else:
                role_day = next(iter(role_dates))
                if any(day < role_day for day in exact_payment_days):
                    finding("SOURCE_PAID_BEFORE_ROLE", "Una quietanza esatta reca una data precedente alla formazione del ruolo: verificare l'imputazione e con l'ente creditore gli eventuali presupposti per lo sgravio.")
                if any(day >= role_day for day in exact_payment_days):
                    finding("SOURCE_PAID_ON_OR_AFTER_ROLE", "Una quietanza esatta reca una data pari o successiva alla formazione del ruolo: verificare il versamento con l'ente creditore e l'eventuale sgravio. Non è una sospensione automatica.")
        else:
            finding("SOURCE_PAYMENT_REVIEW", "Una quietanza esatta documenta un versamento originario: verificare con l'ente creditore l'imputazione e l'eventuale rettifica della pretesa.")
    original_cents = claim.get("original_total_cents", claim.get("original_amount_cents"))
    if isinstance(original_cents, int) and 0 < documentary_direct_cents < original_cents:
        finding("PARTIAL_COLLECTION_PAYMENT", "Le quote documentate sono inferiori all'importo originario della pretesa: il pagamento parziale non chiude il fascicolo.")
    if claim.get("documentary_payment_status") == "PARTIAL_DOCUMENTED":
        finding("PARTIAL_COLLECTION_PAYMENT", "Il registro riporta un pagamento parziale: verificare quote, imputazioni e residuo con i documenti originali.")
    if models and any((isinstance(model.get("importo_residuo_cents"), int) and model["importo_residuo_cents"] > 0) or
                      (model.get("collegamento_quietanza_titolare") or {}).get("righe_non_trovate") for model in models):
        finding("PARTIAL_SOURCE_PAYMENT", "Una delega originaria ha copertura parziale: il collegamento non salda automaticamente tutte le righe.")
    if exact_payment_days and documentary_direct_cents > 0:
        finding("POSSIBLE_DUPLICATE_PAYMENT", "Sono documentati sia un versamento originario sia una quota alla riscossione: verificare sovrapposizione e possibile rimborso, senza presumere che riguardino le stesse somme.")
    dated = sorted((item for item in entries.values() if item["date"]), key=lambda item: (item["date"], item["id"]))
    undated = sorted((item for item in entries.values() if not item["date"]), key=lambda item: item["id"])
    return {"claim_id": ident, "collection_number": number,
            "path": {"code": code, "label": label, "steps": steps},
            "timeline": dated, "undated": undated, "findings": findings,
            "coverage": {"scope": "REGISTERED_CLAIM_GRAPH", "drive_inventory_verified": False,
                         "referenced_documents": len(doc_ids), "loaded_documents": len(docs_by_id),
                         "unavailable_document_ids": sorted(doc_ids - set(docs_by_id)),
                         "rate_plans": len(plans), "correspondence_records": len(correspondence),
                         "settlement_applications": len(settlements)},
            "evidence_summary": {"f24_models": len(models), "documentary_receipts": documentary_receipt_count,
                                 "bank_movements": len(banks), "claim_allocated_cents": documentary_direct_cents},
            "safety": {"payment_inferred": False, "requests_submitted": False}}
