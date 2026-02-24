"""
Warehouse repository for inventory and stock management.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import logging

from .base_repository import BaseRepository
from app.exceptions import NotFoundError

logger = logging.getLogger(__name__)


class WarehouseRepository(BaseRepository):
    """Repository for warehouse product operations."""
    
    async def find_by_product_name(
        self,
        product_name: str,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Find warehouse product by name.
        
        Args:
            product_name: Product name
            user_id: User ID
            
        Returns:
            Product document or None if not found
        """
        return await self.find_one({
            "product_name": product_name,
            "user_id": user_id
        })
    
    async def find_by_supplier(
        self,
        supplier_vat: str,
        user_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Find all products from a specific supplier.
        
        Args:
            supplier_vat: Supplier VAT number
            user_id: User ID
            skip: Number of products to skip
            limit: Maximum number of products to return
            
        Returns:
            List of products
        """
        return await self.find_all(
            filter_query={
                "supplier_vat": supplier_vat,
                "user_id": user_id,
                "is_active": True
            },
            skip=skip,
            limit=limit,
            sort=[("product_name", 1)]
        )
    
    async def find_low_stock(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Find products with stock below minimum level.
        
        Args:
            user_id: User ID
            skip: Number of products to skip
            limit: Maximum number of products to return
            
        Returns:
            List of low stock products
        """
        pipeline = [
            {
                "$match": {
                    "user_id": user_id,
                    "is_active": True,
                    "minimum_stock": {"$exists": True, "$ne": None}
                }
            },
            {
                "$addFields": {
                    "is_low_stock": {
                        "$lt": ["$quantity_available", "$minimum_stock"]
                    }
                }
            },
            {
                "$match": {
                    "is_low_stock": True
                }
            },
            {
                "$sort": {"quantity_available": 1}
            },
            {
                "$skip": skip
            },
            {
                "$limit": limit
            }
        ]
        
        return await self.aggregate(pipeline)
    
    async def find_by_category(
        self,
        category: str,
        user_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Find products by category.
        
        Args:
            category: Product category
            user_id: User ID
            skip: Number of products to skip
            limit: Maximum number of products to return
            
        Returns:
            List of products in category
        """
        return await self.find_all(
            filter_query={
                "category": category,
                "user_id": user_id,
                "is_active": True
            },
            skip=skip,
            limit=limit,
            sort=[("product_name", 1)]
        )
    
    async def update_stock(
        self,
        product_id: str,
        quantity_change: float,
        movement_type: str
    ) -> bool:
        """
        Update product stock quantities.
        
        Args:
            product_id: Product ID
            quantity_change: Quantity to add (positive) or subtract (negative)
            movement_type: Type of movement (carico, scarico, etc.)
            
        Returns:
            True if updated successfully
            
        Raises:
            NotFoundError: If product not found
        """
        product = await self.find_by_id(product_id)
        if not product:
            raise NotFoundError("Product", product_id)
        
        # Update quantities based on movement type
        if movement_type == "carico":
            # Stock in
            quantity_purchased = product.get("quantity_purchased", 0.0) + quantity_change
            quantity_available = product.get("quantity_available", 0.0) + quantity_change
            
            update_data = {
                "quantity_purchased": quantity_purchased,
                "quantity_available": quantity_available,
                "last_movement_date": datetime.now(timezone.utc).date()
            }
        
        elif movement_type == "scarico":
            # Stock out
            quantity_used = product.get("quantity_used", 0.0) + abs(quantity_change)
            quantity_available = product.get("quantity_available", 0.0) - abs(quantity_change)
            
            # Prevent negative stock
            if quantity_available < 0:
                logger.warning(f"Negative stock for product {product_id}: {quantity_available}")
                quantity_available = 0
            
            update_data = {
                "quantity_used": quantity_used,
                "quantity_available": quantity_available,
                "last_movement_date": datetime.now(timezone.utc).date()
            }
        
        else:
            # Rettifica - direct adjustment
            quantity_available = product.get("quantity_available", 0.0) + quantity_change
            update_data = {
                "quantity_available": max(0, quantity_available),
                "last_movement_date": datetime.now(timezone.utc).date()
            }
        
        logger.info(f"Updating stock for product {product_id}: {movement_type} {quantity_change}")
        return await self.update(product_id, update_data)
    
    async def update_pricing(
        self,
        product_id: str,
        unit_price: float
    ) -> bool:
        """
        Update product pricing statistics.
        
        Args:
            product_id: Product ID
            unit_price: New unit price
            
        Returns:
            True if updated successfully
        """
        product = await self.find_by_id(product_id)
        if not product:
            raise NotFoundError("Product", product_id)
        
        # Update price statistics
        current_min = product.get("unit_price_min", float('inf'))
        current_max = product.get("unit_price_max", 0.0)
        current_avg = product.get("unit_price_avg", 0.0)
        total_purchases = product.get("quantity_purchased", 0.0)
        
        new_min = min(current_min, unit_price)
        new_max = max(current_max, unit_price)
        
        # Simple average calculation (can be improved with weighted average)
        if total_purchases > 0:
            new_avg = ((current_avg * total_purchases) + unit_price) / (total_purchases + 1)
        else:
            new_avg = unit_price
        
        update_data = {
            "unit_price_min": new_min,
            "unit_price_max": new_max,
            "unit_price_avg": new_avg,
            "last_purchase_price": unit_price,
            "last_purchase_date": datetime.now(timezone.utc).date()
        }
        
        return await self.update(product_id, update_data)
    
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
            skip: Number of products to skip
            limit: Maximum number of products to return
            
        Returns:
            List of matching products
        """
        filter_query = {
            "user_id": user_id,
            "is_active": True,
            "$or": [
                {"product_name": {"$regex": query, "$options": "i"}},
                {"product_code": {"$regex": query, "$options": "i"}},
                {"product_description": {"$regex": query, "$options": "i"}}
            ]
        }
        
        return await self.find_all(
            filter_query=filter_query,
            skip=skip,
            limit=limit,
            sort=[("product_name", 1)]
        )
    
    async def get_total_inventory_value(self, user_id: str) -> float:
        """
        Calculate total inventory value.
        
        Args:
            user_id: User ID
            
        Returns:
            Total inventory value
        """
        pipeline = [
            {
                "$match": {
                    "user_id": user_id,
                    "is_active": True
                }
            },
            {
                "$addFields": {
                    "value": {
                        "$multiply": ["$quantity_available", "$unit_price_avg"]
                    }
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total_value": {"$sum": "$value"}
                }
            }
        ]
        
        result = await self.aggregate(pipeline)
        return result[0]["total_value"] if result else 0.0
    
    async def get_products_by_chart_account(
        self,
        chart_account_id: str,
        user_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get products linked to a specific chart of account.
        
        Args:
            chart_account_id: Chart of account ID
            user_id: User ID
            
        Returns:
            List of products
        """
        return await self.find_all(
            filter_query={
                "chart_of_account_id": chart_account_id,
                "user_id": user_id,
                "is_active": True
            },
            sort=[("product_name", 1)]
        )


class WarehouseMovementRepository(BaseRepository):
    """Repository for warehouse movement operations."""
    
    async def find_by_product(
        self,
        product_id: str,
        user_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Find all movements for a specific product.
        
        Args:
            product_id: Product ID
            user_id: User ID
            skip: Number of movements to skip
            limit: Maximum number of movements to return
            
        Returns:
            List of movements
        """
        return await self.find_all(
            filter_query={
                "product_id": product_id,
                "user_id": user_id
            },
            skip=skip,
            limit=limit,
            sort=[("movement_date", -1)]
        )
    
    async def find_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        user_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Find movements within date range.
        
        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            user_id: User ID
            skip: Number of movements to skip
            limit: Maximum number of movements to return
            
        Returns:
            List of movements
        """
        return await self.find_all(
            filter_query={
                "movement_date": {
                    "$gte": start_date,
                    "$lte": end_date
                },
                "user_id": user_id
            },
            skip=skip,
            limit=limit,
            sort=[("movement_date", -1)]
        )
    
    async def find_by_invoice(
        self,
        invoice_id: str,
        user_id: str
    ) -> List[Dict[str, Any]]:
        """
        Find all movements linked to a specific invoice.
        
        Args:
            invoice_id: Invoice ID
            user_id: User ID
            
        Returns:
            List of movements
        """
        return await self.find_all(
            filter_query={
                "invoice_id": invoice_id,
                "user_id": user_id
            },
            sort=[("movement_date", -1)]
        )
