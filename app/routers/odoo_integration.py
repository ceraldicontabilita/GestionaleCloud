"""
Odoo External API Integration Module

Integrazione completa con Odoo via XML-RPC per sincronizzazione bidirezionale di:
- Partner (Clienti/Fornitori)
- Fatture (account.move)
- Prodotti (product.product)
- Dipendenti (hr.employee)
- Buste Paga (hr.payslip)
- Ordini Vendita/Acquisto

Documentazione Odoo: https://www.odoo.com/documentation/18.0/developer/reference/external_api.html
"""

import logging
import os
import xmlrpc.client
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel

from app.database import Database

logger = logging.getLogger(__name__)
router = APIRouter()

# ============================================
# CONFIGURAZIONE
# ============================================

ODOO_URL = os.environ.get("ODOO_URL", "")
ODOO_DB = os.environ.get("ODOO_DB", "")
ODOO_USERNAME = os.environ.get("ODOO_USERNAME", "")
ODOO_PASSWORD = os.environ.get("ODOO_PASSWORD", "")  # o API Key


class OdooConfig(BaseModel):
    url: str
    db: str
    username: str
    password: str


class OdooClient:
    """Client XML-RPC per Odoo"""
    
    def __init__(self, url: str, db: str, username: str, password: str):
        self.url = url.rstrip('/')
        self.db = db
        self.username = username
        self.password = password
        self.uid = None
        self._common = None
        self._models = None
    
    @property
    def common(self):
        if not self._common:
            self._common = xmlrpc.client.ServerProxy(f'{self.url}/xmlrpc/2/common')
        return self._common
    
    @property
    def models(self):
        if not self._models:
            self._models = xmlrpc.client.ServerProxy(f'{self.url}/xmlrpc/2/object')
        return self._models
    
    def authenticate(self) -> int:
        """Autentica l'utente e restituisce l'UID"""
        if self.uid:
            return self.uid
        
        try:
            self.uid = self.common.authenticate(self.db, self.username, self.password, {})
            if not self.uid:
                raise Exception("Autenticazione fallita - credenziali non valide")
            logger.info(f"Autenticazione Odoo riuscita - UID: {self.uid}")
            return self.uid
        except Exception as e:
            logger.error(f"Errore autenticazione Odoo: {e}")
            raise
    
    def version(self) -> Dict[str, Any]:
        """Ottiene la versione del server Odoo"""
        return self.common.version()
    
    def execute(self, model: str, method: str, *args, **kwargs) -> Any:
        """Esegue un metodo su un modello Odoo"""
        if not self.uid:
            self.authenticate()
        
        return self.models.execute_kw(
            self.db, self.uid, self.password,
            model, method, args, kwargs
        )
    
    # ==========================================
    # METODI CRUD GENERICI
    # ==========================================
    
    def search(self, model: str, domain: List = None, offset: int = 0, limit: int = None) -> List[int]:
        """Cerca record per dominio"""
        domain = domain or []
        kwargs = {'offset': offset}
        if limit:
            kwargs['limit'] = limit
        return self.execute(model, 'search', domain, **kwargs)
    
    def search_count(self, model: str, domain: List = None) -> int:
        """Conta i record che matchano il dominio"""
        domain = domain or []
        return self.execute(model, 'search_count', domain)
    
    def read(self, model: str, ids: List[int], fields: List[str] = None) -> List[Dict]:
        """Legge i dati dei record specificati"""
        kwargs = {}
        if fields:
            kwargs['fields'] = fields
        return self.execute(model, 'read', ids, **kwargs)
    
    def search_read(self, model: str, domain: List = None, fields: List[str] = None, 
                    offset: int = 0, limit: int = None, order: str = None) -> List[Dict]:
        """Cerca e legge in un'unica chiamata"""
        domain = domain or []
        kwargs = {'offset': offset}
        if fields:
            kwargs['fields'] = fields
        if limit:
            kwargs['limit'] = limit
        if order:
            kwargs['order'] = order
        return self.execute(model, 'search_read', domain, **kwargs)
    
    def create(self, model: str, values: Dict) -> int:
        """Crea un nuovo record"""
        return self.execute(model, 'create', values)
    
    def write(self, model: str, ids: List[int], values: Dict) -> bool:
        """Aggiorna record esistenti"""
        return self.execute(model, 'write', ids, values)
    
    def unlink(self, model: str, ids: List[int]) -> bool:
        """Elimina record"""
        return self.execute(model, 'unlink', ids)
    
    def fields_get(self, model: str, attributes: List[str] = None) -> Dict:
        """Ottiene i metadati dei campi di un modello"""
        kwargs = {}
        if attributes:
            kwargs['attributes'] = attributes
        return self.execute(model, 'fields_get', **kwargs)


# Istanza globale del client (lazy initialization)
_odoo_client: Optional[OdooClient] = None

def get_odoo_client() -> OdooClient:
    """Ottiene il client Odoo configurato"""
    global _odoo_client
    
    if not _odoo_client:
        if not all([ODOO_URL, ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD]):
            raise HTTPException(
                status_code=400,
                detail="Configurazione Odoo mancante. Imposta ODOO_URL, ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD"
            )
        _odoo_client = OdooClient(ODOO_URL, ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD)
    
    return _odoo_client


# ============================================
# ENDPOINTS API
# ============================================

@router.get("/status")
async def odoo_status() -> Dict[str, Any]:
    """Verifica lo stato della connessione Odoo"""
    configured = bool(ODOO_URL and ODOO_DB and ODOO_USERNAME and ODOO_PASSWORD)
    
    if not configured:
        return {
            "status": "not_configured",
            "message": "Credenziali Odoo non configurate",
            "config_needed": ["ODOO_URL", "ODOO_DB", "ODOO_USERNAME", "ODOO_PASSWORD"]
        }
    
    try:
        client = get_odoo_client()
        version = client.version()
        uid = client.authenticate()
        
        return {
            "status": "connected",
            "odoo_version": version.get("server_version"),
            "user_id": uid,
            "database": ODOO_DB,
            "url": ODOO_URL
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "url": ODOO_URL
        }


@router.post("/configure")
async def configure_odoo(config: OdooConfig) -> Dict[str, Any]:
    """Configura le credenziali Odoo (salva in .env)"""
    global _odoo_client
    
    # Testa la connessione prima di salvare
    test_client = OdooClient(config.url, config.db, config.username, config.password)
    try:
        version = test_client.version()
        uid = test_client.authenticate()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Connessione fallita: {e}")
    
    # Salva configurazione nel database
    db = Database.get_db()
    await db["configurazioni"].update_one(
        {"chiave": "odoo"},
        {"$set": {
            "chiave": "odoo",
            "url": config.url,
            "db": config.db,
            "username": config.username,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }},
        upsert=True
    )
    
    # Aggiorna client globale
    _odoo_client = test_client
    
    return {
        "success": True,
        "message": "Connessione Odoo configurata",
        "odoo_version": version.get("server_version"),
        "user_id": uid
    }


# ============================================
# PARTNER (CLIENTI/FORNITORI)
# ============================================

@router.get("/partners")
async def get_odoo_partners(
    is_company: bool = Query(None),
    customer: bool = Query(None),
    supplier: bool = Query(None),
    limit: int = Query(100),
    offset: int = Query(0)
) -> Dict[str, Any]:
    """Lista partner da Odoo (clienti/fornitori)"""
    client = get_odoo_client()
    
    domain = []
    if is_company is not None:
        domain.append(['is_company', '=', is_company])
    if customer:
        domain.append(['customer_rank', '>', 0])
    if supplier:
        domain.append(['supplier_rank', '>', 0])
    
    fields = ['name', 'vat', 'email', 'phone', 'street', 'city', 'country_id', 
              'customer_rank', 'supplier_rank', 'is_company']
    
    partners = client.search_read('res.partner', domain, fields, offset, limit)
    total = client.search_count('res.partner', domain)
    
    return {
        "success": True,
        "total": total,
        "offset": offset,
        "limit": limit,
        "partners": partners
    }


@router.post("/partners/sync-to-local")
async def sync_partners_to_local(limit: int = Query(500)) -> Dict[str, Any]:
    """Sincronizza partner Odoo → Database locale"""
    client = get_odoo_client()
    db = Database.get_db()
    
    fields = ['name', 'vat', 'email', 'phone', 'street', 'city', 'zip', 
              'country_id', 'customer_rank', 'supplier_rank', 'is_company']
    
    partners = client.search_read('res.partner', [], fields, limit=limit)
    
    created = 0
    updated = 0
    
    for p in partners:
        piva = p.get('vat', '').replace('IT', '').strip() if p.get('vat') else None
        
        # Determina se è fornitore o cliente
        if p.get('supplier_rank', 0) > 0:
            # Fornitore
            existing = await db["suppliers"].find_one({"partita_iva": piva}) if piva else None
            
            doc = {
                "odoo_id": p['id'],
                "ragione_sociale": p.get('name'),
                "partita_iva": piva,
                "email": p.get('email'),
                "telefono": p.get('phone'),
                "indirizzo": p.get('street'),
                "citta": p.get('city'),
                "cap": p.get('zip'),
                "paese": p['country_id'][1] if p.get('country_id') else None,
                "sync_odoo": datetime.now(timezone.utc).isoformat()
            }
            
            if existing:
                await db["suppliers"].update_one({"_id": existing["_id"]}, {"$set": doc})
                updated += 1
            else:
                doc["id"] = f"odoo_{p['id']}"
                doc["created_at"] = datetime.now(timezone.utc).isoformat()
                await db["suppliers"].insert_one(doc)
                created += 1
    
    return {
        "success": True,
        "partners_letti": len(partners),
        "creati": created,
        "aggiornati": updated
    }


# ============================================
# FATTURE (account.move)
# ============================================

@router.get("/invoices")
async def get_odoo_invoices(
    move_type: str = Query(None, description="out_invoice, in_invoice, out_refund, in_refund"),
    state: str = Query(None, description="draft, posted, cancel"),
    limit: int = Query(100),
    offset: int = Query(0)
) -> Dict[str, Any]:
    """Lista fatture da Odoo"""
    client = get_odoo_client()
    
    domain = [['move_type', 'in', ['out_invoice', 'in_invoice', 'out_refund', 'in_refund']]]
    if move_type:
        domain = [['move_type', '=', move_type]]
    if state:
        domain.append(['state', '=', state])
    
    fields = ['name', 'move_type', 'partner_id', 'invoice_date', 'invoice_date_due',
              'amount_total', 'amount_tax', 'amount_untaxed', 'state', 'payment_state',
              'currency_id', 'ref']
    
    invoices = client.search_read('account.move', domain, fields, offset, limit, order='invoice_date desc')
    total = client.search_count('account.move', domain)
    
    return {
        "success": True,
        "total": total,
        "invoices": invoices
    }


@router.get("/invoices/{invoice_id}/lines")
async def get_invoice_lines(invoice_id: int) -> Dict[str, Any]:
    """Ottiene le righe di una fattura"""
    client = get_odoo_client()
    
    fields = ['name', 'quantity', 'price_unit', 'price_subtotal', 'tax_ids', 
              'product_id', 'account_id', 'discount']
    
    lines = client.search_read(
        'account.move.line',
        [['move_id', '=', invoice_id], ['display_type', 'in', ['product', False]]],
        fields
    )
    
    return {
        "success": True,
        "invoice_id": invoice_id,
        "lines": lines
    }


@router.post("/invoices/sync-to-local")
async def sync_invoices_to_local(
    move_type: str = Query("in_invoice"),
    limit: int = Query(500)
) -> Dict[str, Any]:
    """Sincronizza fatture Odoo → Database locale"""
    client = get_odoo_client()
    db = Database.get_db()
    
    domain = [['move_type', '=', move_type], ['state', '=', 'posted']]
    
    fields = ['name', 'move_type', 'partner_id', 'invoice_date', 'invoice_date_due',
              'amount_total', 'amount_tax', 'amount_untaxed', 'state', 'ref']
    
    invoices = client.search_read('account.move', domain, fields, limit=limit)
    
    created = 0
    updated = 0
    collection = "fatture_ricevute" if move_type == "in_invoice" else "fatture_emesse"
    
    for inv in invoices:
        existing = await db[collection].find_one({"odoo_id": inv['id']})
        
        doc = {
            "odoo_id": inv['id'],
            "numero_fattura": inv.get('name'),
            "data_fattura": inv.get('invoice_date'),
            "data_scadenza": inv.get('invoice_date_due'),
            "fornitore_id": inv['partner_id'][0] if inv.get('partner_id') else None,
            "fornitore_nome": inv['partner_id'][1] if inv.get('partner_id') else None,
            "totale_imponibile": inv.get('amount_untaxed', 0),
            "totale_iva": inv.get('amount_tax', 0),
            "totale_fattura": inv.get('amount_total', 0),
            "riferimento": inv.get('ref'),
            "sync_odoo": datetime.now(timezone.utc).isoformat()
        }
        
        if existing:
            await db[collection].update_one({"_id": existing["_id"]}, {"$set": doc})
            updated += 1
        else:
            doc["id"] = f"odoo_{inv['id']}"
            doc["created_at"] = datetime.now(timezone.utc).isoformat()
            await db[collection].insert_one(doc)
            created += 1
    
    return {
        "success": True,
        "tipo": move_type,
        "fatture_lette": len(invoices),
        "create": created,
        "aggiornate": updated
    }


# ============================================
# PRODOTTI (product.product)
# ============================================

@router.get("/products")
async def get_odoo_products(
    limit: int = Query(100),
    offset: int = Query(0),
    category_id: int = Query(None)
) -> Dict[str, Any]:
    """Lista prodotti da Odoo"""
    client = get_odoo_client()
    
    domain = []
    if category_id:
        domain.append(['categ_id', '=', category_id])
    
    fields = ['name', 'default_code', 'list_price', 'standard_price', 
              'categ_id', 'type', 'qty_available', 'uom_id', 'barcode']
    
    products = client.search_read('product.product', domain, fields, offset, limit)
    total = client.search_count('product.product', domain)
    
    return {
        "success": True,
        "total": total,
        "products": products
    }


@router.post("/products/sync-to-local")
async def sync_products_to_local(limit: int = Query(1000)) -> Dict[str, Any]:
    """Sincronizza prodotti Odoo → Database locale (magazzino)"""
    client = get_odoo_client()
    db = Database.get_db()
    
    fields = ['name', 'default_code', 'list_price', 'standard_price', 
              'categ_id', 'type', 'qty_available', 'uom_id', 'barcode']
    
    products = client.search_read('product.product', [], fields, limit=limit)
    
    created = 0
    updated = 0
    
    for p in products:
        existing = await db["magazzino"].find_one({"odoo_id": p['id']})
        
        doc = {
            "odoo_id": p['id'],
            "codice": p.get('default_code') or f"ODOO_{p['id']}",
            "descrizione": p.get('name'),
            "prezzo_vendita": p.get('list_price', 0),
            "prezzo_acquisto": p.get('standard_price', 0),
            "categoria": p['categ_id'][1] if p.get('categ_id') else None,
            "tipo": p.get('type'),
            "quantita": p.get('qty_available', 0),
            "unita_misura": p['uom_id'][1] if p.get('uom_id') else 'PZ',
            "barcode": p.get('barcode'),
            "sync_odoo": datetime.now(timezone.utc).isoformat()
        }
        
        if existing:
            await db["magazzino"].update_one({"_id": existing["_id"]}, {"$set": doc})
            updated += 1
        else:
            doc["id"] = f"odoo_{p['id']}"
            doc["created_at"] = datetime.now(timezone.utc).isoformat()
            await db["magazzino"].insert_one(doc)
            created += 1
    
    return {
        "success": True,
        "prodotti_letti": len(products),
        "creati": created,
        "aggiornati": updated
    }


# ============================================
# DIPENDENTI (hr.employee)
# ============================================

@router.get("/employees")
async def get_odoo_employees(
    limit: int = Query(100),
    offset: int = Query(0),
    active: bool = Query(True)
) -> Dict[str, Any]:
    """Lista dipendenti da Odoo"""
    client = get_odoo_client()
    
    domain = []
    if active is not None:
        domain.append(['active', '=', active])
    
    # Campi compatibili con Odoo 19.1 (senza address_home_id)
    fields = ['name', 'work_email', 'work_phone', 'job_title', 'department_id',
              'identification_id', 'birthday', 'contract_id']
    
    employees = client.search_read('hr.employee', domain, fields, offset, limit)
    total = client.search_count('hr.employee', domain)
    
    return {
        "success": True,
        "total": total,
        "employees": employees
    }


@router.post("/employees/sync-to-local")
async def sync_employees_to_local(limit: int = Query(500)) -> Dict[str, Any]:
    """Sincronizza dipendenti Odoo → Database locale"""
    client = get_odoo_client()
    db = Database.get_db()
    
    fields = ['name', 'work_email', 'work_phone', 'job_title', 'department_id',
              'identification_id', 'birthday', 'active']
    
    employees = client.search_read('hr.employee', [], fields, limit=limit)
    
    created = 0
    updated = 0
    
    for emp in employees:
        # Cerca per nome (il CF potrebbe non essere in Odoo)
        nome_parts = emp.get('name', '').split()
        cognome = nome_parts[0] if nome_parts else ''
        nome = ' '.join(nome_parts[1:]) if len(nome_parts) > 1 else ''
        
        existing = await db["employees"].find_one({
            "$or": [
                {"odoo_id": emp['id']},
                {"nome_completo": emp.get('name')}
            ]
        })
        
        doc = {
            "odoo_id": emp['id'],
            "nome_completo": emp.get('name'),
            "cognome": cognome,
            "nome": nome,
            "email": emp.get('work_email'),
            "telefono": emp.get('work_phone'),
            "mansione": emp.get('job_title'),
            "reparto": emp['department_id'][1] if emp.get('department_id') else None,
            "matricola": emp.get('identification_id'),
            "data_nascita": emp.get('birthday'),
            "attivo": emp.get('active', True),
            "sync_odoo": datetime.now(timezone.utc).isoformat()
        }
        
        if existing:
            await db["employees"].update_one({"_id": existing["_id"]}, {"$set": doc})
            updated += 1
        else:
            import uuid
            doc["id"] = str(uuid.uuid4())
            doc["created_at"] = datetime.now(timezone.utc).isoformat()
            await db["employees"].insert_one(doc)
            created += 1
    
    return {
        "success": True,
        "dipendenti_letti": len(employees),
        "creati": created,
        "aggiornati": updated
    }


# ============================================
# BUSTE PAGA (hr.payslip)
# ============================================

@router.get("/payslips")
async def get_odoo_payslips(
    employee_id: int = Query(None),
    state: str = Query(None),
    limit: int = Query(100),
    offset: int = Query(0)
) -> Dict[str, Any]:
    """Lista buste paga da Odoo"""
    client = get_odoo_client()
    
    domain = []
    if employee_id:
        domain.append(['employee_id', '=', employee_id])
    if state:
        domain.append(['state', '=', state])
    
    fields = ['name', 'employee_id', 'date_from', 'date_to', 'state',
              'struct_id', 'contract_id', 'net_wage', 'basic_wage']
    
    payslips = client.search_read('hr.payslip', domain, fields, offset, limit, order='date_from desc')
    total = client.search_count('hr.payslip', domain)
    
    return {
        "success": True,
        "total": total,
        "payslips": payslips
    }


@router.get("/payslips/{payslip_id}/lines")
async def get_payslip_lines(payslip_id: int) -> Dict[str, Any]:
    """Ottiene le righe/voci di una busta paga"""
    client = get_odoo_client()
    
    fields = ['name', 'code', 'category_id', 'quantity', 'rate', 'amount', 'total']
    
    lines = client.search_read(
        'hr.payslip.line',
        [['slip_id', '=', payslip_id]],
        fields
    )
    
    return {
        "success": True,
        "payslip_id": payslip_id,
        "lines": lines
    }


# ============================================
# ORDINI VENDITA/ACQUISTO
# ============================================

@router.get("/sale-orders")
async def get_odoo_sale_orders(
    state: str = Query(None),
    limit: int = Query(100),
    offset: int = Query(0)
) -> Dict[str, Any]:
    """Lista ordini di vendita da Odoo"""
    client = get_odoo_client()
    
    domain = []
    if state:
        domain.append(['state', '=', state])
    
    fields = ['name', 'partner_id', 'date_order', 'amount_total', 'state', 
              'invoice_status', 'delivery_status']
    
    orders = client.search_read('sale.order', domain, fields, offset, limit, order='date_order desc')
    total = client.search_count('sale.order', domain)
    
    return {
        "success": True,
        "total": total,
        "orders": orders
    }


@router.get("/purchase-orders")
async def get_odoo_purchase_orders(
    state: str = Query(None),
    limit: int = Query(100),
    offset: int = Query(0)
) -> Dict[str, Any]:
    """Lista ordini di acquisto da Odoo"""
    client = get_odoo_client()
    
    domain = []
    if state:
        domain.append(['state', '=', state])
    
    fields = ['name', 'partner_id', 'date_order', 'amount_total', 'state', 
              'invoice_status']
    
    orders = client.search_read('purchase.order', domain, fields, offset, limit, order='date_order desc')
    total = client.search_count('purchase.order', domain)
    
    return {
        "success": True,
        "total": total,
        "orders": orders
    }


# ============================================
# PIANO DEI CONTI E ALIQUOTE IVA
# ============================================

@router.get("/chart-of-accounts")
async def get_odoo_chart_of_accounts(limit: int = Query(500)) -> Dict[str, Any]:
    """Lista piano dei conti da Odoo"""
    client = get_odoo_client()
    
    # Campi compatibili con Odoo 19.1
    fields = ['code', 'name', 'account_type', 'reconcile']
    accounts = client.search_read('account.account', [], fields, limit=limit, order='code')
    
    return {
        "success": True,
        "total": len(accounts),
        "accounts": accounts
    }


@router.post("/chart-of-accounts/sync-to-local")
async def sync_chart_of_accounts_to_local() -> Dict[str, Any]:
    """Sincronizza piano dei conti Odoo → Database locale"""
    client = get_odoo_client()
    db = Database.get_db()
    
    # Campi compatibili con Odoo 19.1
    fields = ['code', 'name', 'account_type', 'reconcile']
    accounts = client.search_read('account.account', [], fields, limit=500, order='code')
    
    created = 0
    updated = 0
    
    # Mappa account_type Odoo → tipo italiano
    TYPE_MAP = {
        'asset_receivable': 'attivo_crediti',
        'asset_cash': 'attivo_liquidita',
        'asset_current': 'attivo_corrente',
        'asset_non_current': 'attivo_immobilizzato',
        'asset_prepayments': 'attivo_ratei',
        'asset_fixed': 'attivo_immobilizzato',
        'liability_payable': 'passivo_debiti',
        'liability_credit_card': 'passivo_debiti',
        'liability_current': 'passivo_corrente',
        'liability_non_current': 'passivo_lungo_termine',
        'equity': 'patrimonio_netto',
        'equity_unaffected': 'patrimonio_netto',
        'income': 'ricavo',
        'income_other': 'ricavo_altro',
        'expense': 'costo',
        'expense_depreciation': 'costo_ammortamento',
        'expense_direct_cost': 'costo_diretto',
        'off_balance': 'conti_ordine',
    }
    
    for acc in accounts:
        existing = await db["piano_conti"].find_one({"codice": acc['code']})
        
        doc = {
            "odoo_id": acc['id'],
            "codice": acc['code'],
            "descrizione": acc['name'],
            "tipo_odoo": acc.get('account_type'),
            "tipo": TYPE_MAP.get(acc.get('account_type'), 'altro'),
            "riconciliabile": acc.get('reconcile', False),
            "sync_odoo": datetime.now(timezone.utc).isoformat()
        }
        
        if existing:
            await db["piano_conti"].update_one({"_id": existing["_id"]}, {"$set": doc})
            updated += 1
        else:
            doc["id"] = f"odoo_{acc['id']}"
            doc["created_at"] = datetime.now(timezone.utc).isoformat()
            await db["piano_conti"].insert_one(doc)
            created += 1
    
    return {
        "success": True,
        "conti_letti": len(accounts),
        "creati": created,
        "aggiornati": updated
    }


@router.get("/taxes")
async def get_odoo_taxes(limit: int = Query(100)) -> Dict[str, Any]:
    """Lista aliquote IVA da Odoo"""
    client = get_odoo_client()
    
    fields = ['name', 'amount', 'type_tax_use', 'active', 'description']
    taxes = client.search_read('account.tax', [['active', '=', True]], fields, limit=limit)
    
    return {
        "success": True,
        "total": len(taxes),
        "taxes": taxes
    }


@router.post("/taxes/sync-to-local")
async def sync_taxes_to_local() -> Dict[str, Any]:
    """Sincronizza aliquote IVA Odoo → Database locale"""
    client = get_odoo_client()
    db = Database.get_db()
    
    fields = ['name', 'amount', 'type_tax_use', 'active', 'description']
    taxes = client.search_read('account.tax', [['active', '=', True]], fields, limit=100)
    
    created = 0
    updated = 0
    
    for tax in taxes:
        existing = await db["aliquote_iva"].find_one({"odoo_id": tax['id']})
        
        doc = {
            "odoo_id": tax['id'],
            "codice": tax['name'][:20].replace(' ', '_').upper(),
            "descrizione": tax['name'],
            "aliquota": abs(tax.get('amount', 0)),
            "tipo_uso": tax.get('type_tax_use'),  # sale, purchase, none
            "is_ritenuta": tax.get('amount', 0) < 0,
            "sync_odoo": datetime.now(timezone.utc).isoformat()
        }
        
        if existing:
            await db["aliquote_iva"].update_one({"_id": existing["_id"]}, {"$set": doc})
            updated += 1
        else:
            doc["id"] = f"odoo_{tax['id']}"
            doc["created_at"] = datetime.now(timezone.utc).isoformat()
            await db["aliquote_iva"].insert_one(doc)
            created += 1
    
    return {
        "success": True,
        "aliquote_lette": len(taxes),
        "create": created,
        "aggiornate": updated
    }


@router.get("/journals")
async def get_odoo_journals() -> Dict[str, Any]:
    """Lista giornali contabili da Odoo"""
    client = get_odoo_client()
    
    fields = ['name', 'code', 'type', 'default_account_id']
    journals = client.search_read('account.journal', [], fields)
    
    return {
        "success": True,
        "total": len(journals),
        "journals": journals
    }




# ============================================
# METODI GENERICI
# ============================================

@router.get("/models")
async def list_odoo_models(search: str = Query(None)) -> Dict[str, Any]:
    """Lista tutti i modelli disponibili in Odoo"""
    client = get_odoo_client()
    
    domain = []
    if search:
        domain = [['model', 'ilike', search]]
    
    models = client.search_read(
        'ir.model',
        domain,
        ['name', 'model', 'state'],
        limit=500
    )
    
    return {
        "success": True,
        "total": len(models),
        "models": models
    }


@router.get("/fields/{model}")
async def get_model_fields(model: str) -> Dict[str, Any]:
    """Ottiene i campi di un modello Odoo"""
    client = get_odoo_client()
    
    fields = client.fields_get(model, ['string', 'type', 'help', 'required', 'readonly'])
    
    return {
        "success": True,
        "model": model,
        "fields": fields
    }


@router.post("/execute")
async def execute_odoo_method(
    model: str = Body(...),
    method: str = Body(...),
    args: List = Body(default=[]),
    kwargs: Dict = Body(default={})
) -> Dict[str, Any]:
    """
    Esegue un metodo generico su un modello Odoo.
    
    Esempio:
    {
        "model": "res.partner",
        "method": "search_read",
        "args": [[["is_company", "=", true]]],
        "kwargs": {"fields": ["name", "email"], "limit": 10}
    }
    """
    client = get_odoo_client()
    
    try:
        result = client.execute(model, method, *args, **kwargs)
        return {
            "success": True,
            "model": model,
            "method": method,
            "result": result
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
