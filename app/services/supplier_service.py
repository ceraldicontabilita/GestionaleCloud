"""
DEPRECATO — Usare supplier_service_v2.py

Mantenuto per retrocompatibilità. Non aggiungere nuove funzionalità qui.
Per nuove implementazioni: from app.services.supplier_service_v2 import SupplierServiceV2
"""
"""
Supplier service.
Handles supplier management and business logic.
"""
from typing import Dict, Any, List, Optional
import logging

from app.repositories import SupplierRepository, InvoiceRepository
from app.exceptions import (
    NotFoundError,
    ValidationError
)
from app.models import SupplierCreate, SupplierUpdate

logger = logging.getLogger(__name__)


class SupplierService:
    """Service for supplier operations."""
    
    def __init__(
        self,
        supplier_repo: SupplierRepository,
        invoice_repo: InvoiceRepository
    ):
        """
        Initialize supplier service.
        
        Args:
            supplier_repo: Supplier repository instance
            invoice_repo: Invoice repository instance
        """
        self.supplier_repo = supplier_repo
        self.invoice_repo = invoice_repo
    
    def _validate_vat_number(self, vat_number: str) -> bool:
        """
        Validate Italian VAT number format.
        
        Args:
            vat_number: VAT number to validate
            
        Returns:
            True if valid
            
        Raises:
            ValidationError: If VAT format is invalid
        """
        # Remove spaces and convert to uppercase
        vat = vat_number.strip().upper()
        
        # Check if starts with IT (Italian VAT)
        if vat.startswith("IT"):
            vat = vat[2:]
        
        # Must be 11 digits
        if not vat.isdigit() or len(vat) != 11:
            raise ValidationError(
                f"Invalid VAT number format: {vat_number}. Must be 11 digits.",
                details={"vat_number": vat_number}
            )
        
        return True
    
    async def create_supplier(
        self,
        supplier_data: SupplierCreate,
        user_id: str
    ) -> str:
        """
        Create a new supplier.
        
        Args:
            supplier_data: Supplier creation data
            user_id: User ID
            
        Returns:
            Created supplier ID
            
        Raises:
            DuplicateError: If VAT number already exists
            ValidationError: If data is invalid
        """
        logger.info(f"Creating supplier: {supplier_data.name} ({supplier_data.vat_number})")
        
        # Validate VAT number
        self._validate_vat_number(supplier_data.vat_number)
        
        # Create supplier document
        supplier_doc = supplier_data.model_dump()
        supplier_doc["user_id"] = user_id
        
        # Save supplier
        supplier_id = await self.supplier_repo.create_supplier(supplier_doc)
        
        logger.info(f"✅ Supplier created: {supplier_id}")
        return supplier_id
    
    async def get_supplier(self, supplier_id: str) -> Dict[str, Any]:
        """
        Get supplier by ID.
        
        Args:
            supplier_id: Supplier ID
            
        Returns:
            Supplier document
            
        Raises:
            NotFoundError: If supplier not found
        """
        supplier = await self.supplier_repo.find_by_id(supplier_id)
        
        if not supplier:
            raise NotFoundError("Supplier", supplier_id)
        
        return supplier
    
    async def get_supplier_by_vat(self, vat_number: str) -> Optional[Dict[str, Any]]:
        """
        Get supplier by VAT number.
        
        Args:
            vat_number: Supplier VAT number
            
        Returns:
            Supplier document or None if not found
        """
        return await self.supplier_repo.find_by_vat(vat_number)
    
    async def update_supplier(
        self,
        supplier_id: str,
        update_data: SupplierUpdate
    ) -> bool:
        """
        Update supplier.
        
        Args:
            supplier_id: Supplier ID
            update_data: Update data
            
        Returns:
            True if updated successfully
            
        Raises:
            NotFoundError: If supplier not found
        """
        logger.info(f"Updating supplier: {supplier_id}")
        
        # Verify supplier exists
        await self.get_supplier(supplier_id)
        
        # Update only provided fields
        update_dict = update_data.model_dump(exclude_unset=True)
        
        if not update_dict:
            return True  # Nothing to update
        
        success = await self.supplier_repo.update(supplier_id, update_dict)
        
        if success:
            logger.info(f"✅ Supplier updated: {supplier_id}")
        
        return success
    
    async def upsert_supplier(
        self,
        supplier_data: SupplierCreate,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Create supplier if not exists, otherwise update.
        Useful for automatic supplier creation from invoices.
        
        Args:
            supplier_data: Supplier data
            user_id: User ID
            
        Returns:
            Supplier document with 'created' flag
        """
        logger.info(f"Upserting supplier: {supplier_data.vat_number}")
        
        # Validate VAT
        self._validate_vat_number(supplier_data.vat_number)
        
        # Check if exists
        existing = await self.get_supplier_by_vat(supplier_data.vat_number)
        
        if existing:
            # Update existing
            update_data = SupplierUpdate(**supplier_data.model_dump(exclude={"vat_number"}))
            await self.update_supplier(existing["id"], update_data)
            
            logger.info(f"✅ Supplier updated (upsert): {existing['id']}")
            
            return {
                **existing,
                "created": False
            }
        else:
            # Create new
            supplier_doc = supplier_data.model_dump()
            supplier_doc["user_id"] = user_id
            
            supplier_id = await self.supplier_repo.create_supplier(supplier_doc)
            supplier = await self.get_supplier(supplier_id)
            
            logger.info(f"✅ Supplier created (upsert): {supplier_id}")
            
            return {
                **supplier,
                "created": True
            }
    
    async def list_suppliers(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100,
        active_only: bool = True,
        payment_method: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List suppliers with optional filters.
        
        Args:
            user_id: User ID
            skip: Number to skip (pagination)
            limit: Maximum number to return
            active_only: Only return active suppliers
            payment_method: Filter by payment method
            
        Returns:
            List of suppliers
        """
        if payment_method:
            return await self.supplier_repo.find_by_payment_method(
                payment_method=payment_method,
                user_id=user_id,
                skip=skip,
                limit=limit
            )
        
        if active_only:
            return await self.supplier_repo.find_active_suppliers(
                user_id=user_id,
                skip=skip,
                limit=limit
            )
        
        # All suppliers
        return await self.supplier_repo.find_by_user(
            user_id=user_id,
            skip=skip,
            limit=limit
        )
    
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
            skip: Number to skip
            limit: Maximum number to return
            
        Returns:
            List of matching suppliers
        """
        return await self.supplier_repo.search_suppliers(
            user_id=user_id,
            query=query,
            skip=skip,
            limit=limit
        )
    
    async def get_supplier_stats(self, user_id: str) -> Dict[str, Any]:
        """
        Get supplier statistics.
        
        Args:
            user_id: User ID
            
        Returns:
            Statistics dictionary
        """
        all_suppliers = await self.supplier_repo.find_by_user(
            user_id=user_id,
            limit=10000
        )
        
        total = len(all_suppliers)
        active = len([s for s in all_suppliers if s.get("is_active", True)])
        
        # Calculate totals
        total_invoices = sum(s.get("total_invoices", 0) for s in all_suppliers)
        total_amount = sum(s.get("total_amount", 0.0) for s in all_suppliers)
        
        # Count by payment method
        by_payment = {}
        for supplier in all_suppliers:
            method = supplier.get("payment_method", "unknown")
            by_payment[method] = by_payment.get(method, 0) + 1
        
        # Get top 10 suppliers by amount
        top_suppliers = sorted(
            all_suppliers,
            key=lambda s: s.get("total_amount", 0),
            reverse=True
        )[:10]
        
        return {
            "total_suppliers": total,
            "active_suppliers": active,
            "total_invoices": total_invoices,
            "total_amount": total_amount,
            "by_payment_method": by_payment,
            "top_suppliers": top_suppliers
        }
    
    async def get_supplier_invoices(
        self,
        supplier_vat: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get all invoices for a supplier.
        
        Args:
            supplier_vat: Supplier VAT number
            skip: Number to skip
            limit: Maximum number to return
            
        Returns:
            List of invoices
        """
        return await self.invoice_repo.find_by_supplier(
            supplier_vat=supplier_vat,
            skip=skip,
            limit=limit
        )
    
    async def get_supplier_summary(
        self,
        supplier_id: str
    ) -> Dict[str, Any]:
        """
        Get comprehensive supplier summary with invoices.
        
        Args:
            supplier_id: Supplier ID
            
        Returns:
            Supplier data with invoice summary
        """
        supplier = await self.get_supplier(supplier_id)
        
        # Get recent invoices
        invoices = await self.get_supplier_invoices(
            supplier_vat=supplier["vat_number"],
            limit=10
        )
        
        # Calculate stats
        total_unpaid = sum(
            inv.get("total_amount", 0) - inv.get("amount_paid", 0)
            for inv in invoices
            if inv.get("payment_status") != "paid"
        )
        
        return {
            **supplier,
            "recent_invoices": invoices,
            "invoice_count": supplier.get("total_invoices", 0),
            "total_amount": supplier.get("total_amount", 0.0),
            "total_unpaid": total_unpaid,
            "last_invoice_date": supplier.get("last_invoice_date")
        }
    
    async def deactivate_supplier(self, supplier_id: str) -> bool:
        """
        Deactivate a supplier.
        
        Args:
            supplier_id: Supplier ID
            
        Returns:
            True if deactivated successfully
        """
        logger.warning(f"Deactivating supplier: {supplier_id}")
        
        # Verify exists
        await self.get_supplier(supplier_id)
        
        return await self.supplier_repo.deactivate_supplier(supplier_id)
    
    async def activate_supplier(self, supplier_id: str) -> bool:
        """
        Activate a supplier.
        
        Args:
            supplier_id: Supplier ID
            
        Returns:
            True if activated successfully
        """
        logger.info(f"Activating supplier: {supplier_id}")
        
        # Verify exists
        await self.get_supplier(supplier_id)
        
        return await self.supplier_repo.activate_supplier(supplier_id)
    
    async def get_top_suppliers(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get top suppliers by total amount.
        
        Args:
            user_id: User ID
            limit: Number of suppliers to return
            
        Returns:
            List of top suppliers
        """
        return await self.supplier_repo.get_top_suppliers(
            user_id=user_id,
            limit=limit
        )
