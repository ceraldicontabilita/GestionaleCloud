"""
Public API endpoints - Legacy endpoints non ancora refactorizzati.
Gli endpoint principali sono stati spostati nei router modulari:
- fatture_upload.py: /api/fatture
- corrispettivi_router.py: /api/corrispettivi
- iva_calcolo.py: /api/iva
- ordini_fornitori.py: /api/ordini-fornitori
- products_catalog.py: /api/products
- employees_payroll.py: /api/employees
- f24_tributi.py: /api/f24
"""
from fastapi import APIRouter, HTTPException, Query, Body, UploadFile, File
from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid
import logging

from datetime import timezone
from app.database import Database, Collections
from app.models.stati import STATI_PAGATI

logger = logging.getLogger(__name__)
router = APIRouter()


# ============== F24 PUBLIC ALERTS ==============

@router.get("/f24-public/alerts")
async def get_f24_alerts_public(
    anno: Optional[int] = Query(None, description="Filter by year")
) -> List[Dict[str, Any]]:
    """Alert pubblici scadenze F24 da tutte le collection."""
    db = Database.get_db()
    alerts = []
    today = datetime.now(timezone.utc).date()
    
    # Filtro anno per le query
    anno_filter = {}
    if anno:
        anno_str = str(anno)
        anno_filter = {"$or": [
            {"data_scadenza": {"$regex": f"^{anno_str}"}},
            {"scadenza_stimata": {"$regex": f"^{anno_str}"}},
            {"periodo_riferimento": {"$regex": anno_str}},
            {"dati_generali.data_versamento": {"$regex": f"^{anno_str}"}}
        ]}
    
    # Cerca in f24_models (non pagati)
    query_models = {
        "$or": [
            {"pagato": {"$ne": True}},
            {"pagato": {"$exists": False}}
        ]
    }
    if anno_filter:
        query_models = {"$and": [query_models, anno_filter]}
    
    f24_models = await db["f24_unificato"].find(query_models, {"_id": 0}).to_list(1000)
    
    # Cerca in f24_commercialista (non pagati e non eliminati)
    query_comm = {
        "status": {"$nin": STATI_PAGATI + ["eliminato"]},
    }
    if anno_filter:
        query_comm = {"$and": [query_comm, anno_filter]}
    
    f24_comm = await db["f24_unificato"].find(query_comm, {"_id": 0}).to_list(1000)
    
    all_f24 = []
    
    # Processa f24_models
    for f24 in f24_models:
        all_f24.append({
            "id": f24.get("id"),
            "tipo": "F24 Model",
            "descrizione": f24.get("contribuente", ""),
            "importo": f24.get("saldo_finale", 0),
            "scadenza_raw": f24.get("data_scadenza"),
            "tributi": [t.get("codice") for t in f24.get("tributi_erario", [])][:3],
            "source": "f24_models"
        })
    
    # Processa f24_commercialista  
    for f24 in f24_comm:
        scadenza = f24.get("scadenza_stimata") or f24.get("dati_generali", {}).get("data_versamento")
        tributi = [t.get("codice_tributo") for t in f24.get("sezione_erario", [])][:3]
        importo = f24.get("totali", {}).get("saldo_netto", 0)
        
        all_f24.append({
            "id": f24.get("id"),
            "tipo": "F24 Commercialista",
            "descrizione": f24.get("file_name", ""),
            "importo": importo,
            "scadenza_raw": scadenza,
            "tributi": tributi,
            "source": "f24_commercialista"
        })
    
    # Genera alerts
    for f24 in all_f24:
        try:
            scadenza_str = f24.get("scadenza_raw")
            if not scadenza_str:
                continue
            
            # Parse scadenza in vari formati
            scadenza = None
            if isinstance(scadenza_str, str):
                scadenza_str = scadenza_str.replace("Z", "+00:00")
                for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"]:
                    try:
                        scadenza = datetime.strptime(scadenza_str[:19], fmt).date()
                        break
                    except ValueError:
                        continue
            elif isinstance(scadenza_str, datetime):
                scadenza = scadenza_str.date()
            
            if not scadenza:
                continue
            
            giorni = (scadenza - today).days
            
            if giorni < 0:
                severity, msg = "critical", f"⚠️ SCADUTO da {abs(giorni)} giorni!"
            elif giorni == 0:
                severity, msg = "high", "⏰ SCADE OGGI!"
            elif giorni <= 3:
                severity, msg = "high", f"⚡ Scade tra {giorni} giorni"
            elif giorni <= 7:
                severity, msg = "medium", f"📅 Scade tra {giorni} giorni"
            elif giorni <= 30:
                severity, msg = "low", f"📌 Scade tra {giorni} giorni"
            else:
                continue
            
            alerts.append({
                "f24_id": f24.get("id"),
                "tipo": f24.get("tipo"),
                "descrizione": f24.get("descrizione", ""),
                "importo": float(f24.get("importo", 0) or 0),
                "scadenza": scadenza.isoformat(),
                "giorni_mancanti": giorni,
                "severity": severity,
                "messaggio": msg,
                "tributi": f24.get("tributi", []),
                "source": f24.get("source")
            })
        except Exception as e:
            logger.error(f"Error F24 alert: {e}")
    
    return sorted(alerts, key=lambda x: x["giorni_mancanti"])


@router.get("/f24-public/dashboard")
async def get_f24_dashboard_public(
    anno: Optional[int] = Query(None, description="Filter by year")
) -> Dict[str, Any]:
    """Dashboard pubblica F24."""
    db = Database.get_db()
    today = datetime.now(timezone.utc).date()
    
    query = {}
    if anno:
        anno_str = str(anno)
        query = {"$or": [
            {"data_scadenza": {"$regex": f"^{anno_str}"}},
            {"scadenza_stimata": {"$regex": f"^{anno_str}"}},
            {"periodo_riferimento": {"$regex": anno_str}}
        ]}
    
    all_f24 = await db[Collections.F24_MODELS].find(query, {"_id": 0}).to_list(10000)
    pagati = [f for f in all_f24 if f.get("status") == "paid"]
    non_pagati = [f for f in all_f24 if f.get("status") != "paid"]
    
    def days_to_scadenza(scadenza_str):
        try:
            if not scadenza_str:
                return 999
            if isinstance(scadenza_str, str):
                scadenza_str = scadenza_str.replace("Z", "+00:00")
                if "T" in scadenza_str:
                    scadenza = datetime.fromisoformat(scadenza_str).date()
                else:
                    try:
                        scadenza = datetime.strptime(scadenza_str, "%d/%m/%Y").date()
                    except ValueError:
                        scadenza = datetime.strptime(scadenza_str, "%Y-%m-%d").date()
                return (scadenza - today).days
            return 999
        except (ValueError, TypeError):
            return 999
    
    alert_attivi = sum(1 for f24 in non_pagati if days_to_scadenza(f24.get("scadenza")) <= 7)
    
    return {
        "totale_f24": len(all_f24),
        "pagati": {"count": len(pagati), "totale": round(sum(float(f.get("importo", 0) or 0) for f in pagati), 2)},
        "da_pagare": {"count": len(non_pagati), "totale": round(sum(float(f.get("importo", 0) or 0) for f in non_pagati), 2)},
        "alert_attivi": alert_attivi
    }


# ============== HACCP BASIC (Legacy) ==============

OPERATORI_HACCP = ["VALERIO", "VINCENZO", "POCCI"]
AZIENDA_INFO = {
    "ragione_sociale": "Ceraldi Group SRL",
    "indirizzo": "Piazza Carità 14 - 80134 Napoli (NA)",
    "piva": "04523831214",
    "telefono": "+393937415426",
    "email": "ceraldigroupsrl@gmail.com"
}


@router.get("/haccp/config")
async def get_haccp_config() -> Dict[str, Any]:
    """Configurazione HACCP."""
    return {
        "operatori": OPERATORI_HACCP,
        "temperature_limits": {"frigo": {"min": 2, "max": 5}, "congelatori": {"min": -25, "max": -15}},
        "azienda": AZIENDA_INFO
    }


@router.get("/haccp/temperatures")
async def list_temperatures(skip: int = 0, limit: int = 10000) -> List[Dict[str, Any]]:
    """Lista temperature HACCP legacy."""
    db = Database.get_db()
    return await db[Collections.HACCP_TEMPERATURES].find({}, {"_id": 0}).sort("recorded_at", -1).skip(skip).limit(limit).to_list(limit)


@router.post("/haccp/temperatures")
async def create_temperature(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Crea record temperatura HACCP."""
    db = Database.get_db()
    temp = {
        "id": str(uuid.uuid4()),
        "equipment_name": data.get("equipment_name", ""),
        "temperature": data.get("temperature", 0),
        "location": data.get("location", ""),
        "notes": data.get("notes", ""),
        "recorded_at": data.get("recorded_at", datetime.now(timezone.utc).isoformat()),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db[Collections.HACCP_TEMPERATURES].insert_one(temp.copy())
    temp.pop("_id", None)
    return temp


# ============== INVOICES ==============

@router.get("/invoices")
async def list_invoices(
    skip: int = 0, 
    limit: int = 10000,
    anno: Optional[int] = Query(None, description="Filter by year (YYYY)")
) -> List[Dict[str, Any]]:
    """Lista fatture con filtro opzionale per anno."""
    db = Database.get_db()
    query = {}
    
    # Filtro per anno
    # IMPORTANTE: Consideriamo sia invoice_date (fatture XML complete) 
    # che data_documento (fatture provvisorie da Aruba)
    if anno is not None:
        anno_start = f"{anno}-01-01"
        anno_end = f"{anno}-12-31"
        query["$or"] = [
            {"invoice_date": {"$gte": anno_start, "$lte": anno_end}},
            {"data_documento": {"$gte": anno_start, "$lte": anno_end}}
        ]
    
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
    
    results = await db[Collections.INVOICES].aggregate(pipeline).to_list(limit)
    return results


@router.post("/invoices")
async def create_invoice(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Crea fattura manuale."""
    db = Database.get_db()
    invoice = {
        "id": str(uuid.uuid4()),
        "invoice_number": data.get("invoice_number", ""),
        "supplier_name": data.get("supplier_name", ""),
        "total_amount": data.get("total_amount", 0),
        "invoice_date": data.get("invoice_date", ""),
        "status": data.get("status", "pending"),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db[Collections.INVOICES].insert_one(invoice.copy())
    invoice.pop("_id", None)
    return invoice


@router.delete("/invoices/{invoice_id}")
async def delete_invoice(
    invoice_id: str,
    force: bool = Query(False, description="Forza eliminazione")
) -> Dict[str, Any]:
    """
    Elimina fattura con validazione business rules.
    
    **Regole:**
    - Non può eliminare fatture pagate
    - Non può eliminare fatture registrate
    """
    from app.services.business_rules import BusinessRules, EntityStatus
    from datetime import timezone
    
    db = Database.get_db()
    invoice = await db[Collections.INVOICES].find_one({"id": invoice_id})
    if not invoice:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    # Valida con business rules
    validation = BusinessRules.can_delete_invoice(invoice)
    
    if not validation.is_valid:
        raise HTTPException(
            status_code=400,
            detail={"message": "Eliminazione non consentita", "errors": validation.errors}
        )
    
    if validation.warnings and not force:
        return {"status": "warning", "warnings": validation.warnings, "require_force": True}
    
    # Soft-delete
    await db[Collections.INVOICES].update_one(
        {"id": invoice_id},
        {"$set": {
            "entity_status": EntityStatus.DELETED.value,
            "status": "deleted",
            "deleted_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    return {"success": True, "deleted_id": invoice_id}


# ============== SUPPLIERS ==============
# NOTE: GET /suppliers è gestito da suppliers.py router con supporto per filtri (search, metodo_pagamento, etc.)

@router.post("/suppliers")
async def create_supplier(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Crea fornitore.
    Associa automaticamente le fatture esistenti con la stessa P.IVA.
    """
    db = Database.get_db()
    
    piva = data.get("partita_iva", data.get("vat_number", ""))
    denominazione = data.get("denominazione", data.get("name", ""))
    
    supplier = {
        "id": str(uuid.uuid4()),
        "name": denominazione,
        "vat_number": piva,
        "partita_iva": piva,
        "denominazione": denominazione,
        "email": data.get("email", ""),
        "phone": data.get("phone", ""),
        "address": data.get("address", ""),
        "metodo_pagamento": data.get("metodo_pagamento", "bonifico"),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db[Collections.SUPPLIERS].insert_one(supplier.copy())
    supplier.pop("_id", None)
    
    # === ASSOCIAZIONE AUTOMATICA FATTURE ===
    # Cerca fatture con la stessa P.IVA e aggiorna il riferimento al fornitore
    fatture_associate = 0
    if piva:
        result = await db[Collections.INVOICES].update_many(
            {"cedente_piva": piva, "supplier_id": {"$exists": False}},
            {"$set": {
                "supplier_id": supplier["id"],
                "supplier_name": denominazione,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        fatture_associate = result.modified_count
    
    supplier["fatture_associate"] = fatture_associate
    return supplier


# ============== WAREHOUSE ==============

@router.get("/warehouse/products")
async def list_warehouse_products(skip: int = 0, limit: int = 5000, category: Optional[str] = None, source: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lista prodotti magazzino con filtri opzionali."""
    db = Database.get_db()
    query = {}
    if category:
        query["category"] = category
    if source:
        query["source"] = source
    return await db[Collections.WAREHOUSE_PRODUCTS].find(query, {"_id": 0}).skip(skip).limit(limit).to_list(limit)


@router.post("/warehouse/products")
async def create_warehouse_product(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Crea prodotto magazzino."""
    db = Database.get_db()
    product = {
        "id": str(uuid.uuid4()),
        "name": data.get("name", ""),
        "code": data.get("code", ""),
        "description": data.get("description", ""),
        "quantity": float(data.get("quantity", 0)),
        "unit": data.get("unit", "pz"),
        "unit_price": float(data.get("unit_price", 0)),
        "category": data.get("category", ""),
        "supplier_vat": data.get("supplier_vat", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await db[Collections.WAREHOUSE_PRODUCTS].insert_one(product.copy())
    product.pop("_id", None)
    return product


@router.put("/warehouse/products/{product_id}")
async def update_warehouse_product(product_id: str, data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Aggiorna prodotto magazzino."""
    db = Database.get_db()
    
    update_data = {k: v for k, v in data.items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    result = await db[Collections.WAREHOUSE_PRODUCTS].update_one(
        {"id": product_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")
    
    product = await db[Collections.WAREHOUSE_PRODUCTS].find_one({"id": product_id}, {"_id": 0})
    return product


@router.delete("/warehouse/products/{product_id}")
async def delete_warehouse_product(product_id: str) -> Dict[str, Any]:
    """Elimina prodotto magazzino."""
    db = Database.get_db()
    result = await db[Collections.WAREHOUSE_PRODUCTS].delete_one({"id": product_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")
    return {"success": True, "deleted_id": product_id}


@router.get("/warehouse/movements")
async def list_warehouse_movements(
    skip: int = 0, 
    limit: int = 1000,
    product_id: Optional[str] = Query(None)
) -> List[Dict[str, Any]]:
    """Lista movimenti magazzino."""
    db = Database.get_db()
    query = {}
    if product_id:
        query["product_id"] = product_id
    return await db[Collections.WAREHOUSE_MOVEMENTS].find(query, {"_id": 0}).sort("date", -1).skip(skip).limit(limit).to_list(limit)


@router.post("/warehouse/movements")
async def create_warehouse_movement(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Crea movimento magazzino (carico/scarico)."""
    db = Database.get_db()
    
    movement = {
        "id": str(uuid.uuid4()),
        "product_id": data.get("product_id"),
        "type": data.get("type", "in"),  # "in" = carico, "out" = scarico
        "quantity": float(data.get("quantity", 0)),
        "date": data.get("date", datetime.now(timezone.utc).isoformat()[:10]),
        "reference": data.get("reference", ""),
        "notes": data.get("notes", ""),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Aggiorna quantità prodotto
    product = await db[Collections.WAREHOUSE_PRODUCTS].find_one({"id": movement["product_id"]})
    if product:
        delta = movement["quantity"] if movement["type"] == "in" else -movement["quantity"]
        new_qty = product.get("quantity", 0) + delta
        await db[Collections.WAREHOUSE_PRODUCTS].update_one(
            {"id": movement["product_id"]},
            {"$set": {"quantity": new_qty, "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
    
    await db[Collections.WAREHOUSE_MOVEMENTS].insert_one(movement.copy())
    movement.pop("_id", None)
    return movement


# ============== SUPPLIERS INVENTORY ==============

@router.get("/suppliers/{supplier_id}/inventory")
async def get_supplier_inventory(supplier_id: str) -> Dict[str, Any]:
    """
    Ottieni inventario prodotti di un fornitore.
    Estrae prodotti dalle fatture del fornitore.
    """
    db = Database.get_db()
    
    # Trova fornitore
    supplier = await db[Collections.SUPPLIERS].find_one(
        {"$or": [{"id": supplier_id}, {"partita_iva": supplier_id}]},
        {"_id": 0}
    )
    
    if not supplier:
        raise HTTPException(status_code=404, detail="Fornitore non trovato")
    
    piva = supplier.get("partita_iva", "")
    
    # Trova fatture del fornitore
    invoices = await db[Collections.INVOICES].find(
        {"$or": [
            {"supplier_vat": piva},
            {"cedente_piva": piva}
        ]},
        {"_id": 0, "linee": 1, "invoice_number": 1, "invoice_date": 1, "total_amount": 1}
    ).to_list(1000)
    
    # Estrai prodotti unici
    products = {}
    for inv in invoices:
        linee = inv.get("linee", [])
        for linea in linee:
            desc = linea.get("descrizione", "")
            if not desc:
                continue
            
            key = desc[:100].lower().strip()
            if key not in products:
                products[key] = {
                    "descrizione": desc,
                    "prezzo_ultimo": 0,
                    "quantita_totale": 0,
                    "fatture_count": 0,
                    "ultima_fattura": ""
                }
            
            products[key]["prezzo_ultimo"] = float(linea.get("prezzo_totale", 0) or 0)
            products[key]["quantita_totale"] += float(linea.get("quantita", 1) or 1)
            products[key]["fatture_count"] += 1
            products[key]["ultima_fattura"] = inv.get("invoice_date", "")
    
    return {
        "fornitore": supplier.get("denominazione", supplier.get("name", "")),
        "partita_iva": piva,
        "fatture_totali": len(invoices),
        "prodotti_unici": len(products),
        "prodotti": list(products.values())
    }


# ============== CASH ==============

@router.get("/cash")
async def list_cash(skip: int = 0, limit: int = 10000) -> List[Dict[str, Any]]:
    """Lista movimenti cassa."""
    db = Database.get_db()
    return await db[Collections.CASH_MOVEMENTS].find({}, {"_id": 0}).sort("date", -1).skip(skip).limit(limit).to_list(limit)


@router.post("/cash")
async def create_cash(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Crea movimento cassa."""
    db = Database.get_db()
    cash = {
        "id": str(uuid.uuid4()),
        "date": data.get("date", datetime.now(timezone.utc).isoformat()),
        "type": data.get("type", "in"),
        "amount": data.get("amount", 0),
        "description": data.get("description", ""),
        "category": data.get("category", ""),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db[Collections.CASH_MOVEMENTS].insert_one(cash.copy())
    cash.pop("_id", None)
    return cash


# ============== BANK ==============

@router.get("/bank/statements")
async def list_bank(skip: int = 0, limit: int = 10000) -> List[Dict[str, Any]]:
    """Lista movimenti banca."""
    db = Database.get_db()
    return await db["estratto_conto_movimenti"].find({}, {"_id": 0}).sort("date", -1).skip(skip).limit(limit).to_list(limit)


@router.post("/bank/statements")
async def create_bank(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Crea movimento banca."""
    db = Database.get_db()
    bank = {
        "id": str(uuid.uuid4()),
        "date": data.get("date", datetime.now(timezone.utc).isoformat()),
        "type": data.get("type", "in"),
        "amount": data.get("amount", 0),
        "description": data.get("description", ""),
        "category": data.get("category", ""),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db["estratto_conto_movimenti"].insert_one(bank.copy())
    bank.pop("_id", None)
    return bank


# ============== ORDERS ==============

@router.get("/orders")
async def list_orders(skip: int = 0, limit: int = 10000) -> List[Dict[str, Any]]:
    """Lista ordini."""
    db = Database.get_db()
    return await db[Collections.ORDERS].find({}, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)


@router.post("/orders")
async def create_order(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Crea ordine."""
    db = Database.get_db()
    order = {
        "id": str(uuid.uuid4()),
        "customer_name": data.get("customer_name", ""),
        "items": data.get("items", []),
        "total": data.get("total", 0),
        "status": data.get("status", "pending"),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db[Collections.ORDERS].insert_one(order.copy())
    order.pop("_id", None)
    return order


# ============== ASSEGNI ==============

@router.get("/assegni")
async def list_assegni(
    skip: int = 0, 
    limit: int = 10000,
    anno: int = None
) -> List[Dict[str, Any]]:
    """Lista assegni (esclusi soft-deleted), filtrabili per anno."""
    db = Database.get_db()
    # Filtra assegni eliminati (soft-delete)
    query = {"entity_status": {"$ne": "deleted"}}
    
    # Filtro per anno basato su data_emissione o created_at
    if anno:
        query["$or"] = [
            {"data_emissione": {"$regex": f"^{anno}"}},
            {"created_at": {"$regex": f"^{anno}"}},
            {"data": {"$regex": f"^{anno}"}},
            # Per assegni senza data, usa il numero (se inizia con prefisso anno)
            {"numero_assegno": {"$regex": f"^{anno}"}}
        ]
    
    return await db["assegni"].find(query, {"_id": 0}).sort("numero_assegno", -1).skip(skip).limit(limit).to_list(limit)


@router.post("/assegni")
async def create_assegno(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Crea assegno."""
    db = Database.get_db()
    assegno = {
        "id": str(uuid.uuid4()),
        "numero": data.get("numero", ""),
        "importo": data.get("importo", 0),
        "beneficiario": data.get("beneficiario", ""),
        "data_emissione": data.get("data_emissione", ""),
        "stato": data.get("stato", "emesso"),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db["assegni"].insert_one(assegno.copy())
    assegno.pop("_id", None)
    return assegno


# ============== PIANIFICAZIONE ==============

@router.get("/pianificazione/events")
async def list_events(skip: int = 0, limit: int = 10000) -> List[Dict[str, Any]]:
    """Lista eventi pianificazione."""
    db = Database.get_db()
    return await db["planning_events"].find({}, {"_id": 0}).sort("start_date", 1).skip(skip).limit(limit).to_list(limit)


@router.post("/pianificazione/events")
async def create_event(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Crea evento pianificazione."""
    db = Database.get_db()
    event = {
        "id": str(uuid.uuid4()),
        "title": data.get("title", ""),
        "start_date": data.get("start_date", ""),
        "end_date": data.get("end_date", ""),
        "type": data.get("type", "event"),
        "description": data.get("description", ""),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db["planning_events"].insert_one(event.copy())
    event.pop("_id", None)
    return event


# ============== FINANZIARIA ==============
# NOTA: L'endpoint /finanziaria/summary è stato spostato in finanziaria.py
# con supporto per filtro anno e logica contabile corretta


# ============== PORTAL UPLOAD ==============

@router.post("/portal/upload")
async def portal_upload(
    file: UploadFile = File(...),
    kind: str = ""
) -> Dict[str, Any]:
    """
    Upload generico portale con routing per tipo documento.
    
    kind values:
    - "estratto-conto": Redirect to bank statement import
    - "": Generic upload
    """
    content = await file.read()
    
    # Route to specific handler based on kind
    if kind == "estratto-conto":
        # Import bank statement module
        from app.routers.bank_statement_import import (
            extract_movements_from_pdf, 
            extract_movements_from_excel,
            reconcile_movement
        )
        
        filename = file.filename.lower()
        movements = []
        
        try:
            if filename.endswith('.pdf'):
                movements = extract_movements_from_pdf(content)
            elif filename.endswith(('.xlsx', '.xls', '.csv')):
                movements = extract_movements_from_excel(content, filename)
            else:
                return {
                    "success": False,
                    "error": "Formato non supportato. Usa PDF, Excel o CSV."
                }
        except Exception as e:
            return {
                "success": False,
                "error": f"Errore parsing file: {str(e)}"
            }
        
        if not movements:
            return {
                "success": False,
                "message": "Nessun movimento trovato nel file",
                "movements_found": 0
            }
        
        # Remove duplicates
        seen = set()
        unique_movements = []
        for m in movements:
            key = f"{m['data']}_{m['tipo']}_{m['importo']:.2f}"
            if key not in seen:
                seen.add(key)
                unique_movements.append(m)
        
        db = Database.get_db()
        results = {
            "success": True,
            "filename": file.filename,
            "movements_found": len(unique_movements),
            "reconciled": 0,
            "not_found": 0,
            "movements": [],
            "reconciled_details": [],
            "not_found_details": []
        }
        
        # Process and reconcile each movement
        for movement in unique_movements:
            match = await reconcile_movement(db, movement)
            
            mov_summary = {
                "data": movement["data"],
                "descrizione": movement["descrizione"][:50] if movement.get("descrizione") else "",
                "importo": movement["importo"],
                "tipo": movement["tipo"],
                "riconciliato": bool(match)
            }
            results["movements"].append(mov_summary)
            
            if match:
                results["reconciled"] += 1
                results["reconciled_details"].append({
                    "estratto_conto": mov_summary,
                    "prima_nota": match
                })
            else:
                results["not_found"] += 1
                results["not_found_details"].append(mov_summary)
        
        results["message"] = f"Importati {len(unique_movements)} movimenti. Riconciliati: {results['reconciled']}, Non trovati: {results['not_found']}"
        return results
    
    # Default: generic upload
    return {
        "success": True,
        "filename": file.filename,
        "size": len(content),
        "message": "File caricato (non elaborato)"
    }


# ============== DASHBOARD STATS ==============

@router.get("/dashboard/stats")
async def get_dashboard_stats() -> Dict[str, Any]:
    """Statistiche dashboard."""
    db = Database.get_db()
    return {
        "invoices": await db[Collections.INVOICES].count_documents({}),
        "suppliers": await db[Collections.SUPPLIERS].count_documents({}),
        "employees": await db[Collections.EMPLOYEES].count_documents({}),
        "corrispettivi": await db["corrispettivi"].count_documents({})
    }


# ============== FORNITORI METODI PAGAMENTO ==============

@router.get("/fornitori/metodi-pagamento")
async def get_metodi_pagamento() -> List[str]:
    """Lista metodi pagamento disponibili."""
    return ["contanti", "bonifico", "assegno", "carta", "riba", "mav", "rid", "altro"]


@router.post("/fornitori/import-metodi-da-fatture")
async def import_metodi_from_invoices() -> Dict[str, Any]:
    """Importa metodi pagamento da fatture."""
    db = Database.get_db()
    
    invoices = await db[Collections.INVOICES].find(
        {"pagamento.ModalitaPagamento": {"$exists": True}},
        {"supplier_vat": 1, "pagamento": 1}
    ).to_list(10000)
    
    updated = 0
    for inv in invoices:
        vat = inv.get("supplier_vat")
        modalita = inv.get("pagamento", {}).get("ModalitaPagamento")
        
        if vat and modalita:
            metodo = "bonifico"
            if modalita in ["MP01"]:
                metodo = "contanti"
            elif modalita in ["MP02", "MP03"]:
                metodo = "assegno"
            elif modalita in ["MP05", "MP06", "MP07"]:
                metodo = "bonifico"
            
            result = await db[Collections.SUPPLIERS].update_one(
                {"partita_iva": vat, "metodo_pagamento": {"$exists": False}},
                {"$set": {"metodo_pagamento": metodo}}
            )
            if result.modified_count > 0:
                updated += 1
    
    return {"updated": updated}


# ============== RICERCA GLOBALE ==============

@router.get("/ricerca-globale")
async def global_search_public(
    q: str = Query(..., min_length=2),
    limit: int = Query(10, ge=1, le=50)
) -> Dict[str, Any]:
    """
    Ricerca globale in fatture, fornitori, prodotti, dipendenti.
    Restituisce risultati unificati per la barra di ricerca.
    """
    db = Database.get_db()
    results = []
    per_limit = min(limit // 4 + 1, 10)
    
    # Search invoices (fatture)
    try:
        invoice_results = await db[Collections.INVOICES].find(
            {"$or": [
                {"cedente_denominazione": {"$regex": q, "$options": "i"}},
                {"supplier_name": {"$regex": q, "$options": "i"}},
                {"numero_fattura": {"$regex": q, "$options": "i"}},
                {"invoice_number": {"$regex": q, "$options": "i"}}
            ]},
            {"_id": 0, "id": 1, "invoice_key": 1, "numero_fattura": 1, "invoice_number": 1, 
             "cedente_denominazione": 1, "supplier_name": 1, "importo_totale": 1, "total_amount": 1,
             "data_fattura": 1, "invoice_date": 1}
        ).limit(per_limit).to_list(per_limit)
        
        for inv in invoice_results:
            num = inv.get("numero_fattura") or inv.get("invoice_number", "N/A")
            fornitore = inv.get("cedente_denominazione") or inv.get("supplier_name", "")
            importo = float(inv.get("importo_totale") or inv.get("total_amount", 0) or 0)
            data = inv.get("data_fattura") or inv.get("invoice_date", "")
            
            results.append({
                "tipo": "fattura",
                "id": inv.get("id") or inv.get("invoice_key", ""),
                "titolo": f"Fattura {num}",
                "sottotitolo": f"{fornitore} - €{importo:.2f} ({data[:10] if data else 'N/A'})"
            })
    except Exception as e:
        logger.error(f"Error searching invoices: {e}")
    
    # Search suppliers (fornitori) - con matching migliorato
    try:
        # Prepara regex per matching parziale (ogni parola separatamente)
        words = q.strip().split()
        if words:
            # Crea pattern che cerca ogni parola
            word_patterns = [{"$or": [
                {"denominazione": {"$regex": w, "$options": "i"}},
                {"name": {"$regex": w, "$options": "i"}}
            ]} for w in words]
            
            supplier_query = {"$and": word_patterns} if len(word_patterns) > 1 else word_patterns[0]
        else:
            supplier_query = {"$or": [
                {"denominazione": {"$regex": q, "$options": "i"}},
                {"name": {"$regex": q, "$options": "i"}},
                {"partita_iva": {"$regex": q, "$options": "i"}},
                {"vat_number": {"$regex": q, "$options": "i"}}
            ]}
        
        supplier_results = await db[Collections.SUPPLIERS].find(
            supplier_query,
            {"_id": 0, "id": 1, "denominazione": 1, "name": 1, "partita_iva": 1, "vat_number": 1}
        ).limit(per_limit).to_list(per_limit)
        
        for sup in supplier_results:
            nome = sup.get("denominazione") or sup.get("name", "N/A")
            piva = sup.get("partita_iva") or sup.get("vat_number", "")
            sup_id = sup.get("id", "")
            
            # Conta fatture per questo fornitore
            fatture_count = 0
            fatture_totale = 0
            try:
                pipeline = [
                    {"$match": {"$or": [
                        {"cedente_denominazione": {"$regex": nome[:20], "$options": "i"}},
                        {"supplier_name": {"$regex": nome[:20], "$options": "i"}},
                        {"supplier_id": sup_id}
                    ]}},
                    {"$group": {
                        "_id": None,
                        "count": {"$sum": 1},
                        "totale": {"$sum": {"$ifNull": ["$importo_totale", {"$ifNull": ["$total_amount", 0]}]}}
                    }}
                ]
                agg_result = await db[Collections.INVOICES].aggregate(pipeline).to_list(1)
                if agg_result:
                    fatture_count = agg_result[0].get("count", 0)
                    fatture_totale = agg_result[0].get("totale", 0)
            except Exception as e:
                logger.warning(f"Error counting invoices for supplier: {e}")
            
            sottotitolo = []
            if piva:
                sottotitolo.append(f"P.IVA: {piva}")
            if fatture_count > 0:
                sottotitolo.append(f"{fatture_count} fatture | €{fatture_totale:,.0f}")
            
            results.append({
                "tipo": "fornitore",
                "id": sup_id,
                "titolo": nome,
                "sottotitolo": " | ".join(sottotitolo) if sottotitolo else ""
            })
    except Exception as e:
        logger.error(f"Error searching suppliers: {e}")
    
    # Search products (prodotti magazzino)
    try:
        product_results = await db[Collections.WAREHOUSE_PRODUCTS].find(
            {"$or": [
                {"nome": {"$regex": q, "$options": "i"}},
                {"name": {"$regex": q, "$options": "i"}},
                {"codice": {"$regex": q, "$options": "i"}},
                {"code": {"$regex": q, "$options": "i"}}
            ]},
            {"_id": 0, "id": 1, "nome": 1, "name": 1, "codice": 1, "code": 1, 
             "giacenza": 1, "quantity": 1, "prezzo": 1, "price": 1}
        ).limit(per_limit).to_list(per_limit)
        
        for prod in product_results:
            nome = prod.get("nome") or prod.get("name", "N/A")
            codice = prod.get("codice") or prod.get("code", "")
            giacenza = prod.get("giacenza") or prod.get("quantity", 0)
            prezzo = float(prod.get("prezzo") or prod.get("price", 0) or 0)
            
            results.append({
                "tipo": "prodotto",
                "id": prod.get("id", ""),
                "titolo": nome,
                "sottotitolo": f"Cod: {codice} | Giac: {giacenza} | €{prezzo:.2f}" if codice else f"Giac: {giacenza} | €{prezzo:.2f}"
            })
    except Exception as e:
        logger.error(f"Error searching products: {e}")
    
    # Search employees (dipendenti)
    try:
        employee_results = await db[Collections.EMPLOYEES].find(
            {"$or": [
                {"nome": {"$regex": q, "$options": "i"}},
                {"cognome": {"$regex": q, "$options": "i"}},
                {"name": {"$regex": q, "$options": "i"}},
                {"codice_fiscale": {"$regex": q, "$options": "i"}},
                {"fiscal_code": {"$regex": q, "$options": "i"}}
            ]},
            {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "name": 1, 
             "codice_fiscale": 1, "fiscal_code": 1, "mansione": 1, "role": 1}
        ).limit(per_limit).to_list(per_limit)
        
        for emp in employee_results:
            nome = emp.get("nome", "")
            cognome = emp.get("cognome", "")
            full_name = f"{nome} {cognome}".strip() or emp.get("name", "N/A")
            cf = emp.get("codice_fiscale") or emp.get("fiscal_code", "")
            mansione = emp.get("mansione") or emp.get("role", "")
            
            results.append({
                "tipo": "dipendente",
                "id": emp.get("id", ""),
                "titolo": full_name,
                "sottotitolo": f"{mansione} | CF: {cf[:6]}..." if cf else mansione
            })
    except Exception as e:
        logger.error(f"Error searching employees: {e}")
    
    return {
        "query": q,
        "total": len(results),
        "results": results[:limit]
    }



# ============================================
# API PUBBLICA V1 - INTEGRAZIONI ESTERNE
# ============================================
import hashlib
import secrets

async def verify_api_key_header(x_api_key: str) -> Dict[str, Any]:
    """Verifica API Key e restituisce info client."""
    db = Database.get_db()
    key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()
    
    api_client = await db["api_clients"].find_one(
        {"key_hash": key_hash, "active": True},
        {"_id": 0}
    )
    
    if not api_client:
        raise HTTPException(status_code=401, detail="API Key non valida")
    
    await db["api_clients"].update_one(
        {"key_hash": key_hash},
        {"$set": {"last_used": datetime.now(timezone.utc).isoformat()}, "$inc": {"request_count": 1}}
    )
    
    return api_client


@router.post("/v1/keys/generate")
async def api_genera_key(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Genera nuova API Key per integrazioni esterne."""
    db = Database.get_db()
    
    api_key = f"ak_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    
    client_doc = {
        "id": f"client_{secrets.token_hex(8)}",
        "nome": data.get("nome", "Client API"),
        "key_hash": key_hash,
        "key_prefix": api_key[:12],
        "permessi": data.get("permessi", ["read"]),
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "request_count": 0
    }
    
    await db["api_clients"].insert_one(dict(client_doc).copy())
    
    return {
        "success": True,
        "api_key": api_key,
        "client_id": client_doc["id"],
        "nota": "Salva questa API Key, non sarà più visualizzabile!"
    }


@router.get("/v1/keys")
async def api_lista_keys() -> Dict[str, Any]:
    """Lista API Keys (senza mostrare le key complete)."""
    db = Database.get_db()
    clients = await db["api_clients"].find({}, {"_id": 0, "key_hash": 0}).to_list(100)
    return {"clients": clients}


@router.get("/v1/fatture")
async def api_v1_fatture(
    tipo: str = Query("ricevute"),
    anno: Optional[int] = None,
    limit: int = Query(100, le=500),
    x_api_key: str = Query(..., alias="api_key")
) -> Dict[str, Any]:
    """API pubblica - Lista fatture. Richiede api_key come parametro."""
    await verify_api_key_header(x_api_key)
    
    db = Database.get_db()
    collection = "fatture_ricevute" if tipo == "ricevute" else "fatture_emesse"
    
    query = {}
    if anno:
        query["$or"] = [
            {"data_fattura": {"$regex": f"^{anno}"}},
            {"data_ricezione": {"$regex": f"^{anno}"}}
        ]
    
    fatture = await db[collection].find(query, {"_id": 0}).limit(limit).to_list(limit)
    return {"data": fatture, "total": len(fatture)}


@router.get("/v1/movimenti")
async def api_v1_movimenti(
    data_da: Optional[str] = None,
    data_a: Optional[str] = None,
    limit: int = Query(100, le=500),
    x_api_key: str = Query(..., alias="api_key")
) -> Dict[str, Any]:
    """API pubblica - Lista movimenti prima nota."""
    await verify_api_key_header(x_api_key)
    
    db = Database.get_db()
    query = {}
    if data_da:
        query["data"] = {"$gte": data_da}
    if data_a:
        query.setdefault("data", {})["$lte"] = data_a
    
    movimenti = await db["prima_nota_cassa"].find(query, {"_id": 0}).sort("data", -1).limit(limit).to_list(limit)
    return {"data": movimenti, "total": len(movimenti)}


@router.get("/v1/stats")
async def api_v1_stats(
    anno: int = Query(...),
    x_api_key: str = Query(..., alias="api_key")
) -> Dict[str, Any]:
    """API pubblica - Statistiche aggregate."""
    await verify_api_key_header(x_api_key)
    
    db = Database.get_db()
    
    return {
        "anno": anno,
        "fatture_ricevute": await db["invoices"].count_documents({"data_ricezione": {"$regex": f"^{anno}"}}),
        "fatture_emesse": await db["fatture_emesse"].count_documents({"data_fattura": {"$regex": f"^{anno}"}}),
        "movimenti": await db["prima_nota_cassa"].count_documents({"data": {"$regex": f"^{anno}"}}),
        "dipendenti_attivi": await db["employees"].count_documents({"status": {"$in": ["active", "attivo"]}})
    }
