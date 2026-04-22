"""
Invoice service.
Handles invoice import, management, and business logic.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, date, timezone
import uuid
import hashlib
import logging

from app.repositories import InvoiceRepository, SupplierRepository
from app.exceptions import (
    NotFoundError,
    DuplicateError,
    ValidationError,
    FileProcessingError
)
from app.models import InvoiceCreate, InvoiceUpdate
from app.utils.invoice_xml_parser import InvoiceXMLParser

logger = logging.getLogger(__name__)


class InvoiceService:
    """Service for invoice operations."""
    
    def __init__(
        self,
        invoice_repo: InvoiceRepository,
        supplier_repo: SupplierRepository,
        warehouse_service: Optional[Any] = None,
        accounting_service: Optional[Any] = None,
        cash_service: Optional[Any] = None
    ):
        """
        Initialize invoice service.
        
        Args:
            invoice_repo: Invoice repository instance
            supplier_repo: Supplier repository instance
            warehouse_service: Optional WarehouseService for stock updates
            accounting_service: Optional AccountingEntriesService for accounting
            cash_service: Optional CashService for payments
        """
        self.invoice_repo = invoice_repo
        self.supplier_repo = supplier_repo
        self.warehouse_service = warehouse_service
        self.accounting_service = accounting_service
        self.cash_service = cash_service
    
    async def process_xml_invoice(
        self,
        xml_content: bytes,
        filename: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Process XML invoice file: parse, save, and propagate data.
        
        Args:
            xml_content: XML file content
            filename: Original filename
            user_id: User ID
            
        Returns:
            Dict with results (invoice_id, movements, etc.)
        """
        logger.info(f"Processing XML invoice: {filename}")
        
        # 1. Parse XML
        try:
            parser = InvoiceXMLParser(xml_content)
            parsed_data = parser.parse()
        except Exception as e:
            logger.error(f"XML parsing failed: {e}")
            raise FileProcessingError(f"Failed to parse XML: {str(e)}")
        
        # Extract data with safe access
        supplier_data = parsed_data.get("supplier", {})
        invoice_data = parsed_data.get("invoice", {})
        products_data = parsed_data.get("products", [])
        payment_data = parsed_data.get("payment", {})
        
        # 2. Check duplicate (hash)
        xml_content = parsed_data.get("xml_content", "")
        content_hash = self._generate_content_hash(xml_content)
        existing = await self.invoice_repo.find_by_hash(content_hash)
        if existing:
            logger.warning(f"Duplicate invoice detected: {existing.get('id')}")
            return {
                "status": "duplicate",
                "invoice_id": str(existing.get("id", "")),
                "message": "Invoice already exists"
            }
            
        # 3. Create Invoice Object
        # Prepare products list
        products = []
        total_tax_amount = 0.0
        
        for p in products_data:
            if not isinstance(p, dict):
                continue
            total_price = float(p.get("total_price") or 0)
            vat_rate = float(p.get("vat_rate") or 0)
            tax_amount = total_price * (vat_rate / 100) if vat_rate else 0.0
            total_tax_amount += tax_amount
            products.append({
                "codice": "", # Optional
                "descrizione": p.get("description", ""),
                "quantita": p.get("quantity", 0),
                "prezzo_unitario": p.get("unit_price", 0),
                "sconto": 0.0,
                "prezzo_totale": total_price,
                "aliquota_iva": vat_rate
            })
            
        invoice_doc = {
            "user_id": user_id,
            "filename": filename,
            "content_hash": content_hash,
            "supplier_name": supplier_data["name"],
            "supplier_vat": supplier_data["vat_number"],
            "supplier_address": supplier_data["address"],
            "supplier_city": supplier_data["city"],
            "invoice_number": invoice_data["number"],
            "invoice_date": invoice_data["date"].isoformat() if invoice_data["date"] else datetime.now(timezone.utc).date().isoformat(),
            "month_year": self._generate_month_year(invoice_data["date"] or datetime.now(timezone.utc).date()),
            "total_amount": invoice_data["total_amount"],
            "total_tax_amount": total_tax_amount,
            "total_imponibile": invoice_data["total_amount"] - total_tax_amount,
            "products": products,
            "status": "active",
            "payment_status": "unpaid", # Default
            "uploaded_at": datetime.now(timezone.utc),
            "processed_at": datetime.now(timezone.utc),
            "xml_content": parsed_data["xml_content"]
        }
        
        # Check payment due date
        if payment_data and payment_data["due_date"]:
            invoice_doc["due_date"] = payment_data["due_date"].isoformat()
        
        # 4. Save Invoice
        invoice_id = await self.invoice_repo.create(invoice_doc)
        logger.info(f"Invoice created in DB: {invoice_id}")
        
        # 5. Update Supplier Stats
        if invoice_data["date"]:
             await self.supplier_repo.update_statistics(
                supplier_vat=supplier_data["vat_number"],
                invoice_amount=invoice_data["total_amount"],
                invoice_date=datetime.combine(invoice_data["date"], datetime.min.time())
            )
            
        results = {
            "status": "created",
            "invoice_id": invoice_id,
            "warehouse_movements": 0,
            "accounting_entry": None
        }
        
        # 6. Propagate to Warehouse
        if self.warehouse_service:
            try:
                movements = await self.warehouse_service.add_stock_from_invoice(
                    invoice_id=invoice_id,
                    user_id=user_id
                )
                results["warehouse_movements"] = len(movements)
                logger.info(f"Warehouse updated: {len(movements)} movements")
            except Exception as e:
                logger.error(f"Failed to update warehouse for invoice {invoice_id}: {e}")
                # Don't fail the whole upload
        
        # 7. Propagate to Accounting (Prima Nota)
        if self.accounting_service:
            try:
                # Create basic accounting entry
                entry_data = {
                    "date": invoice_doc["invoice_date"],
                    "description": f"Fattura acquisto n.{invoice_doc['invoice_number']} - {invoice_doc['supplier_name']}",
                    "document_number": invoice_doc["invoice_number"],
                    "entry_type": "acquisto",
                    "amount": invoice_doc["total_amount"],
                    "lines": [
                        # For now, simple entry: Costo vs Fornitore
                        {
                            "account_code": "3.1.01", # Merci c/acquisti (Example)
                            "account_name": "Merci c/acquisti",
                            "debit": invoice_doc["total_imponibile"],
                            "credit": 0
                        },
                        {
                            "account_code": "2.1.01", # IVA su acquisti
                            "account_name": "IVA su acquisti",
                            "debit": invoice_doc["total_tax_amount"],
                            "credit": 0
                        },
                        {
                            "account_code": "1.2.01", # Debiti v/fornitori
                            "account_name": "Debiti v/fornitori",
                            "debit": 0,
                            "credit": invoice_doc["total_amount"]
                        }
                    ]
                }
                
                entry = await self.accounting_service.create_entry(entry_data, user_id)
                results["accounting_entry"] = str(entry.get("id"))
                logger.info(f"Accounting entry created: {entry.get('id')}")
                
            except Exception as e:
                logger.error(f"Failed to create accounting entry: {e}")
                # Don't fail the whole upload

        return results

    def _generate_content_hash(self, xml_content: str) -> str:
        """
        Generate hash for duplicate detection.
        
        Args:
            xml_content: XML content string
            
        Returns:
            SHA256 hash
        """
        return hashlib.sha256(xml_content.encode('utf-8')).hexdigest()
    
    def _generate_month_year(self, invoice_date: date) -> str:
        """
        Generate month-year string from date.
        
        Args:
            invoice_date: Invoice date
            
        Returns:
            Month-year string (format: MM-YYYY)
        """
        return invoice_date.strftime("%m-%Y")
    
    async def create_invoice(
        self,
        invoice_data: InvoiceCreate,
        user_id: str
    ) -> str:
        """
        Create a new invoice.
        
        Args:
            invoice_data: Invoice creation data
            user_id: User ID
            
        Returns:
            Created invoice ID
            
        Raises:
            DuplicateError: If invoice with same hash already exists
            ValidationError: If data is invalid
        """
        logger.info(f"Creating invoice: {invoice_data.invoice_number}")
        
        # Generate content hash if XML provided
        content_hash = None
        if invoice_data.xml_content:
            content_hash = self._generate_content_hash(invoice_data.xml_content)
            
            # Check for duplicate
            existing = await self.invoice_repo.find_by_hash(content_hash)
            if existing:
                raise DuplicateError(
                    "Invoice",
                    "content_hash",
                    f"Invoice already exists (ID: {existing['id']})"
                )
        
        # Generate month-year
        month_year = self._generate_month_year(invoice_data.invoice_date)
        
        # Create invoice document
        invoice_doc = invoice_data.model_dump()
        invoice_doc.update({
            "user_id": user_id,
            "month_year": month_year,
            "content_hash": content_hash,
            "status": "active",
            "payment_status": "unpaid",
            "amount_paid": 0.0,
            "bank_reconciled": False,
            "uploaded_at": datetime.now(timezone.utc),
            "processed_at": datetime.now(timezone.utc)
        })
        
        # Save invoice
        invoice_id = await self.invoice_repo.create(invoice_doc)
        
        # Update supplier statistics
        await self.supplier_repo.update_statistics(
            supplier_vat=invoice_data.supplier_vat,
            invoice_amount=invoice_data.total_amount,
            invoice_date=datetime.combine(invoice_data.invoice_date, datetime.min.time())
        )
        
        logger.info(f"✅ Invoice created: {invoice_id}")
        return invoice_id
    
    async def get_invoice(self, invoice_id: str) -> Dict[str, Any]:
        """
        Get invoice by ID.
        
        Args:
            invoice_id: Invoice ID
            
        Returns:
            Invoice document
            
        Raises:
            NotFoundError: If invoice not found
        """
        invoice = await self.invoice_repo.find_by_id(invoice_id)
        
        if not invoice:
            raise NotFoundError("Invoice", invoice_id)
        
        return invoice
    
    async def update_invoice(
        self,
        invoice_id: str,
        update_data: InvoiceUpdate
    ) -> bool:
        """
        Update invoice.
        
        Args:
            invoice_id: Invoice ID
            update_data: Update data
            
        Returns:
            True if updated successfully
            
        Raises:
            NotFoundError: If invoice not found
        """
        logger.info(f"Updating invoice: {invoice_id}")
        
        # Verify invoice exists
        invoice = await self.get_invoice(invoice_id)
        
        # Update only provided fields
        update_dict = update_data.model_dump(exclude_unset=True)
        
        if not update_dict:
            return True  # Nothing to update
        
        success = await self.invoice_repo.update(invoice_id, update_dict)
        
        if success:
            logger.info(f"✅ Invoice updated: {invoice_id}")
        
        return success
    
    async def list_invoices(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100,
        supplier_vat: Optional[str] = None,
        month_year: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List invoices with optional filters.
        
        Args:
            user_id: User ID
            skip: Number to skip (pagination)
            limit: Maximum number to return
            supplier_vat: Filter by supplier VAT
            month_year: Filter by month-year (MM-YYYY)
            status: Filter by status
            
        Returns:
            List of invoices
        """
        if supplier_vat:
            return await self.invoice_repo.find_by_supplier(
                supplier_vat=supplier_vat,
                skip=skip,
                limit=limit
            )
        
        if month_year:
            return await self.invoice_repo.find_by_month(
                month_year=month_year,
                user_id=user_id,
                skip=skip,
                limit=limit,
                status=status
            )
        
        # Default: all invoices for user
        filter_query = {"user_id": user_id}
        
        if status:
            filter_query["status"] = status
        
        return await self.invoice_repo.find_all(
            filter_query=filter_query,
            skip=skip,
            limit=limit,
            sort=[("invoice_date", -1)]
        )
    
    async def get_unpaid_invoices(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get unpaid invoices.
        
        Args:
            user_id: User ID
            skip: Number to skip
            limit: Maximum number to return
            
        Returns:
            List of unpaid invoices
        """
        return await self.invoice_repo.find_unpaid(
            user_id=user_id,
            skip=skip,
            limit=limit
        )
    
    async def get_overdue_invoices(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get overdue invoices.
        
        Args:
            user_id: User ID
            skip: Number to skip
            limit: Maximum number to return
            
        Returns:
            List of overdue invoices
        """
        return await self.invoice_repo.find_overdue(
            user_id=user_id,
            skip=skip,
            limit=limit
        )
    
    async def record_payment(
        self,
        invoice_id: str,
        amount: float,
        payment_method: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Record payment for an invoice.
        
        Args:
            invoice_id: Invoice ID
            amount: Amount paid
            payment_method: Payment method used
            
        Returns:
            Updated invoice with payment info
            
        Raises:
            NotFoundError: If invoice not found
            ValidationError: If amount is invalid
        """
        logger.info(f"Recording payment for invoice {invoice_id}: €{amount:.2f}")
        
        # Get invoice
        invoice = await self.get_invoice(invoice_id)
        
        # Validate amount
        if amount < 0:
            raise ValidationError("Payment amount cannot be negative")
        
        total_amount = invoice["total_amount"]
        current_paid = invoice.get("amount_paid", 0.0)
        
        # Calculate new total paid
        new_total_paid = current_paid + amount
        
        if new_total_paid > total_amount:
            raise ValidationError(
                f"Payment amount exceeds invoice total. "
                f"Remaining: €{total_amount - current_paid:.2f}"
            )
        
        # Update payment status
        success = await self.invoice_repo.update_payment_status(
            invoice_id=invoice_id,
            amount_paid=new_total_paid,
            payment_method=payment_method
        )
        
        if not success:
            raise Exception("Failed to update payment status")
        
        # Return updated invoice
        updated_invoice = await self.get_invoice(invoice_id)
        
        # E: Propaga pagamento su prima_nota e scadenzario
        try:
            metodi_cassa = ["contanti", "cassa", "contante", "cash"]
            collection_pn = "prima_nota_cassa" if (payment_method or "").lower() in metodi_cassa \
                else "prima_nota_banca"
            fattura = await self.db["invoices"].find_one({"id": invoice_id}, {"_id": 0})
            if fattura:
                mov = {
                    "id": str(uuid.uuid4()),
                    "tipo": "uscita",
                    "importo": amount,
                    "data": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "descrizione": f"Pag. fatt. {fattura.get('invoice_number','N/D')} - {(fattura.get('supplier_name') or '')[:30]}",
                    "categoria": "Pagamento fornitore",
                    "source": "pagamento_fattura",
                    "riferimento_id": invoice_id,
                    "fornitore_piva": fattura.get("supplier_vat") or fattura.get("fornitore_partita_iva"),
                    "metodo_pagamento": payment_method,
                    "riconciliato": False,
                    "anno": datetime.now().year,
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
                await self.db[collection_pn].insert_one(mov.copy())
                await self.db["scadenziario_fornitori"].update_many(
                    {"fattura_id": invoice_id, "pagato": {"$ne": True}},
                    {"$set": {"pagato": True, "data_pagamento": mov["data"],
                              "metodo_pagamento": payment_method,
                              "prima_nota_id": mov["id"],
                              "updated_at": datetime.now(timezone.utc).isoformat()}}
                )
        except Exception as e:
            logger.warning(f"Propagazione prima nota fallita per {invoice_id}: {e}")
        
        logger.info(
            f"✅ Payment recorded: {invoice_id} - "
            f"€{new_total_paid:.2f}/{total_amount:.2f} "
            f"({updated_invoice['payment_status']})"
        )
        
        return updated_invoice
    
    async def archive_invoice(self, invoice_id: str) -> bool:
        """
        Archive an invoice.
        
        Args:
            invoice_id: Invoice ID
            
        Returns:
            True if archived successfully
        """
        logger.info(f"Archiving invoice: {invoice_id}")
        
        # Verify exists
        await self.get_invoice(invoice_id)
        
        return await self.invoice_repo.mark_as_archived(invoice_id)
    
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
            skip: Number to skip
            limit: Maximum number to return
            
        Returns:
            List of matching invoices
        """
        return await self.invoice_repo.search_invoices(
            user_id=user_id,
            query=query,
            skip=skip,
            limit=limit
        )
    
    async def get_invoice_stats(
        self,
        user_id: str,
        month_year: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get invoice statistics.
        
        Args:
            user_id: User ID
            month_year: Optional month-year filter (MM-YYYY)
            
        Returns:
            Statistics dictionary
        """
        if month_year:
            return await self.invoice_repo.get_stats_by_month(
                month_year=month_year,
                user_id=user_id
            )
        
        # Overall stats
        all_invoices = await self.invoice_repo.find_by_user(user_id=user_id, limit=10000)
        
        total = len(all_invoices)
        total_amount = sum(inv.get("total_amount", 0) for inv in all_invoices)
        total_paid = sum(inv.get("amount_paid", 0) for inv in all_invoices)
        total_unpaid = total_amount - total_paid
        
        # Count by status
        by_status = {}
        for inv in all_invoices:
            status = inv.get("status", "active")
            by_status[status] = by_status.get(status, 0) + 1
        
        # Count by payment method
        by_payment = {}
        for inv in all_invoices:
            method = inv.get("payment_method", "unknown")
            by_payment[method] = by_payment.get(method, 0) + 1
        
        return {
            "total_invoices": total,
            "total_amount": total_amount,
            "total_paid": total_paid,
            "total_unpaid": total_unpaid,
            "by_status": by_status,
            "by_payment_method": by_payment
        }
    
    async def reconcile_with_bank(
        self,
        invoice_id: str,
        bank_transaction_id: str
    ) -> bool:
        """
        Mark invoice as reconciled with bank transaction.
        
        Args:
            invoice_id: Invoice ID
            bank_transaction_id: Bank transaction ID
            
        Returns:
            True if reconciled successfully
        """
        logger.info(f"Reconciling invoice {invoice_id} with bank transaction {bank_transaction_id}")
        
        # Verify invoice exists
        await self.get_invoice(invoice_id)
        
        success = await self.invoice_repo.mark_as_reconciled(
            invoice_id=invoice_id,
            bank_transaction_id=bank_transaction_id
        )
        
        if success:
            logger.info(f"✅ Invoice reconciled: {invoice_id}")
        
        return success
