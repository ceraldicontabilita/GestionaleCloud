"""
Export router.
Handle data exports in various formats (Excel, PDF, CSV).
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from typing import Dict, Any, Optional
from datetime import date
import io
import logging

from app.database import Database, Collections
from app.repositories import (
    InvoiceRepository,
    SupplierRepository,
    WarehouseRepository,
    EmployeeRepository
)
from app.services import InvoiceService, WarehouseService, EmployeeService
from app.utils.dependencies import get_current_user
from app.utils.excel_exporter import excel_exporter

logger = logging.getLogger(__name__)
router = APIRouter()


async def get_invoice_service() -> InvoiceService:
    """Get invoice service."""
    db = Database.get_db()
    invoice_repo = InvoiceRepository(db[Collections.INVOICES])
    supplier_repo = SupplierRepository(db[Collections.SUPPLIERS])
    # Pass None for other services as export doesn't need them
    return InvoiceService(invoice_repo, supplier_repo)


async def get_warehouse_service() -> WarehouseService:
    """Get warehouse service."""
    db = Database.get_db()
    warehouse_repo = WarehouseRepository(db[Collections.WAREHOUSE_PRODUCTS])
    # WarehouseService needs other repos too, but for export maybe minimal?
    # Let's check constructor signature again to be safe.
    # It takes (warehouse_repo, movement_repo, invoice_repo)
    # We should provide them or mock them if unused.
    # But usually safer to provide all.
    from app.repositories import WarehouseMovementRepository
    movement_repo = WarehouseMovementRepository(db[Collections.WAREHOUSE_MOVEMENTS])
    invoice_repo = InvoiceRepository(db[Collections.INVOICES])
    return WarehouseService(warehouse_repo, movement_repo, invoice_repo)


async def get_employee_service() -> EmployeeService:
    """Get employee service."""
    db = Database.get_db()
    employee_repo = EmployeeRepository(db[Collections.EMPLOYEES])
    return EmployeeService(employee_repo)


@router.get(
    "/excel",
    summary="Export cart to Excel (Generic)"
)
async def export_excel_generic(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> StreamingResponse:
    """Export generic excel (Cart)."""
    # Just redirect to warehouse export for now or empty
    return StreamingResponse(
        io.BytesIO(b""),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=export.xlsx"}
    )


@router.get(
    "/invoices/excel",
    summary="Export invoices to Excel"
)
async def export_invoices_excel(
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: InvoiceService = Depends(get_invoice_service),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    payment_status: Optional[str] = None
) -> StreamingResponse:
    """
    Export invoices to Excel file.
    """
    if not excel_exporter:
        raise HTTPException(
            status_code=500,
            detail="Excel export not available. Install openpyxl."
        )
    
    user_id = current_user["user_id"]
    
    # Get invoices
    invoices = await service.list_invoices(
        user_id=user_id,
        skip=0,
        limit=10000
    )
    
    # Apply filters
    if start_date:
        invoices = [inv for inv in invoices if inv.get('date', '') >= start_date.isoformat()]
    if end_date:
        invoices = [inv for inv in invoices if inv.get('date', '') <= end_date.isoformat()]
    if payment_status:
        invoices = [inv for inv in invoices if inv.get('payment_status') == payment_status]
    
    # Export to Excel
    excel_file = excel_exporter.export_invoices(invoices)
    
    # Generate filename
    filename = f"fatture_{date.today().isoformat()}.xlsx"
    
    logger.info(f"Exported {len(invoices)} invoices to Excel for user {user_id}")
    
    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@router.get(
    "/warehouse/excel",
    summary="Export warehouse inventory to Excel"
)
async def export_warehouse_excel(
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: WarehouseService = Depends(get_warehouse_service),
    category: Optional[str] = None,
    low_stock_only: bool = False
) -> StreamingResponse:
    """
    Export warehouse inventory to Excel.
    """
    if not excel_exporter:
        raise HTTPException(
            status_code=500,
            detail="Excel export not available. Install openpyxl."
        )
    
    user_id = current_user["user_id"]
    
    # Get products
    products = await service.list_products(
        user_id=user_id,
        category=category,
        skip=0,
        limit=10000
    )
    
    # Filter low stock if requested
    if low_stock_only:
        products = [
            p for p in products
            if p.get('stock', 0) < p.get('min_stock', 0)
        ]
    
    # Export
    excel_file = excel_exporter.export_warehouse_inventory(products)
    
    filename = f"inventario_{date.today().isoformat()}.xlsx"
    
    logger.info(f"Exported {len(products)} products to Excel for user {user_id}")
    
    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@router.get(
    "/employees/excel",
    summary="Export employees to Excel"
)
async def export_employees_excel(
    current_user: Dict[str, Any] = Depends(get_current_user),
    service: EmployeeService = Depends(get_employee_service),
    active_only: bool = True
) -> StreamingResponse:
    """
    Export employees to Excel.
    """
    if not excel_exporter:
        raise HTTPException(
            status_code=500,
            detail="Excel export not available. Install openpyxl."
        )
    
    user_id = current_user["user_id"]
    
    # Get employees
    employees = await service.list_employees(
        user_id=user_id,
        active_only=active_only
    )
    
    # Export
    excel_file = excel_exporter.export_employees(employees)
    
    filename = f"dipendenti_{date.today().isoformat()}.xlsx"
    
    logger.info(f"Exported {len(employees)} employees to Excel for user {user_id}")
    
    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@router.get(
    "/accounting/excel",
    summary="Export accounting report to Excel"
)
async def export_accounting_excel(
    month: str = Query(..., description="Month in format YYYY-MM"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    invoice_service: InvoiceService = Depends(get_invoice_service)
) -> StreamingResponse:
    """
    Export monthly accounting report to Excel.
    """
    if not excel_exporter:
        raise HTTPException(
            status_code=500,
            detail="Excel export not available. Install openpyxl."
        )
    
    user_id = current_user["user_id"]
    
    # Get month data
    try:
        year, month_num = month.split('-')
        year = int(year)
        month_num = int(month_num)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid month format. Use YYYY-MM"
        )
    
    # Get invoices for month
    invoices = await invoice_service.list_invoices(user_id, skip=0, limit=10000)
    month_invoices = [
        inv for inv in invoices
        if inv.get('date', '').startswith(month)
    ]
    
    # Calculate totals
    total_net = sum(
        inv.get('total_amount', 0) - inv.get('vat_amount', 0)
        for inv in month_invoices
    )
    total_vat = sum(inv.get('vat_amount', 0) for inv in month_invoices)
    total_amount = sum(inv.get('total_amount', 0) for inv in month_invoices)
    
    paid_invoices = [inv for inv in month_invoices if inv.get('payment_status') == 'paid']
    total_paid = sum(inv.get('total_amount', 0) for inv in paid_invoices)
    total_unpaid = total_amount - total_paid
    
    report_data = {
        'total_invoices': len(month_invoices),
        'total_net': total_net,
        'total_vat': total_vat,
        'total_amount': total_amount,
        'total_paid': total_paid,
        'total_unpaid': total_unpaid
    }
    
    # Export
    excel_file = excel_exporter.export_accounting_report(report_data, month)
    
    filename = f"contabilita_{month}.xlsx"
    
    logger.info(f"Exported accounting report for {month} for user {user_id}")
    
    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )
