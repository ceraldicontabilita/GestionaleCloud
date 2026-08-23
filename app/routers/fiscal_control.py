"""API della situazione fiscale: letture protette e mutazioni admin con MFA."""

from __future__ import annotations

import asyncio
import base64
import io
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.database import Database
from app.db_collections import (
    COLL_ADER_ARCHIVE_IMPORTS, COLL_ADER_POSITION_SNAPSHOTS,
    COLL_FISCAL_DOCUMENTS, COLL_FISCAL_EVIDENCE, COLL_TAX_ALLOCATIONS,
    COLL_TAX_CODE_CROSSWALK, COLL_TAX_COLLECTION_CLAIMS,
    COLL_TAX_COLLECTION_EVENTS, COLL_TAX_COLLECTION_SNAPSHOTS,
    COLL_TAX_CREDIT_MOVEMENTS, COLL_TAX_OBLIGATIONS, COLL_TAX_PAYMENTS,
    COLL_TAX_RATE_INSTALLMENTS, COLL_TAX_RATE_PLANS,
    COLL_TAX_SETTLEMENT_APPLICATIONS,
    COLL_F24,
)
from app.services.fiscal_agents import AdvisorBriefGenerator, FiscalControlAgent, buildTaxEvidencePackage, buildTaxReviewDossier, load_review_data
from app.services.fiscal_domain import rebuild_vat_credit_chain, reconstruct_collection_state
from app.services.fiscal_evidence import find_linked_evidence, now_iso, stable_id
from app.services.declaration_registry import DECLARATION_TYPES, list_declaration_dossiers
from app.services.ravvedimento_engine import RavvedimentoEngine
from app.services.tax_collection_service import build_snapshot
from app.services.ader_snapshot_import import apply_ader_archive_plan, build_ader_archive_plan
from app.utils.dependencies import get_current_admin_mfa_user, get_current_admin_user


router = APIRouter()


class SnapshotRow(BaseModel):
    collection_number: str
    original_amount: float = 0
    residual: float = 0
    portal_status: Optional[str] = None
    payment_evidence: bool = False
    suspended: bool = False
    disputed: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SnapshotRequest(BaseModel):
    source_document_id: str
    captured_at: str
    rows: List[SnapshotRow]


class RavvedimentoRequest(BaseModel):
    principal: float
    days_late: int = Field(ge=0)
    legal_rule_version: Optional[str] = None


class CollectionEventRequest(BaseModel):
    event_type: str
    effective_at: str
    amount: float = 0
    evidence_ids: List[str] = Field(min_length=1)
    closure_cause: Optional[str] = None
    source_reference: Optional[str] = None


class AderArchiveRequest(BaseModel):
    source_archive_document_id: str = Field(min_length=1)
    expected_sha256: Optional[str] = None


def _company() -> str:
    return settings.FISCAL_COMPANY_ID


def _fiscal_date_sort_key(value: Any) -> str:
    """Normalizza le date miste dell'indice Drive prima dell'ordinamento API."""
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y%m%d")
    text = str(value or "").strip()
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text[:10], pattern).strftime("%Y%m%d")
        except ValueError:
            continue
    return text


async def _load_ader_archive(body: AderArchiveRequest) -> tuple[dict[str, Any], bytes]:
    db = Database.get_db()
    source = await db["documents_inbox"].find_one(
        {"id": body.source_archive_document_id, "company_id": _company()},
        {"_id": 0, "id": 1, "filename": 1, "pdf_data": 1, "content_type": 1},
    )
    if not source:
        raise HTTPException(404, "Archivio AdeR non trovato nel deposito Documenti")
    filename = str(source.get("filename") or "")
    if not filename.lower().endswith(".zip"):
        raise HTTPException(422, "Il documento sorgente AdeR deve essere un archivio ZIP")
    encoded = source.get("pdf_data")
    if not encoded:
        raise HTTPException(409, "Archivio AdeR privo del contenuto originale")
    try:
        content = base64.b64decode(encoded, validate=True) if isinstance(encoded, str) else bytes(encoded)
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, "Contenuto dell'archivio AdeR non valido") from exc
    return source, content


def _ader_plan_preview(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value for key, value in plan.items()
        if key != "pdfs"
    } | {
        "pdfs": [
            {key: value for key, value in item.items() if key != "content"}
            for item in plan["pdfs"]
        ]
    }


@router.get("/summary")
async def summary(_admin: Dict[str, Any] = Depends(get_current_admin_user)):
    drive_index: dict[str, Any]
    try:
        from app.services.drive_document_index import get_overview
        overview = await asyncio.to_thread(get_overview)
        validation = overview.get("validation") or {}
        drive_index = {
            "available": True,
            "verified": bool(validation.get("all_true")),
            "counts": validation.get("counts") or {},
            "semantics": overview.get("semantics") or {},
        }
    except (RuntimeError, ValueError) as exc:
        drive_index = {"available": False, "verified": False, "counts": {}, "warning": str(exc)}
    return {
        "company_id": _company(), "counts": {},
        "requires_review": 0, "drive_index": drive_index,
        "canonical_source": "google_drive",
    }


@router.get("/obligations")
async def obligations(status: str | None = None, limit: int = Query(200, ge=1, le=5000),
                      _admin: Dict[str, Any] = Depends(get_current_admin_user)):
    drive_warning = None
    try:
        from app.services.drive_document_index import list_documented_tax_payments, list_tax_obligations
        loader = list_documented_tax_payments if status == "PAID_ON_TIME" else list_tax_obligations
        drive_payload = await asyncio.to_thread(loader, offset=0, limit=limit)
        drive_items = drive_payload["items"]
        drive_total = drive_payload["total"]
    except (RuntimeError, ValueError) as exc:
        drive_items, drive_total, drive_warning = [], 0, str(exc)
    return {
        "items": drive_items,
        "total": drive_total,
        "sources": {
            "drive_excel_index": len(drive_items),
            "canonical": "google_drive",
            "drive_warning": drive_warning,
        },
    }


@router.get("/f24-rows")
async def f24_rows(
    tax_code: str | None = None,
    document_id: str | None = None,
    year: int | None = Query(None, ge=2000, le=2100),
    credits_only: bool = False,
    offset: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=5000),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
):
    """Normalized F24 lines with a direct, reversible link to their PDF."""
    drive_warning = None
    try:
        from app.services.drive_document_index import list_f24_rows
        drive_payload = await asyncio.to_thread(
            list_f24_rows, year=str(year) if year else None,
            tax_code=tax_code, document_id=document_id,
            credits_only=credits_only, offset=0, limit=5000,
        )
        drive_items = drive_payload["items"]
        drive_total = drive_payload["total"]
    except (RuntimeError, ValueError) as exc:
        drive_items = []
        drive_total = 0
        drive_warning = str(exc)

    drive_items.sort(key=lambda item: (
        _fiscal_date_sort_key(item.get("payment_date")), str(item.get("filename") or ""),
        int(item.get("ordinal") or 0),
    ), reverse=True)
    items = drive_items[offset:offset + limit]
    return {
        "items": items,
        "total": drive_total,
        "offset": offset,
        "limit": limit,
        "sources": {
            "drive_excel_index": len(drive_items),
            "canonical": "google_drive",
            "drive_warning": drive_warning,
        },
        "filters": {"tax_code": tax_code, "document_id": document_id, "year": year, "credits_only": credits_only},
    }


@router.get("/declarations")
async def declarations(
    year: int | None = Query(None, ge=2000, le=2100),
    declaration_type: str | None = None,
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
):
    if declaration_type and declaration_type not in DECLARATION_TYPES:
        raise HTTPException(400, "Tipo dichiarazione non valido")
    drive_warning = None
    try:
        from app.services.drive_document_index import list_declarations as list_drive_declarations
        drive_payload = await asyncio.to_thread(
            list_drive_declarations, year=str(year) if year else None,
            declaration_type=declaration_type, limit=5000,
        )
        drive_items = drive_payload["results"]
    except (RuntimeError, ValueError) as exc:
        drive_items = []
        drive_warning = str(exc)

    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in drive_items:
        identity = str(
            item.get("sha256") or item.get("document_id") or item.get("id")
            or item.get("archive_path") or item.get("filename") or ""
        ).casefold()
        if identity and identity in seen:
            continue
        if identity:
            seen.add(identity)
        merged.append(item)
    merged.sort(key=lambda item: (
        int(item.get("filing_year") or 0), str(item.get("filename") or ""),
    ), reverse=True)
    return {
        "items": merged, "total": len(merged), "year": year,
        "declaration_type": declaration_type,
        "sources": {
            "drive_excel_index": len(drive_items),
            "canonical": "google_drive",
            "drive_warning": drive_warning,
        },
    }


@router.get("/source-certainty")
async def source_certainty(
    year: int | None = Query(None, ge=2000, le=2100),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
):
    """Confronta F24 del commercialista e quietanze Drive su identita' fiscali forti."""
    from app.services.drive_document_index import list_declarations as list_drive_declarations
    from app.services.drive_document_index import list_f24_rows
    from app.services.fiscal_source_certainty import reconcile_f24_sources

    drive_payload = await asyncio.to_thread(
        list_f24_rows, year=str(year) if year else None, offset=0, limit=5000,
    )
    declaration_payload = await asyncio.to_thread(
        list_drive_declarations, year=str(year) if year else None, limit=5000,
    )
    query: dict[str, Any] = {"status": {"$ne": "eliminato"}}
    if year:
        query["$or"] = [
            {"anno": year}, {"anno": str(year)},
            {"periodo_riferimento": {"$regex": str(year)}},
            {"data_scadenza": {"$regex": f"^{year}"}},
        ]
    db = Database.get_db()
    accountant_documents = await db[COLL_F24].find(
        query, {"_id": 0, "pdf_data": 0},
    ).to_list(5000)
    result = reconcile_f24_sources(drive_payload["items"], accountant_documents)
    declarations = declaration_payload["results"]
    declaration_items = [{
        "document_id": item.get("document_id"),
        "document_type": item.get("document_type"),
        "filing_year": item.get("filing_year"),
        "tax_year": item.get("tax_year"),
        "filename": item.get("filename"),
        "protocol": item.get("protocol"),
        "relation_state": item.get("relation_state"),
        "field_check_status": (
            "PRONTO_PER_VERIFICA_CAMPI"
            if item.get("document_type") in {
                "MODELLO_770", "LIPE", "DICHIARAZIONE_IVA", "REDDITI_SC", "DICHIARAZIONE_IRAP",
            }
            and item.get("relation_state") == "CONFERMATA_NOME_UNIVOCO_E_INDICE_VERIFICATO"
            else "PARSER_SPECIFICO_NON_DISPONIBILE"
        ),
    } for item in declarations]
    result.update({
        "year": year,
        "sources": {
            "quietanza_drive_rows": len(drive_payload["items"]),
            "commercialista_f24_documents": len(accountant_documents),
            "declaration_documents": len(declarations),
            "canonical": "drive_sheets",
        },
        "declarations": {
            "documents": len(declarations),
            "with_verified_identity": sum(
                item.get("relation_state") == "CONFERMATA_NOME_UNIVOCO_E_INDICE_VERIFICATO"
                for item in declarations
            ),
            "field_level_reconciled": 0,
            "status": "DATI_DICHIARAZIONE_NON_ANCORA_ESTRATTI"
            if declarations else "DICHIARAZIONI_MANCANTI",
            "requires_review": bool(declarations),
        },
        "declaration_items": declaration_items,
    })
    return result


@router.get("/declarations/{document_id}/field-certainty")
async def declaration_field_certainty(
    document_id: str,
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
):
    """Estrae campi dichiarativi tracciati e li confronta con le righe F24 Drive."""
    from app.services.declaration_field_certainty import (
        extract_declaration_fields,
        reconcile_lipe_management,
        reconcile_declaration_tax_rows,
    )
    from app.services.drive_document_index import (
        build_drive_service,
        list_f24_rows,
        load_declaration_pdf,
    )

    try:
        service = await asyncio.to_thread(build_drive_service)
        source = await asyncio.to_thread(load_declaration_pdf, document_id, service)
        extraction = await asyncio.to_thread(
            extract_declaration_fields,
            source["content"],
            document_type=source["declaration"]["document_type"],
            document_id=document_id,
            filename=source["document"].get("filename"),
            sha256=source["sha256"],
            tax_year=source["declaration"].get("tax_year"),
        )
        f24_payload = await asyncio.to_thread(
            list_f24_rows, service, offset=0, limit=5000,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc

    reconciliation = reconcile_declaration_tax_rows(extraction, f24_payload["items"])
    management_reconciliation = None
    management_warning = None
    if extraction.get("document_type") == "LIPE":
        from app.services.iva_liquidation_query import get_iva_period_snapshot

        tax_year = extraction.get("tax_year")
        months = sorted({
            int(item["month"]) for item in extraction.get("declared_fields") or []
            if item.get("month") and tax_year
        })
        try:
            db = Database.get_db()
            snapshots_list = await asyncio.gather(*[
                get_iva_period_snapshot(db, anno=int(tax_year), mese=month)
                for month in months
            ])
            snapshots = {item["periodo"]: item for item in snapshots_list}
            management_reconciliation = reconcile_lipe_management(extraction, snapshots)
        except Exception as exc:  # la prova dichiarazione/F24 resta consultabile
            management_warning = str(exc)
    return {
        "source": {
            "document": source["document"],
            "declaration": source["declaration"],
            "drive_file_id": source["drive_file_id"],
            "drive_url": source["drive_url"],
            "sha256": source["sha256"],
            "canonical": "google_drive",
        },
        "extraction": extraction,
        "reconciliation": reconciliation,
        "management_reconciliation": management_reconciliation,
        "management_warning": management_warning,
    }


@router.get("/f24-documents")
async def f24_documents(
    year: int | None = Query(None, ge=2000, le=2100),
    offset: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=1000),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
):
    """PDF-first view; every item can be expanded through ``/f24-rows``."""
    query: dict[str, Any] = {
        "company_id": _company(),
        "source_kind": "F24_DOCUMENT_EVIDENCE",
    }
    if year:
        query["payment_year"] = year
    db = Database.get_db()
    items = await db[COLL_TAX_PAYMENTS].find(query, {"_id": 0}).sort([
        ("payment_date", -1), ("filename", 1),
    ]).skip(offset).limit(limit).to_list(limit)
    return {
        "items": items,
        "total": await db[COLL_TAX_PAYMENTS].count_documents(query),
        "offset": offset,
        "limit": limit,
    }


@router.get("/collections")
async def collection_claims(limit: int = Query(200, ge=1, le=1000),
                            _admin: Dict[str, Any] = Depends(get_current_admin_user)):
    query = {"company_id": _company()}
    db = Database.get_db()
    items = await db[COLL_TAX_COLLECTION_CLAIMS].find(query, {"_id": 0}).sort("updated_at", -1).to_list(limit)
    return {"items": items, "total": await db[COLL_TAX_COLLECTION_CLAIMS].count_documents(query)}


@router.get("/ader-snapshots")
async def ader_snapshots(
    business_status: str | None = None,
    limit: int = Query(200, ge=1, le=1000),
    skip: int = Query(0, ge=0),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
):
    query: dict[str, Any] = {"company_id": _company()}
    if business_status:
        query["calculated_business_status"] = business_status
    db = Database.get_db()
    items = await (
        db[COLL_ADER_POSITION_SNAPSHOTS]
        .find(query, {"_id": 0})
        .sort([("snapshot_date", -1), ("net_payable_amount", -1)])
        .skip(skip)
        .limit(limit)
        .to_list(limit)
    )
    latest_import = await db[COLL_ADER_ARCHIVE_IMPORTS].find_one(
        {"company_id": _company()}, {"_id": 0}, sort=[("snapshot_date", -1), ("created_at", -1)]
    )
    rate_plans = await (
        db[COLL_TAX_RATE_PLANS]
        .find({"company_id": _company()}, {"_id": 0})
        .sort([("application_date", -1), ("created_at", -1)])
        .to_list(100)
    )
    installments = await db[COLL_TAX_RATE_INSTALLMENTS].find(
        {"company_id": _company()}, {"_id": 0}
    ).sort([("due_date", -1), ("installment_number", -1)]).to_list(5000)
    installments_by_plan: dict[str, list[dict[str, Any]]] = {}
    for installment in installments:
        installments_by_plan.setdefault(installment.get("rate_plan_id") or "", []).append(installment)
    for plan in rate_plans:
        plan["reconciled_installments"] = installments_by_plan.get(plan.get("id") or "", [])
    settlements = await (
        db[COLL_TAX_SETTLEMENT_APPLICATIONS]
        .find({"company_id": _company()}, {"_id": 0})
        .sort([("created_at", -1)])
        .to_list(100)
    )
    return {
        "items": items,
        "total": await db[COLL_ADER_POSITION_SNAPSHOTS].count_documents(query),
        "latest_import": latest_import,
        "rate_plans": rate_plans,
        "settlements": settlements,
    }


@router.post("/ader-snapshots/dry-run")
async def ader_snapshot_dry_run(
    body: AderArchiveRequest,
    _admin: Dict[str, Any] = Depends(get_current_admin_mfa_user),
):
    _source, content = await _load_ader_archive(body)
    try:
        plan = build_ader_archive_plan(
            content=content,
            company_id=_company(),
            source_archive_id=body.source_archive_document_id,
            expected_sha256=body.expected_sha256,
            threshold_cents=settings.ADER_MICRO_RESIDUAL_THRESHOLD_CENTS,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _ader_plan_preview(plan)


@router.post("/ader-snapshots/import")
async def ader_snapshot_import(
    body: AderArchiveRequest,
    admin: Dict[str, Any] = Depends(get_current_admin_mfa_user),
):
    _source, content = await _load_ader_archive(body)
    try:
        plan = build_ader_archive_plan(
            content=content,
            company_id=_company(),
            source_archive_id=body.source_archive_document_id,
            expected_sha256=body.expected_sha256,
            threshold_cents=settings.ADER_MICRO_RESIDUAL_THRESHOLD_CENTS,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    result = await apply_ader_archive_plan(
        db=Database.get_db(), plan=plan, actor=admin.get("user_id")
    )
    return {**result, "counts": plan["counts"], "requires_review": plan["requires_review"]}


@router.get("/collections/{claim_id}")
async def collection_detail(claim_id: str, _admin: Dict[str, Any] = Depends(get_current_admin_user)):
    db = Database.get_db()
    claim = await db[COLL_TAX_COLLECTION_CLAIMS].find_one({"company_id": _company(), "$or": [{"id": claim_id}, {"collection_number": claim_id}]}, {"_id": 0})
    if not claim:
        raise HTTPException(404, "Posizione fiscale non trovata")
    events = await db[COLL_TAX_COLLECTION_EVENTS].find({"company_id": _company(), "claim_id": claim.get("id") or claim_id}, {"_id": 0}).sort("effective_at", 1).to_list(5000)
    return {"claim": claim, "events": events, "state": reconstruct_collection_state(events)}


@router.post("/collections/{claim_id}/events")
async def append_event(claim_id: str, body: CollectionEventRequest,
                       admin: Dict[str, Any] = Depends(get_current_admin_mfa_user)):
    db = Database.get_db()
    claim = await db[COLL_TAX_COLLECTION_CLAIMS].find_one({"company_id": _company(), "id": claim_id}, {"_id": 0, "id": 1})
    if not claim:
        raise HTTPException(404, "Posizione fiscale non trovata")
    event_id = stable_id("taxevent", _company(), claim_id, body.event_type, body.effective_at, body.source_reference)
    event = {**body.model_dump(), "id": event_id, "company_id": _company(), "claim_id": claim_id, "created_at": now_iso(), "created_by": admin.get("user_id")}
    await db[COLL_TAX_COLLECTION_EVENTS].update_one({"company_id": _company(), "id": event_id}, {"$setOnInsert": event}, upsert=True)
    events = await db[COLL_TAX_COLLECTION_EVENTS].find({"company_id": _company(), "claim_id": claim_id}, {"_id": 0}).to_list(5000)
    state = reconstruct_collection_state(events)
    await db[COLL_TAX_COLLECTION_CLAIMS].update_one({"company_id": _company(), "id": claim_id}, {"$set": {**state, "updated_at": now_iso()}})
    return {"event_id": event_id, "state": state}


@router.get("/evidence/{entity_type}/{entity_id}")
async def evidence(entity_type: str, entity_id: str, _admin: Dict[str, Any] = Depends(get_current_admin_user)):
    return {"links": await find_linked_evidence(Database.get_db(), company_id=_company(), entity_type=entity_type, entity_id=entity_id)}


@router.get("/documents/{document_id}/content")
async def document_content(document_id: str, _admin: Dict[str, Any] = Depends(get_current_admin_user)):
    db = Database.get_db()
    document = await db[COLL_FISCAL_DOCUMENTS].find_one({"company_id": _company(), "id": document_id}, {"_id": 0})
    if not document:
        raise HTTPException(404, "Documento fiscale non trovato")
    inbox_id = (document.get("metadata") or {}).get("documents_inbox_id")
    query = {"id": inbox_id, "company_id": _company()} if inbox_id else {"company_id": _company(), "fiscal_document_id": document_id}
    source = await db["documents_inbox"].find_one(query, {"_id": 0, "pdf_data": 1, "filename": 1})
    if not source or not source.get("pdf_data"):
        raise HTTPException(404, "Originale non disponibile nel deposito Documenti")
    content = base64.b64decode(source["pdf_data"])
    safe_filename = str(source.get("filename") or "documento.pdf").replace('"', "_").replace("\r", "_").replace("\n", "_")
    return StreamingResponse(io.BytesIO(content), media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{safe_filename}"'})


@router.post("/collection-snapshots/dry-run")
async def snapshot_dry_run(body: SnapshotRequest, _admin: Dict[str, Any] = Depends(get_current_admin_mfa_user)):
    return build_snapshot(company_id=_company(), source_document_id=body.source_document_id, captured_at=body.captured_at, rows=[row.model_dump() for row in body.rows])


@router.post("/collection-snapshots/import")
async def snapshot_import(body: SnapshotRequest, admin: Dict[str, Any] = Depends(get_current_admin_mfa_user)):
    db = Database.get_db()
    if not await db[COLL_FISCAL_DOCUMENTS].find_one({"company_id": _company(), "id": body.source_document_id}):
        raise HTTPException(409, "Documento sorgente non registrato: importazione vietata")
    snapshot = build_snapshot(company_id=_company(), source_document_id=body.source_document_id, captured_at=body.captured_at, rows=[row.model_dump() for row in body.rows])
    if await db[COLL_TAX_COLLECTION_SNAPSHOTS].find_one({"company_id": _company(), "id": snapshot["id"]}, {"_id": 0, "id": 1}):
        return {"duplicate": True, "id": snapshot["id"], "row_count": snapshot["row_count"]}
    snapshot.update({"created_at": now_iso(), "created_by": admin.get("user_id")})
    await db[COLL_TAX_COLLECTION_SNAPSHOTS].insert_one(snapshot.copy())
    for row in snapshot["rows"]:
        claim_id = stable_id("taxclaim", _company(), row["collection_number"])
        await db[COLL_TAX_COLLECTION_CLAIMS].update_one(
            {"company_id": _company(), "id": claim_id},
            {"$setOnInsert": {"created_at": now_iso()}, "$set": {**row, "id": claim_id, "company_id": _company(), "snapshot_id": snapshot["id"], "source_document_id": body.source_document_id, "updated_at": now_iso()}}, upsert=True)
    return {"duplicate": False, "id": snapshot["id"], "row_count": snapshot["row_count"]}


@router.post("/ravvedimento/calculate")
async def calculate_ravvedimento(body: RavvedimentoRequest, _admin: Dict[str, Any] = Depends(get_current_admin_user)):
    rule = None
    if body.legal_rule_version:
        rule = await Database.get_db()["legal_rule_versions"].find_one({"company_id": _company(), "version": body.legal_rule_version}, {"_id": 0})
    return RavvedimentoEngine.calculate(principal=body.principal, days_late=body.days_late, legal_rule=rule)


@router.post("/vat-credit-chain/rebuild")
async def vat_credit_chain(start_year: int = Query(..., ge=2000, le=2100), end_year: int = Query(..., ge=2000, le=2100),
                           _admin: Dict[str, Any] = Depends(get_current_admin_mfa_user)):
    if end_year < start_year:
        raise HTTPException(422, "Intervallo anni non valido")
    db = Database.get_db()
    rows = await db[COLL_TAX_CREDIT_MOVEMENTS].find({"company_id": _company(), "tax_family": "IVA", "year": {"$gte": start_year, "$lte": end_year}}, {"_id": 0}).to_list(10000)
    return rebuild_vat_credit_chain(rows, start_year, end_year)


@router.get("/crosswalk")
async def crosswalk(limit: int = Query(200, ge=1, le=1000), _admin: Dict[str, Any] = Depends(get_current_admin_user)):
    db = Database.get_db()
    query = {"company_id": _company()}
    return {"items": await db[COLL_TAX_CODE_CROSSWALK].find(query, {"_id": 0}).limit(limit).to_list(limit), "total": await db[COLL_TAX_CODE_CROSSWALK].count_documents(query)}


@router.get("/review")
async def fiscal_review(_admin: Dict[str, Any] = Depends(get_current_admin_user)):
    obligations_data, claims = await load_review_data(Database.get_db(), _company())
    findings = FiscalControlAgent.review(obligations=obligations_data, claims=claims)
    return {"brief": AdvisorBriefGenerator.build(company_id=_company(), obligations=obligations_data, claims=claims, findings=findings), "findings": findings}


@router.get("/dossier.pdf")
async def dossier(_admin: Dict[str, Any] = Depends(get_current_admin_user)):
    obligations_data, claims = await load_review_data(Database.get_db(), _company())
    findings = FiscalControlAgent.review(obligations=obligations_data, claims=claims)
    brief = AdvisorBriefGenerator.build(company_id=_company(), obligations=obligations_data, claims=claims, findings=findings)
    return StreamingResponse(io.BytesIO(buildTaxReviewDossier(brief, findings)), media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=dossier_fiscale.pdf"})


@router.get("/evidence-package.zip")
async def evidence_package(_admin: Dict[str, Any] = Depends(get_current_admin_mfa_user)):
    return StreamingResponse(io.BytesIO(await buildTaxEvidencePackage(Database.get_db(), company_id=_company())), media_type="application/zip", headers={"Content-Disposition": "attachment; filename=evidence_fiscale.zip"})
