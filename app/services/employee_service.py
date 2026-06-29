"""
Employee service.
Business logic for employee management, payslips, and health booklets.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, date, timezone
import logging

from app.repositories.employee_repository import (
    EmployeeRepository,
    PayslipRepository,
    LibrettoSanitarioRepository
)
from app.exceptions import (
    NotFoundError,
    ValidationError,
    DuplicateError
)
from app.models.employee import (
    EmployeeCreate,
    EmployeeUpdate,
    PayslipCreate,
    LibrettoSanitarioCreate
)

logger = logging.getLogger(__name__)


class EmployeeService:
    """Service for employee operations."""
    
    def __init__(
        self,
        employee_repo: EmployeeRepository,
        payslip_repo: PayslipRepository,
        libretto_repo: LibrettoSanitarioRepository
    ):
        """
        Initialize employee service.
        
        Args:
            employee_repo: Employee repository instance
            payslip_repo: Payslip repository instance
            libretto_repo: Libretto sanitario repository instance
        """
        self.employee_repo = employee_repo
        self.payslip_repo = payslip_repo
        self.libretto_repo = libretto_repo
    
    def _validate_codice_fiscale(self, cf: str) -> str:
        """
        Validate and normalize codice fiscale.
        
        Args:
            cf: Codice fiscale
            
        Returns:
            Normalized codice fiscale (uppercase)
            
        Raises:
            ValidationError: If invalid format
        """
        cf_clean = cf.strip().upper()
        
        # Italian CF is 16 alphanumeric characters
        if len(cf_clean) != 16:
            raise ValidationError(
                "Codice fiscale must be exactly 16 characters",
                details={"codice_fiscale": cf, "length": len(cf_clean)}
            )
        
        if not cf_clean.isalnum():
            raise ValidationError(
                "Codice fiscale must be alphanumeric",
                details={"codice_fiscale": cf}
            )
        
        return cf_clean
    
    async def create_employee(
        self,
        employee_data: EmployeeCreate,
        user_id: str
    ) -> str:
        """
        Create a new employee.
        
        Args:
            employee_data: Employee creation data
            user_id: User ID
            
        Returns:
            Created employee ID
            
        Raises:
            ValidationError: If codice fiscale invalid
            DuplicateError: If codice fiscale already exists
        """
        logger.info(
            f"Creating employee: {employee_data.first_name} {employee_data.last_name}"
        )
        
        # Validate codice fiscale
        cf = self._validate_codice_fiscale(employee_data.codice_fiscale)
        
        # Prepare document
        employee_doc = employee_data.model_dump()
        employee_doc.update({
            "user_id": user_id,
            "codice_fiscale": cf,
            "full_name": f"{employee_data.first_name} {employee_data.last_name}",
            "is_active": True,
            "created_at": datetime.now(timezone.utc)
        })
        
        employee_id = await self.employee_repo.create_employee(employee_doc)
        
        logger.info(f"✅ Employee created: {employee_id}")
        
        return employee_id
    
    async def get_employee(
        self,
        employee_id: str
    ) -> Dict[str, Any]:
        """
        Get employee by ID.
        
        Args:
            employee_id: Employee ID
            
        Returns:
            Employee document
            
        Raises:
            NotFoundError: If employee not found
        """
        employee = await self.employee_repo.find_by_id(employee_id)
        
        if not employee:
            raise NotFoundError("Employee", employee_id)
        
        return employee
    
    async def list_employees(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100,
        active_only: bool = True,
        role: Optional[str] = None,
        search: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List employees with filters.
        
        Args:
            user_id: User ID
            skip: Pagination offset
            limit: Maximum results
            active_only: Only return active employees
            role: Filter by role
            search: Search query
            
        Returns:
            List of employees
        """
        if search:
            return await self.employee_repo.search_employees(
                user_id=user_id,
                query=search,
                skip=skip,
                limit=limit
            )
        
        if role:
            return await self.employee_repo.find_by_role(
                role=role,
                user_id=user_id,
                active_only=active_only
            )
        
        if active_only:
            return await self.employee_repo.find_active_employees(
                user_id=user_id,
                skip=skip,
                limit=limit
            )
        
        return await self.employee_repo.find_by_user(
            user_id=user_id,
            skip=skip,
            limit=limit
        )
    
    async def update_employee(
        self,
        employee_id: str,
        update_data: EmployeeUpdate
    ) -> bool:
        """
        Update employee.
        
        Args:
            employee_id: Employee ID
            update_data: Update data
            
        Returns:
            True if updated
            
        Raises:
            NotFoundError: If employee not found
        """
        logger.info(f"Updating employee: {employee_id}")
        
        # Verify exists
        employee = await self.get_employee(employee_id)
        
        update_dict = update_data.model_dump(exclude_unset=True)
        
        if not update_dict:
            return True
        
        # Update full_name if first/last name changed
        if "first_name" in update_dict or "last_name" in update_dict:
            first = update_dict.get("first_name", employee["first_name"])
            last = update_dict.get("last_name", employee["last_name"])
            update_dict["full_name"] = f"{first} {last}"
        
        update_dict["updated_at"] = datetime.now(timezone.utc)
        
        success = await self.employee_repo.update(employee_id, update_dict)
        
        logger.info(f"✅ Employee updated: {employee_id}")
        
        return success
    
    async def delete_employee(
        self,
        employee_id: str
    ) -> bool:
        """
        Soft delete employee (set inactive).
        
        Args:
            employee_id: Employee ID
            
        Returns:
            True if deleted
            
        Raises:
            NotFoundError: If employee not found
        """
        logger.warning(f"Deactivating employee: {employee_id}")
        
        # Verify exists
        await self.get_employee(employee_id)
        
        return await self.employee_repo.update(
            employee_id,
            {
                "is_active": False,
                "termination_date": date.today().isoformat(),
                "updated_at": datetime.now(timezone.utc)
            }
        )
    
    async def create_payslip(
        self,
        payslip_data: PayslipCreate,
        user_id: str
    ) -> str:
        """
        Create payslip record.
        
        Args:
            payslip_data: Payslip data
            user_id: User ID
            
        Returns:
            Created payslip ID
            
        Raises:
            NotFoundError: If employee not found
            ValidationError: If net > gross
        """
        logger.info(
            f"Creating payslip for employee {payslip_data.employee_id}, "
            f"period {payslip_data.period}"
        )
        
        # Verify employee exists
        await self.get_employee(payslip_data.employee_id)
        
        # Validate amounts
        if payslip_data.net_salary > payslip_data.gross_salary:
            raise ValidationError(
                "Net salary cannot be greater than gross salary",
                details={
                    "gross": payslip_data.gross_salary,
                    "net": payslip_data.net_salary
                }
            )
        
        # Check if payslip already exists for this period
        existing = await self.payslip_repo.find_by_employee_and_period(
            employee_id=payslip_data.employee_id,
            period=payslip_data.period,
            user_id=user_id
        )
        
        if existing:
            raise DuplicateError(
                "Payslip",
                "employee_period",
                f"{payslip_data.employee_id}_{payslip_data.period}"
            )
        
        payslip_doc = payslip_data.model_dump()
        payslip_doc.update({
            "user_id": user_id,
            "uploaded_at": datetime.now(timezone.utc)
        })
        
        payslip_id = await self.payslip_repo.create(payslip_doc)
        
        logger.info(f"✅ Payslip created: {payslip_id}")
        
        return payslip_id
    
    async def get_employee_payslips(
        self,
        employee_id: str,
        user_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get all payslips for employee.
        
        Args:
            employee_id: Employee ID
            user_id: User ID
            skip: Pagination offset
            limit: Maximum results
            
        Returns:
            List of payslips
            
        Raises:
            NotFoundError: If employee not found
        """
        # Verify employee exists
        await self.get_employee(employee_id)
        
        return await self.payslip_repo.find_by_employee(
            employee_id=employee_id,
            user_id=user_id,
            skip=skip,
            limit=limit
        )
    
    async def upsert_libretto_sanitario(
        self,
        employee_id: str,
        libretto_data: LibrettoSanitarioCreate,
        user_id: str
    ) -> str:
        """
        Create or update libretto sanitario.
        
        Args:
            employee_id: Employee ID
            libretto_data: Libretto data
            user_id: User ID
            
        Returns:
            Libretto ID (created or updated)
            
        Raises:
            NotFoundError: If employee not found
            ValidationError: If expiry before issue
        """
        logger.info(f"Upserting libretto for employee {employee_id}")
        
        # Verify employee exists
        await self.get_employee(employee_id)
        
        # Validate dates
        if libretto_data.expiry_date <= libretto_data.issue_date:
            raise ValidationError(
                "Expiry date must be after issue date",
                details={
                    "issue_date": libretto_data.issue_date,
                    "expiry_date": libretto_data.expiry_date
                }
            )
        
        # Check if exists
        existing = await self.libretto_repo.find_by_employee(employee_id, user_id)
        
        if existing:
            # Update
            update_dict = libretto_data.model_dump()
            update_dict["updated_at"] = datetime.now(timezone.utc)
            
            # Update status based on expiry
            if libretto_data.expiry_date < date.today():
                update_dict["status"] = "expired"
            else:
                update_dict["status"] = "valid"
            
            await self.libretto_repo.update(existing["id"], update_dict)
            
            logger.info(f"✅ Libretto updated: {existing['id']}")
            
            return existing["id"]
        else:
            # Create
            libretto_doc = libretto_data.model_dump()
            libretto_doc.update({
                "user_id": user_id,
                "employee_id": employee_id,
                "status": "valid" if libretto_data.expiry_date >= date.today() else "expired",
                "created_at": datetime.now(timezone.utc)
            })
            
            libretto_id = await self.libretto_repo.create(libretto_doc)
            
            logger.info(f"✅ Libretto created: {libretto_id}")
            
            return libretto_id
    
    async def get_libretto_sanitario(
        self,
        employee_id: str,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get libretto sanitario for employee.
        
        Args:
            employee_id: Employee ID
            user_id: User ID
            
        Returns:
            Libretto document or None
            
        Raises:
            NotFoundError: If employee not found
        """
        # Verify employee exists
        await self.get_employee(employee_id)
        
        return await self.libretto_repo.find_by_employee(employee_id, user_id)
    
    async def get_employee_stats(
        self,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Get employee statistics.
        
        Args:
            user_id: User ID
            
        Returns:
            Statistics dictionary
        """
        all_employees = await self.employee_repo.find_by_user(
            user_id=user_id,
            limit=10000
        )
        
        active = [e for e in all_employees if e.get("is_active", False)]
        inactive = [e for e in all_employees if not e.get("is_active", False)]
        
        # Group by role
        by_role = {}
        for emp in active:
            role = emp.get("role", "unknown")
            by_role[role] = by_role.get(role, 0) + 1
        
        # Recent hires (last 30 days)
        recent_hires = await self.employee_repo.get_recent_hires(user_id, days=30)
        
        # Expiring libretti
        expiring_libretti = await self.libretto_repo.find_expiring_soon(user_id, days=30)
        
        return {
            "total_employees": len(all_employees),
            "active_employees": len(active),
            "inactive_employees": len(inactive),
            "by_role": by_role,
            "recent_hires": len(recent_hires),
            "expiring_libretti": len(expiring_libretti)
        }
