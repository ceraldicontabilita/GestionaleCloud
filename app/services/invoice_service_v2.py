"""
INVOICE SERVICE V2 - Con Controlli di Sicurezza
================================================

Servizio unificato per la gestione fatture con:
- Validazione business rules
- Controlli di sicurezza pre-operazione
- Flusso dati relazionale documentato
- Soft-delete per audit trail
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import hashlib
import logging

from app.database import Database
from app.services.business_rules import (
    BusinessRules, 
    InvoiceStatus, 
    PaymentStatus,
    EntityStatus
)
from app.utils.invoice_xml_parser import InvoiceXMLParser

logger = logging.getLogger(__name__)


class InvoiceServiceV2:
    """
    Servizio fatture con controlli di sicurezza integrati.
    
    FLUSSO UPLOAD XML:
    1. Parse XML → Estrai dati
    2. Verifica duplicato (hash)
    3. Crea/Aggiorna fornitore
    4. Salva fattura
    5. Propaga a Magazzino (opzionale)
    6. Propaga a Prima Nota (opzionale)
    """
    
    def __init__(self, db=None):
        self.db = db or Database.get_db()
        self.invoices = self.db["invoices"]
        self.warehouse_movements = self.db["warehouse_movements"]
        self.accounting_entries = self.db["accounting_entries"]
        self.cash_movements = self.db["prima_nota_cassa"]  # Usa collection corretta
    
    # ==================== CREATE ====================
    
    async def process_xml(self, xml_content: bytes, filename: str, user_id: str = None) -> Dict[str, Any]:
        """
        Processa un file XML FatturaPA.
        
        Returns:
            Dict con status, invoice_id, e dettagli operazione
        """
        logger.info(f"Processing XML: {filename}")
        
        # 1. Parse XML
        try:
            parser = InvoiceXMLParser(xml_content)
            parsed = parser.parse()
        except Exception as e:
            logger.error(f"XML parse error: {e}")
            return {"status": "error", "message": f"Errore parsing XML: {str(e)}"}
        
        # 2. Check duplicato
        content_hash = hashlib.sha256(xml_content).hexdigest()
        existing = await self.invoices.find_one({"content_hash": content_hash})
        if existing:
            return {
                "status": "duplicate",
                "invoice_id": str(existing.get("id", existing.get("_id"))),
                "message": "Fattura già presente nel sistema"
            }
        
        # 3. Prepara documento fattura
        supplier_data = parsed.get("supplier", {})
        invoice_data = parsed.get("invoice", {})
        products_data = parsed.get("products", [])
        
        # Calcola totali
        imponibile = sum(p.get("total_price", 0) for p in products_data)
        totale_iva = sum(p.get("total_price", 0) * (p.get("vat_rate", 22) / 100) for p in products_data)
        totale = invoice_data.get("total_amount", imponibile + totale_iva)
        
        invoice_doc = {
            "id": self._generate_id(),
            "filename": filename,
            "content_hash": content_hash,
            
            # Dati fornitore
            "supplier_name": supplier_data.get("name", ""),
            "supplier_vat": supplier_data.get("vat_number", ""),
            "cedente_denominazione": supplier_data.get("name", ""),
            "cedente_id_fiscale": supplier_data.get("vat_number", ""),
            "cedente_indirizzo": supplier_data.get("address", ""),
            
            # Dati fattura
            "invoice_number": invoice_data.get("number", ""),
            "numero_fattura": invoice_data.get("number", ""),
            "invoice_date": invoice_data.get("date").isoformat() if invoice_data.get("date") else None,
            "data_fattura": invoice_data.get("date").isoformat() if invoice_data.get("date") else None,
            
            # Importi
            "total_amount": totale,
            "importo_totale": totale,
            "taxable_amount": imponibile,
            "imponibile": imponibile,
            "vat_amount": totale_iva,
            "totale_iva": totale_iva,
            
            # Righe
            "linee": products_data,
            "items": products_data,
            
            # Stati
            "status": InvoiceStatus.IMPORTED.value,
            "payment_status": PaymentStatus.UNPAID.value,
            "entity_status": EntityStatus.ACTIVE.value,
            
            # Metadata
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "created_by": user_id,
            
            # Relazioni (da popolare)
            "supplier_id": None,
            "warehouse_movements": [],
            "accounting_entry_id": None,
            "payments": []
        }
        
        # 4. Crea/Aggiorna fornitore
        supplier_id = await self._ensure_supplier(supplier_data)
        invoice_doc["supplier_id"] = supplier_id
        
        # 5. Salva fattura
        result = await self.invoices.insert_one(invoice_doc.copy())
        invoice_id = invoice_doc["id"]
        
        logger.info(f"Invoice created: {invoice_id}")
        
        return {
            "status": "created",
            "invoice_id": invoice_id,
            "invoice_number": invoice_doc["invoice_number"],
            "supplier": invoice_doc["supplier_name"],
            "total": totale,
            "message": "Fattura importata con successo"
        }
    
    # ==================== READ ====================
    
    async def get_all(self, filters: Dict[str, Any] = None, 
                      skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        """Recupera tutte le fatture con filtri."""
        query = {"entity_status": {"$ne": EntityStatus.DELETED.value}}
        
        if filters:
            if filters.get("year"):
                query["invoice_date"] = {"$regex": f"^{filters['year']}"}
            if filters.get("supplier_vat"):
                query["supplier_vat"] = filters["supplier_vat"]
            if filters.get("status"):
                query["status"] = filters["status"]
            if filters.get("payment_status"):
                query["payment_status"] = filters["payment_status"]
        
        cursor = self.invoices.find(query, {"_id": 0}).skip(skip).limit(limit).sort("invoice_date", -1)
        return await cursor.to_list(limit)
    
    async def get_by_id(self, invoice_id: str) -> Optional[Dict[str, Any]]:
        """Recupera una fattura per ID."""
        return await self.invoices.find_one(
            {"id": invoice_id, "entity_status": {"$ne": EntityStatus.DELETED.value}},
            {"_id": 0}
        )
    
    # ==================== UPDATE ====================
    
    async def update(self, invoice_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Aggiorna una fattura con validazione business rules.
        """
        # 1. Recupera fattura esistente
        invoice = await self.get_by_id(invoice_id)
        if not invoice:
            return {"status": "error", "message": "Fattura non trovata"}
        
        # 2. Valida modifica
        fields_to_modify = list(update_data.keys())
        validation = BusinessRules.can_modify_invoice(invoice, fields_to_modify)
        
        if not validation.is_valid:
            return {
                "status": "error",
                "message": "Modifica non consentita",
                "errors": validation.errors
            }
        
        # 3. Applica modifica
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        await self.invoices.update_one(
            {"id": invoice_id},
            {"$set": update_data}
        )
        
        return {
            "status": "success",
            "message": "Fattura aggiornata",
            "warnings": validation.warnings
        }
    
    # ==================== DELETE ====================
    
    async def delete(self, invoice_id: str, force: bool = False) -> Dict[str, Any]:
        """
        Elimina (soft-delete) una fattura con validazione.
        
        Args:
            invoice_id: ID fattura
            force: Se True, ignora alcuni warning (non errori)
        """
        # 1. Recupera fattura
        invoice = await self.get_by_id(invoice_id)
        if not invoice:
            return {"status": "error", "message": "Fattura non trovata"}
        
        # 2. Valida eliminazione
        validation = BusinessRules.can_delete_invoice(invoice)
        
        if not validation.is_valid:
            return {
                "status": "error",
                "message": "Eliminazione non consentita",
                "errors": validation.errors
            }
        
        # 3. Se ci sono warning e non è force, chiedi conferma
        if validation.warnings and not force:
            return {
                "status": "warning",
                "message": "Eliminazione richiede conferma",
                "warnings": validation.warnings,
                "require_force": True
            }
        
        # 4. Soft-delete
        await self.invoices.update_one(
            {"id": invoice_id},
            {"$set": {
                "entity_status": EntityStatus.DELETED.value,
                "deleted_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        # 5. Annulla movimenti collegati
        if invoice.get("warehouse_movements"):
            await self.warehouse_movements.update_many(
                {"invoice_id": invoice_id},
                {"$set": {"status": "cancelled", "cancelled_at": datetime.now(timezone.utc).isoformat()}}
            )
        
        logger.info(f"Invoice soft-deleted: {invoice_id}")
        
        return {
            "status": "success",
            "message": "Fattura eliminata (archiviata)"
        }
    
    # ==================== PAYMENT ====================
    
    async def mark_as_paid(self, invoice_id: str, payment_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Marca una fattura come pagata e crea movimento in Prima Nota.
        
        payment_data:
            - amount: importo pagamento
            - method: metodo (cassa, bonifico, assegno)
            - date: data pagamento
            - note: note opzionali
        """
        # 1. Recupera fattura
        invoice = await self.get_by_id(invoice_id)
        if not invoice:
            return {"status": "error", "message": "Fattura non trovata"}
        
        # 2. Valida pagamento
        amount = payment_data.get("amount", 0)
        validation = BusinessRules.can_mark_invoice_paid(invoice, amount)
        
        if not validation.is_valid:
            return {
                "status": "error",
                "message": "Pagamento non valido",
                "errors": validation.errors
            }
        
        # 3. Determina tipo movimento
        method = payment_data.get("method", "cassa").lower()
        payment_date = payment_data.get("date", datetime.now(timezone.utc).isoformat())
        
        # 4. Crea movimento Prima Nota
        movement_collection = "prima_nota_cassa" if method == "cassa" else "prima_nota_banca"
        
        movement_doc = {
            "id": self._generate_id(),
            "data": payment_date,
            "tipo": "uscita",
            "importo": amount,
            "descrizione": f"Pagamento fattura {invoice['invoice_number']} - {invoice['supplier_name']}",
            "categoria": f"Fattura {method.capitalize()}",
            "fattura_id": invoice_id,
            "fornitore_id": invoice.get("supplier_id"),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        await self.db[movement_collection].insert_one(movement_doc.copy())
        
        # 5. Aggiorna fattura
        total = invoice.get("total_amount", 0)
        paid_so_far = sum(p.get("amount", 0) for p in invoice.get("payments", []))
        new_total_paid = paid_so_far + amount
        
        new_status = PaymentStatus.PAID.value if new_total_paid >= total * 0.99 else PaymentStatus.PARTIAL.value
        
        payment_record = {
            "date": payment_date,
            "amount": amount,
            "method": method,
            "movement_id": movement_doc["id"],
            "note": payment_data.get("note", "")
        }
        
        await self.invoices.update_one(
            {"id": invoice_id},
            {
                "$set": {
                    "payment_status": new_status,
                    "metodo_pagamento": method,
                    "pagato": new_status == PaymentStatus.PAID.value,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                },
                "$push": {"payments": payment_record}
            }
        )
        
        # 6. Aggiorna saldo fornitore
        if invoice.get("supplier_id"):
            await self.db["fornitori"].update_one(
                {"id": invoice["supplier_id"]},
                {"$inc": {"saldo_aperto": -amount}}
            )
        
        logger.info(f"Invoice {invoice_id} marked as {new_status}")
        
        return {
            "status": "success",
            "payment_status": new_status,
            "movement_id": movement_doc["id"],
            "message": f"Pagamento registrato: €{amount:.2f}"
        }
    
    # ==================== HELPERS ====================
    
    async def _ensure_supplier(self, supplier_data: Dict[str, Any]) -> Optional[str]:
        """Crea o aggiorna il fornitore."""
        vat = supplier_data.get("vat_number", "")
        if not vat:
            return None
        
        existing = await self.db["fornitori"].find_one({"vat_number": vat})
        
        if existing:
            # Aggiorna statistiche
            await self.db["fornitori"].update_one(
                {"vat_number": vat},
                {
                    "$inc": {"fatture_count": 1},
                    "$set": {"last_invoice_date": datetime.now(timezone.utc).isoformat()}
                }
            )
            return existing.get("id", str(existing.get("_id")))
        
        # Crea nuovo
        supplier_doc = {
            "id": self._generate_id(),
            "name": supplier_data.get("name", ""),
            "vat_number": vat,
            "address": supplier_data.get("address", ""),
            "city": supplier_data.get("city", ""),
            "fatture_count": 1,
            "saldo_aperto": 0,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        await self.db["fornitori"].insert_one(supplier_doc.copy())
        return supplier_doc["id"]
    
    def _generate_id(self) -> str:
        """Genera un ID univoco."""
        import uuid
        return str(uuid.uuid4())


# Factory function per ottenere il service
def get_invoice_service_v2():
    """Factory per InvoiceServiceV2."""
    return InvoiceServiceV2()
