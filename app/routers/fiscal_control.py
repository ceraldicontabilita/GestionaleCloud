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
    COLL_FISCAL_DOCUMENTS, COLL_TAX_CODE_CROSSWALK, COLL_TAX_COLLECTION_CLAIMS,
    COLL_TAX_COLLECTION_EVENTS, COLL_TAX_COLLECTION_SNAPSHOTS,
    COLL_TAX_CREDIT_MOVEMENTS, COLL_TAX_PAYMENTS,
    COLL_TAX_RATE_INSTALLMENTS, COLL_TAX_RATE_PLANS,
    COLL_TAX_SETTLEMENT_APPLICATIONS,
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


_REGISTRO_TTL_SECONDI = 15.0
_registro_letto: dict[str, Any] = {}


async def _righe_registro(db) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Registro unico F24 (modelli, quietanze, addebiti) e le sue righe tributo.

    La pagina chiede riepilogo e scheda insieme: una lettura sola per entrambi,
    tenuta 15 secondi (le stesse del giro della cache del runtime).
    """
    import time

    from app.services.f24_controllo_incrociato import carica_registro
    from app.services.registro_fiscale_f24 import righe_da_registro

    adesso = time.monotonic()
    if _registro_letto.get("db") is db and adesso - _registro_letto.get("at", 0.0) < _REGISTRO_TTL_SECONDI:
        return _registro_letto["registro"], _registro_letto["righe"]
    registro = await carica_registro(db)
    righe = righe_da_registro(registro)
    _registro_letto.update({"db": db, "at": adesso, "registro": registro, "righe": righe})
    return registro, righe


def _fonti(righe: list[dict[str, Any]]) -> dict[str, Any]:
    return {"registro_f24": len(righe), "canonical": "registro_f24"}


@router.get("/summary")
async def summary(_admin: Dict[str, Any] = Depends(get_current_admin_user)):
    from app.services.registro_fiscale_f24 import conteggi

    db = Database.get_db()
    registro, righe = await _righe_registro(db)
    dichiarazioni = await db[COLL_FISCAL_DOCUMENTS].count_documents(
        {"company_id": _company(), "document_type": {"$in": sorted(DECLARATION_TYPES)}},
    )
    return {
        "company_id": _company(), "counts": conteggi(registro, righe, dichiarazioni),
        "requires_review": 0, "canonical_source": "registro_f24",
    }


def _pagina_documenti(righe, *, cerca, anno_documento, stato_documento, offset, limit):
    """Documenti F24 interi (righe raggruppate), filtrati e a pagine sul server."""
    from app.services.registro_fiscale_f24 import pagina_documenti_f24

    return pagina_documenti_f24(
        righe, cerca=cerca, anno=anno_documento, stato=stato_documento,
        offset=offset, limit=limit,
    )


@router.get("/obligations")
async def obligations(status: str | None = None, limit: int = Query(200, ge=1, le=5000),
                      _admin: Dict[str, Any] = Depends(get_current_admin_user),
                      raggruppa: bool = False, offset: int = 0,
                      cerca: Optional[str] = None, anno_documento: Optional[str] = None,
                      stato_documento: Optional[str] = None):
    """Deleghe per stato. Con ``raggruppa`` una pagina di documenti interi
    (``offset``/``limit``), filtrati per testo, anno e stato, con conteggi e
    totali dell'intero elenco: la pagina non scarica piu' tutte le righe."""
    from app.services.registro_fiscale_f24 import obblighi

    _, righe = await _righe_registro(Database.get_db())
    items = obblighi(righe, status)
    if raggruppa:
        return {
            **_pagina_documenti(items, cerca=cerca, anno_documento=anno_documento,
                                stato_documento=stato_documento, offset=max(0, offset), limit=limit),
            "sources": _fonti(items),
        }
    return {"items": items[:limit], "total": len(items), "sources": _fonti(items)}


@router.get("/f24-rows")
async def f24_rows(
    tax_code: str | None = None,
    document_id: str | None = None,
    year: int | None = Query(None, ge=2000, le=2100),
    credits_only: bool = False,
    offset: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=5000),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
    raggruppa: bool = False,
    cerca: Optional[str] = None,
    anno_documento: Optional[str] = None,
    stato_documento: Optional[str] = None,
):
    """Righe F24 del registro, ognuna col suo modello o quietanza d'origine.

    Con ``raggruppa`` rende documenti interi a pagine, come ``/obligations``.
    """
    from app.services.registro_fiscale_f24 import filtra_righe

    _, righe = await _righe_registro(Database.get_db())
    items = filtra_righe(righe, year=year, tax_code=tax_code, document_id=document_id,
                         credits_only=credits_only)
    if raggruppa:
        return {
            **_pagina_documenti(items, cerca=cerca, anno_documento=anno_documento,
                                stato_documento=stato_documento, offset=offset, limit=limit),
            "sources": _fonti(items),
            "filters": {"tax_code": tax_code, "document_id": document_id, "year": year,
                        "credits_only": credits_only},
        }
    return {
        "items": items[offset:offset + limit],
        "total": len(items),
        "offset": offset,
        "limit": limit,
        "sources": _fonti(items),
        "filters": {"tax_code": tax_code, "document_id": document_id, "year": year, "credits_only": credits_only},
    }


@router.get("/declarations")
async def declarations(
    year: int | None = Query(None, ge=2000, le=2100),
    declaration_type: str | None = None,
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
):
    """770/IVA/IRAP/LIPE/Redditi SC gia' ingeriti in fiscal_documents, con i
    tributi F24/quietanza gia' agganciati da ``list_declaration_dossiers``."""
    if declaration_type and declaration_type not in DECLARATION_TYPES:
        raise HTTPException(400, "Tipo dichiarazione non valido")
    db = Database.get_db()
    dossiers = await list_declaration_dossiers(
        db, company_id=_company(), year=year, declaration_type=declaration_type,
    )
    dossiers.sort(key=lambda item: (
        int(item.get("filing_year") or 0), str(item.get("filename") or ""),
    ), reverse=True)
    return {
        "items": dossiers, "total": len(dossiers), "year": year,
        "declaration_type": declaration_type,
        "sources": {
            "fiscal_documents": len(dossiers),
            "canonical": "fiscal_documents",
        },
    }


@router.get("/source-certainty")
async def source_certainty(
    year: int | None = Query(None, ge=2000, le=2100),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
):
    """Confronta modelli F24 del commercialista e quietanze su identita' fiscali forti."""
    from app.services.fiscal_source_certainty import (
        annotate_declaration_certainty,
        group_model_rows,
        reconcile_f24_sources,
    )
    from app.services.registro_fiscale_f24 import obblighi

    db = Database.get_db()
    _, righe = await _righe_registro(db)
    all_rows = obblighi(righe)
    if year:
        all_rows = [row for row in all_rows if str(row.get("payment_year") or "") == str(year)]
    receipt_rows = [row for row in all_rows if row.get("documentary_payment_status") == "QUIETANZA_PRESENTE"]
    model_rows = [row for row in all_rows if row.get("source_role") == "MODELLO_F24_COMMERCIALISTA"]
    accountant_documents = group_model_rows(model_rows)
    result = reconcile_f24_sources(receipt_rows, accountant_documents)
    declarations = await list_declaration_dossiers(db, company_id=_company(), year=year)
    declaration_items = annotate_declaration_certainty([{
        "document_id": item.get("id"),
        "document_type": item.get("document_type"),
        "filing_year": item.get("filing_year"),
        "tax_year": item.get("tax_year"),
        "filename": item.get("filename"),
        "protocol": item.get("protocol"),
        # Registrata in fiscal_documents con una versione: il deposito e'
        # l'indice, e l'originale si legge per id, non per nome.
        "relation_state": "CONFERMATA_NOME_UNIVOCO_E_INDICE_VERIFICATO"
        if item.get("current_version_id") else None,
    } for item in declarations])
    result.update({
        "year": year,
        "sources": {
            "quietanza_drive_rows": len(receipt_rows),
            "commercialista_f24_documents": len(accountant_documents),
            "unattributed_f24_model_documents": 0,
            "unattributed_f24_model_rows": 0,
            "declaration_documents": len(declarations),
            "canonical": "registro_f24",
        },
        "declarations": {
            "documents": len(declarations),
            "with_verified_identity": sum(bool(item.get("current_version_id")) for item in declarations),
            "ready_for_field_check": sum(
                item.get("field_check_status") == "PRONTO_PER_VERIFICA_CAMPI"
                for item in declaration_items
            ),
            "identity_or_version_review": sum(
                item.get("version_resolution_status")
                == "IDENTITA_DICHIARANTE_E_VERSIONE_DA_VERIFICARE"
                for item in declaration_items
            ),
            "field_level_reconciled": 0,
            "status": "DATI_DICHIARAZIONE_NON_ANCORA_ESTRATTI"
            if declarations else "DICHIARAZIONI_MANCANTI",
            "requires_review": bool(declarations),
        },
        "declaration_items": declaration_items,
    })
    return result


async def _originale_fiscale(db, document: dict[str, Any]) -> tuple[bytes, str]:
    """PDF originale di un documento fiscale, dal deposito Documenti."""
    inbox_id = (document.get("metadata") or {}).get("documents_inbox_id")
    query = ({"id": inbox_id, "company_id": _company()} if inbox_id
             else {"company_id": _company(), "fiscal_document_id": document.get("id")})
    source = await db["documents_inbox"].find_one(query, {"_id": 0, "pdf_data": 1, "filename": 1})
    if not source or not source.get("pdf_data"):
        raise HTTPException(404, "Originale non disponibile nel deposito Documenti")
    return base64.b64decode(source["pdf_data"]), str(source.get("filename") or "documento.pdf")


@router.get("/declarations/{document_id}/field-certainty")
async def declaration_field_certainty(
    document_id: str,
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
):
    """Estrae campi dichiarativi tracciati e li confronta con le righe F24 del registro."""
    import hashlib

    from app.services.declaration_field_certainty import (
        extract_declaration_fields,
        reconcile_770_management,
        reconcile_lipe_management,
        reconcile_declaration_tax_rows,
    )
    from app.services.declaration_registry import declaration_metadata
    from app.services.registro_fiscale_f24 import obblighi

    db = Database.get_db()
    raw = await db[COLL_FISCAL_DOCUMENTS].find_one({"company_id": _company(), "id": document_id}, {"_id": 0})
    if not raw or raw.get("document_type") not in DECLARATION_TYPES:
        raise HTTPException(404, "Dichiarazione non trovata")
    declaration = declaration_metadata(raw)
    content, filename = await _originale_fiscale(db, raw)
    sha256 = hashlib.sha256(content).hexdigest()
    try:
        extraction = await asyncio.to_thread(
            extract_declaration_fields,
            content,
            document_type=declaration["document_type"],
            document_id=document_id,
            filename=declaration.get("filename") or filename,
            sha256=sha256,
            tax_year=declaration.get("tax_year"),
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    _, righe = await _righe_registro(db)

    reconciliation = reconcile_declaration_tax_rows(extraction, obblighi(righe))
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
            snapshots_list = await asyncio.gather(*[
                get_iva_period_snapshot(db, anno=int(tax_year), mese=month)
                for month in months
            ])
            snapshots = {item["periodo"]: item for item in snapshots_list}
            management_reconciliation = reconcile_lipe_management(extraction, snapshots)
        except Exception as exc:  # la prova dichiarazione/F24 resta consultabile
            management_warning = f"{type(exc).__name__}: {exc}"
    elif extraction.get("document_type") == "MODELLO_770":
        periods = sorted({
            str(item.get("reference_period") or "")
            for item in extraction.get("tax_rows") or []
            if item.get("reference_period")
        })
        try:
            records = [] if not periods else await db["ritenute_acconto"].find(
                {"periodo_ritenuta": {"$in": periods}},
                {"_id": 0, "id": 1, "periodo_ritenuta": 1, "importo": 1,
                 "importo_cents": 1, "source_document_id": 1, "projection_source": 1},
            ).to_list(10000)
            management_reconciliation = reconcile_770_management(extraction, records)
        except Exception as exc:  # la prova dichiarazione/F24 resta consultabile
            management_warning = f"{type(exc).__name__}: {exc}"
    return {
        "source": {
            "document": {"id": document_id, "filename": declaration.get("filename") or filename},
            "declaration": {k: declaration.get(k) for k in ("document_type", "filing_year", "tax_year", "protocol")},
            "sha256": sha256,
            "canonical": "fiscal_documents",
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
    content, filename = await _originale_fiscale(db, document)
    safe_filename = filename.replace('"', "_").replace("\r", "_").replace("\n", "_")
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
