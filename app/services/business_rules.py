"""
CORE BUSINESS LOGIC - Regole e Controlli di Sicurezza
=====================================================

Questo modulo definisce le regole di business centralizzate per l'ERP.
Tutti i servizi devono rispettare queste regole.

FLUSSO DATI PRINCIPALE:
-----------------------
1. XML Upload → Fattura (invoices collection)
2. Fattura → Fornitore (suppliers - auto-create/update)
3. Fattura → Magazzino (warehouse_movements - se prodotti)
4. Fattura → Prima Nota (accounting_entries - registrazione contabile)
5. Pagamento Fattura → Prima Nota Cassa/Banca (cash_movements / bank_movements)
6. Corrispettivi XML → corrispettivi collection → Prima Nota Cassa
7. Prima Nota + Corrispettivi → Controllo Mensile (aggregazione)
8. Tutto → IVA / Finanziaria (report)

REGOLE DI SICUREZZA:
--------------------
- NON eliminare fatture pagate
- NON eliminare movimenti contabilizzati
- NON modificare corrispettivi già inviati all'AdE
- Soft-delete invece di hard-delete per audit trail
- Validazione importi > 0
- Validazione date coerenti
"""

from enum import Enum
from typing import Dict, Any, List
from datetime import date
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


class EntityStatus(str, Enum):
    """Stati possibili per le entità."""
    ACTIVE = "active"
    DELETED = "deleted"
    ARCHIVED = "archived"


class PaymentStatus(str, Enum):
    """Stati di pagamento."""
    UNPAID = "unpaid"
    PARTIAL = "partial"
    PAID = "paid"


class InvoiceStatus(str, Enum):
    """Stati fattura."""
    IMPORTED = "imported"
    VALIDATED = "validated"
    REGISTERED = "registered"  # Registrata in prima nota
    PAID = "paid"
    CANCELLED = "cancelled"


class CorrispettivoStatus(str, Enum):
    """Stati corrispettivo."""
    IMPORTED = "imported"
    VALIDATED = "validated"
    SENT_ADE = "sent_ade"  # Inviato all'Agenzia delle Entrate


class MovementStatus(str, Enum):
    """Stati movimento contabile."""
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    RECONCILED = "reconciled"  # Riconciliato con banca


@dataclass
class ValidationResult:
    """Risultato di una validazione."""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    
    @classmethod
    def success(cls, warnings: List[str] = None):
        return cls(is_valid=True, errors=[], warnings=warnings or [])
    
    @classmethod
    def failure(cls, errors: List[str], warnings: List[str] = None):
        return cls(is_valid=False, errors=errors, warnings=warnings or [])


class BusinessRules:
    """
    Regole di business centralizzate.
    Usare questi metodi prima di ogni operazione CRUD critica.
    """
    
    # ==================== FATTURE ====================
    
    @staticmethod
    def can_delete_invoice(invoice: Dict[str, Any]) -> ValidationResult:
        """
        Verifica se una fattura può essere eliminata.
        
        NON può essere eliminata se:
        - È stata pagata (payment_status = 'paid' o pagato = True)
        - È stata registrata in prima nota (status = 'registered')
        - Ha movimenti di magazzino associati confermati
        """
        errors = []
        warnings = []
        
        # Check payment status (supporta entrambi i campi legacy)
        payment_status = invoice.get("payment_status", "unpaid")
        is_paid = invoice.get("pagato", False)
        
        if payment_status == PaymentStatus.PAID.value or is_paid == True:
            errors.append("Impossibile eliminare: fattura già pagata")
        elif payment_status == PaymentStatus.PARTIAL.value:
            errors.append("Impossibile eliminare: fattura con pagamento parziale")
        
        # Check registration status
        status = invoice.get("status", "imported")
        if status == InvoiceStatus.REGISTERED.value:
            errors.append("Impossibile eliminare: fattura già registrata in Prima Nota")
        
        # Check if has confirmed warehouse movements
        if invoice.get("has_warehouse_movements"):
            warnings.append("La fattura ha movimenti di magazzino che verranno annullati")
        
        # Check if has accounting entries
        if invoice.get("accounting_entry_id"):
            errors.append("Impossibile eliminare: fattura con registrazione contabile")
        
        if errors:
            return ValidationResult.failure(errors, warnings)
        return ValidationResult.success(warnings)
    
    @staticmethod
    def can_modify_invoice(invoice: Dict[str, Any], fields_to_modify: List[str]) -> ValidationResult:
        """
        Verifica se una fattura può essere modificata.
        
        Campi sempre modificabili: note, metodo_pagamento, categoria
        Campi MAI modificabili dopo registrazione: importo, data, numero, fornitore
        """
        ALWAYS_MODIFIABLE = {"note", "notes", "metodo_pagamento", "payment_method", "categoria", "category", "tags"}
        NEVER_MODIFIABLE_AFTER_REGISTRATION = {"total_amount", "importo_totale", "invoice_date", "data_fattura", 
                                                "invoice_number", "numero_fattura", "supplier_name", "supplier_vat"}
        
        errors = []
        warnings = []
        
        status = invoice.get("status", "imported")
        payment_status = invoice.get("payment_status", "unpaid")
        
        # If paid, very limited modifications
        if payment_status == PaymentStatus.PAID.value:
            invalid_fields = set(fields_to_modify) - ALWAYS_MODIFIABLE
            if invalid_fields:
                errors.append(f"Fattura pagata: non puoi modificare {', '.join(invalid_fields)}")
        
        # If registered, cannot modify critical fields
        if status in [InvoiceStatus.REGISTERED.value, InvoiceStatus.PAID.value]:
            blocked_fields = set(fields_to_modify) & NEVER_MODIFIABLE_AFTER_REGISTRATION
            if blocked_fields:
                errors.append(f"Fattura registrata: non puoi modificare {', '.join(blocked_fields)}")
        
        if errors:
            return ValidationResult.failure(errors, warnings)
        return ValidationResult.success(warnings)
    
    @staticmethod
    def can_mark_invoice_paid(invoice: Dict[str, Any], payment_amount: float) -> ValidationResult:
        """Verifica se una fattura può essere marcata come pagata."""
        errors = []
        
        total = invoice.get("total_amount") or invoice.get("importo_totale") or 0
        
        if payment_amount <= 0:
            errors.append("L'importo del pagamento deve essere maggiore di 0")
        
        if payment_amount > total * 1.01:  # 1% tolerance
            errors.append(f"Importo pagamento (€{payment_amount:.2f}) superiore al totale fattura (€{total:.2f})")
        
        if invoice.get("payment_status") == PaymentStatus.PAID.value:
            errors.append("Fattura già pagata")
        
        if errors:
            return ValidationResult.failure(errors)
        return ValidationResult.success()
    
    # ==================== CORRISPETTIVI ====================
    
    @staticmethod
    def can_delete_corrispettivo(corrispettivo: Dict[str, Any]) -> ValidationResult:
        """
        Verifica se un corrispettivo può essere eliminato.
        
        NON può essere eliminato se:
        - È stato inviato all'Agenzia delle Entrate
        - È già stato contabilizzato in Prima Nota
        """
        errors = []
        
        status = corrispettivo.get("status", "imported")
        if status == CorrispettivoStatus.SENT_ADE.value:
            errors.append("Impossibile eliminare: corrispettivo già inviato all'Agenzia delle Entrate")
        
        if corrispettivo.get("prima_nota_id"):
            errors.append("Impossibile eliminare: corrispettivo già registrato in Prima Nota")
        
        if errors:
            return ValidationResult.failure(errors)
        return ValidationResult.success()
    
    @staticmethod
    def can_modify_corrispettivo(corrispettivo: Dict[str, Any]) -> ValidationResult:
        """Verifica se un corrispettivo può essere modificato."""
        errors = []
        
        status = corrispettivo.get("status", "imported")
        if status == CorrispettivoStatus.SENT_ADE.value:
            errors.append("Impossibile modificare: corrispettivo già inviato all'Agenzia delle Entrate")
        
        if errors:
            return ValidationResult.failure(errors)
        return ValidationResult.success()
    
    # ==================== MOVIMENTI PRIMA NOTA ====================
    
    @staticmethod
    def can_delete_movement(movement: Dict[str, Any]) -> ValidationResult:
        """
        Verifica se un movimento può essere eliminato.
        
        NON può essere eliminato se:
        - È stato riconciliato con la banca
        - È collegato a una fattura pagata
        - È collegato a un corrispettivo inviato
        """
        errors = []
        warnings = []
        
        status = movement.get("status", "draft")
        if status == MovementStatus.RECONCILED.value:
            errors.append("Impossibile eliminare: movimento già riconciliato con la banca")
        
        if status == MovementStatus.CONFIRMED.value:
            warnings.append("Il movimento è confermato - l'eliminazione richiede conferma")
        
        # Check linked entities
        if movement.get("invoice_id"):
            warnings.append("Il movimento è collegato a una fattura")
        
        if movement.get("corrispettivo_id"):
            warnings.append("Il movimento è collegato a un corrispettivo")
        
        if errors:
            return ValidationResult.failure(errors, warnings)
        return ValidationResult.success(warnings)
    
    # ==================== ASSEGNI ====================
    
    @staticmethod
    def can_delete_assegno(assegno: Dict[str, Any]) -> ValidationResult:
        """Verifica se un assegno può essere eliminato."""
        errors = []
        
        stato = assegno.get("stato", "vuoto")
        if stato in ["emesso", "incassato"]:
            errors.append(f"Impossibile eliminare: assegno già {stato}")
        
        if assegno.get("fatture_collegate") and len(assegno.get("fatture_collegate", [])) > 0:
            errors.append("Impossibile eliminare: assegno collegato a fatture")
        
        if errors:
            return ValidationResult.failure(errors)
        return ValidationResult.success()
    
    # ==================== FORNITORI ====================
    
    @staticmethod
    def can_delete_supplier(supplier: Dict[str, Any], invoice_count: int = 0) -> ValidationResult:
        """Verifica se un fornitore può essere eliminato."""
        errors = []
        warnings = []
        
        if invoice_count > 0:
            errors.append(f"Impossibile eliminare: fornitore ha {invoice_count} fatture associate")
        
        if supplier.get("saldo_aperto", 0) != 0:
            errors.append(f"Impossibile eliminare: fornitore ha saldo aperto di €{supplier.get('saldo_aperto', 0):.2f}")
        
        if errors:
            return ValidationResult.failure(errors, warnings)
        return ValidationResult.success(warnings)
    
    # ==================== VALIDAZIONI GENERICHE ====================
    
    @staticmethod
    def validate_amount(amount: float, field_name: str = "importo") -> ValidationResult:
        """Valida che un importo sia positivo."""
        if amount is None:
            return ValidationResult.failure([f"{field_name} è obbligatorio"])
        if amount < 0:
            return ValidationResult.failure([f"{field_name} non può essere negativo"])
        if amount == 0:
            return ValidationResult.failure([f"{field_name} deve essere maggiore di 0"])
        return ValidationResult.success()
    
    @staticmethod
    def validate_date(date_value: date, field_name: str = "data", 
                      min_date: date = None, max_date: date = None) -> ValidationResult:
        """Valida una data."""
        errors = []
        
        if date_value is None:
            errors.append(f"{field_name} è obbligatoria")
        else:
            if min_date and date_value < min_date:
                errors.append(f"{field_name} non può essere anteriore a {min_date}")
            if max_date and date_value > max_date:
                errors.append(f"{field_name} non può essere successiva a {max_date}")
        
        if errors:
            return ValidationResult.failure(errors)
        return ValidationResult.success()


class DataFlowManager:
    """
    Gestisce il flusso dati tra le varie entità.
    Documenta e applica le relazioni tra i moduli.
    """
    
    # Mappa delle relazioni tra entità
    ENTITY_RELATIONS = {
        "invoice": {
            "creates": ["warehouse_movement", "accounting_entry"],
            "updates": ["supplier_stats"],
            "linked_to": ["supplier", "payment"]
        },
        "corrispettivo": {
            "creates": ["cash_movement"],
            "linked_to": ["prima_nota_cassa"]
        },
        "payment": {
            "creates": ["cash_movement", "bank_movement"],
            "updates": ["invoice.payment_status", "supplier.saldo_aperto"],
            "linked_to": ["invoice", "assegno"]
        },
        "assegno": {
            "linked_to": ["invoice", "supplier", "payment"]
        },
        "bank_statement": {
            "creates": ["bank_movement"],
            "updates": ["movement.reconciliation_status"]
        }
    }
    
    @staticmethod
    def get_cascade_effects(entity_type: str, action: str) -> List[str]:
        """
        Restituisce gli effetti a cascata di un'azione su un'entità.
        
        Args:
            entity_type: Tipo di entità (invoice, corrispettivo, payment, etc.)
            action: Azione (delete, update, create)
            
        Returns:
            Lista di effetti descritti
        """
        effects = []
        relations = DataFlowManager.ENTITY_RELATIONS.get(entity_type, {})
        
        if action == "delete":
            # Soft-delete su entità collegate
            for created in relations.get("creates", []):
                effects.append(f"Annullamento {created} collegati")
            for updated in relations.get("updates", []):
                effects.append(f"Ricalcolo {updated}")
        
        elif action == "create":
            for creates in relations.get("creates", []):
                effects.append(f"Creazione automatica {creates}")
            for updates in relations.get("updates", []):
                effects.append(f"Aggiornamento {updates}")
        
        return effects


# Singleton per accesso globale alle regole
business_rules = BusinessRules()
data_flow = DataFlowManager()
