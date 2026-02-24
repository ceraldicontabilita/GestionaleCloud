"""
Temperature repository.
Data access layer for HACCP temperature monitoring.
"""
from typing import List, Dict, Any, Optional
from datetime import date
import logging

from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class TemperatureRepository(BaseRepository):
    """Repository for temperature operations."""
    
    async def find_by_date_range(
        self,
        start_date: date,
        end_date: date,
        user_id: str,
        equipment_type: Optional[str] = None,
        skip: int = 0,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Find temperatures within date range.
        
        Args:
            start_date: Start date
            end_date: End date
            user_id: User ID
            equipment_type: Optional equipment type filter
            skip: Number to skip
            limit: Maximum number to return
            
        Returns:
            List of temperature records
        """
        filter_query = {
            "user_id": user_id,
            "reading_date": {
                "$gte": start_date.isoformat(),
                "$lte": end_date.isoformat()
            }
        }
        
        if equipment_type:
            filter_query["equipment_type"] = equipment_type
        
        logger.info(
            f"Finding temperatures from {start_date} to {end_date} "
            f"for user {user_id}, equipment: {equipment_type or 'all'}"
        )
        
        return await self.find_all(
            filter_query=filter_query,
            skip=skip,
            limit=limit,
            sort=[("reading_date", -1), ("reading_time", -1)]
        )
    
    async def find_by_date(
        self,
        target_date: date,
        user_id: str,
        equipment_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Find temperatures for a specific date.
        
        Args:
            target_date: Target date
            user_id: User ID
            equipment_type: Optional equipment type filter
            
        Returns:
            List of temperature records
        """
        filter_query = {
            "user_id": user_id,
            "reading_date": target_date.isoformat()
        }
        
        if equipment_type:
            filter_query["equipment_type"] = equipment_type
        
        return await self.find_all(
            filter_query=filter_query,
            sort=[("reading_time", 1)]
        )
    
    async def find_by_equipment(
        self,
        equipment_type: str,
        user_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Find temperatures by equipment type.
        
        Args:
            equipment_type: Equipment type
            user_id: User ID
            skip: Number to skip
            limit: Maximum number to return
            
        Returns:
            List of temperature records
        """
        return await self.find_all(
            filter_query={
                "user_id": user_id,
                "equipment_type": equipment_type
            },
            skip=skip,
            limit=limit,
            sort=[("reading_date", -1), ("reading_time", -1)]
        )
    
    async def delete_by_day(
        self,
        target_date: date,
        equipment_type: str,
        user_id: str
    ) -> int:
        """
        Delete all temperatures for a specific day and equipment.
        
        Args:
            target_date: Target date
            equipment_type: Equipment type
            user_id: User ID
            
        Returns:
            Number of deleted records
        """
        logger.warning(
            f"Deleting temperatures for {target_date}, "
            f"equipment: {equipment_type}, user: {user_id}"
        )
        
        return await self.delete_many({
            "user_id": user_id,
            "reading_date": target_date.isoformat(),
            "equipment_type": equipment_type
        })
    
    async def delete_by_month(
        self,
        month: int,
        year: int,
        equipment_type: str,
        user_id: str
    ) -> int:
        """
        Delete all temperatures for a month and equipment.
        
        Args:
            month: Month (1-12)
            year: Year
            equipment_type: Equipment type
            user_id: User ID
            
        Returns:
            Number of deleted records
        """
        # Create regex pattern for month-year (e.g., "2024-01-")
        date_prefix = f"{year:04d}-{month:02d}-"
        
        logger.warning(
            f"Deleting temperatures for {month:02d}/{year}, "
            f"equipment: {equipment_type}, user: {user_id}"
        )
        
        return await self.delete_many({
            "user_id": user_id,
            "reading_date": {"$regex": f"^{date_prefix}"},
            "equipment_type": equipment_type
        })
    
    async def get_non_compliant(
        self,
        user_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get non-compliant temperature readings.
        
        Args:
            user_id: User ID
            start_date: Optional start date filter
            end_date: Optional end date filter
            skip: Number to skip
            limit: Maximum number to return
            
        Returns:
            List of non-compliant records
        """
        filter_query = {
            "user_id": user_id,
            "is_compliant": False
        }
        
        if start_date and end_date:
            filter_query["reading_date"] = {
                "$gte": start_date.isoformat(),
                "$lte": end_date.isoformat()
            }
        
        return await self.find_all(
            filter_query=filter_query,
            skip=skip,
            limit=limit,
            sort=[("reading_date", -1), ("reading_time", -1)]
        )
    
    async def count_by_compliance(
        self,
        user_id: str,
        start_date: date,
        end_date: date
    ) -> Dict[str, int]:
        """
        Count temperatures by compliance status.
        
        Args:
            user_id: User ID
            start_date: Start date
            end_date: End date
            
        Returns:
            Dictionary with compliant and non_compliant counts
        """
        all_temps = await self.find_by_date_range(
            start_date=start_date,
            end_date=end_date,
            user_id=user_id,
            limit=10000
        )
        
        compliant = sum(1 for t in all_temps if t.get("is_compliant", True))
        non_compliant = len(all_temps) - compliant
        
        return {
            "total": len(all_temps),
            "compliant": compliant,
            "non_compliant": non_compliant
        }


class EquipmentRepository(BaseRepository):
    """Repository for equipment operations."""
    
    async def find_by_type(
        self,
        equipment_type: str,
        user_id: str,
        active_only: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Find equipment by type.
        
        Args:
            equipment_type: Equipment type
            user_id: User ID
            active_only: Only return active equipment
            
        Returns:
            List of equipment records
        """
        filter_query = {
            "user_id": user_id,
            "type": equipment_type
        }
        
        if active_only:
            filter_query["is_active"] = True
        
        return await self.find_all(filter_query=filter_query)
    
    async def find_active_equipment(
        self,
        user_id: str
    ) -> List[Dict[str, Any]]:
        """
        Find all active equipment.
        
        Args:
            user_id: User ID
            
        Returns:
            List of active equipment
        """
        return await self.find_all(
            filter_query={
                "user_id": user_id,
                "is_active": True
            },
            sort=[("type", 1), ("name", 1)]
        )
