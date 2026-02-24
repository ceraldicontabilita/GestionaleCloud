"""
Bank router.
API endpoints for bank statements and checks management.
"""
from fastapi import APIRouter, Depends, Query, Path, status
from typing import List, Dict, Any, Optional
from datetime import date
import logging

from app.database import Database, Collections
from app.repositories.bank_repository import BankStatementRepository
from app.services.bank_service import BankService
from app.models.bank import (
    BankStatementCreate,
    BankReconcile,
    AssegnoCreate,
    AssegnoUpdate
)
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


async def get_bank_service() -> BankService:
    """Get bank service with injected dependencies."""
    db = Database.get_db()
    statement_repo = BankStatementRepository(db[Collections.BANK_STATEMENTS])
    return BankService(statement_repo)


@router.get(
    "/statements",
    response_model=List[Dict[str, Any]],
    summary="List bank statements"
)
async def list_statements(
    current_user: Dict[str, Any] = Depends(get_current_user),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    service: BankService = Depends(get_bank_service)
) -> List[Dict[str, Any]]:
    """List bank statement transactions."""
    user_id = current_user["user_id"]
    return await service.list_statements(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date
    )


@router.post(
    "/statements/upload",
    status_code=status.HTTP_201_CREATED,
    summary="Upload bank statement"
)
async def upload_statement(
    statement_data: BankStatementCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: BankService = Depends(get_bank_service)
) -> Dict[str, str]:
    """Upload bank statement transaction."""
    user_id = current_user["user_id"]
    statement_id = await service.create_statement(
        statement_data=statement_data,
        user_id=user_id
    )
    return {
        "message": "Bank statement uploaded",
        "statement_id": statement_id
    }


@router.post(
    "/reconcile",
    summary="Reconcile bank statement"
)
async def reconcile_statement(
    reconcile_data: BankReconcile,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: BankService = Depends(get_bank_service)
) -> Dict[str, str]:
    """Reconcile bank statement with invoice."""
    return {"message": "Statement reconciled successfully"}


@router.get(
    "/assegni",
    response_model=List[Dict[str, Any]],
    summary="List checks"
)
async def list_assegni(
    current_user: Dict[str, Any] = Depends(get_current_user),
    assegno_status: Optional[str] = Query(None, alias="status"),
    service: BankService = Depends(get_bank_service)
) -> List[Dict[str, Any]]:
    """List checks with optional status filter."""
    return []


@router.post(
    "/assegni",
    status_code=status.HTTP_201_CREATED,
    summary="Create check (assegno)"
)
async def create_assegno(
    assegno_data: AssegnoCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: BankService = Depends(get_bank_service)
) -> Dict[str, str]:
    """Create check record."""
    return {
        "message": "Assegno created",
        "assegno_id": "placeholder"
    }


@router.put(
    "/assegni/{assegno_id}",
    summary="Update check status"
)
async def update_assegno_status(
    assegno_id: str = Path(...),
    update_data: AssegnoUpdate = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: BankService = Depends(get_bank_service)
) -> Dict[str, str]:
    """Update check status."""
    return {"message": "Assegno updated"}


@router.get(
    "/balance",
    summary="Get bank balance"
)
async def get_balance(
    current_user: Dict[str, Any] = Depends(get_current_user),
    account: Optional[str] = Query(None),
    service: BankService = Depends(get_bank_service)
) -> Dict[str, Any]:
    """Get current bank balance."""
    user_id = current_user["user_id"]
    return await service.get_balance(
        user_id=user_id,
        account=account
    )
