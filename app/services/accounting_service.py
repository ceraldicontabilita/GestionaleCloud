"""
Accounting service.
Handles accounting entries and financial operations.
"""
from typing import Dict, Any, Optional
from datetime import datetime, date
import logging

from app.repositories import InvoiceRepository

logger = logging.getLogger(__name__)


class AccountingService:
    """Service for accounting operations."""
    
    def __init__(self, invoice_repo: InvoiceRepository):
        """
        Initialize accounting service.
        
        Args:
            invoice_repo: Invoice repository instance
        """
        self.invoice_repo = invoice_repo
    
    async def get_monthly_summary(
        self,
        month_year: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Get monthly accounting summary.
        
        Args:
            month_year: Month-year string (MM-YYYY)
            user_id: User ID
            
        Returns:
            Monthly summary with totals
        """
        logger.info(f"Generating monthly summary: {month_year}")
        
        # Get invoice stats for month
        stats = await self.invoice_repo.get_stats_by_month(
            month_year=month_year,
            user_id=user_id
        )
        
        return {
            "month_year": month_year,
            "total_invoices": stats["total_invoices"],
            "total_purchases": stats["total_amount"],
            "total_imponibile": stats["total_imponibile"],
            "total_iva": stats["total_iva"],
            "generated_at": datetime.now(timezone.utc)
        }
    
    async def get_annual_summary(
        self,
        year: int,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Get annual accounting summary.
        
        Args:
            year: Year (e.g., 2024)
            user_id: User ID
            
        Returns:
            Annual summary
        """
        logger.info(f"Generating annual summary: {year}")
        
        # Get all invoices for the year
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
        
        invoices = await self.invoice_repo.find_by_date_range(
            start_date=start_date,
            end_date=end_date,
            user_id=user_id,
            limit=10000
        )
        
        # Calculate totals
        total_invoices = len(invoices)
        total_amount = sum(inv.get("total_amount", 0) for inv in invoices)
        total_imponibile = sum(inv.get("total_imponibile", 0) for inv in invoices)
        total_iva = sum(inv.get("total_iva", 0) for inv in invoices)
        
        # Group by month
        by_month = {}
        for inv in invoices:
            month = inv.get("month_year", "unknown")
            if month not in by_month:
                by_month[month] = {
                    "count": 0,
                    "total": 0.0,
                    "imponibile": 0.0,
                    "iva": 0.0
                }
            
            by_month[month]["count"] += 1
            by_month[month]["total"] += inv.get("total_amount", 0)
            by_month[month]["imponibile"] += inv.get("total_imponibile", 0)
            by_month[month]["iva"] += inv.get("total_iva", 0)
        
        # Group by supplier
        by_supplier = {}
        for inv in invoices:
            supplier = inv.get("supplier_name", "unknown")
            if supplier not in by_supplier:
                by_supplier[supplier] = {
                    "vat": inv.get("supplier_vat"),
                    "count": 0,
                    "total": 0.0
                }
            
            by_supplier[supplier]["count"] += 1
            by_supplier[supplier]["total"] += inv.get("total_amount", 0)
        
        # Top 10 suppliers
        top_suppliers = sorted(
            by_supplier.items(),
            key=lambda x: x[1]["total"],
            reverse=True
        )[:10]
        
        return {
            "year": year,
            "total_invoices": total_invoices,
            "total_amount": total_amount,
            "total_imponibile": total_imponibile,
            "total_iva": total_iva,
            "by_month": by_month,
            "top_suppliers": dict(top_suppliers),
            "generated_at": datetime.now(timezone.utc)
        }
    
    async def get_payment_summary(
        self,
        user_id: str,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Get payment summary (paid vs unpaid).
        
        Args:
            user_id: User ID
            date_from: Start date (optional)
            date_to: End date (optional)
            
        Returns:
            Payment summary
        """
        logger.info("Generating payment summary")
        
        # Get invoices
        if date_from and date_to:
            invoices = await self.invoice_repo.find_by_date_range(
                start_date=date_from,
                end_date=date_to,
                user_id=user_id,
                limit=10000
            )
        else:
            invoices = await self.invoice_repo.find_by_user(
                user_id=user_id,
                limit=10000
            )
        
        # Calculate payment stats
        total_invoices = len(invoices)
        total_amount = sum(inv.get("total_amount", 0) for inv in invoices)
        total_paid = sum(inv.get("amount_paid", 0) for inv in invoices)
        total_unpaid = total_amount - total_paid
        
        # Count by payment status
        paid_count = len([inv for inv in invoices if inv.get("payment_status") == "paid"])
        partial_count = len([inv for inv in invoices if inv.get("payment_status") == "partial"])
        unpaid_count = len([inv for inv in invoices if inv.get("payment_status") == "unpaid"])
        
        # Count by payment method
        by_method = {}
        for inv in invoices:
            if inv.get("payment_status") == "paid":
                method = inv.get("payment_method", "unknown")
                by_method[method] = by_method.get(method, 0) + 1
        
        return {
            "period": {
                "from": date_from.isoformat() if date_from else None,
                "to": date_to.isoformat() if date_to else None
            },
            "total_invoices": total_invoices,
            "total_amount": total_amount,
            "total_paid": total_paid,
            "total_unpaid": total_unpaid,
            "payment_percentage": (total_paid / total_amount * 100) if total_amount > 0 else 0,
            "by_status": {
                "paid": paid_count,
                "partial": partial_count,
                "unpaid": unpaid_count
            },
            "by_payment_method": by_method,
            "generated_at": datetime.now(timezone.utc)
        }
    
    async def get_vat_summary(
        self,
        month_year: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Get VAT summary for a month.
        
        Args:
            month_year: Month-year string (MM-YYYY)
            user_id: User ID
            
        Returns:
            VAT summary by rate
        """
        logger.info(f"Generating VAT summary: {month_year}")
        
        # Get invoices for month
        invoices = await self.invoice_repo.find_by_month(
            month_year=month_year,
            user_id=user_id,
            limit=10000
        )
        
        # Group by VAT rate
        by_rate = {}
        
        for inv in invoices:
            for product in inv.get("products", []):
                rate = product.get("iva", 0)
                
                if rate not in by_rate:
                    by_rate[rate] = {
                        "imponibile": 0.0,
                        "imposta": 0.0,
                        "count": 0
                    }
                
                imponibile = product["prezzo_unitario"] * product["quantita"]
                imposta = imponibile * (rate / 100)
                
                by_rate[rate]["imponibile"] += imponibile
                by_rate[rate]["imposta"] += imposta
                by_rate[rate]["count"] += 1
        
        # Calculate totals
        total_imponibile = sum(r["imponibile"] for r in by_rate.values())
        total_imposta = sum(r["imposta"] for r in by_rate.values())
        
        return {
            "month_year": month_year,
            "by_rate": by_rate,
            "total_imponibile": total_imponibile,
            "total_imposta": total_imposta,
            "total": total_imponibile + total_imposta,
            "generated_at": datetime.now(timezone.utc)
        }
    
    async def get_supplier_balance(
        self,
        supplier_vat: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Get balance for a specific supplier.
        
        Args:
            supplier_vat: Supplier VAT number
            user_id: User ID
            
        Returns:
            Supplier balance summary
        """
        logger.info(f"Generating supplier balance: {supplier_vat}")
        
        # Get all invoices for supplier
        invoices = await self.invoice_repo.find_by_supplier(
            supplier_vat=supplier_vat,
            limit=10000
        )
        
        # Filter by user
        invoices = [inv for inv in invoices if inv.get("user_id") == user_id]
        
        total_invoices = len(invoices)
        total_amount = sum(inv.get("total_amount", 0) for inv in invoices)
        total_paid = sum(inv.get("amount_paid", 0) for inv in invoices)
        total_unpaid = total_amount - total_paid
        
        # Get unpaid invoices details
        unpaid_invoices = [
            {
                "id": inv["id"],
                "invoice_number": inv["invoice_number"],
                "invoice_date": inv["invoice_date"],
                "total_amount": inv["total_amount"],
                "amount_paid": inv.get("amount_paid", 0),
                "remaining": inv["total_amount"] - inv.get("amount_paid", 0)
            }
            for inv in invoices
            if inv.get("payment_status") != "paid"
        ]
        
        return {
            "supplier_vat": supplier_vat,
            "supplier_name": invoices[0]["supplier_name"] if invoices else "Unknown",
            "total_invoices": total_invoices,
            "total_amount": total_amount,
            "total_paid": total_paid,
            "total_unpaid": total_unpaid,
            "unpaid_invoices": unpaid_invoices,
            "generated_at": datetime.now(timezone.utc)
        }
