"""
Integrated Accounting Schema - End-to-End Business Logic
Schema database per logica integrata fatture → magazzino → prima nota → riconciliazione
"""

from datetime import datetime, timezone
from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from enum import Enum


class PaymentStatus(str, Enum):
    """Stati pagamento fattura"""
    PENDING = "pending"  # Appena caricata, pagamento non ancora registrato
    PAID_CASH = "paid_cash"  # Pagata in contanti, registrata in Prima Nota Cassa
    PAID_BANK_PENDING = "paid_bank_pending"  # Pagata per banca, in attesa riconciliazione
    RECONCILED = "reconciled"  # Riconciliata con estratto conto


class MovementType(str, Enum):
    """Tipo movimento magazzino"""
    IN = "in"  # Ingresso (fattura acquisto)
    OUT = "out"  # Uscita (vendita, produzione, scarto)


class EntryType(str, Enum):
    """Tipo registrazione contabile"""
    ENTRATA = "entrata"  # Incasso
    USCITA = "uscita"  # Pagamento


class InvoiceExtended(BaseModel):
    """
    Schema esteso fattura con gestione pagamenti e riconciliazione.
    
    Aggiunge campi per tracciare stato pagamento e collegamento bancario.
    """
    invoice_number: str
    invoice_date: str  # ISO format YYYY-MM-DD
    supplier_vat: str
    supplier_name: str
    total_amount: float
    taxable_amount: float
    products: List[dict]  # [{"description": str, "quantity": float, "unit_price": float, ...}]
    
    # Campi pagamento e riconciliazione
    payment_method: Literal["cassa", "banca", ""] = ""
    payment_status: PaymentStatus = PaymentStatus.PENDING
    reconciliation_date: Optional[str] = None  # ISO format
    bank_transaction_id: Optional[str] = None  # Link a bank_statements
    suspended_reason: Optional[str] = None  # Motivo sospensione (se applicabile)
    
    # Metadata
    user_id: str
    status: str = "active"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    # Soft delete
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None


class InventoryItem(BaseModel):
    """
    Schema master articoli magazzino.
    
    Contiene dati anagrafici prodotto e giacenza corrente.
    """
    product_code: str  # Codice univoco prodotto (SKU)
    description: str  # Descrizione canonica
    unit_of_measure: Literal["kg", "pz", "lt", "g", "ml", "conf"] = "pz"
    
    # Giacenza
    stock_quantity: float = 0.0  # Quantità disponibile
    reorder_level: float = 0.0  # Soglia riordino
    
    # Metadata
    user_id: str
    last_updated: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    # Soft delete
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None


class InventoryMovement(BaseModel):
    """
    Schema movimenti magazzino (append-only log).
    
    Registra ogni ingresso/uscita con riferimento al documento origine.
    """
    movement_id: str = Field(default_factory=lambda: f"MOV-{datetime.now(timezone.utc).timestamp()}")
    movement_type: MovementType
    
    # Riferimento documento origine
    invoice_id: Optional[str] = None  # Se da fattura acquisto
    invoice_number: Optional[str] = None
    supplier_vat: Optional[str] = None
    
    # Dettagli movimento
    product_code: str
    quantity: float  # Positivo per IN, negativo per OUT
    cost_basis: Optional[float] = None  # Costo unitario (se da fattura)
    
    # Metadata
    date: str  # ISO format
    notes: Optional[str] = None
    user_id: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    # Soft delete
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None


class ProductAlias(BaseModel):
    """
    Schema mapping descrizioni fatture → codici prodotto.
    
    Permette di normalizzare nomi variabili (es. "Pomodori pelati" → "POMODORO-PELATO-500G").
    """
    supplier_vat: str
    raw_description: str  # Descrizione esatta da fattura
    normalized_description: str  # Descrizione normalizzata (lowercase, trim)
    product_code: str  # Codice prodotto magazzino
    
    # Metadata
    confidence: Literal["high", "medium", "low", "manual"] = "manual"
    last_used: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    user_id: str
    
    # Soft delete
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None


class BankJournalEntry(BaseModel):
    """
    Schema prima nota banca (journal entries).
    
    Registra movimenti bancari collegati a fatture.
    """
    entry_id: str = Field(default_factory=lambda: f"BANK-{datetime.now(timezone.utc).timestamp()}")
    
    # Dettagli registrazione
    date: str  # ISO format
    description: str
    amount: float
    currency: str = "EUR"
    entry_type: EntryType
    
    # Collegamenti
    invoice_id: Optional[str] = None
    invoice_number: Optional[str] = None
    bank_transaction_id: Optional[str] = None  # Link a bank_statements dopo riconciliazione
    
    # Riconciliazione
    reconciled: bool = False
    reconciliation_date: Optional[str] = None
    
    # Metadata
    user_id: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    # Soft delete
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None


class CashJournalEntry(BaseModel):
    """
    Schema prima nota cassa (cash movements).
    
    Estende cash_movements esistente con campi standard.
    """
    entry_id: str = Field(default_factory=lambda: f"CASH-{datetime.now(timezone.utc).timestamp()}")
    
    # Dettagli registrazione
    date: str  # ISO format
    description: str
    amount: float
    entry_type: EntryType
    category: str  # "Fattura Fornitore", "Incasso Cliente", etc
    
    # Collegamenti
    invoice_id: Optional[str] = None
    invoice_number: Optional[str] = None
    
    # Metadata
    user_id: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    # Soft delete
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None


class OperationAudit(BaseModel):
    """
    Schema audit log completo per compliance.
    
    Traccia ogni operazione CRUD su documenti critici.
    """
    audit_id: str = Field(default_factory=lambda: f"AUDIT-{datetime.now(timezone.utc).timestamp()}")
    
    # Contesto operazione
    entity: str  # "invoices", "inventory_items", "bank_journal", etc
    entity_id: str  # ID del documento modificato
    action: Literal["create", "update", "delete", "reconcile", "restore"]
    
    # Dettagli cambiamenti
    before: Optional[dict] = None  # Stato precedente (per update/delete)
    after: Optional[dict] = None  # Stato successivo (per create/update)
    
    # Metadata
    user_id: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = "api"  # "api", "automated", "migration", "system"
    notes: Optional[str] = None


# Utility functions per schema
def normalize_product_description(raw: str) -> str:
    """Normalizza descrizione prodotto per matching"""
    return raw.lower().strip().replace("  ", " ")


def generate_product_code(description: str, supplier_vat: str) -> str:
    """Genera codice prodotto univoco"""
    normalized = normalize_product_description(description)
    # Semplice: prime 3 parole + prime 4 cifre VAT
    words = normalized.split()[:3]
    vat_suffix = supplier_vat[:4] if supplier_vat else "0000"
    return f"{'_'.join(words).upper()}_{vat_suffix}"
