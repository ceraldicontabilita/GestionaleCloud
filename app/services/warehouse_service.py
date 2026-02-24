"""
Warehouse service.
Handles inventory management and stock movements.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import logging

from app.repositories import (
    WarehouseRepository,
    WarehouseMovementRepository,
    InvoiceRepository
)
from app.exceptions import (
    NotFoundError,
    ValidationError,
    BusinessLogicError
)

logger = logging.getLogger(__name__)


class WarehouseService:
    """Service for warehouse operations."""
    
    def __init__(
        self,
        warehouse_repo: WarehouseRepository,
        movement_repo: WarehouseMovementRepository,
        invoice_repo: InvoiceRepository
    ):
        """
        Initialize warehouse service.
        
        Args:
            warehouse_repo: Warehouse repository instance
            movement_repo: Movement repository instance
            invoice_repo: Invoice repository instance
        """
        self.warehouse_repo = warehouse_repo
        self.movement_repo = movement_repo
        self.invoice_repo = invoice_repo
    
    async def add_stock_from_invoice(
        self,
        invoice_id: str,
        user_id: str
    ) -> List[str]:
        """
        Add stock to warehouse from invoice products.
        Creates products if they don't exist and records movements.
        
        Args:
            invoice_id: Invoice ID
            user_id: User ID
            
        Returns:
            List of created movement IDs
            
        Raises:
            NotFoundError: If invoice not found
        """
        logger.info(f"Adding stock from invoice: {invoice_id}")
        
        # Get invoice
        invoice = await self.invoice_repo.find_by_id(invoice_id)
        if not invoice:
            raise NotFoundError("Invoice", invoice_id)
        
        movement_ids = []
        
        # Process each product in invoice
        for product in invoice.get("products", []):
            descrizione = product["descrizione"]
            quantita = product["quantita"]
            prezzo_unitario = product["prezzo_unitario"]
            unita_misura = product.get("unita_misura", "PZ")
            
            # Find or create warehouse product
            warehouse_product = await self.warehouse_repo.find_by_product_name(
                product_name=descrizione,
                user_id=user_id
            )
            
            if not warehouse_product:
                # Create new warehouse product
                product_doc = {
                    "user_id": user_id,
                    "product_name": descrizione,
                    "product_description": descrizione,
                    "unit_of_measure": unita_misura,
                    "quantity_purchased": quantita,
                    "quantity_used": 0.0,
                    "quantity_available": quantita,
                    "supplier_vat": invoice["supplier_vat"],
                    "supplier_name": invoice["supplier_name"],
                    "unit_price_avg": prezzo_unitario,
                    "unit_price_min": prezzo_unitario,
                    "unit_price_max": prezzo_unitario,
                    "last_purchase_price": prezzo_unitario,
                    "last_purchase_date": invoice["invoice_date"],
                    "is_active": True
                }
                
                product_id = await self.warehouse_repo.create(product_doc)
                quantity_before = 0.0
                logger.info(f"Created new warehouse product: {product_id}")
            else:
                # Update existing product stock
                product_id = warehouse_product["id"]
                quantity_before = warehouse_product.get("quantity_available", 0.0)
                
                await self.warehouse_repo.update_stock(
                    product_id=product_id,
                    quantity_change=quantita,
                    movement_type="carico"
                )
                
                await self.warehouse_repo.update_pricing(
                    product_id=product_id,
                    unit_price=prezzo_unitario
                )
            
            # Create movement record
            movement_doc = {
                "user_id": user_id,
                "product_id": product_id,
                "product_name": descrizione,
                "movement_type": "carico",
                "quantity": quantita,
                "unit_of_measure": unita_misura,
                "unit_price": prezzo_unitario,
                "total_value": quantita * prezzo_unitario,
                "quantity_before": quantity_before,
                "quantity_after": quantity_before + quantita,
                "document_type": "fattura",
                "document_id": invoice_id,
                "document_number": invoice["invoice_number"],
                "invoice_id": invoice_id,
                "supplier_vat": invoice["supplier_vat"],
                "supplier_name": invoice["supplier_name"],
                "movement_date": datetime.now(timezone.utc),
                "reason": f"Carico da fattura {invoice['invoice_number']}"
            }
            
            movement_id = await self.movement_repo.create(movement_doc)
            movement_ids.append(movement_id)
            
            logger.debug(f"Stock movement created: {movement_id} (+{quantita} {unita_misura})")
        
        logger.info(f"✅ Stock added from invoice {invoice_id}: {len(movement_ids)} movements")
        return movement_ids
    
    async def subtract_stock(
        self,
        product_id: str,
        quantity: float,
        reason: str,
        user_id: str,
        document_type: Optional[str] = None,
        document_id: Optional[str] = None
    ) -> str:
        """
        Subtract stock (scarico).
        
        Args:
            product_id: Product ID
            quantity: Quantity to subtract
            reason: Reason for subtraction
            user_id: User ID
            document_type: Optional document type
            document_id: Optional document ID
            
        Returns:
            Movement ID
            
        Raises:
            NotFoundError: If product not found
            ValidationError: If quantity invalid
            BusinessLogicError: If insufficient stock
        """
        logger.info(f"Subtracting stock: {product_id} (-{quantity})")
        
        # Validate quantity
        if quantity <= 0:
            raise ValidationError("Quantity must be positive")
        
        # Get product
        product = await self.warehouse_repo.find_by_id(product_id)
        if not product:
            raise NotFoundError("Product", product_id)
        
        # Check available stock
        available = product.get("quantity_available", 0.0)
        if available < quantity:
            raise BusinessLogicError(
                f"Insufficient stock for {product['product_name']}. "
                f"Available: {available}, Requested: {quantity}",
                details={
                    "product_id": product_id,
                    "product_name": product["product_name"],
                    "available": available,
                    "requested": quantity
                }
            )
        
        # Update stock
        await self.warehouse_repo.update_stock(
            product_id=product_id,
            quantity_change=-quantity,
            movement_type="scarico"
        )
        
        # Create movement record
        movement_doc = {
            "user_id": user_id,
            "product_id": product_id,
            "product_name": product["product_name"],
            "movement_type": "scarico",
            "quantity": -quantity,  # Negative for scarico
            "unit_of_measure": product["unit_of_measure"],
            "unit_price": product.get("unit_price_avg"),
            "total_value": quantity * product.get("unit_price_avg", 0),
            "quantity_before": available,
            "quantity_after": available - quantity,
            "document_type": document_type,
            "document_id": document_id,
            "movement_date": datetime.now(timezone.utc),
            "reason": reason
        }
        
        movement_id = await self.movement_repo.create(movement_doc)
        
        logger.info(f"✅ Stock subtracted: {movement_id} (-{quantity})")
        return movement_id
    
    async def adjust_stock(
        self,
        product_id: str,
        new_quantity: float,
        reason: str,
        user_id: str
    ) -> str:
        """
        Adjust stock to specific quantity (rettifica).
        
        Args:
            product_id: Product ID
            new_quantity: New quantity
            reason: Reason for adjustment
            user_id: User ID
            
        Returns:
            Movement ID
            
        Raises:
            NotFoundError: If product not found
            ValidationError: If quantity invalid
        """
        logger.info(f"Adjusting stock: {product_id} -> {new_quantity}")
        
        # Validate quantity
        if new_quantity < 0:
            raise ValidationError("Quantity cannot be negative")
        
        # Get product
        product = await self.warehouse_repo.find_by_id(product_id)
        if not product:
            raise NotFoundError("Product", product_id)
        
        current_quantity = product.get("quantity_available", 0.0)
        quantity_change = new_quantity - current_quantity
        
        # Update stock
        await self.warehouse_repo.update(
            product_id,
            {"quantity_available": new_quantity}
        )
        
        # Create movement record
        movement_doc = {
            "user_id": user_id,
            "product_id": product_id,
            "product_name": product["product_name"],
            "movement_type": "rettifica",
            "quantity": quantity_change,
            "unit_of_measure": product["unit_of_measure"],
            "quantity_before": current_quantity,
            "quantity_after": new_quantity,
            "movement_date": datetime.now(timezone.utc),
            "reason": reason
        }
        
        movement_id = await self.movement_repo.create(movement_doc)
        
        logger.info(f"✅ Stock adjusted: {movement_id} ({quantity_change:+.2f})")
        return movement_id
    
    async def get_product(self, product_id: str) -> Dict[str, Any]:
        """
        Get product by ID.
        
        Args:
            product_id: Product ID
            
        Returns:
            Product document
            
        Raises:
            NotFoundError: If product not found
        """
        product = await self.warehouse_repo.find_by_id(product_id)
        
        if not product:
            raise NotFoundError("Product", product_id)
        
        return product
    
    async def list_products(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100,
        category: Optional[str] = None,
        supplier_vat: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List warehouse products with filters.
        
        Args:
            user_id: User ID
            skip: Number to skip
            limit: Maximum number to return
            category: Filter by category
            supplier_vat: Filter by supplier
            
        Returns:
            List of products
        """
        if category:
            return await self.warehouse_repo.find_by_category(
                category=category,
                user_id=user_id,
                skip=skip,
                limit=limit
            )
        
        if supplier_vat:
            return await self.warehouse_repo.find_by_supplier(
                supplier_vat=supplier_vat,
                user_id=user_id,
                skip=skip,
                limit=limit
            )
        
        return await self.warehouse_repo.find_by_user(
            user_id=user_id,
            skip=skip,
            limit=limit
        )
    
    async def get_low_stock_products(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get products with stock below minimum level.
        
        Args:
            user_id: User ID
            skip: Number to skip
            limit: Maximum number to return
            
        Returns:
            List of low stock products
        """
        return await self.warehouse_repo.find_low_stock(
            user_id=user_id,
            skip=skip,
            limit=limit
        )
    
    async def get_product_movements(
        self,
        product_id: str,
        user_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get movement history for a product.
        
        Args:
            product_id: Product ID
            user_id: User ID
            skip: Number to skip
            limit: Maximum number to return
            
        Returns:
            List of movements
        """
        return await self.movement_repo.find_by_product(
            product_id=product_id,
            user_id=user_id,
            skip=skip,
            limit=limit
        )
    
    async def calculate_inventory_value(self, user_id: str) -> float:
        """
        Calculate total inventory value.
        
        Args:
            user_id: User ID
            
        Returns:
            Total inventory value
        """
        return await self.warehouse_repo.get_total_inventory_value(user_id)
    
    async def search_products(
        self,
        user_id: str,
        query: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Search products by name or code.
        
        Args:
            user_id: User ID
            query: Search query
            skip: Number to skip
            limit: Maximum number to return
            
        Returns:
            List of matching products
        """
        return await self.warehouse_repo.search_products(
            user_id=user_id,
            query=query,
            skip=skip,
            limit=limit
        )
    
    async def get_inventory_summary(self, user_id: str) -> Dict[str, Any]:
        """
        Get comprehensive inventory summary.
        
        Args:
            user_id: User ID
            
        Returns:
            Summary with stats
        """
        all_products = await self.warehouse_repo.find_by_user(
            user_id=user_id,
            limit=10000
        )
        
        total_products = len(all_products)
        total_value = await self.calculate_inventory_value(user_id)
        
        # Count low stock items
        low_stock = [
            p for p in all_products
            if p.get("minimum_stock") and
            p.get("quantity_available", 0) < p["minimum_stock"]
        ]
        
        # Count by category
        by_category = {}
        for product in all_products:
            category = product.get("category", "uncategorized")
            by_category[category] = by_category.get(category, 0) + 1
        
        return {
            "total_products": total_products,
            "total_value": total_value,
            "low_stock_count": len(low_stock),
            "low_stock_products": low_stock[:10],  # Top 10
            "by_category": by_category
        }
