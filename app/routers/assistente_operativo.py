"""API dell'Assistente Ceraldi operativo.

Il router espone memoria, controlli e domande decisionali. Le azioni di
scansione sono amministrative e protette da MFA; il motore sottostante puo'
scrivere esclusivamente nelle collezioni dedicate all'assistente.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from app.database import Database
from app.services.operational_learning_engine import (
    OperationalLearningEngine,
    build_driver_fact,
    build_tax_obligation,
)
from app.utils.dependencies import get_current_admin_mfa_user, get_current_admin_user


router = APIRouter()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnswerQuestionRequest(StrictModel):
    option_id: str = Field(min_length=1, max_length=120)
    notes: str = Field(default="", max_length=2000)


class ObservationRequest(StrictModel):
    source: str = Field(min_length=1, max_length=200)
    source_version: str = Field(min_length=1, max_length=200)
    payload: Dict[str, Any]
    observed_at: Optional[str] = None
    supersedes: Optional[str] = Field(default=None, max_length=200)


class DriverAssignmentRequest(StrictModel):
    targa: str = Field(min_length=2, max_length=20)
    driver_id: str = Field(min_length=1, max_length=200)
    valid_from: str = Field(min_length=8, max_length=40)
    valid_to: Optional[str] = Field(default=None, max_length=40)
    confirmations: int = Field(default=1, ge=0, le=100000)
    contradictions: int = Field(default=0, ge=0, le=100000)
    sources: list[Dict[str, Any]] = Field(default_factory=list, max_length=100)


class ConfirmedCaseRequest(StrictModel):
    case_type: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=300)
    resolution: str = Field(min_length=1, max_length=4000)
    source_id: Optional[str] = Field(default=None, max_length=200)
    evidence: list[Dict[str, Any]] = Field(default_factory=list, max_length=100)


class TaxObligationRequest(StrictModel):
    tax_code: str = Field(min_length=1, max_length=30)
    year: int = Field(ge=2000, le=2200)
    due_date: str = Field(min_length=8, max_length=40)
    expected_amount: Decimal = Field(gt=Decimal("0.00"), max_digits=16, decimal_places=2)
    source_id: str = Field(min_length=1, max_length=200)
    period: Optional[str] = Field(default=None, max_length=40)
    entity: Optional[str] = Field(default=None, max_length=200)


class OfficialSourceRequest(StrictModel):
    authority: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=500)
    url: str = Field(min_length=8, max_length=2000)
    version: str = Field(min_length=1, max_length=200)
    verified_at: str = Field(min_length=8, max_length=40)
    valid_from: Optional[str] = Field(default=None, max_length=40)
    valid_to: Optional[str] = Field(default=None, max_length=40)
    payload: Dict[str, Any] = Field(default_factory=dict)


def _engine() -> OperationalLearningEngine:
    return OperationalLearningEngine(Database.get_db())


def _actor(user: Dict[str, Any]) -> str:
    return str(user.get("email") or user.get("user_id") or "admin")


@router.get("/dashboard")
async def dashboard(
    limit: int = Query(default=100, ge=1, le=500),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    return await _engine().dashboard(limit=limit)


@router.post("/scan/payroll")
async def scan_payroll(
    _admin: Dict[str, Any] = Depends(get_current_admin_mfa_user),
) -> Dict[str, Any]:
    rows = await _engine().scan_payroll_residuals()
    return {"status": "ok", "questions": len(rows)}


@router.post("/scan/employees")
async def scan_employees(
    _admin: Dict[str, Any] = Depends(get_current_admin_mfa_user),
) -> Dict[str, Any]:
    rows = await _engine().scan_employee_expiries()
    return {"status": "ok", "questions": len(rows)}


@router.post("/scan/f24")
async def scan_f24(
    _admin: Dict[str, Any] = Depends(get_current_admin_mfa_user),
) -> Dict[str, Any]:
    anomalies = await _engine().scan_f24_misallocations()
    patterns = await _engine().learn_periodic_f24()
    expected = await _engine().reconcile_expected_tax_events()
    return {
        "status": "ok",
        "anomalies": len(anomalies),
        "patterns": len(patterns),
        "reconciled_tax_events": len(expected),
    }


@router.post("/scan/all")
async def scan_all(
    _admin: Dict[str, Any] = Depends(get_current_admin_mfa_user),
) -> Dict[str, Any]:
    return await _engine().run_sentinel()


@router.post("/questions/{question_id}/answer")
async def answer_question(
    question_id: str,
    payload: AnswerQuestionRequest,
    admin: Dict[str, Any] = Depends(get_current_admin_mfa_user),
) -> Dict[str, Any]:
    try:
        result = await _engine().answer_question(
            question_id=question_id,
            option_id=payload.option_id,
            actor=_actor(admin),
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domanda non trovata")
    return result


@router.post("/observations", status_code=status.HTTP_201_CREATED)
async def record_observation(
    payload: ObservationRequest,
    _admin: Dict[str, Any] = Depends(get_current_admin_mfa_user),
) -> Dict[str, Any]:
    try:
        return await _engine().record_observation(**payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/tax-obligations", status_code=status.HTTP_201_CREATED)
async def create_tax_obligation(
    payload: TaxObligationRequest,
    _admin: Dict[str, Any] = Depends(get_current_admin_mfa_user),
) -> Dict[str, Any]:
    try:
        event = build_tax_obligation(**payload.model_dump())
        return await _engine().upsert_expected_event(event)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/knowledge-sources/official", status_code=status.HTTP_201_CREATED)
async def record_official_source(
    payload: OfficialSourceRequest,
    _admin: Dict[str, Any] = Depends(get_current_admin_mfa_user),
) -> Dict[str, Any]:
    source_payload = {
        "authority": payload.authority,
        "title": payload.title,
        "url": payload.url,
        "valid_from": payload.valid_from,
        "valid_to": payload.valid_to,
        "data": payload.payload,
    }
    try:
        return await _engine().record_observation(
            source=f"official:{payload.authority}",
            source_version=payload.version,
            payload=source_payload,
            observed_at=payload.verified_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/facts/driver-assignment", status_code=status.HTTP_201_CREATED)
async def record_driver_assignment(
    payload: DriverAssignmentRequest,
    _admin: Dict[str, Any] = Depends(get_current_admin_mfa_user),
) -> Dict[str, Any]:
    fact = build_driver_fact(**payload.model_dump())
    return await _engine().upsert_fact(fact)


@router.post("/cases", status_code=status.HTTP_201_CREATED)
async def remember_confirmed_case(
    payload: ConfirmedCaseRequest,
    admin: Dict[str, Any] = Depends(get_current_admin_mfa_user),
) -> Dict[str, Any]:
    try:
        return await _engine().remember_case(
            {
                **payload.model_dump(),
                "outcome_status": "confirmed",
                "confirmed_by": _actor(admin),
            }
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
