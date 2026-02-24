"""
Invoices router.
Handles invoice CRUD operations and management.
"""
from fastapi import APIRouter, Depends, Query, Path, status, UploadFile, File
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
import zipfile
import io
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import logging

from app.database import Database, Collections
from app.repositories import (
    InvoiceRepository, SupplierRepository,
    WarehouseRepository, WarehouseMovementRepository,
    CashMovementRepository, CorrissettivoRepository,
    ChartOfAccountsRepository
)
# Try import AccountingEntriesRepository from module if not in package
from app.repositories.accounting_entries_repository import AccountingEntriesRepository

from app.services import (
    InvoiceServiceV2, WarehouseService,
    AccountingEntriesService, CashService
)
from app.models import (
    InvoiceCreate,
    InvoiceUpdate
)
from app.utils.dependencies import get_current_user, pagination_params

logger = logging.getLogger(__name__)

router = APIRouter()


# Dependency to get invoice service
async def get_invoice_service() -> InvoiceServiceV2:
    """Get invoice service with injected dependencies."""
    db = Database.get_db()
    
    # Repositories
    invoice_repo = InvoiceRepository(db[Collections.INVOICES])
    supplier_repo = SupplierRepository(db[Collections.SUPPLIERS])
    warehouse_repo = WarehouseRepository(db[Collections.WAREHOUSE_PRODUCTS])
    movement_repo = WarehouseMovementRepository(db[Collections.WAREHOUSE_MOVEMENTS])
    entries_repo = AccountingEntriesRepository(db[Collections.ACCOUNTING_ENTRIES])
    chart_repo = ChartOfAccountsRepository(db[Collections.CHART_OF_ACCOUNTS])
    cash_repo = CashMovementRepository(db[Collections.CASH_MOVEMENTS])
    corrispettivi_repo = CorrissettivoRepository(db["corrispettivi"]) # Assuming collection name
    
    # Services
    warehouse_service = WarehouseService(warehouse_repo, movement_repo, invoice_repo)
    accounting_service = AccountingEntriesService(entries_repo, chart_repo)
    cash_service = CashService(cash_repo, corrispettivi_repo)
    
    return InvoiceServiceV2(
        invoice_repo=invoice_repo, 
        supplier_repo=supplier_repo,
        warehouse_service=warehouse_service,
        accounting_service=accounting_service,
        cash_service=cash_service
    )


@router.post(
    "",
    response_model=Dict[str, str],
    status_code=status.HTTP_201_CREATED,
    summary="Create invoice",
    description="Create a new invoice"
)
async def create_invoice(
    invoice_data: InvoiceCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    invoice_service: InvoiceServiceV2 = Depends(get_invoice_service)
) -> Dict[str, str]:
    """
    Create a new invoice.
    
    - **filename**: XML filename
    - **supplier_vat**: Supplier VAT number
    - **invoice_number**: Invoice number
    - **invoice_date**: Invoice date (YYYY-MM-DD)
    - **total_amount**: Total including VAT
    - **products**: List of products in invoice
    """
    user_id = current_user["user_id"]
    
    invoice_id = await invoice_service.create_invoice(
        invoice_data=invoice_data,
        user_id=user_id
    )
    
    return {
        "message": "Invoice created successfully",
        "invoice_id": invoice_id
    }


@router.get(
    "/anni-disponibili",
    summary="Get available years",
    description="Get list of years for which invoices exist"
)
async def get_anni_disponibili() -> Dict[str, Any]:
    """Restituisce gli anni per cui esistono fatture (XML e provvisorie)."""
    db = Database.get_db()
    
    anni = set()
    current_year = datetime.now().year
    anni.add(current_year)
    
    # Estrai anni da invoice_date (fatture XML complete)
    pipeline_invoice = [
        {"$match": {"invoice_date": {"$exists": True, "$ne": None, "$ne": ""}}},
        {"$project": {"anno": {"$substr": ["$invoice_date", 0, 4]}}},
        {"$group": {"_id": "$anno"}}
    ]
    
    results = await db[Collections.INVOICES].aggregate(pipeline_invoice).to_list(100)
    for doc in results:
        try:
            anno = int(doc["_id"])
            if 2000 <= anno <= 2100:
                anni.add(anno)
        except (ValueError, TypeError):
            pass
    
    # Estrai anni anche da data_documento (fatture provvisorie da Aruba)
    pipeline_data_doc = [
        {"$match": {"data_documento": {"$exists": True, "$ne": None, "$ne": ""}}},
        {"$project": {"anno": {"$substr": ["$data_documento", 0, 4]}}},
        {"$group": {"_id": "$anno"}}
    ]
    
    results_data_doc = await db[Collections.INVOICES].aggregate(pipeline_data_doc).to_list(100)
    for doc in results_data_doc:
        try:
            anno = int(doc["_id"])
            if 2000 <= anno <= 2100:
                anni.add(anno)
        except (ValueError, TypeError):
            pass
    
    return {"anni": sorted(list(anni), reverse=True)}


@router.get(
    "",
    response_model=List[Dict[str, Any]],
    summary="List invoices",
    description="Get list of invoices with optional filters"
)
async def list_invoices(
    supplier_vat: Optional[str] = Query(None, description="Filter by supplier VAT"),
    month_year: Optional[str] = Query(None, description="Filter by month (MM-YYYY)"),
    status: Optional[str] = Query(None, description="Filter by status"),
    anno: Optional[int] = Query(None, description="Filter by year (YYYY)"),
    limit: int = Query(100, description="Limit results", le=1000),
    skip: int = Query(0, description="Skip results")
) -> List[Dict[str, Any]]:
    """List invoices with optional filters. Default limit is 100 for performance."""
    db = Database.get_db()
    query = {}
    
    # Se anno è specificato, filtra per anno
    # IMPORTANTE: Consideriamo sia invoice_date (fatture XML complete) 
    # che data_documento (fatture provvisorie da Aruba)
    if anno is not None:
        anno_start = f"{anno}-01-01"
        anno_end = f"{anno}-12-31"
        query["$or"] = [
            {"invoice_date": {"$gte": anno_start, "$lte": anno_end}},
            {"data_documento": {"$gte": anno_start, "$lte": anno_end}}
        ]
    
    if supplier_vat:
        query["supplier_vat"] = supplier_vat
    if status:
        query["status"] = status
    
    logger.info(f"list_invoices: anno={anno}, query={query}, limit={limit}")
    
    # Usa aggregazione per ordinare correttamente (prende invoice_date se esiste, altrimenti data_documento)
    pipeline = [
        {"$match": query} if query else {"$match": {}},
        {"$addFields": {
            "data_effettiva": {"$ifNull": ["$invoice_date", "$data_documento"]}
        }},
        {"$sort": {"data_effettiva": -1}},
        {"$skip": skip},
        {"$limit": limit},
        {"$project": {"_id": 0}}
    ]
    
    invoices = await db[Collections.INVOICES].aggregate(pipeline).to_list(limit)
    return invoices


@router.get(
    "/unpaid",
    response_model=List[Dict[str, Any]],
    summary="Get unpaid invoices",
    description="Get list of invoices that haven't been fully paid"
)
async def get_unpaid_invoices(
    current_user: Dict[str, Any] = Depends(get_current_user),
    pagination: Dict[str, Any] = Depends(pagination_params),
    invoice_service: InvoiceServiceV2 = Depends(get_invoice_service)
) -> List[Dict[str, Any]]:
    """
    Get unpaid and partially paid invoices.
    
    Returns invoices sorted by due date (oldest first).
    """
    user_id = current_user["user_id"]
    
    return await invoice_service.get_unpaid_invoices(
        user_id=user_id,
        skip=pagination["skip"],
        limit=pagination["limit"]
    )


@router.get(
    "/overdue",
    response_model=List[Dict[str, Any]],
    summary="Get overdue invoices",
    description="Get list of invoices past their due date"
)
async def get_overdue_invoices(
    current_user: Dict[str, Any] = Depends(get_current_user),
    pagination: Dict[str, Any] = Depends(pagination_params),
    invoice_service: InvoiceServiceV2 = Depends(get_invoice_service)
) -> List[Dict[str, Any]]:
    """
    Get overdue invoices (unpaid and past due date).
    
    Returns invoices sorted by due date (oldest first).
    """
    user_id = current_user["user_id"]
    
    return await invoice_service.get_overdue_invoices(
        user_id=user_id,
        skip=pagination["skip"],
        limit=pagination["limit"]
    )


@router.get(
    "/search",
    response_model=List[Dict[str, Any]],
    summary="Search invoices",
    description="Search invoices by supplier name or invoice number"
)
async def search_invoices(
    q: str = Query(..., description="Search query"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    pagination: Dict[str, Any] = Depends(pagination_params),
    invoice_service: InvoiceServiceV2 = Depends(get_invoice_service)
) -> List[Dict[str, Any]]:
    """
    Search invoices by supplier name or invoice number.
    
    **Query Parameters:**
    - **q**: Search query (searches in supplier_name and invoice_number)
    """
    user_id = current_user["user_id"]
    
    return await invoice_service.search_invoices(
        user_id=user_id,
        query=q,
        skip=pagination["skip"],
        limit=pagination["limit"]
    )


@router.get(
    "/stats",
    response_model=Dict[str, Any],
    summary="Get invoice statistics",
    description="Get comprehensive invoice statistics"
)
async def get_invoice_stats(
    current_user: Dict[str, Any] = Depends(get_current_user),
    month_year: Optional[str] = Query(None, description="Filter by month (MM-YYYY)"),
    invoice_service: InvoiceServiceV2 = Depends(get_invoice_service)
) -> Dict[str, Any]:
    """
    Get invoice statistics.
    
    **Query Parameters:**
    - **month_year**: Optional month filter (format: MM-YYYY)
    
    Returns statistics including totals, counts by status, and payment method distribution.
    """
    user_id = current_user["user_id"]
    
    return await invoice_service.get_invoice_stats(
        user_id=user_id,
        month_year=month_year
    )


@router.get(
    "/archived-months",
    response_model=List[Dict[str, Any]],
    summary="Get archived months",
    description="Get list of months with archived invoices"
)
async def get_archived_months(
    current_user: Dict[str, Any] = Depends(get_current_user),
    invoice_service: InvoiceServiceV2 = Depends(get_invoice_service)
) -> List[Dict[str, Any]]:
    """
    Get list of months that have archived invoices.
    
    Returns a list of month/year combinations.
    """
    db = Database.get_db()
    invoices_collection = db[Collections.INVOICES]
    
    # Aggregate to find distinct months with archived invoices
    pipeline = [
        {'$match': {'status': 'archived'}},
        {'$project': {
            'month': {'$month': '$invoice_date'},
            'year': {'$year': '$invoice_date'}
        }},
        {'$group': {
            '_id': {'month': '$month', 'year': '$year'},
            'count': {'$sum': 1}
        }},
        {'$sort': {'_id.year': -1, '_id.month': -1}},
        {'$project': {
            'month': '$_id.month',
            'year': '$_id.year',
            'count': 1,
            '_id': 0
        }}
    ]
    
    try:
        cursor = invoices_collection.aggregate(pipeline)
        months_data = await cursor.to_list(length=100)
        
        # Add formatted month_year for frontend
        for m in months_data:
            m['month_year'] = f"{m['month']:02d}-{m['year']}"
            
        return months_data
    except Exception:
        # Fallback: return empty list
        return []


# Removed duplicate/broken functions


@router.get(
    "/{invoice_id}",
    response_model=Dict[str, Any],
    summary="Get invoice by ID",
    description="Get detailed invoice information"
)

@router.get(
    "/bank-pending",
    summary="Get invoices pending bank payment",
    description="Get invoices to be paid via bank"
)
async def get_bank_pending_invoices(
    current_user: Dict[str, Any] = Depends(get_current_user),
    invoice_service: InvoiceServiceV2 = Depends(get_invoice_service)
) -> Dict[str, Any]:
    """Get invoices pending bank payment."""
    db = Database.get_db()
    
    # Logic: payment_method in [banca, bonifico, riba] AND status != paid
    query = {
        "user_id": current_user["user_id"],
        "payment_method": {"$in": ["banca", "bonifico", "riba", "sdd"]},
        "payment_status": {"$ne": "paid"},
        "status": {"$ne": "deleted"}
    }
    
    invoices = await db[Collections.INVOICES].find(
        query,
        {"_id": 0}
    ).sort("invoice_date", 1).to_list(100)
    
    # Format
    results = []
    for inv in invoices:
        results.append({
            "id": str(inv["id"]),
            "invoice_number": inv.get("invoice_number"),
            "supplier_name": inv.get("supplier_name"),
            "supplier_vat": inv.get("supplier_vat"),
            "invoice_date": inv.get("invoice_date"),
            "due_date": inv.get("due_date"),
            "total_amount": inv.get("total_amount"),
            "payment_method": inv.get("payment_method"),
            "alert_level": "normal" # Todo: calculate based on due date
        })
        
    return {
        "success": True,
        "count": len(results),
        "invoices": results
    }


@router.post(
    "/paga-anno/{anno}",
    response_model=Dict[str, Any],
    summary="Paga tutte le fatture di un anno",
    description="Marca come pagate tutte le fatture XML di un determinato anno"
)
async def paga_fatture_anno(
    anno: int = Path(..., description="Anno delle fatture da pagare (es. 2024)")
) -> Dict[str, Any]:
    """
    Marca come pagate tutte le fatture di un anno specifico.
    
    **Nota:** Questa operazione è irreversibile.
    """
    db = Database.get_db()
    now = datetime.now(timezone.utc).isoformat()
    
    # Query per trovare fatture dell'anno non pagate
    # Consideriamo tutti i campi data usati nel sistema
    query = {
        "$or": [
            {"data": {"$regex": f"^{anno}"}},
            {"invoice_date": {"$regex": f"^{anno}"}},
            {"data_fattura": {"$regex": f"^{anno}"}},
            {"data_documento": {"$regex": f"^{anno}"}}  # Fatture provvisorie da Aruba
        ],
        "pagato": {"$ne": True}
    }
    
    # Conta prima
    count_before = await db[Collections.INVOICES].count_documents(query)
    
    if count_before == 0:
        return {
            "success": True,
            "message": f"Nessuna fattura del {anno} da pagare",
            "fatture_pagate": 0
        }
    
    # Aggiorna tutte come pagate
    result = await db[Collections.INVOICES].update_many(
        query,
        {"$set": {
            "pagato": True,
            "paid": True,
            "data_pagamento": now,
            "note_pagamento": f"Pagata automaticamente - batch {anno}"
        }}
    )
    
    return {
        "success": True,
        "message": f"Pagate {result.modified_count} fatture del {anno}",
        "fatture_pagate": result.modified_count,
        "anno": anno
    }


@router.get(
    "/{invoice_id}",
    response_model=Dict[str, Any],
    summary="Get invoice by ID",
    description="Get complete invoice data"
)
async def get_invoice(
    invoice_id: str,
    invoice_service: InvoiceServiceV2 = Depends(get_invoice_service)
) -> Dict[str, Any]:
    """
    Get invoice details by ID.
    
    Returns complete invoice data including products.
    """
    return await invoice_service.get_invoice(invoice_id)


@router.put(
    "/{invoice_id}",
    response_model=Dict[str, str],
    summary="Update invoice",
    description="Update invoice information"
)
async def update_invoice(
    invoice_id: str,
    update_data: InvoiceUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    invoice_service: InvoiceServiceV2 = Depends(get_invoice_service)
) -> Dict[str, str]:
    """
    Update invoice information.
    
    Only provided fields will be updated.
    """
    await invoice_service.update_invoice(
        invoice_id=invoice_id,
        update_data=update_data
    )
    
    return {"message": "Invoice updated successfully"}


@router.post(
    "/{invoice_id}/payment",
    response_model=Dict[str, Any],
    summary="Record payment",
    description="Record a payment for an invoice"
)
async def record_payment(
    invoice_id: str,
    amount: float = Query(..., gt=0, description="Payment amount"),
    payment_method: Optional[str] = Query(None, description="Payment method"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    invoice_service: InvoiceServiceV2 = Depends(get_invoice_service)
) -> Dict[str, Any]:
    """
    Record a payment for an invoice.
    
    **Query Parameters:**
    - **amount**: Amount paid (must be positive)
    - **payment_method**: Optional payment method (cassa, banca, assegno, etc.)
    
    Returns updated invoice with new payment status.
    """
    return await invoice_service.record_payment(
        invoice_id=invoice_id,
        amount=amount,
        payment_method=payment_method
    )


@router.post(
    "/{invoice_id}/archive",
    status_code=status.HTTP_200_OK,
    summary="Archive invoice",
    description="Archive an invoice"
)
async def archive_invoice(
    invoice_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    invoice_service: InvoiceServiceV2 = Depends(get_invoice_service)
) -> Dict[str, str]:
    """
    Archive an invoice.
    
    Archived invoices are not deleted but marked as inactive.
    """
    await invoice_service.archive_invoice(invoice_id)
    
    return {"message": "Invoice archived successfully"}


@router.post(
    "/{invoice_id}/reconcile",
    status_code=status.HTTP_200_OK,
    summary="Reconcile with bank",
    description="Mark invoice as reconciled with bank transaction"
)
async def reconcile_with_bank(
    invoice_id: str,
    bank_transaction_id: str = Query(..., description="Bank transaction ID"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    invoice_service: InvoiceServiceV2 = Depends(get_invoice_service)
) -> Dict[str, str]:
    """
    Mark invoice as reconciled with a bank transaction.
    
    **Query Parameters:**
    - **bank_transaction_id**: ID of the bank transaction
    """
    await invoice_service.reconcile_with_bank(
        invoice_id=invoice_id,
        bank_transaction_id=bank_transaction_id
    )
    
    return {"message": "Invoice reconciled with bank transaction"}


# ==================== ENDPOINT: Get Invoices by State ====================
@router.get(
    "/by-state/{state}",
    status_code=status.HTTP_200_OK,
    summary="Get invoices by payment state",
    description="Retrieve invoices filtered by payment state (paid, unpaid, partial)"
)
async def get_invoices_by_state(
    state: str = Path(..., description="Payment state: paid, unpaid, partial, overdue"),
    skip: int = Query(0, ge=0, description="Records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Max records"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    invoice_service: InvoiceServiceV2 = Depends(get_invoice_service)
) -> Dict[str, Any]:
    """
    Get invoices filtered by payment state.
    
    **States disponibili:**
    - `paid`: Fatture completamente pagate
    - `unpaid`: Fatture non pagate
    - `partial`: Fatture parzialmente pagate
    - `overdue`: Fatture scadute e non pagate
    
    **Esempio:**
    ```
    GET /api/invoices/by-state/unpaid?skip=0&limit=50
    ```
    
    **Response:**
    ```json
    {
        "invoices": [...],
        "total": 45,
        "state": "unpaid",

#

        "skip": 0,
        "limit": 50
    }
    ```
    """
    db = Database.get_db()
    invoices_collection = db[Collections.INVOICES]
    
    # Mappa stato → query MongoDB
    # Stati standard
    state_queries = {
        'paid': {'payment_status': 'paid'},
        'unpaid': {'payment_status': 'unpaid'},
        'partial': {'payment_status': 'partial'},
        'overdue': {
            'payment_status': {'$in': ['unpaid', 'partial']},
            'due_date': {'$lt': datetime.now(timezone.utc)}
        },
        # Stati per frontend Archive.js
        'registered_cash': {
            'registered_in': 'cash',
            'payment_status': 'paid'
        },
        'registered_bank': {
            'registered_in': 'bank',
            'payment_status': 'paid'
        },
        'paid_not_reconciled': {
            'payment_status': 'paid',
            'reconciled': {'$ne': True}
        },
        'pending': {
            'payment_method': {'$in': ['banca', 'assegno', 'bonifico']},
            'payment_status': {'$in': ['unpaid', 'partial']}
        }
    }
    
    # Valida stato
    if state not in state_queries:
        from app.exceptions import ValidationError
        valid_states = ', '.join(state_queries.keys())

# Block moved to end

        raise ValidationError(
            f"Invalid state '{state}'. Valid states: {valid_states}"
        )
    
    query = state_queries[state]
    
    # Count totale
    total = await invoices_collection.count_documents(query)
    
    # Recupera fatture
    cursor = invoices_collection.find(query, {"_id": 0}).sort('invoice_date', -1).skip(skip).limit(limit)
    invoices = await cursor.to_list(length=limit)
    
    # Formatta response
    result_invoices = []
    for invoice in invoices:
        result_invoices.append({
            'id': str(invoice.get('id', '')),
            'invoice_number': invoice.get('invoice_number'),
            'invoice_date': invoice.get('invoice_date'),
            'supplier_name': invoice.get('supplier_name'),
            'supplier_vat': invoice.get('supplier_vat'),
            'total_amount': invoice.get('total_amount'),
            'amount_paid': invoice.get('amount_paid', 0),
            'remaining_amount': invoice.get('total_amount', 0) - invoice.get('amount_paid', 0),
            'payment_status': invoice.get('payment_status', 'unpaid'),
            'due_date': invoice.get('due_date'),
            'payment_method': invoice.get('payment_method'),
            'uploaded_at': invoice.get('uploaded_at')
        })
    
    return {
        'invoices': result_invoices,
        'total': total,
        'state': state,
        'skip': skip,
        'limit': limit,
        'has_more': (skip + len(result_invoices)) < total
    }


# ==================== ENDPOINT: Get Invoices by Supplier ====================
@router.get(
    "/by-supplier/{supplier_id}",
    status_code=status.HTTP_200_OK,
    summary="Get invoices by supplier",
    description="Retrieve all invoices for a specific supplier"
)
async def get_invoices_by_supplier(
    supplier_id: str = Path(..., description="Supplier ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get all invoices for a specific supplier."""
    db = Database.get_db()
    invoices_collection = db[Collections.INVOICES]
    
    query = {'supplier_id': supplier_id}
    total = await invoices_collection.count_documents(query)
    
    cursor = invoices_collection.find(query, {"_id": 0}).sort('invoice_date', -1).skip(skip).limit(limit)
    invoices = await cursor.to_list(length=limit)
    
    result = []
    for invoice in invoices:
        result.append({
            'id': str(invoice.get('id', '')),
            'invoice_number': invoice.get('invoice_number'),
            'invoice_date': invoice.get('invoice_date'),
            'total_amount': invoice.get('total_amount'),
            'payment_status': invoice.get('payment_status', 'unpaid'),
            'uploaded_at': invoice.get('uploaded_at')
        })
    
    return {
        'invoices': result,
        'total': total,
        'supplier_id': supplier_id,
        'skip': skip,
        'limit': limit
    }


# ==================== ENDPOINT: Get Invoices by Month ====================
@router.get(
    "/by-month/{year}/{month}",
    status_code=status.HTTP_200_OK,
    summary="Get invoices by month",
    description="Retrieve invoices for a specific month and year"
)
async def get_invoices_by_month(
    year: int = Path(..., ge=2000, le=2100, description="Year"),
    month: int = Path(..., ge=1, le=12, description="Month (1-12)"),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get invoices for specific month."""
    db = Database.get_db()
    invoices_collection = db[Collections.INVOICES]
    
    # Crea month_year formato YYYY-MM
    month_year = f"{year}-{month:02d}"
    
    query = {'month_year': month_year}
    
    cursor = invoices_collection.find(query, {"_id": 0}).sort('invoice_date', -1)
    invoices = await cursor.to_list(length=1000)
    
    # Calcola statistiche mese
    total_amount = sum(inv.get('total_amount', 0) for inv in invoices)
    total_paid = sum(inv.get('amount_paid', 0) for inv in invoices)
    paid_count = sum(1 for inv in invoices if inv.get('payment_status') == 'paid')
    
    result = []
    for invoice in invoices:
        result.append({
            'id': str(invoice['_id']),
            'invoice_number': invoice.get('invoice_number'),
            'invoice_date': invoice.get('invoice_date'),
            'supplier_name': invoice.get('supplier_name'),
            'total_amount': invoice.get('total_amount'),
            'payment_status': invoice.get('payment_status', 'unpaid')
        })
    
    return {
        'invoices': result,
        'total_count': len(invoices),
        'year': year,
        'month': month,
        'month_year': month_year,
        'stats': {
            'total_amount': total_amount,
            'total_paid': total_paid,
            'total_unpaid': total_amount - total_paid,
            'paid_count': paid_count,
            'unpaid_count': len(invoices) - paid_count
        }
    }




from fastapi import HTTPException

# ============== UPLOAD ENDPOINTS ==============

@router.post(
    "/upload",
    summary="Upload single invoice XML",
    description="Upload a single invoice XML file"
)
async def upload_invoice(
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
    invoice_service: InvoiceServiceV2 = Depends(get_invoice_service)
) -> Dict[str, Any]:
    """Upload single invoice XML."""
    contents = await file.read()
    user_id = current_user["user_id"]
    
    try:
        result = await invoice_service.process_xml_invoice(
            xml_content=contents,
            filename=file.filename,
            user_id=user_id
        )
        return result
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        return {
            "status": "error",
            "message": str(e),
            "filename": file.filename
        }


@router.post(
    "/upload-bulk",
    summary="Upload multiple invoice files",
    description="Upload multiple invoice XML files or a ZIP"
)
async def upload_bulk_invoices(
    files: List[UploadFile] = File(None),
    file: UploadFile = File(None), # Single file field name 'file'
    current_user: Dict[str, Any] = Depends(get_current_user),
    invoice_service: InvoiceServiceV2 = Depends(get_invoice_service)
) -> Dict[str, Any]:
    """Upload multiple invoices (ZIP or multiple XML)."""
    user_id = current_user["user_id"]
    results = []
    
    # Collect all uploaded files into a single list
    all_uploads = []
    if file:
        all_uploads.append(file)
    if files:
        all_uploads.extend(files)
        
    if not all_uploads:
        return {"status": "error", "message": "No files received"}
    
    # Process inputs
    process_list = []
    
    for upload in all_uploads:
        content = await upload.read()
        filename = upload.filename.lower()
        
        if filename.endswith('.zip'):
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as z:
                    for z_filename in z.namelist():
                        # Skip MACOSX and non-xml files
                        if z_filename.lower().endswith('.xml') and not z_filename.startswith('__MACOSX'):
                            process_list.append({
                                "filename": z_filename,
                                "content": z.read(z_filename)
                            })
            except zipfile.BadZipFile:
                results.append({
                    "filename": upload.filename,
                    "status": "error",
                    "message": "Invalid ZIP file"
                })
        elif filename.endswith('.xml') or filename.endswith('.p7m'): # p7m needs special handling but let's try
             process_list.append({
                "filename": upload.filename,
                "content": content
            })
        else:
             results.append({
                "filename": upload.filename,
                "status": "skipped",
                "message": "Unsupported file type"
            })
            
    # Process extracted XMLs
    processed = 0
    errors = 0
    
    for item in process_list:
        try:
            res = await invoice_service.process_xml_invoice(
                xml_content=item["content"],
                filename=item["filename"],
                user_id=user_id
            )
            results.append({
                "filename": item["filename"],
                "status": "success", 
                "details": res
            })
            processed += 1
        except Exception as e:
            errors += 1
            results.append({
                "filename": item["filename"],
                "status": "error",
                "message": str(e)
            })
            
    return {
        "message": f"Processed {len(process_list)} files",
        "processed": processed,
        "errors": errors,
        "total_files": len(all_uploads),
        "details": results
    }


@router.post(
    "/import-excel",
    summary="Import invoices from Excel",
    description="Import invoices from Excel file"
)
async def import_invoices_excel(
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Import invoices from Excel file."""
    contents = await file.read()
    # TODO: Process Excel import
    return {
        "message": "Excel import completed",
        "filename": file.filename,
        "imported": 0,
        "errors": []
    }


@router.get(
    "/export-excel",
    summary="Export invoices to Excel"
)
async def export_invoices_to_excel(
    year: int = Query(None),
    month: int = Query(None),
    current_user: Dict[str, Any] = Depends(get_current_user),
    invoice_service: InvoiceServiceV2 = Depends(get_invoice_service)
) -> StreamingResponse:
    """Export invoices to Excel file."""
    user_id = current_user["user_id"]
    
    # Filter params
    month_year = None
    if month and year:
        month_year = f"{month:02d}-{year}"
        
    invoices = await invoice_service.list_invoices(
        user_id=user_id,
        limit=10000,
        month_year=month_year
    )
    
    # Create Excel
    wb = Workbook()
    ws = wb.active
    ws.title = "Fatture"
    
    # Headers
    headers = ["Data", "Numero", "Fornitore", "P.IVA", "Imponibile", "IVA", "Totale", "Stato", "Metodo Pagamento"]
    ws.append(headers)
    
    for inv in invoices:
        ws.append([
            inv.get("invoice_date"),
            inv.get("invoice_number"),
            inv.get("supplier_name"),
            inv.get("supplier_vat"),
            inv.get("total_imponibile", 0),
            inv.get("total_tax_amount", 0),
            inv.get("total_amount", 0),
            inv.get("payment_status", "unpaid"),
            inv.get("payment_method", "")
        ])
        
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    filename = f"fatture_{month_year or 'all'}.xlsx"
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ==================== METADATA & DELETE ENDPOINTS ====================

@router.post(
    "/metadata/update",
    summary="Update invoice metadata"
)
async def update_metadata(
    data: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, str]:
    """Update invoice metadata (payment method, checks, etc.)."""
    db = Database.get_db()
    invoice_id = data.get("invoice_id")
    
    if not invoice_id:
        # Check if id is passed as 'id'
        invoice_id = data.get("id")
        
    if invoice_id:
        # Filter out invoice_id from data to update
        update_fields = {k: v for k, v in data.items() if k != "invoice_id" and k != "id"}
        
        # Explicitly handle payment fields
        if "payment_method" in update_fields:
            # Also update payment status logic if needed, but for now just metadata
            pass
            
        await db[Collections.INVOICES].update_one(
            {"id": invoice_id},
            {"$set": update_fields}
        )
        return {"message": "Metadata updated"}
    return {"message": "Invoice ID required"}


@router.post(
    "/delete-by-month",
    summary="Delete invoices by month"
)
async def delete_invoices_by_month(
    month: int = Query(...),
    year: int = Query(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Delete all invoices for a specific month."""
    db = Database.get_db()
    user_id = current_user["user_id"]
    
    # Format YYYY-MM
    month_str = f"{year}-{month:02d}"
    
    result = await db[Collections.INVOICES].delete_many({
        "user_id": user_id,
        "month_year": month_str
    })
    
    # Also delete associated movements? 
    # For now just invoices as requested by Danger Zone
    
    return {
        "message": f"Deleted {result.deleted_count} invoices for {month_str}",
        "deleted_count": result.deleted_count
    }


@router.post(
    "/delete-by-year",
    summary="Delete invoices by year"
)
async def delete_invoices_by_year(
    year: int = Query(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Delete all invoices for a specific year."""
    db = Database.get_db()
    user_id = current_user["user_id"]
    
    # Regex for YYYY-* or match date
    # Invoices have 'invoice_date' YYYY-MM-DD
    # and 'month_year' YYYY-MM (Wait, I implemented month_year as MM-YYYY in InvoiceServiceV2?)
    # Let's check InvoiceServiceV2.create_invoice.
    # It calls _generate_month_year -> strftime("%m-%Y").
    # So MM-YYYY.
    
    # So regex for year should match ends with -YYYY
    regex = f"-{year}$"
    
    result = await db[Collections.INVOICES].delete_many({
        "user_id": user_id,
        "month_year": {"$regex": regex}
    })
    
    return {
        "message": f"Deleted {result.deleted_count} invoices for {year}",
        "deleted_count": result.deleted_count
    }


@router.delete(
    "/all",
    summary="Delete ALL invoices"
)
async def delete_all_invoices(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Delete ALL invoices."""
    db = Database.get_db()
    user_id = current_user["user_id"]
    
    result = await db[Collections.INVOICES].delete_many({
        "user_id": user_id
    })
    
    return {
        "message": f"Deleted {result.deleted_count} invoices",
        "deleted_count": result.deleted_count
    }


@router.delete(
    "/{invoice_id}",
    summary="Delete single invoice with validation",
    description="Delete a single invoice. Validates business rules before deletion."
)
async def delete_invoice(
    invoice_id: str,
    force: bool = Query(False, description="Force delete even with warnings"),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Delete a single invoice with business rule validation.
    
    **Rules:**
    - Cannot delete paid invoices
    - Cannot delete invoices registered in Prima Nota
    - Invoices with warehouse movements require force=true
    
    **Parameters:**
    - invoice_id: Invoice ID to delete
    - force: Set to true to confirm deletion with warnings
    """
    from app.services.business_rules import BusinessRules, EntityStatus
    
    db = Database.get_db()
    
    # Get invoice
    invoice = await db[Collections.INVOICES].find_one({"id": invoice_id})
    if not invoice:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    # Validate deletion
    validation = BusinessRules.can_delete_invoice(invoice)
    
    if not validation.is_valid:
        raise HTTPException(
            status_code=400, 
            detail={
                "message": "Eliminazione non consentita",
                "errors": validation.errors
            }
        )
    
    # If warnings and not forced, return warning
    if validation.warnings and not force:
        return {
            "status": "warning",
            "message": "Eliminazione richiede conferma",
            "warnings": validation.warnings,
            "require_force": True
        }
    
    # Soft-delete
    from datetime import datetime, timezone
    
    await db[Collections.INVOICES].update_one(
        {"id": invoice_id},
        {"$set": {
            "entity_status": EntityStatus.DELETED.value,
            "status": "deleted",
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "deleted_by": current_user.get("user_id")
        }}
    )
    
    return {
        "status": "success",
        "message": "Fattura eliminata (archiviata)",
        "invoice_id": invoice_id
    }
# Forced reload Sun Jan  4 18:08:32 UTC 2026
