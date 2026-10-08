"""
Chart of accounts service.
"""
from typing import List, Dict, Any
from datetime import datetime, timezone
import logging

from app.repositories.chart_repository import ChartOfAccountsRepository
from app.exceptions import DuplicateError
from app.models.accounting_extended import (
    ChartOfAccountCreate,
    ChartOfAccountUpdate
)

logger = logging.getLogger(__name__)


class ChartOfAccountsService:
    """Service for chart of accounts."""
    
    def __init__(self, chart_repo: ChartOfAccountsRepository):
        self.chart_repo = chart_repo
    
    async def create_account(
        self,
        account_data: ChartOfAccountCreate,
        user_id: str
    ) -> str:
        """Create chart of account."""
        # Check duplicate code
        existing = await self.chart_repo.find_by_code(
            account_data.code, user_id
        )
        if existing:
            raise DuplicateError("Account", "code", account_data.code)
        
        account_doc = account_data.model_dump()
        account_doc.update({
            "user_id": user_id,
            "is_active": True,
            "level": account_data.code.count('.'),
            "created_at": datetime.now(timezone.utc)
        })
        
        return await self.chart_repo.create(account_doc)
    
    async def list_accounts(
        self,
        user_id: str,
        account_type: str = None
    ) -> List[Dict[str, Any]]:
        """List accounts."""
        if account_type:
            return await self.chart_repo.find_by_type(account_type, user_id)
        
        return await self.chart_repo.find_by_user(user_id, limit=1000)
    
    async def update_account(
        self,
        account_id: str,
        update_data: ChartOfAccountUpdate
    ) -> bool:
        """Update account."""
        update_dict = update_data.model_dump(exclude_unset=True)
        if not update_dict:
            return True
        
        update_dict["updated_at"] = datetime.now(timezone.utc)
        return await self.chart_repo.update(account_id, update_dict)
    
    async def delete_account(self, account_id: str) -> bool:
        """Delete account."""
        return await self.chart_repo.update(
            account_id,
            {"is_active": False, "updated_at": datetime.now(timezone.utc)}
        )
