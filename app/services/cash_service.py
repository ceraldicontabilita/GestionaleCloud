"""
Cash service.
Business logic for cash register management and daily closures.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, date
import logging

from app.repositories.cash_repository import (
    CashMovementRepository,
    CorrissettivoRepository
)
from app.exceptions import (
    NotFoundError,
    DuplicateError
)
from app.models.cash import (
    CashMovementCreate,
    CashMovementUpdate,
    CorrissettivoCreate
)

logger = logging.getLogger(__name__)


class CashService:
    """Service for cash register operations."""
    
    def __init__(
        self,
        movement_repo: CashMovementRepository,
        corrispettivo_repo: CorrissettivoRepository
    ):
        """
        Initialize cash service.
        
        Args:
            movement_repo: Cash movement repository instance
            corrispettivo_repo: Corrispettivo repository instance
        """
        self.movement_repo = movement_repo
        self.corrispettivo_repo = corrispettivo_repo
    
    async def create_movement(
        self,
        movement_data: CashMovementCreate,
        user_id: str
    ) -> str:
        """
        Create cash movement.
        
        Args:
            movement_data: Movement data
            user_id: User ID
            
        Returns:
            Created movement ID
        """
        logger.info(
            f"Creating cash movement: {movement_data.type} "
            f"€{movement_data.amount} - {movement_data.description}"
        )
        
        movement_doc = movement_data.model_dump()
        movement_doc.update({
            "user_id": user_id,
            "date": movement_data.date.isoformat(),
            "created_at": datetime.now(timezone.utc)
        })
        
        movement_id = await self.movement_repo.create(movement_doc)
        
        logger.info(f"✅ Cash movement created: {movement_id}")
        
        return movement_id
    
    async def get_movement(
        self,
        movement_id: str
    ) -> Dict[str, Any]:
        """
        Get movement by ID.
        
        Args:
            movement_id: Movement ID
            
        Returns:
            Movement document
            
        Raises:
            NotFoundError: If movement not found
        """
        movement = await self.movement_repo.find_by_id(movement_id)
        
        if not movement:
            raise NotFoundError("Cash movement", movement_id)
        
        return movement
    
    async def list_movements(
        self,
        user_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        movement_type: Optional[str] = None,
        category: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        List cash movements with filters.
        
        Args:
            user_id: User ID
            start_date: Optional start date filter
            end_date: Optional end date filter
            movement_type: Optional type filter (entrata/uscita)
            category: Optional category filter
            skip: Pagination offset
            limit: Maximum results
            
        Returns:
            List of movements
        """
        if category:
            return await self.movement_repo.find_by_category(
                category=category,
                user_id=user_id,
                skip=skip,
                limit=limit
            )
        
        if movement_type and not (start_date and end_date):
            return await self.movement_repo.find_by_type(
                movement_type=movement_type,
                user_id=user_id,
                skip=skip,
                limit=limit
            )
        
        if start_date and end_date:
            return await self.movement_repo.find_by_date_range(
                start_date=start_date,
                end_date=end_date,
                user_id=user_id,
                movement_type=movement_type,
                skip=skip,
                limit=limit
            )
        
        # All movements
        return await self.movement_repo.find_by_user(
            user_id=user_id,
            skip=skip,
            limit=limit
        )
    
    async def update_movement(
        self,
        movement_id: str,
        update_data: CashMovementUpdate
    ) -> bool:
        """
        Update cash movement.
        
        Args:
            movement_id: Movement ID
            update_data: Update data
            
        Returns:
            True if updated
            
        Raises:
            NotFoundError: If movement not found
        """
        logger.info(f"Updating cash movement: {movement_id}")
        
        # Verify exists
        await self.get_movement(movement_id)
        
        update_dict = update_data.model_dump(exclude_unset=True)
        
        if not update_dict:
            return True
        
        update_dict["updated_at"] = datetime.now(timezone.utc)
        
        return await self.movement_repo.update(movement_id, update_dict)
    
    async def delete_movement(
        self,
        movement_id: str
    ) -> bool:
        """
        Delete cash movement.
        
        Args:
            movement_id: Movement ID
            
        Returns:
            True if deleted
            
        Raises:
            NotFoundError: If movement not found
        """
        logger.warning(f"Deleting cash movement: {movement_id}")
        
        # Verify exists
        await self.get_movement(movement_id)
        
        return await self.movement_repo.delete(movement_id)
    
    async def get_cash_stats(
        self,
        user_id: str,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """
        Get cash register statistics.
        
        Args:
            user_id: User ID
            start_date: Start date
            end_date: End date
            
        Returns:
            Statistics dictionary
        """
        movements = await self.movement_repo.find_by_date_range(
            start_date=start_date,
            end_date=end_date,
            user_id=user_id,
            limit=10000
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
        
        # Group by category
        by_category = {}
        for m in movements:
            cat = m.get("category", "uncategorized")
            if cat not in by_category:
                by_category[cat] = {"in": 0, "out": 0, "count": 0}
            
            if m.get("type") == "entrata":
                by_category[cat]["in"] += m.get("amount", 0)
            else:
                by_category[cat]["out"] += m.get("amount", 0)
            
            by_category[cat]["count"] += 1
        
        # Group by payment method
        by_payment = {}
        for m in movements:
            pm = m.get("payment_method", "unknown")
            by_payment[pm] = by_payment.get(pm, 0) + m.get("amount", 0)
        
        return {
            "total_in": total_in,
            "total_out": total_out,
            "current_balance": total_in - total_out,
            "movements_count": len(movements),
            "by_category": by_category,
            "by_payment_method": by_payment,
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            }
        }
    
    async def create_corrispettivo(
        self,
        corrispettivo_data: CorrissettivoCreate,
        user_id: str
    ) -> str:
        """
        Create daily corrispettivo (closure).
        
        Args:
            corrispettivo_data: Corrispettivo data
            user_id: User ID
            
        Returns:
            Created corrispettivo ID
            
        Raises:
            DuplicateError: If corrispettivo already exists for date
        """
        logger.info(f"Creating corrispettivo for {corrispettivo_data.date}")
        
        # Check if already exists
        existing = await self.corrispettivo_repo.find_by_date(
            target_date=corrispettivo_data.date,
            user_id=user_id
        )
        
        if existing:
            raise DuplicateError(
                "Corrispettivo",
                "date",
                corrispettivo_data.date.isoformat()
            )
        
        # Calculate totals
        total_amount = (
            corrispettivo_data.total_cash +
            corrispettivo_data.total_card +
            corrispettivo_data.total_other
        )
        
        # Calculate expected balance and difference if applicable
        expected_balance = None
        difference = None
        
        if corrispettivo_data.opening_balance is not None:
            # Get cash movements for the day
            movements = await self.movement_repo.find_by_date(
                target_date=corrispettivo_data.date,
                user_id=user_id
            )
            
            cash_in = sum(
                m.get("amount", 0)
                for m in movements
                if m.get("type") == "entrata" and m.get("payment_method") == "contanti"
            )
            
            cash_out = sum(
                m.get("amount", 0)
                for m in movements
                if m.get("type") == "uscita"
            )
            
            expected_balance = (
                corrispettivo_data.opening_balance +
                cash_in -
                cash_out
            )
            
            if corrispettivo_data.closing_balance is not None:
                difference = corrispettivo_data.closing_balance - expected_balance
        
        corrispettivo_doc = corrispettivo_data.model_dump()
        corrispettivo_doc.update({
            "user_id": user_id,
            "date": corrispettivo_data.date.isoformat(),
            "total_amount": total_amount,
            "expected_balance": expected_balance,
            "difference": difference,
            "is_reconciled": False,
            "created_at": datetime.now(timezone.utc)
        })
        
        corrispettivo_id = await self.corrispettivo_repo.create(corrispettivo_doc)
        
        logger.info(f"✅ Corrispettivo created: {corrispettivo_id}")
        
        return corrispettivo_id
    
    async def get_corrispettivo(
        self,
        corrispettivo_date: date,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get corrispettivo for date.
        
        Args:
            corrispettivo_date: Date
            user_id: User ID
            
        Returns:
            Corrispettivo document or None
        """
        return await self.corrispettivo_repo.find_by_date(
            target_date=corrispettivo_date,
            user_id=user_id
        )
    
    async def list_corrispettivi(
        self,
        user_id: str,
        month: Optional[int] = None,
        year: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        """
        List corrispettivi with filters.
        
        Args:
            user_id: User ID
            month: Optional month filter
            year: Optional year filter
            start_date: Optional start date
            end_date: Optional end date
            
        Returns:
            List of corrispettivi
        """
        if month and year:
            return await self.corrispettivo_repo.find_by_month(
                month=month,
                year=year,
                user_id=user_id
            )
        
        if start_date and end_date:
            return await self.corrispettivo_repo.find_by_date_range(
                start_date=start_date,
                end_date=end_date,
                user_id=user_id
            )
        
        # All corrispettivi
        return await self.corrispettivo_repo.find_by_user(
            user_id=user_id,
            limit=1000
        )
