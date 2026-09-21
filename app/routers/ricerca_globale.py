"""Ricerca globale condivisa temporaneamente con il frontend Lotti.

Estratta dal router storico in Fase 0C. Verrà assorbita dal frontend unico
quando Lotti diventerà un modulo nativo ERP.
"""
import logging
import re
from typing import Any, Dict

from fastapi import APIRouter, Query

from app.database import Collections, Database

logger = logging.getLogger(__name__)
router = APIRouter()

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
                {"cedente_denominazione": {"$regex": re.escape(q), "$options": "i"}},
                {"supplier_name": {"$regex": re.escape(q), "$options": "i"}},
                {"numero_fattura": {"$regex": re.escape(q), "$options": "i"}},
                {"invoice_number": {"$regex": re.escape(q), "$options": "i"}}
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
                {"denominazione": {"$regex": re.escape(w), "$options": "i"}},
                {"name": {"$regex": re.escape(w), "$options": "i"}}
            ]} for w in words]
            
            supplier_query = {"$and": word_patterns} if len(word_patterns) > 1 else word_patterns[0]
        else:
            supplier_query = {"$or": [
                {"denominazione": {"$regex": re.escape(q), "$options": "i"}},
                {"name": {"$regex": re.escape(q), "$options": "i"}},
                {"partita_iva": {"$regex": re.escape(q), "$options": "i"}},
                {"vat_number": {"$regex": re.escape(q), "$options": "i"}}
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
                        {"cedente_denominazione": {"$regex": re.escape(nome[:20]), "$options": "i"}},
                        {"supplier_name": {"$regex": re.escape(nome[:20]), "$options": "i"}},
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
                {"nome": {"$regex": re.escape(q), "$options": "i"}},
                {"name": {"$regex": re.escape(q), "$options": "i"}},
                {"codice": {"$regex": re.escape(q), "$options": "i"}},
                {"code": {"$regex": re.escape(q), "$options": "i"}}
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
                {"nome": {"$regex": re.escape(q), "$options": "i"}},
                {"cognome": {"$regex": re.escape(q), "$options": "i"}},
                {"name": {"$regex": re.escape(q), "$options": "i"}},
                {"codice_fiscale": {"$regex": re.escape(q), "$options": "i"}},
                {"fiscal_code": {"$regex": re.escape(q), "$options": "i"}}
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



