"""
Accounting router.
Handles accounting reports and financial summaries.
"""
from fastapi import APIRouter, Depends, Path
from typing import Dict, Any, Optional
from datetime import date
import logging

from app.database import Database, Collections
from app.repositories import InvoiceRepository
from app.services import AccountingService
from app.utils.dependencies import get_current_user, date_range_params

logger = logging.getLogger(__name__)

router = APIRouter()


# Dependency to get accounting service
async def get_accounting_service() -> AccountingService:
    """Get accounting service with injected dependencies."""
    db = Database.get_db()
    invoice_repo = InvoiceRepository(db[Collections.INVOICES])
    return AccountingService(invoice_repo)


@router.get(
    "/monthly/{month_year}",
    response_model=Dict[str, Any],
    summary="Get monthly summary",
    description="Get accounting summary for a specific month"
)
async def get_monthly_summary(
    month_year: str = Path(..., description="Month-year (format: MM-YYYY, e.g., 01-2024)"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    accounting_service: AccountingService = Depends(get_accounting_service)
) -> Dict[str, Any]:
    """
    Get monthly accounting summary.
    
    **Path Parameters:**
    - **month_year**: Month and year in format MM-YYYY (e.g., "01-2024")
    
    Returns:
    - Total invoices for the month
    - Total purchases amount
    - Total imponibile (taxable amount)
    - Total IVA (VAT)
    """
    user_id = current_user["user_id"]
    
    return await accounting_service.get_monthly_summary(
        month_year=month_year,
        user_id=user_id
    )


@router.get(
    "/annual/{year}",
    response_model=Dict[str, Any],
    summary="Get annual summary",
    description="Get accounting summary for a full year"
)
async def get_annual_summary(
    year: int = Path(..., ge=2000, le=2100, description="Year (e.g., 2024)"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    accounting_service: AccountingService = Depends(get_accounting_service)
) -> Dict[str, Any]:
    """
    Get annual accounting summary.
    
    **Path Parameters:**
    - **year**: Year (e.g., 2024)
    
    Returns:
    - Total invoices for the year
    - Total amount, imponibile, IVA
    - Month-by-month breakdown
    - Top suppliers for the year
    """
    user_id = current_user["user_id"]
    
    return await accounting_service.get_annual_summary(
        year=year,
        user_id=user_id
    )


@router.get(
    "/payments",
    response_model=Dict[str, Any],
    summary="Get payment summary",
    description="Get payment summary (paid vs unpaid)"
)
async def get_payment_summary(
    current_user: Dict[str, Any] = Depends(get_current_user),
    date_range: Dict[str, Optional[date]] = Depends(date_range_params),
    accounting_service: AccountingService = Depends(get_accounting_service)
) -> Dict[str, Any]:
    """
    Get payment summary showing paid vs unpaid amounts.
    
    **Query Parameters:**
    - **date_from**: Start date (YYYY-MM-DD, optional)
    - **date_to**: End date (YYYY-MM-DD, optional)
    
    Returns:
    - Total invoices
    - Total amount
    - Total paid
    - Total unpaid
    - Payment percentage
    - Counts by payment status
    - Distribution by payment method
    """
    user_id = current_user["user_id"]
    
    return await accounting_service.get_payment_summary(
        user_id=user_id,
        date_from=date_range["date_from"],
        date_to=date_range["date_to"]
    )


@router.get(
    "/vat/{month_year}",
    response_model=Dict[str, Any],
    summary="Get VAT summary",
    description="Get VAT summary by rate for a month"
)
async def get_vat_summary(
    month_year: str = Path(..., description="Month-year (format: MM-YYYY)"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    accounting_service: AccountingService = Depends(get_accounting_service)
) -> Dict[str, Any]:
    """
    Get VAT summary grouped by rate.
    
    **Path Parameters:**
    - **month_year**: Month and year in format MM-YYYY
    
    Returns VAT breakdown by rate:
    - Imponibile (taxable amount) per rate
    - Imposta (tax amount) per rate
    - Total imponibile and imposta
    """
    user_id = current_user["user_id"]
    
    return await accounting_service.get_vat_summary(
        month_year=month_year,
        user_id=user_id
    )


@router.get(
    "/supplier-balance/{supplier_vat}",
    response_model=Dict[str, Any],
    summary="Get supplier balance",
    description="Get balance for a specific supplier"
)
async def get_supplier_balance(
    supplier_vat: str = Path(..., description="Supplier VAT number"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    accounting_service: AccountingService = Depends(get_accounting_service)
) -> Dict[str, Any]:
    """
    Get accounting balance for a specific supplier.
    
    **Path Parameters:**
    - **supplier_vat**: Supplier VAT number
    
    Returns:
    - Total invoices from supplier
    - Total amount
    - Total paid
    - Total unpaid
    - List of unpaid invoices with details
    """
    user_id = current_user["user_id"]
    
    return await accounting_service.get_supplier_balance(
        supplier_vat=supplier_vat,
        user_id=user_id
    )


@router.get(
    "/dashboard",
    response_model=Dict[str, Any],
    summary="Get accounting dashboard",
    description="Get overview of key accounting metrics"
)
async def get_accounting_dashboard(
    current_user: Dict[str, Any] = Depends(get_current_user),
    accounting_service: AccountingService = Depends(get_accounting_service)
) -> Dict[str, Any]:
    """
    Get accounting dashboard with key metrics.
    
    Returns overview of:
    - Current month summary
    - Payment status
    - Recent activity
    """
    user_id = current_user["user_id"]
    
    # Get current month
    from datetime import datetime, timezone
    now = datetime.now()
    current_month = now.strftime("%m-%Y")
    
    # Get summaries
    monthly = await accounting_service.get_monthly_summary(current_month, user_id)
    payments = await accounting_service.get_payment_summary(user_id)
    
    return {
        "current_month": monthly,
        "payment_status": payments,
        "generated_at": datetime.now(timezone.utc)
    }


@router.post(
    "/auto-categorize/invoice/{invoice_id}",
    summary="Auto categorize invoice",
    description="Suggest accounting categories for invoice products"
)
async def auto_categorize_invoice(
    invoice_id: str = Path(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
    accounting_service: AccountingService = Depends(get_accounting_service)
) -> Dict[str, Any]:
    """Auto categorize invoice products based on rules."""
    # Get Invoice
    invoice_repo = accounting_service.invoice_repo
    invoice = await invoice_repo.find_by_id(invoice_id)
    
    if not invoice:
        return {"success": False, "message": "Invoice not found"}
        
    suggestions = []
    
    # Simple Rule Engine
    rules = {
        "energia": "4.2.03", "luce": "4.2.03", "gas": "4.2.03", "acqua": "4.2.03",
        "telefono": "4.2.04", "internet": "4.2.04",
        "affitto": "4.2.01", "locazione": "4.2.01",
        "cancelleria": "4.1.03", "carta": "4.1.03",
        "consulenza": "4.2.05", "commercialista": "4.2.05",
        "pulizia": "4.2.06",
        "trasporto": "4.2.07", "spedizione": "4.2.07",
        "banca": "4.2.08", "commissioni": "4.2.08",
        "carburante": "4.2.09", "benzina": "4.2.09", "diesel": "4.2.09",
        "manutenzione": "4.2.10", "riparazione": "4.2.10",
        "pubblicita": "4.2.11", "marketing": "4.2.11", "facebook": "4.2.11", "google": "4.2.11",
        "assicurazione": "4.2.12",
        "pasto": "4.2.13", "ristorante": "4.2.13", "hotel": "4.2.13"
    }
    
    products = invoice.get("products", [])
    matched_count = 0
    
    for p in products:
        desc = p.get("descrizione", "").lower()
        suggested_code = None
        match_source = "none"
        confidence = "none"
        
        # Check rules
        for keyword, code in rules.items():
            if keyword in desc:
                suggested_code = code
                match_source = "rule"
                confidence = "high"
                break
        
        # Fallback to general purchase
        if not suggested_code:
            suggested_code = "3.1.01" # Merci c/acquisti
            confidence = "low"
            
        suggestions.append({
            "description": p.get("descrizione"),
            "quantity": p.get("quantita"),
            "total": p.get("prezzo_totale"),
            "suggested_account": suggested_code,
            "match_source": match_source,
            "confidence": confidence
        })
        
        if match_source == "rule":
            matched_count += 1
            
    success_rate = matched_count / len(products) if products else 0
    
    return {
        "invoice_number": invoice.get("invoice_number"),
        "supplier": invoice.get("supplier_name"),
        "categorizations": suggestions,
        "success_rate": success_rate,
        "success": True
    }
