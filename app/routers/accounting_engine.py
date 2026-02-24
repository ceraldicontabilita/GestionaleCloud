"""
Motore Contabile basato sulla logica Odoo
=========================================

Implementa la contabilità in partita doppia seguendo la logica di Odoo:
- Registrazioni contabili automatiche
- Bilanciamento DARE/AVERE
- Riconciliazione automatica
- Gestione scadenze
- Calcolo IVA automatico

Basato su: https://www.odoo.com/documentation/18.0/applications/finance/accounting/get_started/cheat_sheet.html
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field

from app.database import Database

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================
# COSTANTI E CONFIGURAZIONE
# ============================================

# Tipi di conto (account_type) - mappatura Odoo
ACCOUNT_TYPES = {
    # Attivo
    'asset_receivable': {'name': 'Crediti verso clienti', 'nature': 'debit', 'balance_sheet': True},
    'asset_cash': {'name': 'Liquidità', 'nature': 'debit', 'balance_sheet': True},
    'asset_current': {'name': 'Attivo corrente', 'nature': 'debit', 'balance_sheet': True},
    'asset_non_current': {'name': 'Immobilizzazioni', 'nature': 'debit', 'balance_sheet': True},
    'asset_prepayments': {'name': 'Ratei e risconti attivi', 'nature': 'debit', 'balance_sheet': True},
    
    # Passivo
    'liability_payable': {'name': 'Debiti verso fornitori', 'nature': 'credit', 'balance_sheet': True},
    'liability_current': {'name': 'Passivo corrente', 'nature': 'credit', 'balance_sheet': True},
    'liability_non_current': {'name': 'Passivo lungo termine', 'nature': 'credit', 'balance_sheet': True},
    
    # Patrimonio Netto
    'equity': {'name': 'Patrimonio netto', 'nature': 'credit', 'balance_sheet': True},
    'equity_unaffected': {'name': 'Utili non distribuiti', 'nature': 'credit', 'balance_sheet': True},
    
    # Conto Economico
    'income': {'name': 'Ricavi', 'nature': 'credit', 'balance_sheet': False},
    'income_other': {'name': 'Altri ricavi', 'nature': 'credit', 'balance_sheet': False},
    'expense': {'name': 'Costi', 'nature': 'debit', 'balance_sheet': False},
    'expense_direct_cost': {'name': 'Costi diretti', 'nature': 'debit', 'balance_sheet': False},
    'expense_depreciation': {'name': 'Ammortamenti', 'nature': 'debit', 'balance_sheet': False},
    
    # Conti d'ordine
    'off_balance': {'name': 'Conti ordine', 'nature': 'debit', 'balance_sheet': False},
}

# Conti predefiniti italiani
DEFAULT_ACCOUNTS = {
    # ATTIVO
    'cassa': {'code': '101000', 'name': 'Cassa', 'type': 'asset_cash'},
    'banca': {'code': '102000', 'name': 'Banca c/c', 'type': 'asset_cash'},
    'crediti_clienti': {'code': '110000', 'name': 'Crediti verso clienti', 'type': 'asset_receivable'},
    'crediti_diversi': {'code': '115000', 'name': 'Crediti diversi', 'type': 'asset_current'},
    'magazzino': {'code': '120000', 'name': 'Magazzino', 'type': 'asset_current'},
    'iva_credito': {'code': '130000', 'name': 'IVA a credito', 'type': 'asset_current'},
    'ratei_attivi': {'code': '140000', 'name': 'Ratei attivi', 'type': 'asset_prepayments'},
    'risconti_attivi': {'code': '141000', 'name': 'Risconti attivi', 'type': 'asset_prepayments'},
    'immobilizzazioni': {'code': '150000', 'name': 'Immobilizzazioni', 'type': 'asset_non_current'},
    'fondo_ammortamento': {'code': '155000', 'name': 'Fondo ammortamento', 'type': 'asset_non_current'},
    
    # PASSIVO
    'debiti_fornitori': {'code': '201000', 'name': 'Debiti verso fornitori', 'type': 'liability_payable'},
    'debiti_diversi': {'code': '205000', 'name': 'Debiti diversi', 'type': 'liability_current'},
    'iva_debito': {'code': '210000', 'name': 'IVA a debito', 'type': 'liability_current'},
    'debiti_tributari': {'code': '220000', 'name': 'Debiti tributari', 'type': 'liability_current'},
    'debiti_previdenziali': {'code': '225000', 'name': 'Debiti previdenziali', 'type': 'liability_current'},
    'tfr': {'code': '230000', 'name': 'TFR', 'type': 'liability_non_current'},
    'mutui': {'code': '240000', 'name': 'Mutui passivi', 'type': 'liability_non_current'},
    'ratei_passivi': {'code': '250000', 'name': 'Ratei passivi', 'type': 'liability_current'},
    'risconti_passivi': {'code': '251000', 'name': 'Risconti passivi', 'type': 'liability_current'},
    
    # PATRIMONIO NETTO
    'capitale_sociale': {'code': '301000', 'name': 'Capitale sociale', 'type': 'equity'},
    'riserva_legale': {'code': '302000', 'name': 'Riserva legale', 'type': 'equity'},
    'utile_esercizio': {'code': '310000', 'name': 'Utile/Perdita esercizio', 'type': 'equity_unaffected'},
    'utili_portati_nuovo': {'code': '320000', 'name': 'Utili portati a nuovo', 'type': 'equity_unaffected'},
    
    # RICAVI
    'vendite_merci': {'code': '401000', 'name': 'Vendite merci', 'type': 'income'},
    'vendite_servizi': {'code': '402000', 'name': 'Vendite servizi', 'type': 'income'},
    'corrispettivi': {'code': '403000', 'name': 'Corrispettivi', 'type': 'income'},
    'altri_ricavi': {'code': '490000', 'name': 'Altri ricavi', 'type': 'income_other'},
    'sopravvenienze_attive': {'code': '495000', 'name': 'Sopravvenienze attive', 'type': 'income_other'},
    
    # COSTI
    'acquisti_merci': {'code': '501000', 'name': 'Acquisti merci', 'type': 'expense_direct_cost'},
    'acquisti_materie': {'code': '502000', 'name': 'Acquisti materie prime', 'type': 'expense_direct_cost'},
    'costi_personale': {'code': '510000', 'name': 'Costi del personale', 'type': 'expense'},
    'stipendi': {'code': '511000', 'name': 'Stipendi e salari', 'type': 'expense'},
    'contributi': {'code': '512000', 'name': 'Contributi previdenziali', 'type': 'expense'},
    'tfr_costo': {'code': '513000', 'name': 'Accantonamento TFR', 'type': 'expense'},
    'affitti': {'code': '520000', 'name': 'Affitti passivi', 'type': 'expense'},
    'utenze': {'code': '521000', 'name': 'Utenze', 'type': 'expense'},
    'spese_generali': {'code': '530000', 'name': 'Spese generali', 'type': 'expense'},
    'ammortamenti': {'code': '540000', 'name': 'Ammortamenti', 'type': 'expense_depreciation'},
    'interessi_passivi': {'code': '550000', 'name': 'Interessi passivi', 'type': 'expense'},
    'sopravvenienze_passive': {'code': '590000', 'name': 'Sopravvenienze passive', 'type': 'expense'},
}


# ============================================
# MODELLI PYDANTIC
# ============================================

class JournalLine(BaseModel):
    """Riga di una registrazione contabile"""
    account_code: str = Field(..., description="Codice conto")
    account_name: Optional[str] = None
    debit: float = Field(default=0, ge=0)
    credit: float = Field(default=0, ge=0)
    partner_id: Optional[str] = None
    partner_name: Optional[str] = None
    name: Optional[str] = None  # Descrizione riga
    tax_ids: Optional[List[str]] = None
    reconcile_id: Optional[str] = None  # Per riconciliazione


class JournalEntry(BaseModel):
    """Registrazione contabile (prima nota)"""
    date: str = Field(..., description="Data registrazione YYYY-MM-DD")
    ref: Optional[str] = None  # Riferimento (es. numero fattura)
    journal_type: str = Field(default="general", description="sale, purchase, bank, cash, general")
    lines: List[JournalLine]
    narration: Optional[str] = None  # Note
    move_type: Optional[str] = None  # entry, out_invoice, in_invoice, out_refund, in_refund


class InvoiceCreate(BaseModel):
    """Creazione fattura con generazione automatica scritture"""
    move_type: str = Field(..., description="out_invoice (emessa), in_invoice (ricevuta), out_refund, in_refund")
    partner_id: str
    partner_name: str
    date: str  # Data fattura
    due_date: Optional[str] = None  # Scadenza
    ref: Optional[str] = None  # Numero fattura
    lines: List[Dict[str, Any]]  # Righe fattura: {description, quantity, price_unit, tax_id}
    

class PaymentCreate(BaseModel):
    """Registrazione pagamento con riconciliazione automatica"""
    payment_type: str = Field(..., description="inbound (incasso), outbound (pagamento)")
    partner_id: str
    amount: float
    date: str
    journal_type: str = Field(default="bank", description="bank o cash")
    invoice_ids: Optional[List[str]] = None  # Fatture da riconciliare


# ============================================
# FUNZIONI HELPER
# ============================================

def round_currency(amount: float) -> float:
    """Arrotonda a 2 decimali (standard monetario)"""
    return float(Decimal(str(amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def validate_journal_entry(lines: List[JournalLine]) -> Tuple[bool, str]:
    """
    Valida una registrazione contabile.
    
    Regola fondamentale partita doppia: Totale DARE = Totale AVERE
    """
    total_debit = sum(round_currency(l.debit) for l in lines)
    total_credit = sum(round_currency(l.credit) for l in lines)
    
    # Tolleranza per errori di arrotondamento (0.01)
    if abs(total_debit - total_credit) > 0.01:
        return False, f"Scrittura non bilanciata: DARE {total_debit:.2f} ≠ AVERE {total_credit:.2f}"
    
    # Ogni riga deve avere solo DARE o AVERE, non entrambi
    for i, line in enumerate(lines):
        if line.debit > 0 and line.credit > 0:
            return False, f"Riga {i+1}: non può avere sia DARE che AVERE"
        if line.debit == 0 and line.credit == 0:
            return False, f"Riga {i+1}: deve avere DARE o AVERE"
    
    return True, "OK"


async def get_account_by_code(db, code: str) -> Optional[Dict]:
    """Recupera un conto dal piano dei conti"""
    return await db["piano_conti"].find_one({"codice": code}, {"_id": 0})


async def ensure_default_accounts(db) -> int:
    """Assicura che esistano i conti predefiniti"""
    created = 0
    for key, acc in DEFAULT_ACCOUNTS.items():
        existing = await db["piano_conti"].find_one({"codice": acc['code']})
        if not existing:
            await db["piano_conti"].insert_one({
                "id": str(uuid.uuid4()),
                "codice": acc['code'],
                "descrizione": acc['name'],
                "tipo": acc['type'],
                "created_at": datetime.now(timezone.utc).isoformat()
            })
            created += 1
    return created


# ============================================
# ENDPOINTS API
# ============================================

@router.get("/status")
async def accounting_engine_status() -> Dict[str, Any]:
    """Stato del motore contabile"""
    db = Database.get_db()
    
    # Conta conti e registrazioni
    conti = await db["piano_conti"].count_documents({})
    registrazioni = await db["prima_nota_righe"].count_documents({})
    
    return {
        "status": "active",
        "conti_piano_conti": conti,
        "registrazioni_totali": registrazioni,
        "engine": "Odoo-compatible double-entry bookkeeping"
    }


@router.post("/init-default-accounts")
async def init_default_accounts() -> Dict[str, Any]:
    """Inizializza i conti predefiniti italiani"""
    db = Database.get_db()
    created = await ensure_default_accounts(db)
    
    return {
        "success": True,
        "conti_creati": created,
        "totale_conti_default": len(DEFAULT_ACCOUNTS)
    }


@router.post("/journal-entry")
async def create_journal_entry(entry: JournalEntry) -> Dict[str, Any]:
    """
    Crea una registrazione contabile (prima nota).
    
    La scrittura deve essere bilanciata: Totale DARE = Totale AVERE
    
    Esempio fattura cliente €100 + IVA 22%:
    ```
    {
        "date": "2025-01-27",
        "ref": "FE/2025/001",
        "journal_type": "sale",
        "lines": [
            {"account_code": "110000", "debit": 122.00, "name": "Credito cliente"},
            {"account_code": "401000", "credit": 100.00, "name": "Vendita"},
            {"account_code": "210000", "credit": 22.00, "name": "IVA 22%"}
        ]
    }
    ```
    """
    db = Database.get_db()
    
    # Valida bilanciamento
    is_valid, message = validate_journal_entry(entry.lines)
    if not is_valid:
        raise HTTPException(status_code=400, detail=message)
    
    # Genera ID registrazione
    move_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    # Calcola totali
    total_debit = sum(round_currency(l.debit) for l in entry.lines)
    total_credit = sum(round_currency(l.credit) for l in entry.lines)
    
    # Salva header registrazione
    move_doc = {
        "id": move_id,
        "date": entry.date,
        "ref": entry.ref,
        "journal_type": entry.journal_type,
        "move_type": entry.move_type or "entry",
        "narration": entry.narration,
        "total_debit": round_currency(total_debit),
        "total_credit": round_currency(total_credit),
        "state": "posted",
        "created_at": now
    }
    await db["prima_nota"].insert_one(move_doc.copy())
    
    # Salva righe
    line_docs = []
    for i, line in enumerate(entry.lines):
        line_doc = {
            "id": str(uuid.uuid4()),
            "move_id": move_id,
            "sequence": i + 1,
            "account_code": line.account_code,
            "account_name": line.account_name,
            "debit": round_currency(line.debit),
            "credit": round_currency(line.credit),
            "balance": round_currency(line.debit - line.credit),
            "partner_id": line.partner_id,
            "partner_name": line.partner_name,
            "name": line.name,
            "date": entry.date,
            "reconciled": False,
            "reconcile_id": None,
            "created_at": now
        }
        line_docs.append(line_doc)
    
    if line_docs:
        await db["prima_nota_righe"].insert_many(line_docs)
    
    return {
        "success": True,
        "move_id": move_id,
        "date": entry.date,
        "total_debit": round_currency(total_debit),
        "total_credit": round_currency(total_credit),
        "lines_count": len(entry.lines)
    }


@router.post("/invoice")
async def create_invoice_with_entries(invoice: InvoiceCreate) -> Dict[str, Any]:
    """
    Crea una fattura e genera automaticamente le scritture contabili.
    
    Logica Odoo:
    - Fattura emessa (out_invoice): DARE Crediti clienti, AVERE Ricavi + IVA debito
    - Fattura ricevuta (in_invoice): DARE Costi + IVA credito, AVERE Debiti fornitori
    - Nota credito emessa (out_refund): inverso di out_invoice
    - Nota credito ricevuta (in_refund): inverso di in_invoice
    """
    db = Database.get_db()
    await ensure_default_accounts(db)
    
    # Calcola totali
    subtotal = 0
    total_tax = 0
    
    for line in invoice.lines:
        qty = line.get('quantity', 1)
        price = line.get('price_unit', 0)
        tax_rate = line.get('tax_rate', 22) / 100  # Default IVA 22%
        
        line_total = qty * price
        line_tax = line_total * tax_rate
        
        subtotal += line_total
        total_tax += line_tax
    
    total = round_currency(subtotal + total_tax)
    subtotal = round_currency(subtotal)
    total_tax = round_currency(total_tax)
    
    # Genera scritture contabili in base al tipo
    journal_lines = []
    
    if invoice.move_type == 'out_invoice':
        # Fattura emessa: Cliente a Ricavi + IVA
        journal_lines = [
            JournalLine(
                account_code='110000',
                account_name='Crediti verso clienti',
                debit=total,
                credit=0,
                partner_id=invoice.partner_id,
                partner_name=invoice.partner_name,
                name=f"Fattura {invoice.ref or ''}"
            ),
            JournalLine(
                account_code='401000',
                account_name='Vendite merci',
                debit=0,
                credit=subtotal,
                name="Ricavo vendita"
            ),
            JournalLine(
                account_code='210000',
                account_name='IVA a debito',
                debit=0,
                credit=total_tax,
                name="IVA 22%"
            )
        ]
        journal_type = 'sale'
        
    elif invoice.move_type == 'in_invoice':
        # Fattura ricevuta: Costi + IVA a Fornitore
        journal_lines = [
            JournalLine(
                account_code='501000',
                account_name='Acquisti merci',
                debit=subtotal,
                credit=0,
                name="Costo acquisto"
            ),
            JournalLine(
                account_code='130000',
                account_name='IVA a credito',
                debit=total_tax,
                credit=0,
                name="IVA 22%"
            ),
            JournalLine(
                account_code='201000',
                account_name='Debiti verso fornitori',
                debit=0,
                credit=total,
                partner_id=invoice.partner_id,
                partner_name=invoice.partner_name,
                name=f"Fattura {invoice.ref or ''}"
            )
        ]
        journal_type = 'purchase'
        
    elif invoice.move_type == 'out_refund':
        # Nota credito emessa (inverso di out_invoice)
        journal_lines = [
            JournalLine(
                account_code='401000',
                account_name='Vendite merci',
                debit=subtotal,
                credit=0,
                name="Storno ricavo"
            ),
            JournalLine(
                account_code='210000',
                account_name='IVA a debito',
                debit=total_tax,
                credit=0,
                name="Storno IVA"
            ),
            JournalLine(
                account_code='110000',
                account_name='Crediti verso clienti',
                debit=0,
                credit=total,
                partner_id=invoice.partner_id,
                partner_name=invoice.partner_name,
                name=f"Nota credito {invoice.ref or ''}"
            )
        ]
        journal_type = 'sale'
        
    elif invoice.move_type == 'in_refund':
        # Nota credito ricevuta (inverso di in_invoice)
        journal_lines = [
            JournalLine(
                account_code='201000',
                account_name='Debiti verso fornitori',
                debit=total,
                credit=0,
                partner_id=invoice.partner_id,
                partner_name=invoice.partner_name,
                name=f"Nota credito {invoice.ref or ''}"
            ),
            JournalLine(
                account_code='501000',
                account_name='Acquisti merci',
                debit=0,
                credit=subtotal,
                name="Storno costo"
            ),
            JournalLine(
                account_code='130000',
                account_name='IVA a credito',
                debit=0,
                credit=total_tax,
                name="Storno IVA"
            )
        ]
        journal_type = 'purchase'
    else:
        raise HTTPException(status_code=400, detail=f"Tipo fattura non valido: {invoice.move_type}")
    
    # Crea la registrazione contabile
    entry = JournalEntry(
        date=invoice.date,
        ref=invoice.ref,
        journal_type=journal_type,
        move_type=invoice.move_type,
        lines=journal_lines
    )
    
    result = await create_journal_entry(entry)
    
    # Salva anche nella collection fatture per tracking
    invoice_doc = {
        "id": result["move_id"],
        "move_id": result["move_id"],
        "move_type": invoice.move_type,
        "partner_id": invoice.partner_id,
        "partner_name": invoice.partner_name,
        "date": invoice.date,
        "due_date": invoice.due_date or invoice.date,
        "ref": invoice.ref,
        "subtotal": subtotal,
        "tax_amount": total_tax,
        "total": total,
        "amount_residual": total,  # Da pagare
        "state": "posted",
        "payment_state": "not_paid",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db["invoices"].insert_one(invoice_doc.copy())
    
    return {
        "success": True,
        "invoice_id": result["move_id"],
        "move_type": invoice.move_type,
        "subtotal": subtotal,
        "tax_amount": total_tax,
        "total": total,
        "journal_entry": result
    }


@router.post("/payment")
async def create_payment_with_reconciliation(payment: PaymentCreate) -> Dict[str, Any]:
    """
    Registra un pagamento e riconcilia automaticamente con le fatture.
    
    Logica Odoo:
    - Incasso (inbound): DARE Banca/Cassa, AVERE Crediti clienti
    - Pagamento (outbound): DARE Debiti fornitori, AVERE Banca/Cassa
    
    La riconciliazione chiude automaticamente le fatture indicate.
    """
    db = Database.get_db()
    await ensure_default_accounts(db)
    
    amount = round_currency(payment.amount)
    
    # Determina conti
    if payment.journal_type == 'bank':
        cash_account = '102000'
        cash_name = 'Banca c/c'
    else:
        cash_account = '101000'
        cash_name = 'Cassa'
    
    # Genera scritture
    if payment.payment_type == 'inbound':
        # Incasso da cliente
        journal_lines = [
            JournalLine(
                account_code=cash_account,
                account_name=cash_name,
                debit=amount,
                credit=0,
                name="Incasso"
            ),
            JournalLine(
                account_code='110000',
                account_name='Crediti verso clienti',
                debit=0,
                credit=amount,
                partner_id=payment.partner_id,
                name="Chiusura credito"
            )
        ]
    elif payment.payment_type == 'outbound':
        # Pagamento a fornitore
        journal_lines = [
            JournalLine(
                account_code='201000',
                account_name='Debiti verso fornitori',
                debit=amount,
                credit=0,
                partner_id=payment.partner_id,
                name="Chiusura debito"
            ),
            JournalLine(
                account_code=cash_account,
                account_name=cash_name,
                debit=0,
                credit=amount,
                name="Pagamento"
            )
        ]
    else:
        raise HTTPException(status_code=400, detail=f"Tipo pagamento non valido: {payment.payment_type}")
    
    # Crea registrazione
    entry = JournalEntry(
        date=payment.date,
        ref=f"PAY/{payment.date}/{payment.partner_id[:8]}",
        journal_type=payment.journal_type,
        move_type='entry',
        lines=journal_lines
    )
    
    result = await create_journal_entry(entry)
    
    # Riconcilia fatture se specificate
    reconciled_invoices = []
    if payment.invoice_ids:
        remaining = amount
        for inv_id in payment.invoice_ids:
            if remaining <= 0:
                break
            
            invoice = await db["invoices"].find_one({"id": inv_id})
            if invoice:
                residual = invoice.get("amount_residual", invoice.get("total", 0))
                to_pay = min(remaining, residual)
                new_residual = residual - to_pay
                
                await db["invoices"].update_one(
                    {"id": inv_id},
                    {"$set": {
                        "amount_residual": round_currency(new_residual),
                        "payment_state": "paid" if new_residual <= 0 else "partial",
                        "last_payment_date": payment.date
                    }}
                )
                
                reconciled_invoices.append({
                    "invoice_id": inv_id,
                    "amount_paid": round_currency(to_pay),
                    "residual": round_currency(new_residual)
                })
                
                remaining -= to_pay
    
    return {
        "success": True,
        "payment_id": result["move_id"],
        "payment_type": payment.payment_type,
        "amount": amount,
        "journal_entry": result,
        "reconciled_invoices": reconciled_invoices
    }


@router.get("/trial-balance")
async def get_trial_balance(
    date_from: str = Query(None),
    date_to: str = Query(None),
    anno: int = Query(None)
) -> Dict[str, Any]:
    """
    Bilancio di verifica (Trial Balance).
    
    Mostra il saldo di ogni conto con totali DARE e AVERE.
    """
    db = Database.get_db()
    
    # Filtro date
    match_filter = {}
    if anno:
        match_filter["date"] = {"$regex": f"^{anno}"}
    elif date_from and date_to:
        match_filter["date"] = {"$gte": date_from, "$lte": date_to}
    
    # Aggrega per conto
    pipeline = [
        {"$match": match_filter} if match_filter else {"$match": {}},
        {
            "$group": {
                "_id": "$account_code",
                "account_name": {"$first": "$account_name"},
                "total_debit": {"$sum": "$debit"},
                "total_credit": {"$sum": "$credit"},
                "movements": {"$sum": 1}
            }
        },
        {"$sort": {"_id": 1}}
    ]
    
    results = await db["prima_nota_righe"].aggregate(pipeline).to_list(500)
    
    # Calcola saldi
    accounts = []
    grand_total_debit = 0
    grand_total_credit = 0
    
    for r in results:
        debit = round_currency(r["total_debit"])
        credit = round_currency(r["total_credit"])
        balance = round_currency(debit - credit)
        
        accounts.append({
            "code": r["_id"],
            "name": r.get("account_name", ""),
            "debit": debit,
            "credit": credit,
            "balance": balance,
            "movements": r["movements"]
        })
        
        grand_total_debit += debit
        grand_total_credit += credit
    
    return {
        "success": True,
        "date_from": date_from,
        "date_to": date_to,
        "anno": anno,
        "accounts": accounts,
        "totals": {
            "debit": round_currency(grand_total_debit),
            "credit": round_currency(grand_total_credit),
            "balance": round_currency(grand_total_debit - grand_total_credit)
        }
    }


@router.get("/partner-ledger/{partner_id}")
async def get_partner_ledger(
    partner_id: str,
    anno: int = Query(None)
) -> Dict[str, Any]:
    """
    Estratto conto partner (cliente o fornitore).
    
    Mostra tutte le movimentazioni e il saldo residuo.
    """
    db = Database.get_db()
    
    query = {"partner_id": partner_id}
    if anno:
        query["date"] = {"$regex": f"^{anno}"}
    
    movements = await db["prima_nota_righe"].find(
        query,
        {"_id": 0}
    ).sort("date", 1).to_list(1000)
    
    # Calcola saldo progressivo
    balance = 0
    for m in movements:
        balance += m.get("debit", 0) - m.get("credit", 0)
        m["running_balance"] = round_currency(balance)
    
    return {
        "success": True,
        "partner_id": partner_id,
        "anno": anno,
        "movements": movements,
        "final_balance": round_currency(balance),
        "total_debit": round_currency(sum(m.get("debit", 0) for m in movements)),
        "total_credit": round_currency(sum(m.get("credit", 0) for m in movements))
    }


@router.get("/aged-receivable")
async def get_aged_receivable() -> Dict[str, Any]:
    """
    Scadenzario clienti (Aged Receivable).
    
    Raggruppa i crediti per fasce di scadenza:
    - Non scaduto
    - 0-30 giorni
    - 31-60 giorni
    - 61-90 giorni
    - Oltre 90 giorni
    """
    db = Database.get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Trova fatture non pagate
    invoices = await db["invoices"].find({
        "move_type": "out_invoice",
        "payment_state": {"$in": ["not_paid", "partial"]}
    }, {"_id": 0}).to_list(1000)
    
    # Raggruppa per fascia
    buckets = {
        "not_due": {"label": "Non scaduto", "amount": 0, "count": 0},
        "0_30": {"label": "0-30 giorni", "amount": 0, "count": 0},
        "31_60": {"label": "31-60 giorni", "amount": 0, "count": 0},
        "61_90": {"label": "61-90 giorni", "amount": 0, "count": 0},
        "over_90": {"label": "Oltre 90 giorni", "amount": 0, "count": 0}
    }
    
    for inv in invoices:
        due_date = inv.get("due_date", inv.get("date"))
        residual = inv.get("amount_residual", inv.get("total", 0))
        
        if not due_date:
            bucket = "not_due"
        elif due_date >= today:
            bucket = "not_due"
        else:
            try:
                days_overdue = (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(due_date, "%Y-%m-%d")).days
                if days_overdue <= 30:
                    bucket = "0_30"
                elif days_overdue <= 60:
                    bucket = "31_60"
                elif days_overdue <= 90:
                    bucket = "61_90"
                else:
                    bucket = "over_90"
            except ValueError:
                bucket = "not_due"
        
        buckets[bucket]["amount"] += residual
        buckets[bucket]["count"] += 1
    
    return {
        "success": True,
        "date": today,
        "buckets": buckets,
        "total": round_currency(sum(b["amount"] for b in buckets.values()))
    }


@router.get("/aged-payable")
async def get_aged_payable() -> Dict[str, Any]:
    """
    Scadenzario fornitori (Aged Payable).
    
    Come aged-receivable ma per i debiti.
    """
    db = Database.get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    
    invoices = await db["invoices"].find({
        "move_type": "in_invoice",
        "payment_state": {"$in": ["not_paid", "partial"]}
    }, {"_id": 0}).to_list(1000)
    
    buckets = {
        "not_due": {"label": "Non scaduto", "amount": 0, "count": 0},
        "0_30": {"label": "0-30 giorni", "amount": 0, "count": 0},
        "31_60": {"label": "31-60 giorni", "amount": 0, "count": 0},
        "61_90": {"label": "61-90 giorni", "amount": 0, "count": 0},
        "over_90": {"label": "Oltre 90 giorni", "amount": 0, "count": 0}
    }
    
    for inv in invoices:
        due_date = inv.get("due_date", inv.get("date"))
        residual = inv.get("amount_residual", inv.get("total", 0))
        
        if not due_date:
            bucket = "not_due"
        elif due_date >= today:
            bucket = "not_due"
        else:
            try:
                days_overdue = (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(due_date, "%Y-%m-%d")).days
                if days_overdue <= 30:
                    bucket = "0_30"
                elif days_overdue <= 60:
                    bucket = "31_60"
                elif days_overdue <= 90:
                    bucket = "61_90"
                else:
                    bucket = "over_90"
            except ValueError:
                bucket = "not_due"
        
        buckets[bucket]["amount"] += residual
        buckets[bucket]["count"] += 1
    
    return {
        "success": True,
        "date": today,
        "buckets": buckets,
        "total": round_currency(sum(b["amount"] for b in buckets.values()))
    }
