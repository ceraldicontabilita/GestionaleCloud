"""
DATA PROPAGATION SERVICE - Cascading Updates
=============================================

Gestisce la propagazione automatica dei dati tra entità correlate.

FLUSSI IMPLEMENTATI:
1. Fattura Pagata → Prima Nota + Aggiornamento Fornitore
2. Corrispettivo Creato → Prima Nota Cassa
3. Fornitore Aggiornato → Ricalcolo Saldi
4. Movimento Eliminato → Aggiornamento Entità Collegate
"""

from typing import Dict, Any, Optional
from datetime import datetime, timezone
import logging
import uuid

from app.database import Database, Collections

logger = logging.getLogger(__name__)


class DataPropagationService:
    """
    Servizio per la propagazione automatica dei dati.
    Garantisce la consistenza tra entità correlate.
    """
    
    def __init__(self, db=None):
        self.db = db or Database.get_db()
    
    # ==================== FATTURA → PRIMA NOTA ====================
    
    async def propagate_invoice_payment(
        self,
        invoice_id: str,
        payment_amount: float,
        payment_method: str,
        payment_date: str = None,
        note: str = ""
    ) -> Dict[str, Any]:
        """
        Propaga il pagamento di una fattura a Prima Nota e aggiorna il fornitore.
        
        Flow:
        1. Crea movimento in Prima Nota (Cassa o Banca)
        2. Aggiorna stato fattura
        3. Aggiorna saldo fornitore
        """
        results = {
            "movement_created": False,
            "invoice_updated": False,
            "supplier_updated": False,
            "errors": []
        }
        
        # 1. Recupera fattura
        invoice = await self.db[Collections.INVOICES].find_one({"id": invoice_id})
        if not invoice:
            results["errors"].append("Fattura non trovata")
            return results
        
        # 2. Determina collection per movimento
        collection = "prima_nota_cassa" if payment_method.lower() in ["cassa", "contanti"] else "prima_nota_banca"
        
        # 3. Crea movimento
        movement_id = str(uuid.uuid4())
        movement = {
            "id": movement_id,
            "date": payment_date or datetime.now(timezone.utc).isoformat()[:10],
            "data": payment_date or datetime.now(timezone.utc).isoformat()[:10],
            "type": "uscita",
            "tipo": "uscita",
            "amount": payment_amount,
            "importo": payment_amount,
            "description": f"Pagamento fattura {invoice.get('invoice_number', 'N/A')} - {invoice.get('supplier_name', 'N/A')}",
            "descrizione": f"Pagamento fattura {invoice.get('invoice_number', 'N/A')} - {invoice.get('supplier_name', 'N/A')}",
            "category": f"Fatture {payment_method.capitalize()}",
            "categoria": f"Fatture {payment_method.capitalize()}",
            "invoice_id": invoice_id,
            "supplier_id": invoice.get("supplier_id"),
            "source": "payment_propagation",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "note": note
        }
        
        try:
            await self.db[collection].insert_one(movement.copy())
            results["movement_created"] = True
            results["movement_id"] = movement_id
            results["movement_collection"] = collection
        except Exception as e:
            results["errors"].append(f"Errore creazione movimento: {str(e)}")
            return results
        
        # 4. Aggiorna fattura
        total = float(invoice.get("total_amount", 0) or invoice.get("importo_totale", 0))
        payments = invoice.get("payments", [])
        paid_so_far = sum(p.get("amount", 0) for p in payments)
        new_total_paid = paid_so_far + payment_amount
        
        new_status = "paid" if new_total_paid >= total * 0.99 else "partial"
        
        payment_record = {
            "date": payment_date or datetime.now(timezone.utc).isoformat()[:10],
            "amount": payment_amount,
            "method": payment_method,
            "movement_id": movement_id,
            "note": note
        }
        
        try:
            await self.db[Collections.INVOICES].update_one(
                {"id": invoice_id},
                {
                    "$set": {
                        "payment_status": new_status,
                        "pagato": new_status == "paid",
                        "metodo_pagamento": payment_method,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    },
                    "$push": {"payments": payment_record}
                }
            )
            results["invoice_updated"] = True
            results["payment_status"] = new_status
        except Exception as e:
            results["errors"].append(f"Errore aggiornamento fattura: {str(e)}")
        
        # 5. Aggiorna saldo fornitore
        supplier_id = invoice.get("supplier_id")
        if supplier_id:
            try:
                await self.db["fornitori"].update_one(
                    {"id": supplier_id},
                    {
                        "$inc": {"saldo_aperto": -payment_amount},
                        "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
                    }
                )
                results["supplier_updated"] = True
            except Exception as e:
                results["errors"].append(f"Errore aggiornamento fornitore: {str(e)}")
        
        logger.info(f"Payment propagated for invoice {invoice_id}: {results}")
        return results
    
    # ==================== CORRISPETTIVO → PRIMA NOTA ====================
    
    async def propagate_corrispettivo_to_prima_nota(
        self,
        corrispettivo: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Propaga un corrispettivo a Prima Nota Cassa come entrata.
        """
        results = {
            "movement_created": False,
            "movement_id": None,
            "errors": []
        }
        
        movement_id = str(uuid.uuid4())
        
        movement = {
            "id": movement_id,
            "date": corrispettivo.get("data"),
            "data": corrispettivo.get("data"),
            "type": "entrata",
            "tipo": "entrata",
            "amount": corrispettivo.get("totale", 0),
            "importo": corrispettivo.get("totale", 0),
            "description": f"Corrispettivo giornaliero {corrispettivo.get('data', '')}",
            "descrizione": f"Corrispettivo giornaliero {corrispettivo.get('data', '')}",
            "category": "Corrispettivi",
            "categoria": "Corrispettivi",
            "corrispettivo_id": corrispettivo.get("id"),
            "source": "corrispettivo_import",
            "created_at": datetime.now(timezone.utc).isoformat(),
            # Dettaglio pagamenti (struttura usata da ControlloMensile)
            "dettaglio": {
                "contanti": corrispettivo.get("pagato_contanti", 0),
                "elettronico": corrispettivo.get("pagato_elettronico", 0),
                "totale_iva": corrispettivo.get("totale_iva", 0),
                "matricola_rt": corrispettivo.get("matricola_rt", ""),
                "numero_documenti": corrispettivo.get("numero_documenti", 0)
            },
            # Campi flat per retrocompatibilità
            "pagato_contanti": corrispettivo.get("pagato_contanti", 0),
            "pagato_elettronico": corrispettivo.get("pagato_elettronico", 0)
        }
        
        try:
            await self.db["prima_nota_cassa"].insert_one(movement.copy())
            results["movement_created"] = True
            results["movement_id"] = movement_id
        except Exception as e:
            results["errors"].append(f"Errore creazione movimento: {str(e)}")
        
        return results
    
    # ==================== RICALCOLO SALDI ====================
    
    async def recalculate_supplier_balance(self, supplier_id: str) -> Dict[str, Any]:
        """
        Ricalcola il saldo aperto di un fornitore basandosi sulle fatture.
        """
        # Somma fatture non pagate
        pipeline = [
            {"$match": {
                "supplier_id": supplier_id,
                "$or": [
                    {"pagato": {"$ne": True}},
                    {"payment_status": {"$nin": ["paid"]}}
                ],
                "entity_status": {"$ne": "deleted"}
            }},
            {"$group": {
                "_id": None,
                "totale": {"$sum": {"$ifNull": ["$total_amount", "$importo_totale"]}}
            }}
        ]
        
        result = await self.db[Collections.INVOICES].aggregate(pipeline).to_list(1)
        saldo = result[0]["totale"] if result else 0
        
        await self.db["fornitori"].update_one(
            {"id": supplier_id},
            {"$set": {
                "saldo_aperto": saldo,
                "saldo_updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        return {"supplier_id": supplier_id, "saldo_aperto": saldo}
    
    async def recalculate_all_supplier_balances(self) -> Dict[str, Any]:
        """Ricalcola i saldi di tutti i fornitori."""
        suppliers = await self.db["fornitori"].find({}, {"id": 1, "_id": 0}).to_list(1000)
        
        updated = 0
        for s in suppliers:
            await self.recalculate_supplier_balance(s["id"])
            updated += 1
        
        return {"suppliers_updated": updated}
    
    # ==================== ELIMINAZIONE CON CASCATA ====================
    
    async def handle_invoice_deletion(self, invoice_id: str) -> Dict[str, Any]:
        """
        Gestisce gli effetti a cascata dell'eliminazione di una fattura.
        
        - Annulla movimenti Prima Nota collegati
        - Ricalcola saldo fornitore
        """
        results = {
            "movements_cancelled": 0,
            "supplier_recalculated": False
        }
        
        invoice = await self.db[Collections.INVOICES].find_one({"id": invoice_id})
        if not invoice:
            return results
        
        # Annulla movimenti Prima Nota
        for collection in ["prima_nota_cassa", "prima_nota_banca"]:
            result = await self.db[collection].update_many(
                {"invoice_id": invoice_id},
                {"$set": {"status": "cancelled", "cancelled_at": datetime.now(timezone.utc).isoformat()}}
            )
            results["movements_cancelled"] += result.modified_count
        
        # Ricalcola saldo fornitore
        supplier_id = invoice.get("supplier_id")
        if supplier_id:
            await self.recalculate_supplier_balance(supplier_id)
            results["supplier_recalculated"] = True
        
        return results
    
    async def handle_corrispettivo_deletion(self, corrispettivo_id: str) -> Dict[str, Any]:
        """
        Gestisce gli effetti a cascata dell'eliminazione di un corrispettivo.
        """
        # Annulla movimento Prima Nota collegato
        result = await self.db["prima_nota_cassa"].update_many(
            {"corrispettivo_id": corrispettivo_id},
            {"$set": {"status": "cancelled", "cancelled_at": datetime.now(timezone.utc).isoformat()}}
        )
        
        return {"movements_cancelled": result.modified_count}
    
    # ==================== SINCRONIZZAZIONE ====================
    
    async def sync_invoice_to_supplier(self, invoice: Dict[str, Any]) -> Optional[str]:
        """
        Sincronizza i dati fattura con il fornitore (crea o aggiorna).
        """
        vat = invoice.get("supplier_vat") or invoice.get("cedente_id_fiscale")
        if not vat:
            return None
        
        name = invoice.get("supplier_name") or invoice.get("cedente_denominazione") or ""
        
        existing = await self.db["fornitori"].find_one({"vat_number": vat})
        
        if existing:
            # Aggiorna statistiche
            await self.db["fornitori"].update_one(
                {"vat_number": vat},
                {
                    "$inc": {"fatture_count": 1},
                    "$set": {
                        "last_invoice_date": invoice.get("invoice_date") or invoice.get("data_fattura"),
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            return existing.get("id")
        
        # Crea nuovo fornitore
        supplier_id = str(uuid.uuid4())
        supplier = {
            "id": supplier_id,
            "name": name,
            "denominazione": name,
            "vat_number": vat,
            "partita_iva": vat,
            "address": invoice.get("cedente_indirizzo", ""),
            "fatture_count": 1,
            "saldo_aperto": float(invoice.get("total_amount", 0) or invoice.get("importo_totale", 0)),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        await self.db["fornitori"].insert_one(supplier.copy())
        logger.info(f"Created supplier {supplier_id} from invoice")
        
        return supplier_id


# Factory
def get_propagation_service():
    return DataPropagationService()
