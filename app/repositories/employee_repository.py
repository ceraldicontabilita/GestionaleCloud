"""
Employee repository.
Data access layer for employee operations.
"""
from typing import List, Dict, Any, Optional
from datetime import date, timedelta
import logging

from .base_repository import BaseRepository
from app.exceptions import DuplicateError

logger = logging.getLogger(__name__)


class EmployeeRepository(BaseRepository):
    """Repository for employee operations."""
    
    async def find_by_codice_fiscale(
        self,
        codice_fiscale: str,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Find employee by codice fiscale.
        
        Args:
            codice_fiscale: Italian tax code
            user_id: User ID
            
        Returns:
            Employee document or None
        """
        return await self.find_one({
            "user_id": user_id,
            "codice_fiscale": codice_fiscale.upper()
        })
    
    async def codice_fiscale_exists(
        self,
        codice_fiscale: str,
        user_id: str,
        exclude_id: Optional[str] = None
    ) -> bool:
        """
        Check if codice fiscale exists.
        
        Args:
            codice_fiscale: Italian tax code
            user_id: User ID
            exclude_id: Optional employee ID to exclude from check
            
        Returns:
            True if exists
        """
        query = {
            "user_id": user_id,
            "codice_fiscale": codice_fiscale.upper()
        }
        
        if exclude_id:
            query["_id"] = {"$ne": exclude_id}
        
        employee = await self.find_one(query)
        return employee is not None
    
    async def create_employee(
        self,
        employee_data: Dict[str, Any]
    ) -> str:
        """
        Create employee with duplicate check.
        
        Args:
            employee_data: Employee data
            
        Returns:
            Created employee ID
            
        Raises:
            DuplicateError: If codice fiscale already exists
        """
        cf = employee_data.get("codice_fiscale", "").upper()
        user_id = employee_data.get("user_id")
        
        logger.info(f"Creating employee with CF: {cf}")
        
        if await self.codice_fiscale_exists(cf, user_id):
            raise DuplicateError("Employee", "codice_fiscale", cf)
        
        # Normalize codice fiscale
        employee_data["codice_fiscale"] = cf
        
        # Generate full_name
        employee_data["full_name"] = (
            f"{employee_data['first_name']} {employee_data['last_name']}"
        )
        
        return await self.create(employee_data)
    
    async def find_active_employees(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Find active employees.
        
        Args:
            user_id: User ID
            skip: Number to skip
            limit: Maximum to return
            
        Returns:
            List of active employees
        """
        return await self.find_all(
            filter_query={
                "user_id": user_id,
                "is_active": True
            },
            skip=skip,
            limit=limit,
            sort=[("last_name", 1), ("first_name", 1)]
        )
    
    async def search_employees(
        self,
        user_id: str,
        query: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Search employees by name or codice fiscale.
        
        Args:
            user_id: User ID
            query: Search query
            skip: Number to skip
            limit: Maximum to return
            
        Returns:
            List of matching employees
        """
        return await self.find_all(
            filter_query={
                "user_id": user_id,
                "$or": [
                    {"full_name": {"$regex": query, "$options": "i"}},
                    {"first_name": {"$regex": query, "$options": "i"}},
                    {"last_name": {"$regex": query, "$options": "i"}},
                    {"codice_fiscale": {"$regex": query, "$options": "i"}}
                ]
            },
            skip=skip,
            limit=limit,
            sort=[("last_name", 1)]
        )
    
    async def find_by_role(
        self,
        role: str,
        user_id: str,
        active_only: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Find employees by role.
        
        Args:
            role: Job role
            user_id: User ID
            active_only: Only return active employees
            
        Returns:
            List of employees
        """
        filter_query = {
            "user_id": user_id,
            "role": role
        }
        
        if active_only:
            filter_query["is_active"] = True
        
        return await self.find_all(
            filter_query=filter_query,
            sort=[("last_name", 1)]
        )
    
    async def get_recent_hires(
        self,
        user_id: str,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get employees hired in the last N days.
        
        Args:
            user_id: User ID
            days: Number of days to look back
            
        Returns:
            List of recent hires
        """
        cutoff_date = date.today() - timedelta(days=days)
        
        return await self.find_all(
            filter_query={
                "user_id": user_id,
                "hire_date": {"$gte": cutoff_date.isoformat()}
            },
            sort=[("hire_date", -1)]
        )


class PayslipRepository(BaseRepository):
    """Repository for payslip operations."""
    
    async def find_by_employee(
        self,
        employee_id: str,
        user_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Find payslips for employee.
        
        Args:
            employee_id: Employee ID
            user_id: User ID
            skip: Number to skip
            limit: Maximum to return
            
        Returns:
            List of payslips
        """
        return await self.find_all(
            filter_query={
                "user_id": user_id,
                "employee_id": employee_id
            },
            skip=skip,
            limit=limit,
            sort=[("year", -1), ("month", -1)]
        )
    
    async def find_by_period(
        self,
        period: str,
        user_id: str
    ) -> List[Dict[str, Any]]:
        """
        Find payslips by period (MM-YYYY).
        
        Args:
            period: Period string (e.g., "12-2024")
            user_id: User ID
            
        Returns:
            List of payslips
        """
        return await self.find_all(
            filter_query={
                "user_id": user_id,
                "period": period
            },
            sort=[("employee_id", 1)]
        )
    
    async def find_by_employee_and_period(
        self,
        employee_id: str,
        period: str,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Find payslip for specific employee and period.
        
        Args:
            employee_id: Employee ID
            period: Period string (e.g., "12-2024")
            user_id: User ID
            
        Returns:
            Payslip document or None
        """
        return await self.find_one({
            "user_id": user_id,
            "employee_id": employee_id,
            "period": period
        })
    
    async def get_total_payroll(
        self,
        month: int,
        year: int,
        user_id: str
    ) -> float:
        """
        Calculate total payroll for a month.
        
        Args:
            month: Month (1-12)
            year: Year
            user_id: User ID
            
        Returns:
            Total net salary
        """
        period = f"{month:02d}-{year}"
        
        payslips = await self.find_by_period(period, user_id)
        
        return sum(p.get("net_salary", 0) for p in payslips)


class LibrettoSanitarioRepository(BaseRepository):
    """Repository for libretto sanitario operations."""
    
    async def find_by_employee(
        self,
        employee_id: str,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Find libretto for employee (should be unique).
        
        Args:
            employee_id: Employee ID
            user_id: User ID
            
        Returns:
            Libretto document or None
        """
        return await self.find_one({
            "user_id": user_id,
            "employee_id": employee_id
        })
    
    async def find_expiring_soon(
        self,
        user_id: str,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Find libretti expiring in the next N days.
        
        Args:
            user_id: User ID
            days: Number of days to look ahead
            
        Returns:
            List of expiring libretti
        """
        today = date.today()
        cutoff_date = today + timedelta(days=days)
        
        return await self.find_all(
            filter_query={
                "user_id": user_id,
                "expiry_date": {
                    "$gte": today.isoformat(),
                    "$lte": cutoff_date.isoformat()
                },
                "status": "valid"
            },
            sort=[("expiry_date", 1)]
        )
    
    async def find_expired(
        self,
        user_id: str
    ) -> List[Dict[str, Any]]:
        """
        Find expired libretti.
        
        Args:
            user_id: User ID
            
        Returns:
            List of expired libretti
        """
        today = date.today()
        
        return await self.find_all(
            filter_query={
                "user_id": user_id,
                "expiry_date": {"$lt": today.isoformat()},
                "status": "valid"  # Still marked as valid but actually expired
            },
            sort=[("expiry_date", 1)]
        )
