"""Import fail-closed degli snapshot AdeR da un archivio registrato in Documenti.

Il parser legge esclusivamente valori presenti nei PDF. Il contenitore del
portale (``Saldati``/``Da saldare``) resta distinto dallo stato aziendale:
nessun documento viene dichiarato pagato senza una prova di pagamento.
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import PurePosixPath
from typing import Any

from app.services.fiscal_document_ingestion import FiscalDocumentIngestionService, extract_pdf_pages
from app.services.fiscal_evidence import link_evidence, normalize_evidence, stable_id


ANALYTIC_FILENAME = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})_(?P<company>\d{11,16})_"
    r"(?P<number>\d{20})_Analitica_(?P<bucket>DaSaldare|Saldati)\.pdf$",
    re.IGNORECASE,
)
MONEY = r"-?(?:\d{1,3}(?:\.\d{3})*|\d+),\d{2}"
SUMMARY_ROW = re.compile(
    rf"(?P<notification>\d{{2}}-\d{{2}}-\d{{4}})\s+"
    rf"(?P<initial>{MONEY})\s+(?P<relief>{MONEY})\s+(?P<paid>{MONEY})\s+"
    rf"(?P<settlement>{MONEY})\s+(?P<principal>{MONEY})\s+"
    rf"(?P<interest>{MONEY})\s+(?P<fees>{MONEY})\s+(?P<total>{MONEY})\s+"
    rf"(?P<suspended>{MONEY})\s+(?P<net>{MONEY})\s+"
    r"(?P<rateiz>Si|Sì|No)\s+(?P<procedure>Si|Sì|No)\s+(?P<settled>Si|Sì|No)",
    re.IGNORECASE,
)
LEGACY_SUMMARY_ROW = re.compile(
    rf"NA\s+(?P<creditor>.*?)\s+(?P<notification>\d{{2}}-\d{{2}}-\d{{4}})\s+"
    rf"(?P<initial>{MONEY})\s+(?P<relief>{MONEY})\s+(?P<paid>{MONEY})\s+"
    rf"(?P<settlement>{MONEY})\s+(?P<principal>{MONEY})\s+Ente/Ufficio:",
    re.IGNORECASE,
)
MAX_ARCHIVE_FILES = 1_000
MAX_ARCHIVE_UNCOMPRESSED = 300 * 1024 * 1024


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decimal(value: str | int | float | Decimal) -> Decimal:
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    normalized = str(value).replace("\u00a0", "").replace("'", "").strip()
    if "," in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    try:
        return Decimal(normalized or "0").quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError(f"Importo AdeR non leggibile: {value!r}") from exc


def _money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _cents(value: Decimal) -> int:
    return int(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100)


def _pdf_text(content: bytes) -> str:
    return "\n".join(page["text"] for page in extract_pdf_pages(content))


def _safe_zip(data: bytes) -> zipfile.ZipFile:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError("Archivio AdeR non valido") from exc
    infos = archive.infolist()
    if len(infos) > MAX_ARCHIVE_FILES:
        archive.close()
        raise ValueError("Archivio AdeR con troppi file")
    if sum(item.file_size for item in infos) > MAX_ARCHIVE_UNCOMPRESSED:
        archive.close()
        raise ValueError("Archivio AdeR oltre il limite decompressed")
    for item in infos:
        path = PurePosixPath(item.filename.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts:
            archive.close()
            raise ValueError("Percorso non sicuro nell'archivio AdeR")
        if item.flag_bits & 0x1:
            archive.close()
            raise ValueError("Archivio AdeR cifrato non supportato")
    return archive


def _dataset_bytes(source: bytes) -> tuple[bytes, str | None]:
    """Accetta sia CARTELLE ESATTORIALI.zip sia il master che lo contiene."""
    with _safe_zip(source) as archive:
        names = [item.filename for item in archive.infolist() if not item.is_dir()]
        if any(ANALYTIC_FILENAME.match(PurePosixPath(name).name) for name in names):
            return source, None
        candidates: list[tuple[bytes, str]] = []
        for name in names:
            if not name.lower().endswith(".zip"):
                continue
            nested = archive.read(name)
            try:
                with _safe_zip(nested) as child:
                    if any(ANALYTIC_FILENAME.match(PurePosixPath(n).name) for n in child.namelist()):
                        candidates.append((nested, name))
            except ValueError:
                continue
        if len(candidates) != 1:
            raise ValueError("Il master deve contenere un solo archivio analitico AdeR")
        return candidates[0]


def _business_status(*, net_cents: int, suspended_cents: int, paid_cents: int,
                     portal_bucket: str, threshold_cents: int) -> tuple[str, str | None]:
    if net_cents > threshold_cents:
        return "PAYABLE", None
    if 0 < net_cents <= threshold_cents:
        return "MICRO_RESIDUAL_REVIEW", None
    if suspended_cents > 0 and paid_cents > 0:
        return "PARTIALLY_PAID_SUSPENDED", None
    if suspended_cents > 0:
        return "SUSPENDED_NO_CURRENT_PAYMENT", None
    if portal_bucket == "SALDATI":
        return "PORTAL_CLOSED_PENDING_EVIDENCE", "PORTAL_BUCKET_ONLY"
    return "REVIEW_REQUIRED", None


def parse_analytic_pdf(*, content: bytes, filename: str, source_archive_id: str,
                       dataset_sha256: str, threshold_cents: int) -> dict[str, Any]:
    match = ANALYTIC_FILENAME.match(PurePosixPath(filename).name)
    if not match:
        raise ValueError(f"Nome analitica AdeR non riconosciuto: {filename}")
    text = _pdf_text(content).replace("\r", "\n")
    document_number = match.group("number")
    upper_text = text.upper()
    is_cartella = f"CARTELLA N. {document_number}" in upper_text
    is_avviso = (f"AVVISO DI ADDEBITO N. {document_number}" in upper_text
                 or f"AVVISO DI ACCERTAMENTO N. {document_number}" in upper_text)
    if not (is_cartella or is_avviso):
        raise ValueError(f"Numero documento incoerente nel PDF {filename}")
    normalized_text = re.sub(r"\s+", " ", text)
    summary = SUMMARY_ROW.search(normalized_text)
    legacy_summary = None if summary else LEGACY_SUMMARY_ROW.search(normalized_text)
    if not summary and not legacy_summary:
        raise ValueError(f"Tabella riepilogativa non leggibile nel PDF {filename}")
    if summary:
        values: dict[str, Decimal | None] = {key: _decimal(summary.group(key)) for key in (
            "initial", "relief", "paid", "settlement", "principal", "interest",
            "fees", "total", "suspended", "net",
        )}
        notification = summary.group("notification")
        creditor_match = re.search(r"Rateiz\.\s+Proc\. Attive\s+Def\. age\.\s+NA\s+(.*?)\s+"
                                   + re.escape(notification), text, re.DOTALL | re.IGNORECASE)
        creditor = re.sub(r"\s+", " ", creditor_match.group(1)).strip() if creditor_match else None
        installment_status = "ACTIVE" if summary.group("rateiz").lower() != "no" else "NONE"
        active_procedure: bool | None = summary.group("procedure").lower() != "no"
        settlement_status = "ACTIVE" if summary.group("settled").lower() != "no" else "NONE"
    else:
        assert legacy_summary is not None
        values = {key: _decimal(legacy_summary.group(key)) for key in (
            "initial", "relief", "paid", "settlement", "principal",
        )}
        # Il vecchio prospetto non espone interessi, spese, sospensioni e netto.
        # Il residuo carico e' l'unico totale corrente dichiarato dal documento.
        values.update({"interest": None, "fees": None, "suspended": None,
                       "total": values["principal"], "net": values["principal"]})
        notification = legacy_summary.group("notification")
        creditor = re.sub(r"\s+", " ", legacy_summary.group("creditor")).strip()
        installment_status = "UNKNOWN"
        active_procedure = None
        settlement_status = "UNKNOWN"
    bucket = "DA_SALDARE" if match.group("bucket").lower() == "dasaldare" else "SALDATI"
    status, closure_reason = _business_status(
        net_cents=_cents(values["net"] or Decimal("0")),
        suspended_cents=_cents(values["suspended"] or Decimal("0")),
        paid_cents=_cents(values["paid"] or Decimal("0")), portal_bucket=bucket,
        threshold_cents=threshold_cents,
    )
    source_document_id = stable_id("aderpdf", dataset_sha256, filename)
    row: dict[str, Any] = {
        "id": stable_id("adersnapshot", match.group("company"), document_number,
                        match.group("date"), dataset_sha256),
        "company_id": match.group("company"),
        "snapshot_date": match.group("date"),
        "source_document_id": source_document_id,
        "source_archive_id": source_archive_id,
        "source_archive_sha256": dataset_sha256,
        "source_filename": PurePosixPath(filename).name,
        "document_number": document_number,
        "document_type": "CARTELLA_ESATTORIALE" if is_cartella else "AVVISO_ADDEBITO",
        "portal_bucket": bucket,
        "creditor": creditor,
        "notification_date": datetime.strptime(notification, "%d-%m-%Y").date().isoformat(),
        "initial_amount": _money(values["initial"]),
        "relief_amount": _money(values["relief"]),
        "paid_amount": _money(values["paid"]),
        "settlement_amount": _money(values["settlement"]),
        "residual_principal": _money(values["principal"]),
        "interest_amount": _money(values["interest"]) if values["interest"] is not None else None,
        "additional_sums": None,
        "fees_amount": _money(values["fees"]) if values["fees"] is not None else None,
        "notification_costs": None,
        "total_residual": _money(values["total"]),
        "suspended_amount": _money(values["suspended"]) if values["suspended"] is not None else None,
        "net_payable_amount": _money(values["net"]),
        "installment_status": installment_status,
        "active_procedure": active_procedure,
        "settlement_status": settlement_status,
        "portal_status": bucket,
        "calculated_business_status": status,
        "closure_reason": closure_reason,
        "payment_evidence": False,
        "micro_residual_threshold_cents": threshold_cents,
        "amounts_cents": {key: (_cents(value) if value is not None else None)
                          for key, value in values.items()},
        "source_layout": "CURRENT_10_AMOUNT" if summary else "LEGACY_5_AMOUNT",
        "immutable": True,
    }
    return row


def _resolve_document_reference(reference: str, document_numbers: list[str]) -> str | None:
    matches = [number for number in document_numbers if number == reference or number.startswith(reference)]
    return matches[0] if len(matches) == 1 else None


def parse_rate_plan(*, content: bytes, filename: str, company_id: str,
                    document_numbers: list[str], dataset_sha256: str) -> dict[str, Any]:
    text = re.sub(r"\s+", " ", _pdf_text(content))
    match = re.search(r"identificativo\s+(\d+)\s+del\s+(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE)
    if not match:
        raise ValueError(f"Identificativo rateizzazione non leggibile: {filename}")
    filename_plan = re.search(r"(AR\d+)", filename, re.IGNORECASE)
    plan_id = filename_plan.group(1).upper() if filename_plan else f"AR{match.group(1)}"
    references = re.findall(r"\b[0137]\d{16,19}\b", text)
    unique_references = list(dict.fromkeys(references))
    resolved = [{"printed_reference": ref, "document_number": _resolve_document_reference(ref, document_numbers)}
                for ref in unique_references]
    unresolved = [item["printed_reference"] for item in resolved if not item["document_number"]]
    count_match = re.search(r"Numero rate accordato:\s*(\d+)", text, re.IGNORECASE)
    first_row = re.search(r"\b1\s+(\d{2}/\d{2}/\d{4})(.*?)(?=\s+2\s+\d{2}/\d{2}/\d{4})",
                          text, re.IGNORECASE)
    first_summary = re.search(
        r"Importo Prima Rata(.*?)[€â‚¬]\s*([\d.'â€™]+,\d{2})\s+(\d{2}/\d{2}/\d{4})\s+Successive scadenze",
        text,
        re.IGNORECASE,
    )
    first_amounts = (re.findall(r"€\s*([\d.'’]+,\d{2})", first_row.group(2))
                     if first_row else [])
    total_row = re.search(r"Totale piano(.*?)(?=\s+\d+\s+Per i carichi|\s+Per i carichi)",
                          text, re.IGNORECASE)
    total_amounts = (re.findall(r"€\s*([\d.'’]+,\d{2})", total_row.group(1))
                     if total_row else [])
    return {
        "id": stable_id("aderrateplan", company_id, plan_id, dataset_sha256),
        "company_id": company_id,
        "plan_reference": plan_id,
        "application_date": datetime.strptime(match.group(2), "%d/%m/%Y").date().isoformat(),
        "installment_count": int(count_match.group(1)) if count_match else None,
        "first_installment_amount": (
            _money(_decimal(first_summary.group(2))) if first_summary
            else (_money(_decimal(first_amounts[-1])) if first_amounts else None)
        ),
        "first_installment_due_date": (
            datetime.strptime(first_summary.group(3), "%d/%m/%Y").date().isoformat() if first_summary
            else (datetime.strptime(first_row.group(1), "%d/%m/%Y").date().isoformat() if first_row else None)
        ),
        "total_plan_amount": _money(_decimal(total_amounts[-1])) if total_amounts else None,
        "document_references": resolved,
        "requires_review": bool(unresolved),
        "unresolved_references": unresolved,
        "source_filename": filename,
        "source_document_id": stable_id("aderpdf", dataset_sha256, filename),
        "immutable": True,
    }


def parse_settlement(*, content: bytes, filename: str, company_id: str,
                     dataset_sha256: str) -> dict[str, Any]:
    text = re.sub(r"\s+", " ", _pdf_text(content))
    communication = re.search(r"Documento\s+rif\.\s*AT\s*-\s*(\d{20})", text, re.IGNORECASE)
    all_documents = list(dict.fromkeys(re.findall(r"\b(?:071|371)\d{17}\b", text)))
    communication_number = communication.group(1) if communication else None
    source_number = PurePosixPath(filename).stem if PurePosixPath(filename).stem.isdigit() else None
    related_documents = [
        number for number in all_documents
        if number not in {communication_number, source_number}
    ]
    amount_due = re.search(r"Debito da pagare per la definizione\s+euro\s+([\d.'’]+,\d{2,3})",
                           text, re.IGNORECASE)
    eligible_amount = re.search(r"Debito oggetto\d*\s+di definizione agevolata\s+euro\s+([\d.'’]+,\d{2,3})",
                                text, re.IGNORECASE)
    return {
        "id": stable_id("adersettlement", company_id, filename, dataset_sha256),
        "company_id": company_id,
        "communication_number": communication_number,
        "collection_document_number": related_documents[0] if len(related_documents) == 1 else None,
        "related_document_candidates": related_documents,
        "eligible_amount": _money(_decimal(eligible_amount.group(1))) if eligible_amount else None,
        "amount_due": _money(_decimal(amount_due.group(1))) if amount_due else None,
        "payment_evidence": False,
        "status": "PENDING_PAYMENT_EVIDENCE",
        "closure_reason": "SETTLEMENT_OFFER_WITHOUT_PAYMENT_PROOF",
        "source_filename": filename,
        "source_document_id": stable_id("aderpdf", dataset_sha256, filename),
        "immutable": True,
    }


def parse_payment_module(*, content: bytes, filename: str, company_id: str,
                         dataset_sha256: str) -> dict[str, Any]:
    text = re.sub(r"\s+", " ", _pdf_text(content))
    document_match = re.search(r"DOCUMENTO N\.\s*(\d{20})", text, re.IGNORECASE)
    # Nei moduli reali AdeR lo stesso identificativo puo' essere stampato
    # compatto (AR071812706) oppure spezzato tipograficamente
    # (AR071 - 812706). Il trattino non introduce il numero rata.
    split_plan_match = re.search(
        r"ISTANZA DI RATEIZZAZIONE N\.\s*(AR\d{3})\s*-\s*(\d{6})\b",
        text,
        re.IGNORECASE,
    )
    compact_plan_match = re.search(
        r"ISTANZA DI RATEIZZAZIONE N\.\s*(AR\d{9})\b",
        text,
        re.IGNORECASE,
    )
    plan_reference = None
    if split_plan_match:
        plan_reference = f"{split_plan_match.group(1)}{split_plan_match.group(2)}".upper()
    elif compact_plan_match:
        plan_reference = compact_plan_match.group(1).upper()
    installments = []
    for number, due_date, amount in re.findall(
        r"(\d{1,2})[°º]?\s*RATA\s+entro il\s+(\d{2}/\d{2}/\d{4}).*?Euro\s+([\d.'’]+,\d{2})",
        text, re.IGNORECASE,
    ):
        item = {
            "number": int(number),
            "due_date": datetime.strptime(due_date, "%d/%m/%Y").date().isoformat(),
            "amount": _money(_decimal(amount)),
        }
        if item not in installments:
            installments.append(item)
    return {
        "id": stable_id("aderpaymentmodule", company_id, filename, dataset_sha256),
        "company_id": company_id,
        "document_number": document_match.group(1) if document_match else None,
        "plan_reference": plan_reference,
        "installment_numbers": [item["number"] for item in installments],
        "installments": installments,
        "source_filename": filename,
        "source_document_id": stable_id("aderpdf", dataset_sha256, filename),
        "payment_evidence": False,
        "immutable": True,
    }


def build_ader_archive_plan(*, content: bytes, company_id: str, source_archive_id: str,
                            expected_sha256: str | None = None,
                            threshold_cents: int = 500) -> dict[str, Any]:
    if threshold_cents < 0:
        raise ValueError("Soglia micro-residuo non valida")
    outer_sha256 = hashlib.sha256(content).hexdigest()
    dataset, nested_name = _dataset_bytes(content)
    dataset_sha256 = hashlib.sha256(dataset).hexdigest()
    if expected_sha256 and expected_sha256.lower() not in {outer_sha256, dataset_sha256}:
        raise ValueError("SHA-256 dell'archivio AdeR non coincide")
    pdfs: list[dict[str, Any]] = []
    analytics: list[dict[str, Any]] = []
    auxiliary: list[tuple[str, bytes]] = []
    with _safe_zip(dataset) as archive:
        for item in archive.infolist():
            if item.is_dir():
                continue
            name = PurePosixPath(item.filename).name
            if not name.lower().endswith(".pdf"):
                continue
            payload = archive.read(item)
            pdfs.append({"filename": name, "content": payload,
                         "sha256": hashlib.sha256(payload).hexdigest()})
            if ANALYTIC_FILENAME.match(name):
                analytics.append(parse_analytic_pdf(
                    content=payload, filename=name, source_archive_id=source_archive_id,
                    dataset_sha256=dataset_sha256, threshold_cents=threshold_cents,
                ))
            else:
                auxiliary.append((name, payload))
    if not analytics:
        raise ValueError("Nessuna analitica AdeR trovata")
    if len({row["document_number"] for row in analytics}) != len(analytics):
        raise ValueError("Analitiche AdeR duplicate nello stesso snapshot")
    wrong_company = [row["source_filename"] for row in analytics if row["company_id"] != company_id]
    if wrong_company:
        raise ValueError("Archivio AdeR riferito a un'altra azienda")
    document_numbers = [row["document_number"] for row in analytics]
    plans: list[dict[str, Any]] = []
    settlements: list[dict[str, Any]] = []
    payment_modules: list[dict[str, Any]] = []
    for name, payload in auxiliary:
        if name.lower().startswith("accoglimento_ar"):
            plans.append(parse_rate_plan(content=payload, filename=name, company_id=company_id,
                                         document_numbers=document_numbers, dataset_sha256=dataset_sha256))
        elif "ISTANZA DI RATEIZZAZIONE N." in _pdf_text(payload).upper():
            payment_modules.append(parse_payment_module(
                content=payload, filename=name, company_id=company_id,
                dataset_sha256=dataset_sha256,
            ))
        else:
            settlements.append(parse_settlement(content=payload, filename=name, company_id=company_id,
                                                dataset_sha256=dataset_sha256))
    counts: dict[str, int] = {}
    for row in analytics:
        key = row["calculated_business_status"]
        counts[key] = counts.get(key, 0) + 1
    return {
        "id": stable_id("aderarchive", company_id, dataset_sha256),
        "company_id": company_id,
        "source_archive_id": source_archive_id,
        "source_sha256": outer_sha256,
        "dataset_sha256": dataset_sha256,
        "nested_archive_name": nested_name,
        "snapshot_date": max(row["snapshot_date"] for row in analytics),
        "analytics": analytics,
        "rate_plans": plans,
        "settlements": settlements,
        "payment_modules": payment_modules,
        "pdfs": pdfs,
        "counts": counts,
        "pdf_count": len(pdfs),
        "analytic_count": len(analytics),
        "requires_review": any(plan["requires_review"] for plan in plans),
    }


async def apply_ader_archive_plan(*, db, plan: dict[str, Any], actor: str | None = None) -> dict[str, Any]:
    """Applica un piano già validato; ogni scrittura è idempotente e append-only."""
    from app.db_collections import (
        COLL_ADER_ARCHIVE_IMPORTS, COLL_ADER_POSITION_SNAPSHOTS,
        COLL_TAX_COLLECTION_CLAIMS, COLL_TAX_RATE_PLANS, COLL_TAX_SETTLEMENT_APPLICATIONS,
    )

    now = _now_iso()
    ingestor = FiscalDocumentIngestionService(db, plan["company_id"])
    document_refs: dict[str, dict[str, Any]] = {}
    for item in plan["pdfs"]:
        result = await ingestor.ingest(
            content=item["content"], filename=item["filename"], source="ader_archive",
            source_metadata={"source_archive_id": plan["source_archive_id"],
                             "source_archive_sha256": plan["dataset_sha256"]},
            expected_sha256=item["sha256"], category_hint="riscossione",
        )
        document_refs[item["filename"]] = result

    async def link_source(*, entity_type: str, entity_id: str, source_filename: str,
                          relation_type: str = "source_document") -> None:
        reference = document_refs[source_filename]
        evidence = normalize_evidence(
            document_id=reference["document_id"],
            version_id=reference["version_id"],
            page_number=1,
            field="ader_source_document",
            raw_value=source_filename,
            normalized_value=entity_id,
            parser_version="ader-snapshot-v1",
            reason="document_source",
        )
        await link_evidence(
            db,
            company_id=plan["company_id"],
            entity_type=entity_type,
            entity_id=entity_id,
            relation_type=relation_type,
            evidence=[evidence],
            actor=actor or "ader_archive_import",
        )
    inserted = 0
    for original in plan["analytics"]:
        row = dict(original)
        row["source_document_id"] = document_refs[row["source_filename"]]["document_id"]
        row.update({"created_at": now, "created_by": actor})
        result = await db[COLL_ADER_POSITION_SNAPSHOTS].update_one(
            {"company_id": row["company_id"], "id": row["id"]},
            {"$setOnInsert": row}, upsert=True,
        )
        inserted += int(result.upserted_id is not None)
        claim_id = stable_id("taxclaim", row["company_id"], row["document_number"])
        await db[COLL_TAX_COLLECTION_CLAIMS].update_one(
            {"company_id": row["company_id"], "id": claim_id},
            {"$setOnInsert": {"id": claim_id, "company_id": row["company_id"],
                              "collection_number": row["document_number"], "created_at": now}},
            upsert=True,
        )
        await db[COLL_TAX_COLLECTION_CLAIMS].update_one(
            {"company_id": row["company_id"], "id": claim_id,
             "$or": [{"latest_ader_snapshot_date": {"$exists": False}},
                      {"latest_ader_snapshot_date": {"$lte": row["snapshot_date"]}}]},
            {"$set": {"ader_latest_snapshot_id": row["id"],
                      "latest_ader_snapshot_date": row["snapshot_date"],
                      "portal_status": row["portal_status"],
                      "business_status": row["calculated_business_status"],
                      "residual_cents": row["amounts_cents"]["net"],
                      "source_document_id": row["source_document_id"], "updated_at": now}},
        )
        await link_source(entity_type="ader_snapshot", entity_id=row["id"],
                          source_filename=row["source_filename"])
        await link_source(entity_type="tax_collection_claim", entity_id=claim_id,
                          source_filename=row["source_filename"], relation_type="ader_snapshot_source")

    modules_by_plan: dict[str, list[dict[str, Any]]] = {}
    for original in plan["payment_modules"]:
        module = dict(original)
        source = document_refs[module["source_filename"]]
        module["source_document_id"] = source["document_id"]
        modules_by_plan.setdefault(module.get("plan_reference") or "", []).append(module)
    for collection, items in ((COLL_TAX_RATE_PLANS, plan["rate_plans"]),
                              (COLL_TAX_SETTLEMENT_APPLICATIONS, plan["settlements"])):
        for original in items:
            item = dict(original)
            item["source_document_id"] = document_refs[item["source_filename"]]["document_id"]
            if collection == COLL_TAX_RATE_PLANS:
                item["payment_modules"] = modules_by_plan.get(item.get("plan_reference") or "", [])
            item.update({"created_at": now, "created_by": actor})
            await db[collection].update_one(
                {"company_id": item["company_id"], "id": item["id"]},
                {"$setOnInsert": item}, upsert=True,
            )
            entity_type = ("tax_rate_plan" if collection == COLL_TAX_RATE_PLANS
                           else "tax_settlement_application")
            await link_source(entity_type=entity_type, entity_id=item["id"],
                              source_filename=item["source_filename"])
            if collection == COLL_TAX_RATE_PLANS:
                for module in item["payment_modules"]:
                    await link_source(entity_type=entity_type, entity_id=item["id"],
                                      source_filename=module["source_filename"],
                                      relation_type="payment_module")
                for reference in item.get("document_references", []):
                    document_number = reference.get("document_number")
                    if not document_number:
                        continue
                    claim_id = stable_id("taxclaim", item["company_id"], document_number)
                    await link_source(entity_type="tax_collection_claim", entity_id=claim_id,
                                      source_filename=item["source_filename"],
                                      relation_type="rate_plan_source")
            elif item.get("collection_document_number"):
                claim_id = stable_id("taxclaim", item["company_id"], item["collection_document_number"])
                await link_source(entity_type="tax_collection_claim", entity_id=claim_id,
                                  source_filename=item["source_filename"],
                                  relation_type="settlement_source")
    archive_record = {key: value for key, value in plan.items()
                      if key not in {"analytics", "rate_plans", "settlements", "pdfs"}}
    archive_record.update({"created_at": now, "created_by": actor})
    await db[COLL_ADER_ARCHIVE_IMPORTS].update_one(
        {"company_id": plan["company_id"], "id": plan["id"]},
        {"$setOnInsert": archive_record}, upsert=True,
    )
    return {"archive_id": plan["id"], "inserted_snapshots": inserted,
            "existing_snapshots": len(plan["analytics"]) - inserted,
            "analytic_count": len(plan["analytics"]), "pdf_count": len(plan["pdfs"])}
