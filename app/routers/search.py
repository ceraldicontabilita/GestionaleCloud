"""Search router - Global search functionality."""
from fastapi import APIRouter, Query
from typing import Dict, Any
import logging

from app.database import Database, Collections

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/global",
    summary="Global search",
    description="Search across all collections"
)
async def global_search(
    q: str = Query(..., min_length=2),
    limit: int = Query(10, ge=1, le=50)
) -> Dict[str, Any]:
    """
    Ricerca globale in fatture, fornitori, prodotti, dipendenti.
    Restituisce risultati unificati.
    """
    db = Database.get_db()
    results = []
    per_limit = min(limit // 4 + 1, 10)  # Divide limit tra le categorie
    
    # Search invoices (fatture)
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
        importo = inv.get("importo_totale") or inv.get("total_amount", 0)
        data = inv.get("data_fattura") or inv.get("invoice_date", "")
        
        results.append({
            "tipo": "fattura",
            "id": inv.get("id") or inv.get("invoice_key", ""),
            "titolo": f"Fattura {num}",
            "sottotitolo": f"{fornitore} - €{importo:.2f} ({data[:10] if data else 'N/A'})"
        })
    
    # Search suppliers (fornitori)
    supplier_results = await db[Collections.SUPPLIERS].find(
        {"$or": [
            {"denominazione": {"$regex": q, "$options": "i"}},
            {"name": {"$regex": q, "$options": "i"}},
            {"partita_iva": {"$regex": q, "$options": "i"}},
            {"vat_number": {"$regex": q, "$options": "i"}}
        ]},
        {"_id": 0, "id": 1, "denominazione": 1, "name": 1, "partita_iva": 1, "vat_number": 1}
    ).limit(per_limit).to_list(per_limit)
    
    for sup in supplier_results:
        nome = sup.get("denominazione") or sup.get("name", "N/A")
        piva = sup.get("partita_iva") or sup.get("vat_number", "")
        
        results.append({
            "tipo": "fornitore",
            "id": sup.get("id", ""),
            "titolo": nome,
            "sottotitolo": f"P.IVA: {piva}" if piva else ""
        })
    
    # Search products (prodotti magazzino)
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
        prezzo = prod.get("prezzo") or prod.get("price", 0)
        
        results.append({
            "tipo": "prodotto",
            "id": prod.get("id", ""),
            "titolo": nome,
            "sottotitolo": f"Cod: {codice} | Giac: {giacenza} | €{prezzo:.2f}" if codice else f"Giac: {giacenza} | €{prezzo:.2f}"
        })
    
    # Search employees (dipendenti)
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
    
    return {
        "query": q,
        "total": len(results),
        "results": results[:limit]
    }
