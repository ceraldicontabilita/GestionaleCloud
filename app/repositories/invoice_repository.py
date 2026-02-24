"""
Invoice repository for passive invoices management.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, date
import logging

from .base_repository import BaseRepository
from app.exceptions import NotFoundError

logger = logging.getLogger(__name__)


class InvoiceRepository(BaseRepository):
    """Repository for invoice operations."""
    
    async def find_by_hash(self, content_hash: str) -> Optional[Dict[str, Any]]:
        """
        Find invoice by content hash (for duplicate detection).
        
        Args:
            content_hash: Content hash of the invoice
            
        Returns:
            Invoice document or None if not found
        """
        return await self.find_one({"content_hash": content_hash})
    
    async def find_by_supplier(
        self,
        supplier_vat: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Find all invoices from a specific supplier.
        
        Args:
            supplier_vat: Supplier VAT number
            skip: Number of invoices to skip
            limit: Maximum number of invoices to return
            
        Returns:
            List of invoices
        """
        return await self.find_all(
            filter_query={"supplier_vat": supplier_vat, "status": {"$ne": "deleted"}},
            skip=skip,
            limit=limit,
            sort=[("invoice_date", -1)]
        )
    
    async def find_by_month(
        self,
        month_year: str,
        user_id: str,
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Find invoices by month-year.
        
        Args:
            month_year: Month-year string (format: MM-YYYY)
            user_id: User ID
            skip: Number of invoices to skip
            limit: Maximum number of invoices to return
            status: Optional status filter
            
        Returns:
            List of invoices
        """
        query = {
            "month_year": month_year,
            "user_id": user_id
        }
        
        if status:
            query["status"] = status
        else:
            query["status"] = {"$ne": "deleted"}
            
        return await self.find_all(
            filter_query=query,
            skip=skip,
            limit=limit,
            sort=[("invoice_date", -1)]
        )
    
    async def find_by_date_range(
        self,
        start_date: date,
        end_date: date,
        user_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Find invoices within date range.
        
        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            user_id: User ID
            skip: Number of invoices to skip
            limit: Maximum number of invoices to return
            
        Returns:
            List of invoices
        """
        return await self.find_all(
            filter_query={
                "invoice_date": {
                    "$gte": start_date.isoformat(),
                    "$lte": end_date.isoformat()
                },
                "user_id": user_id,
                "status": {"$ne": "deleted"}
            },
            skip=skip,
            limit=limit,
            sort=[("invoice_date", -1)]
        )
    
    async def find_unpaid(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Find unpaid invoices.
        
        Args:
            user_id: User ID
            skip: Number of invoices to skip
            limit: Maximum number of invoices to return
            
        Returns:
            List of unpaid invoices
        """
        return await self.find_all(
            filter_query={
                "user_id": user_id,
                "payment_status": {"$in": ["unpaid", "partial"]},
                "status": "active"
            },
            skip=skip,
            limit=limit,
            sort=[("due_date", 1)]
        )
    
    async def find_overdue(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Find overdue invoices (unpaid and past due date).
        
        Args:
            user_id: User ID
            skip: Number of invoices to skip
            limit: Maximum number of invoices to return
            
        Returns:
            List of overdue invoices
        """
        today = datetime.now(timezone.utc).date().isoformat()
        
        return await self.find_all(
            filter_query={
                "user_id": user_id,
                "payment_status": {"$in": ["unpaid", "partial"]},
                "due_date": {"$lt": today},
                "status": "active"
            },
            skip=skip,
            limit=limit,
            sort=[("due_date", 1)]
        )
    
    async def update_payment_status(
        self,
        invoice_id: str,
        amount_paid: float,
        payment_method: Optional[str] = None
    ) -> bool:
        """
        Update invoice payment status.
        
        Args:
            invoice_id: Invoice ID
            amount_paid: Amount paid
            payment_method: Payment method used
            
        Returns:
            True if updated successfully
        """
        invoice = await self.find_by_id(invoice_id)
        if not invoice:
            raise NotFoundError("Invoice", invoice_id)
        
        total_amount = invoice["total_amount"]
        
        # Determine payment status
        if amount_paid >= total_amount:
            payment_status = "paid"
        elif amount_paid > 0:
            payment_status = "partial"
        else:
            payment_status = "unpaid"
        
        update_data = {
            "amount_paid": amount_paid,
            "payment_status": payment_status
        }
        
        if payment_method:
            update_data["payment_method"] = payment_method
        
        logger.info(f"Updating payment status for invoice {invoice_id}: {payment_status}")
        return await self.update(invoice_id, update_data)
    
    async def mark_as_archived(self, invoice_id: str) -> bool:
        """
        Archive an invoice.
        
        Args:
            invoice_id: Invoice ID
            
        Returns:
            True if archived successfully
        """
        logger.info(f"Archiving invoice: {invoice_id}")
        return await self.update(invoice_id, {"status": "archived"})
    
    async def mark_as_reconciled(
        self,
        invoice_id: str,
        bank_transaction_id: str
    ) -> bool:
        """
        Mark invoice as bank reconciled.
        
        Args:
            invoice_id: Invoice ID
            bank_transaction_id: Bank transaction ID
            
        Returns:
            True if updated successfully
        """
        logger.info(f"Marking invoice {invoice_id} as reconciled with transaction {bank_transaction_id}")
        return await self.update(
            invoice_id,
            {
                "bank_reconciled": True,
                "bank_transaction_id": bank_transaction_id
            }
        )
    
    async def get_total_by_supplier(
        self,
        supplier_vat: str,
        user_id: str
    ) -> float:
        """
        Get total amount for all invoices from a supplier.
        
        Args:
            supplier_vat: Supplier VAT number
            user_id: User ID
            
        Returns:
            Total amount
        """
        pipeline = [
            {
                "$match": {
                    "supplier_vat": supplier_vat,
                    "user_id": user_id,
                    "status": {"$ne": "deleted"}
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total": {"$sum": "$total_amount"}
                }
            }
        ]
        
        result = await self.aggregate(pipeline)
        return result[0]["total"] if result else 0.0
    
    async def get_stats_by_month(
        self,
        month_year: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Get invoice statistics for a specific month.
        
        Args:
            month_year: Month-year string (format: MM-YYYY)
            user_id: User ID
            
        Returns:
            Statistics dictionary
        """
        pipeline = [
            {
                "$match": {
                    "month_year": month_year,
                    "user_id": user_id,
                    "status": {"$ne": "deleted"}
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total_invoices": {"$sum": 1},
                    "total_amount": {"$sum": "$total_amount"},
                    "total_imponibile": {"$sum": "$total_imponibile"},
                    "total_iva": {"$sum": "$total_iva"}
                }
            }
        ]
        
        result = await self.aggregate(pipeline)
        
        if result:
            return {
                "month_year": month_year,
                "total_invoices": result[0]["total_invoices"],
                "total_amount": result[0]["total_amount"],
                "total_imponibile": result[0]["total_imponibile"],
                "total_iva": result[0]["total_iva"]
            }
        
        return {
            "month_year": month_year,
            "total_invoices": 0,
            "total_amount": 0.0,
            "total_imponibile": 0.0,
            "total_iva": 0.0
        }
    
    async def search_invoices(
        self,
        user_id: str,
        query: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Search invoices by supplier name or invoice number.
        
        Args:
            user_id: User ID
            query: Search query
            skip: Number of invoices to skip
            limit: Maximum number of invoices to return
            
        Returns:
            List of matching invoices
        """
        filter_query = {
            "user_id": user_id,
            "status": {"$ne": "deleted"},
            "$or": [
                {"supplier_name": {"$regex": query, "$options": "i"}},
                {"invoice_number": {"$regex": query, "$options": "i"}}
            ]
        }
        
        return await self.find_all(
            filter_query=filter_query,
            skip=skip,
            limit=limit,
            sort=[("invoice_date", -1)]
        )
