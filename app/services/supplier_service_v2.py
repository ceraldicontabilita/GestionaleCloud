"""
Supplier service with referential integrity.
Enhanced version with cascade updates and delete prevention.
"""
from typing import Dict, Any
from datetime import datetime, timezone
import logging

from app.repositories import SupplierRepository, InvoiceRepository
from app.exceptions import NotFoundError, DuplicateError, ValidationError
from app.models import SupplierCreate, SupplierUpdate
from app.utils.referential_integrity import referential_integrity

logger = logging.getLogger(__name__)


class SupplierServiceV2:
    """
    Enhanced supplier service with referential integrity.
    
    Features:
    - Cascade updates when supplier name changes
    - Delete prevention when supplier has invoices
    - Force delete with cascade to related records
    """
    
    def __init__(
        self,
        supplier_repo: SupplierRepository,
        invoice_repo: InvoiceRepository
    ):
        self.supplier_repo = supplier_repo
        self.invoice_repo = invoice_repo
    
    def _validate_vat_number(self, vat_number: str) -> bool:
        """Validate Italian VAT number format (11 digits)."""
        if not vat_number:
            raise ValidationError("VAT number is required", "vat_number")
        
        # Remove spaces and common prefixes
        vat_clean = vat_number.replace(" ", "").replace("IT", "").replace("it", "")
        
        if not vat_clean.isdigit():
            raise ValidationError(
                "VAT number must contain only digits",
                "vat_number"
            )
        
        if len(vat_clean) != 11:
            raise ValidationError(
                "Italian VAT number must be 11 digits",
                "vat_number"
            )
        
        return True
    
    async def create_supplier(
        self,
        supplier_data: SupplierCreate,
        user_id: str
    ) -> str:
        """Create new supplier with validation."""
        logger.info(f"Creating supplier: {supplier_data.name}")
        
        # Validate VAT number
        self._validate_vat_number(supplier_data.vat_number)
        
        # Check for duplicate
        existing = await self.supplier_repo.find_by_vat_number(
            supplier_data.vat_number,
            user_id
        )
        
        if existing:
            raise DuplicateError("Supplier", "vat_number", supplier_data.vat_number)
        
        supplier_doc = supplier_data.model_dump()
        supplier_doc.update({
            "user_id": user_id,
            "is_active": True,
            "created_at": datetime.now(timezone.utc)
        })
        
        return await self.supplier_repo.create(supplier_doc)
    
    async def update_supplier(
        self,
        supplier_id: str,
        update_data: SupplierUpdate,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Update supplier with cascade to related documents.
        
        When supplier name changes, automatically updates:
        - All invoices with this supplier
        - All warehouse products from this supplier
        
        Returns dict with update results and cascade info.
        """
        logger.info(f"Updating supplier: {supplier_id}")
        
        # Get current supplier
        supplier = await self.supplier_repo.find_by_id(supplier_id)
        if not supplier:
            raise NotFoundError("Supplier", supplier_id)
        
        update_dict = update_data.model_dump(exclude_unset=True)
        if not update_dict:
            return {"message": "No changes"}
        
        update_dict["updated_at"] = datetime.now(timezone.utc)
        
        cascade_results = {}
        
        # Check if name is changing -> CASCADE UPDATE
        if "name" in update_dict and update_dict["name"] != supplier.get("name"):
            logger.info(
                f"Supplier name changing: '{supplier.get('name')}' -> '{update_dict['name']}'"
            )
            
            # Cascade update to related collections
            cascade_results = await referential_integrity.cascade_update(
                collection_name="suppliers",
                document_id=supplier_id,
                updates={"supplier_name": update_dict["name"]},
                user_id=user_id
            )
            
            logger.info(f"Cascaded updates: {cascade_results}")
        
        # Perform the supplier update
        await self.supplier_repo.update(supplier_id, update_dict)
        
        return {
            "message": "Supplier updated successfully",
            "supplier_id": supplier_id,
            "cascade_updates": cascade_results if cascade_results else None
        }
    
    async def delete_supplier(
        self,
        supplier_id: str,
        user_id: str,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Delete supplier with referential integrity check.
        
        PREVENTS deletion if supplier has:
        - Invoices
        - Warehouse products
        
        Unless force=True (cascade delete).
        
        Args:
            supplier_id: Supplier to delete
            user_id: User ID
            force: If True, cascade delete to related records
            
        Returns:
            Dict with deletion result
            
        Raises:
            ValidationError: If supplier has references and force=False
        """
        logger.info(f"Attempting to delete supplier: {supplier_id}")
        
        # CHECK REFERENTIAL INTEGRITY
        check_result = await referential_integrity.check_can_delete(
            collection_name="suppliers",
            document_id=supplier_id,
            user_id=user_id
        )
        
        if not check_result["can_delete"] and not force:
            # Get sample references for error message
            references = await referential_integrity.get_references(
                collection_name="suppliers",
                document_id=supplier_id,
                user_id=user_id,
                limit=5
            )
            
            raise ValidationError(
                f"❌ Cannot delete supplier: {check_result['total_count']} "
                f"related records found. "
                f"Set force=true to cascade delete.",
                "supplier_id",
                metadata={
                    "can_delete": False,
                    "references": check_result["references"],
                    "sample_records": references,
                    "suggestion": "Use DELETE with ?force=true to cascade delete"
                }
            )
        
        cascade_results = {}
        
        # FORCE DELETE with CASCADE
        if force and not check_result["can_delete"]:
            logger.warning(
                f"🔥 Force deleting supplier {supplier_id} with {check_result['total_count']} references"
            )
            
            cascade_results = await referential_integrity.cascade_delete(
                collection_name="suppliers",
                document_id=supplier_id,
                user_id=user_id,
                force=True
            )
            
            logger.warning(f"Cascade deleted: {cascade_results}")
        
        # Soft delete supplier
        await self.supplier_repo.update(
            supplier_id,
            {
                "is_active": False,
                "deleted_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc)
            }
        )
        
        return {
            "message": "Supplier deleted successfully",
            "supplier_id": supplier_id,
            "was_forced": force,
            "cascade_deletes": cascade_results if cascade_results else None
        }
    
    async def get_supplier_references(
        self,
        supplier_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Get all references to this supplier.
        
        Useful for showing user what will be affected before delete/update.
        """
        check_result = await referential_integrity.check_can_delete(
            collection_name="suppliers",
            document_id=supplier_id,
            user_id=user_id
        )
        
        references = await referential_integrity.get_references(
            collection_name="suppliers",
            document_id=supplier_id,
            user_id=user_id,
            limit=10
        )
        
        return {
            "supplier_id": supplier_id,
            "can_delete": check_result["can_delete"],
            "total_references": check_result["total_count"],
            "references_by_collection": check_result["references"],
            "sample_records": references
        }
