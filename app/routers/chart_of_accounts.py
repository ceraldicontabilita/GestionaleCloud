"""
Chart of accounts router.
API endpoints for chart of accounts (Piano dei conti).
"""
from fastapi import APIRouter, Depends, Query, Path, status
from typing import List, Dict, Any, Optional
import logging

from app.database import Database, Collections
from app.repositories.chart_repository import ChartOfAccountsRepository
from app.services.chart_service import ChartOfAccountsService
from app.models.accounting_extended import (
    ChartOfAccountCreate,
    ChartOfAccountUpdate
)
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


async def get_chart_service() -> ChartOfAccountsService:
    """Get chart service with injected dependencies."""
    db = Database.get_db()
    chart_repo = ChartOfAccountsRepository(db[Collections.CHART_OF_ACCOUNTS])
    return ChartOfAccountsService(chart_repo)


@router.get(
    "",
    response_model=List[Dict[str, Any]],
    summary="List chart of accounts"
)
async def list_accounts(
    current_user: Dict[str, Any] = Depends(get_current_user),
    type: Optional[str] = Query(None, pattern="^(attivo|passivo|costi|ricavi)$"),
    service: ChartOfAccountsService = Depends(get_chart_service)
) -> List[Dict[str, Any]]:
    """
    List chart of accounts.
    
    **Query Parameters:**
    - **type**: Filter by type (attivo/passivo/costi/ricavi)
    """
    user_id = current_user["user_id"]
    
    return await service.list_accounts(
        user_id=user_id,
        account_type=type
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create account"
)
async def create_account(
    account_data: ChartOfAccountCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: ChartOfAccountsService = Depends(get_chart_service)
) -> Dict[str, str]:
    """
    Create chart of account.
    
    **Request Body:**
    - **code**: Account code (e.g., 1.01.01)
    - **name**: Account name
    - **type**: Type (attivo/passivo/costi/ricavi)
    - **parent_id**: Optional parent account
    - **description**: Optional description
    """
    user_id = current_user["user_id"]
    
    account_id = await service.create_account(
        account_data=account_data,
        user_id=user_id
    )
    
    return {
        "message": "Account created",
        "account_id": account_id
    }


@router.put(
    "/{account_id}",
    summary="Update account"
)
async def update_account(
    account_id: str = Path(...),
    update_data: ChartOfAccountUpdate = ...,
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: ChartOfAccountsService = Depends(get_chart_service)
) -> Dict[str, str]:
    """Update chart of account."""
    await service.update_account(
        account_id=account_id,
        update_data=update_data
    )
    
    return {"message": "Account updated"}


@router.delete(
    "/{account_id}",
    summary="Delete account"
)
async def delete_account(
    account_id: str = Path(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: ChartOfAccountsService = Depends(get_chart_service)
) -> Dict[str, str]:
    """Soft delete account (set inactive)."""
    await service.delete_account(account_id)
    
    return {"message": "Account deleted"}
