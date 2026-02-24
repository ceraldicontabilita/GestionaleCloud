"""
Cash repository.
Data access layer for cash register operations.
"""
from typing import List, Dict, Any, Optional
from datetime import date
import logging

from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class CashMovementRepository(BaseRepository):
    """Repository for cash movement operations."""
    
    async def find_by_date_range(
        self,
        start_date: date,
        end_date: date,
        user_id: str,
        movement_type: Optional[str] = None,
        skip: int = 0,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Find cash movements within date range.
        
        Args:
            start_date: Start date
            end_date: End date
            user_id: User ID
            movement_type: Optional filter by type (entrata/uscita)
            skip: Number to skip
            limit: Maximum to return
            
        Returns:
            List of movements
        """
        filter_query = {
            "user_id": user_id,
            "date": {
                "$gte": start_date.isoformat(),
                "$lte": end_date.isoformat()
            }
        }
        
        if movement_type:
            filter_query["type"] = movement_type
        
        logger.info(
            f"Finding cash movements from {start_date} to {end_date}, "
            f"type: {movement_type or 'all'}"
        )
        
        return await self.find_all(
            filter_query=filter_query,
            skip=skip,
            limit=limit,
            sort=[("date", -1), ("time", -1)]
        )
    
    async def find_by_date(
        self,
        target_date: date,
        user_id: str
    ) -> List[Dict[str, Any]]:
        """
        Find movements for specific date.
        
        Args:
            target_date: Target date
            user_id: User ID
            
        Returns:
            List of movements
        """
        return await self.find_all(
            filter_query={
                "user_id": user_id,
                "date": target_date.isoformat()
            },
            sort=[("time", 1)]
        )
    
    async def find_by_type(
        self,
        movement_type: str,
        user_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Find movements by type.
        
        Args:
            movement_type: Type (entrata/uscita)
            user_id: User ID
            skip: Number to skip
            limit: Maximum to return
            
        Returns:
            List of movements
        """
        return await self.find_all(
            filter_query={
                "user_id": user_id,
                "type": movement_type
            },
            skip=skip,
            limit=limit,
            sort=[("date", -1), ("time", -1)]
        )
    
    async def find_by_category(
        self,
        category: str,
        user_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Find movements by category.
        
        Args:
            category: Category name
            user_id: User ID
            skip: Number to skip
            limit: Maximum to return
            
        Returns:
            List of movements
        """
        return await self.find_all(
            filter_query={
                "user_id": user_id,
                "category": category
            },
            skip=skip,
            limit=limit,
            sort=[("date", -1)]
        )
    
    async def calculate_balance(
        self,
        user_id: str,
        up_to_date: Optional[date] = None
    ) -> Dict[str, float]:
        """
        Calculate cash balance.
        
        Args:
            user_id: User ID
            up_to_date: Calculate balance up to this date (inclusive)
            
        Returns:
            Dictionary with total_in, total_out, balance
        """
        filter_query = {"user_id": user_id}
        
        if up_to_date:
            filter_query["date"] = {"$lte": up_to_date.isoformat()}
        
        movements = await self.find_all(
            filter_query=filter_query,
            limit=100000
        )
        
        total_in = sum(
            m.get("amount", 0)
            for m in movements
            if m.get("type") == "entrata"
        )
        
        total_out = sum(
            m.get("amount", 0)
            for m in movements
            if m.get("type") == "uscita"
        )
        
        return {
            "total_in": total_in,
            "total_out": total_out,
            "balance": total_in - total_out
        }


class CorrissettivoRepository(BaseRepository):
    """Repository for corrispettivo (daily closure) operations."""
    
    async def find_by_date(
        self,
        target_date: date,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Find corrispettivo for specific date.
        
        Args:
            target_date: Target date
            user_id: User ID
            
        Returns:
            Corrispettivo document or None
        """
        return await self.find_one({
            "user_id": user_id,
            "date": target_date.isoformat()
        })
    
    async def find_by_month(
        self,
        month: int,
        year: int,
        user_id: str
    ) -> List[Dict[str, Any]]:
        """
        Find corrispettivi for a month.
        
        Args:
            month: Month (1-12)
            year: Year
            user_id: User ID
            
        Returns:
            List of corrispettivi
        """
        # Create date range for month
        date_prefix = f"{year:04d}-{month:02d}"
        
        return await self.find_all(
            filter_query={
                "user_id": user_id,
                "date": {"$regex": f"^{date_prefix}"}
            },
            sort=[("date", 1)]
        )
    
    async def find_by_date_range(
        self,
        start_date: date,
        end_date: date,
        user_id: str
    ) -> List[Dict[str, Any]]:
        """
        Find corrispettivi within date range.
        
        Args:
            start_date: Start date
            end_date: End date
            user_id: User ID
            
        Returns:
            List of corrispettivi
        """
        return await self.find_all(
            filter_query={
                "user_id": user_id,
                "date": {
                    "$gte": start_date.isoformat(),
                    "$lte": end_date.isoformat()
                }
            },
            sort=[("date", 1)]
        )
    
    async def find_unreconciled(
        self,
        user_id: str
    ) -> List[Dict[str, Any]]:
        """
        Find unreconciled corrispettivi.
        
        Args:
            user_id: User ID
            
        Returns:
            List of unreconciled corrispettivi
        """
        return await self.find_all(
            filter_query={
                "user_id": user_id,
                "is_reconciled": False
            },
            sort=[("date", 1)]
        )
    
    async def get_month_totals(
        self,
        month: int,
        year: int,
        user_id: str
    ) -> Dict[str, float]:
        """
        Calculate monthly totals.
        
        Args:
            month: Month (1-12)
            year: Year
            user_id: User ID
            
        Returns:
            Dictionary with totals
        """
        corrispettivi = await self.find_by_month(month, year, user_id)
        
        total_cash = sum(c.get("total_cash", 0) for c in corrispettivi)
        total_card = sum(c.get("total_card", 0) for c in corrispettivi)
        total_other = sum(c.get("total_other", 0) for c in corrispettivi)
        total_receipts = sum(c.get("total_receipts", 0) for c in corrispettivi)
        
        return {
            "total_cash": total_cash,
            "total_card": total_card,
            "total_other": total_other,
            "total_amount": total_cash + total_card + total_other,
            "total_receipts": total_receipts,
            "days_count": len(corrispettivi)
        }
