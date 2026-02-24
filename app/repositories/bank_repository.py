"""
Bank repository.
Data access layer for bank statements and checks.
"""
from typing import List, Dict, Any
from datetime import date
import logging

from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class BankStatementRepository(BaseRepository):
    """Repository for bank statement operations."""
    
    async def find_by_date_range(
        self,
        start_date: date,
        end_date: date,
        user_id: str
    ) -> List[Dict[str, Any]]:
        """Find statements within date range."""
        return await self.find_all(
            filter_query={
                "user_id": user_id,
                "date": {
                    "$gte": start_date.isoformat(),
                    "$lte": end_date.isoformat()
                }
            },
            sort=[("date", -1)]
        )
    
    async def find_unreconciled(
        self,
        user_id: str
    ) -> List[Dict[str, Any]]:
        """Find unreconciled statements."""
        return await self.find_all(
            filter_query={
                "user_id": user_id,
                "reconciled": False
            },
            sort=[("date", -1)]
        )


class AssegnoRepository(BaseRepository):
    """Repository for assegno operations."""
    
    async def find_by_status(
        self,
        status: str,
        user_id: str
    ) -> List[Dict[str, Any]]:
        """Find checks by status."""
        return await self.find_all(
            filter_query={
                "user_id": user_id,
                "status": status
            },
            sort=[("date", -1)]
        )
    
    async def find_by_date_range(
        self,
        start_date: date,
        end_date: date,
        user_id: str
    ) -> List[Dict[str, Any]]:
        """Find checks within date range."""
        return await self.find_all(
            filter_query={
                "user_id": user_id,
                "date": {
                    "$gte": start_date.isoformat(),
                    "$lte": end_date.isoformat()
                }
            },
            sort=[("date", -1)]
        )


# Alias for backward compatibility
BankRepository = BankStatementRepository
