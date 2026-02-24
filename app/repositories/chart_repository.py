"""
Chart of accounts repository.
"""
from typing import List, Dict, Any
import logging

from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class ChartOfAccountsRepository(BaseRepository):
    """Repository for chart of accounts."""
    
    async def find_by_type(
        self,
        account_type: str,
        user_id: str
    ) -> List[Dict[str, Any]]:
        """Find accounts by type."""
        return await self.find_all(
            filter_query={
                "user_id": user_id,
                "type": account_type,
                "is_active": True
            },
            sort=[("code", 1)]
        )
    
    async def find_by_code(
        self,
        code: str,
        user_id: str
    ) -> Dict[str, Any]:
        """Find account by code."""
        return await self.find_one({
            "user_id": user_id,
            "code": code
        })
