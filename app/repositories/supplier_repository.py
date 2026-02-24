"""
Supplier repository for supplier management.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

from .base_repository import BaseRepository
from app.exceptions import DuplicateError

logger = logging.getLogger(__name__)


class SupplierRepository(BaseRepository):
    """Repository for supplier operations."""
    
    async def find_by_vat(self, vat_number: str) -> Optional[Dict[str, Any]]:
        """
        Find supplier by VAT number.
        
        Args:
            vat_number: Supplier VAT number
            
        Returns:
            Supplier document or None if not found
        """
        return await self.find_one({"vat_number": vat_number})
    
    async def vat_exists(self, vat_number: str) -> bool:
        """
        Check if VAT number exists.
        
        Args:
            vat_number: VAT number to check
            
        Returns:
            True if exists, False otherwise
        """
        return await self.exists({"vat_number": vat_number})
    
    async def create_supplier(self, supplier_data: Dict[str, Any]) -> str:
        """
        Create a new supplier.
        
        Args:
            supplier_data: Supplier data
            
        Returns:
            Created supplier ID
            
        Raises:
            DuplicateError: If VAT number already exists
        """
        vat_number = supplier_data["vat_number"]
        
        # Check for duplicate VAT
        if await self.vat_exists(vat_number):
            raise DuplicateError("Supplier", "vat_number", vat_number)
        
        # Initialize statistics
        supplier_data.setdefault("total_invoices", 0)
        supplier_data.setdefault("total_amount", 0.0)
        supplier_data.setdefault("last_invoice_date", None)
        supplier_data.setdefault("is_active", True)
        
        logger.info(f"Creating new supplier: {supplier_data.get('name', vat_number)}")
        return await self.create(supplier_data)
    
    async def upsert_supplier(self, supplier_data: Dict[str, Any]) -> str:
        """
        Create supplier if not exists, otherwise update.
        
        Args:
            supplier_data: Supplier data
            
        Returns:
            Supplier ID (existing or newly created)
        """
        vat_number = supplier_data["vat_number"]
        
        # Try to find existing supplier
        existing = await self.find_by_vat(vat_number)
        
        if existing:
            # Update existing supplier
            update_data = {k: v for k, v in supplier_data.items() if k != "vat_number"}
            await self.update(existing["id"], update_data)
            logger.info(f"Updated existing supplier: {vat_number}")
            return existing["id"]
        else:
            # Create new supplier
            logger.info(f"Creating new supplier: {vat_number}")
            return await self.create_supplier(supplier_data)
    
    async def find_active_suppliers(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Find all active suppliers.
        
        Args:
            user_id: User ID
            skip: Number of suppliers to skip
            limit: Maximum number of suppliers to return
            
        Returns:
            List of active suppliers
        """
        return await self.find_all(
            filter_query={"user_id": user_id, "is_active": True},
            skip=skip,
            limit=limit,
            sort=[("name", 1)]
        )
    
    async def find_by_payment_method(
        self,
        payment_method: str,
        user_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Find suppliers by payment method.
        
        Args:
            payment_method: Payment method (cassa, banca, etc.)
            user_id: User ID
            skip: Number of suppliers to skip
            limit: Maximum number of suppliers to return
            
        Returns:
            List of suppliers
        """
        return await self.find_all(
            filter_query={
                "user_id": user_id,
                "payment_method": payment_method,
                "is_active": True
            },
            skip=skip,
            limit=limit,
            sort=[("name", 1)]
        )
    
    async def update_statistics(
        self,
        supplier_vat: str,
        invoice_amount: float,
        invoice_date: datetime
    ) -> bool:
        """
        Update supplier statistics after adding an invoice.
        
        Args:
            supplier_vat: Supplier VAT number
            invoice_amount: Invoice amount
            invoice_date: Invoice date
            
        Returns:
            True if updated successfully
        """
        supplier = await self.find_by_vat(supplier_vat)
        if not supplier:
            logger.warning(f"Supplier not found for statistics update: {supplier_vat}")
            return False
        
        # Increment counters
        total_invoices = supplier.get("total_invoices", 0) + 1
        total_amount = supplier.get("total_amount", 0.0) + invoice_amount
        
        # Update last invoice date
        last_date = supplier.get("last_invoice_date")
        if not last_date or invoice_date > last_date:
            last_date = invoice_date
        
        update_data = {
            "total_invoices": total_invoices,
            "total_amount": total_amount,
            "last_invoice_date": last_date
        }
        
        logger.debug(f"Updating statistics for supplier {supplier_vat}: {total_invoices} invoices, €{total_amount:.2f}")
        return await self.update(supplier["id"], update_data)
    
    async def search_suppliers(
        self,
        user_id: str,
        query: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Search suppliers by name or VAT number.
        
        Args:
            user_id: User ID
            query: Search query
            skip: Number of suppliers to skip
            limit: Maximum number of suppliers to return
            
        Returns:
            List of matching suppliers
        """
        filter_query = {
            "user_id": user_id,
            "$or": [
                {"name": {"$regex": query, "$options": "i"}},
                {"vat_number": {"$regex": query, "$options": "i"}}
            ]
        }
        
        return await self.find_all(
            filter_query=filter_query,
            skip=skip,
            limit=limit,
            sort=[("name", 1)]
        )
    
    async def get_top_suppliers(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get top suppliers by total amount.
        
        Args:
            user_id: User ID
            limit: Number of top suppliers to return
            
        Returns:
            List of top suppliers sorted by total amount
        """
        return await self.find_all(
            filter_query={"user_id": user_id, "is_active": True},
            skip=0,
            limit=limit,
            sort=[("total_amount", -1)]
        )
    
    async def deactivate_supplier(self, supplier_id: str) -> bool:
        """
        Deactivate a supplier.
        
        Args:
            supplier_id: Supplier ID
            
        Returns:
            True if deactivated successfully
        """
        logger.warning(f"Deactivating supplier: {supplier_id}")
        return await self.update(supplier_id, {"is_active": False})
    
    async def activate_supplier(self, supplier_id: str) -> bool:
        """
        Activate a supplier.
        
        Args:
            supplier_id: Supplier ID
            
        Returns:
            True if activated successfully
        """
        logger.info(f"Activating supplier: {supplier_id}")
        return await self.update(supplier_id, {"is_active": True})
    
    async def count_active_suppliers(self, user_id: str) -> int:
        """
        Count active suppliers for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            Number of active suppliers
        """
        return await self.count({"user_id": user_id, "is_active": True})
