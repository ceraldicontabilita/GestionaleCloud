"""
Funzioni helper per auto-popolamento magazzino da fatture XML.
"""
import re
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


def normalize_product_name(name: str) -> str:
    """
    Normalizza nome prodotto per matching.
    Rimuove articoli, preposizioni e caratteri speciali.
    """
    if not name:
        return ""
    
    # Lowercase
    name = name.lower()
    
    # Rimuovi caratteri speciali eccetto spazi
    name = re.sub(r'[^\w\s]', ' ', name)
    
    # Articoli e preposizioni italiane da rimuovere
    stop_words = [
        'il', 'lo', 'la', 'i', 'gli', 'le',
        'un', 'uno', 'una',
        'di', 'da', 'in', 'con', 'su', 'per', 'tra', 'fra',
        'del', 'dello', 'della', 'dei', 'degli', 'delle',
        'al', 'allo', 'alla', 'ai', 'agli', 'alle',
        'dal', 'dallo', 'dalla', 'dai', 'dagli', 'dalle',
        'nel', 'nello', 'nella', 'nei', 'negli', 'nelle',
        'col', 'coi',
        'kg', 'lt', 'pz', 'conf', 'bott', 'cf', 'nr', 'n',
    ]
    
    words = name.split()
    words = [w for w in words if w not in stop_words and len(w) > 1]
    
    # Rimuovi numeri isolati (es. quantità)
    words = [w for w in words if not w.isdigit()]
    
    return ' '.join(words).strip()


def extract_unit_from_description(desc: str, default_unit: str = "") -> str:
    """Estrae unità di misura dalla descrizione."""
    if default_unit:
        return default_unit.upper()
        
    desc_lower = desc.lower()
    
    if 'kg' in desc_lower or 'kilo' in desc_lower:
        return 'KG'
    elif 'lt' in desc_lower or 'litri' in desc_lower or 'litro' in desc_lower:
        return 'LT'
    elif 'pz' in desc_lower or 'pezzi' in desc_lower or 'pezzo' in desc_lower:
        return 'PZ'
    elif 'conf' in desc_lower or 'confezione' in desc_lower:
        return 'CONF'
    elif 'bott' in desc_lower or 'bottigli' in desc_lower:
        return 'BOTT'
    elif 'gr' in desc_lower or 'grammi' in desc_lower:
        return 'GR'
    elif 'ml' in desc_lower:
        return 'ML'
    
    return 'PZ'


def categorize_product(desc: str) -> str:
    """Categorizza prodotto in base alla descrizione."""
    desc_lower = desc.lower()
    
    categories = {
        'bevande': ['coca', 'cola', 'fanta', 'sprite', 'acqua', 'birra', 'vino', 'succo', 'the', 'tè', 'bevand', 'redbull', 'energy', 'chinotto'],
        'caffe': ['caffè', 'caffe', 'espresso', 'lavazza', 'illy', 'kimbo', 'segafredo'],
        'latticini': ['latte', 'formaggio', 'mozzarella', 'panna', 'burro', 'yogurt', 'mascarpone', 'ricotta', 'grana', 'parmigiano'],
        'pasta_riso': ['pasta', 'spaghetti', 'penne', 'fusilli', 'riso', 'risotto', 'lasagna', 'ravioli'],
        'salumi': ['prosciutto', 'salame', 'mortadella', 'bresaola', 'speck', 'pancetta', 'bacon', 'wurstel'],
        'verdure': ['pomodoro', 'insalata', 'verdur', 'ortaggi', 'patate', 'cipolla', 'carota', 'zucchina', 'peperone'],
        'frutta': ['frutta', 'mela', 'pera', 'arancia', 'banana', 'limone', 'fragola', 'kiwi'],
        'carne': ['carne', 'pollo', 'manzo', 'maiale', 'vitello', 'bistecca', 'hamburger', 'salsiccia'],
        'pesce': ['pesce', 'tonno', 'salmone', 'gamberi', 'calamari', 'merluzzo', 'acciuga', 'pesce spada'],
        'pane': ['pane', 'panino', 'focaccia', 'grissini', 'cracker', 'pizza', 'impasto'],
        'condimenti': ['olio', 'aceto', 'sale', 'pepe', 'spezie', 'salsa', 'maionese', 'ketchup', 'senape'],
        'dolci': ['zucchero', 'cioccolato', 'biscotti', 'torta', 'gelato', 'dolce', 'marmellata', 'miele'],
        'snack': ['patatine', 'chips', 'snack', 'noccioline', 'salatini', 'taralli'],
        'pulizia': ['detergent', 'sapone', 'detersivo', 'pulizia', 'carta', 'igienica', 'scottex'],
        'attrezzature': ['bicchieri', 'piatti', 'posate', 'tovaglioli', 'contenitori', 'vaschette'],
        'farine': ['farina', 'semola', 'lievito', 'amido'],
        'grassi': ['margarina', 'strutto', 'grasso'],
    }
    
    for category, keywords in categories.items():
        for keyword in keywords:
            if keyword in desc_lower:
                return category
    
    return 'altro'


async def auto_populate_warehouse_from_invoice(db, invoice_data: Dict[str, Any], invoice_id: str) -> Dict[str, Any]:
    """
    Auto-popola il magazzino con i prodotti di una fattura.
    
    Args:
        db: Database connection
        invoice_data: Dati fattura parsati dal XML
        invoice_id: ID fattura nel database
        
    Returns:
        Dict con statistiche: products_created, products_updated, price_records
    """
    result = {
        "products_created": 0,
        "products_updated": 0,
        "price_records": 0,
        "errors": []
    }
    
    linee = invoice_data.get("linee", [])
    if not linee:
        return result
    
    fornitore = invoice_data.get("fornitore", {})
    supplier_name = fornitore.get("denominazione", "")
    supplier_vat = fornitore.get("partita_iva", "")
    
    numero_fattura = invoice_data.get("numero_fattura", "")
    data_fattura = invoice_data.get("data_fattura", "")
    
    for linea in linee:
        try:
            descrizione = linea.get("descrizione", "")
            if not descrizione or len(descrizione) < 3:
                continue
            
            # Normalizza nome
            nome_normalizzato = normalize_product_name(descrizione)
            if not nome_normalizzato:
                continue
            
            # Estrai dati
            try:
                quantita = float(linea.get("quantita", 1) or 1)
            except (ValueError, TypeError):
                quantita = 1.0
                
            try:
                prezzo_unitario = float(linea.get("prezzo_unitario", 0) or 0)
            except (ValueError, TypeError):
                prezzo_unitario = 0.0
                
            unita = extract_unit_from_description(descrizione, linea.get("unita_misura", ""))
            categoria = categorize_product(descrizione)
            
            if prezzo_unitario <= 0:
                continue
            
            # Cerca prodotto esistente
            existing = await db["warehouse_inventory"].find_one({
                "nome_normalizzato": nome_normalizzato
            })
            
            product_id = None
            
            if existing:
                product_id = existing.get("id")
                
                # Aggiorna prodotto esistente
                new_qty = existing.get("giacenza", 0) + quantita
                
                # Ricalcola prezzi
                prices = existing.get("prezzi", {})
                price_min = min(prices.get("min", prezzo_unitario), prezzo_unitario)
                price_max = max(prices.get("max", prezzo_unitario), prezzo_unitario)
                
                # Media ponderata
                old_avg = prices.get("avg", prezzo_unitario)
                old_qty = existing.get("giacenza", 0)
                total_qty = old_qty + quantita
                new_avg = ((old_avg * old_qty) + (prezzo_unitario * quantita)) / total_qty if total_qty > 0 else prezzo_unitario
                
                # Aggiungi a history
                history_entry = {
                    "data": data_fattura,
                    "fattura": numero_fattura,
                    "fornitore": supplier_name,
                    "quantita": quantita,
                    "prezzo": prezzo_unitario,
                    "tipo": "acquisto"
                }
                
                await db["warehouse_inventory"].update_one(
                    {"_id": existing["_id"]},
                    {
                        "$set": {
                            "giacenza": new_qty,
                            "prezzi": {
                                "min": round(price_min, 4),
                                "max": round(price_max, 4),
                                "avg": round(new_avg, 4)
                            },
                            "ultimo_acquisto": data_fattura,
                            "ultimo_fornitore": supplier_name,
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        },
                        "$push": {
                            "history": history_entry
                        },
                        "$addToSet": {
                            "fornitori": supplier_name
                        }
                    }
                )
                result["products_updated"] += 1
            else:
                # Crea nuovo prodotto
                product_id = str(uuid.uuid4())
                new_product = {
                    "id": product_id,
                    "nome": descrizione,
                    "nome_normalizzato": nome_normalizzato,
                    "categoria": categoria,
                    "unita_misura": unita,
                    "giacenza": quantita,
                    "giacenza_minima": 0,
                    "prezzi": {
                        "min": round(prezzo_unitario, 4),
                        "max": round(prezzo_unitario, 4),
                        "avg": round(prezzo_unitario, 4)
                    },
                    "fornitori": [supplier_name] if supplier_name else [],
                    "ultimo_acquisto": data_fattura,
                    "ultimo_fornitore": supplier_name,
                    "history": [{
                        "data": data_fattura,
                        "fattura": numero_fattura,
                        "fornitore": supplier_name,
                        "quantita": quantita,
                        "prezzo": prezzo_unitario,
                        "tipo": "acquisto"
                    }],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
                
                await db["warehouse_inventory"].insert_one(new_product.copy())
                result["products_created"] += 1
            
            # Salva storico prezzi
            if product_id:
                price_record = {
                    "id": str(uuid.uuid4()),
                    "product_id": product_id,
                    "product_name": descrizione,
                    "product_name_normalized": nome_normalizzato,
                    "supplier_name": supplier_name,
                    "supplier_vat": supplier_vat,
                    "price": prezzo_unitario,
                    "quantity": quantita,
                    "unit": unita,
                    "invoice_id": invoice_id,
                    "invoice_number": numero_fattura,
                    "invoice_date": data_fattura,
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
                
                await db["price_history"].insert_one(price_record.copy())
                result["price_records"] += 1
                
        except Exception as e:
            logger.error(f"Errore processamento linea: {e}")
            result["errors"].append(str(e))
    
    # Flag fattura come registrata in magazzino
    if result["products_created"] > 0 or result["products_updated"] > 0:
        await db["invoices"].update_one(
            {"id": invoice_id},
            {"$set": {
                "warehouse_registered": True, 
                "warehouse_updated_at": datetime.now(timezone.utc).isoformat(),
                "warehouse_products_count": result["products_created"] + result["products_updated"]
            }}
        )
    
    logger.info(f"Auto-popolamento completato: {result['products_created']} creati, {result['products_updated']} aggiornati")
    return result


async def get_product_catalog(db, category: Optional[str] = None, search: Optional[str] = None, days: int = 30, exact: bool = False) -> List[Dict[str, Any]]:
    """
    Restituisce catalogo prodotti con miglior prezzo ultimi N giorni.
    
    Args:
        exact: Se True, cerca match esatto invece di simili
    """
    query = {}
    if category:
        query["categoria"] = category
    if search:
        if exact:
            # Match esatto (case insensitive)
            query["$or"] = [
                {"nome": {"$regex": f"^{re.escape(search)}$", "$options": "i"}},
                {"nome_normalizzato": normalize_product_name(search)}
            ]
        else:
            # Match parziale (simili) - cerca in più campi
            search_terms = search.split()
            if len(search_terms) == 1:
                query["$or"] = [
                    {"nome": {"$regex": search, "$options": "i"}},
                    {"nome_normalizzato": {"$regex": search, "$options": "i"}}
                ]
            else:
                # Cerca tutti i termini
                conditions = []
                for term in search_terms:
                    conditions.append({"nome": {"$regex": term, "$options": "i"}})
                query["$and"] = conditions
    
    # Limita risultati per performance
    products = await db["warehouse_inventory"].find(query, {"_id": 0}).limit(500).to_list(500)
    
    # Restituisci prodotti con i prezzi già memorizzati (senza query aggiuntive)
    result = []
    for product in products:
        product["best_price"] = product.get("prezzi", {}).get("min")
        product["best_supplier"] = product.get("ultimo_fornitore")
        result.append(product)
    
    result.sort(key=lambda x: x.get("nome", "").lower())
    return result


async def search_products_predictive(db, query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Ricerca predittiva prodotti con matching intelligente.
    Include best_price per ogni prodotto.
    """
    if not query or len(query) < 2:
        return []
    
    query_normalized = normalize_product_name(query)
    query_words = set(query_normalized.split())
    
    products = await db["warehouse_inventory"].find({
        "$or": [
            {"nome": {"$regex": query, "$options": "i"}},
            {"nome_normalizzato": {"$regex": query_normalized, "$options": "i"}}
        ]
    }, {"_id": 0}).limit(50).to_list(50)
    
    # Date threshold per best price (ultimi 30 giorni)
    date_threshold = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    
    results = []
    for product in products:
        nome_norm = product.get("nome_normalizzato", "")
        product_words = set(nome_norm.split())
        
        # Word overlap score
        if product_words:
            overlap = len(query_words & product_words)
            word_score = overlap / len(query_words) if query_words else 0
        else:
            word_score = 0
        
        # Similarity score
        from difflib import SequenceMatcher
        similarity = SequenceMatcher(None, query_normalized, nome_norm).ratio()
        
        score = (word_score * 0.5) + (similarity * 0.5)
        
        if score >= 0.3:
            product["match_score"] = round(score * 100)
            
            # Aggiungi best_price
            product_id = product.get("id")
            if product_id:
                price_record = await db["price_history"].find_one(
                    {"product_id": product_id, "created_at": {"$gte": date_threshold}},
                    {"_id": 0, "price": 1, "supplier_name": 1},
                    sort=[("price", 1)]
                )
                if price_record:
                    product["best_price"] = price_record.get("price")
                    product["best_supplier"] = price_record.get("supplier_name")
                else:
                    # Fallback ai prezzi salvati nel prodotto
                    product["best_price"] = product.get("prezzi", {}).get("min")
                    product["best_supplier"] = product.get("ultimo_fornitore")
            else:
                product["best_price"] = product.get("prezzi", {}).get("min")
                product["best_supplier"] = product.get("ultimo_fornitore")
            
            # Aggiungi descrizione come alias di nome per il frontend
            product["descrizione"] = product.get("nome", "")
            
            results.append(product)
    
    results.sort(key=lambda x: x.get("match_score", 0), reverse=True)
    return results[:limit]


async def get_suppliers_for_product(db, product_id: str, days: int = 90) -> List[Dict[str, Any]]:
    """
    Restituisce fornitori e prezzi per un prodotto.
    """
    date_threshold = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    pipeline = [
        {
            "$match": {
                "product_id": product_id,
                "created_at": {"$gte": date_threshold}
            }
        },
        {
            "$group": {
                "_id": "$supplier_name",
                "supplier_vat": {"$first": "$supplier_vat"},
                "min_price": {"$min": "$price"},
                "max_price": {"$max": "$price"},
                "avg_price": {"$avg": "$price"},
                "last_price": {"$last": "$price"},
                "last_date": {"$max": "$invoice_date"},
                "count": {"$sum": 1}
            }
        },
        {
            "$sort": {"min_price": 1}
        }
    ]
    
    results = await db["price_history"].aggregate(pipeline).to_list(100)
    
    return [{
        "supplier_name": r["_id"],
        "supplier_vat": r.get("supplier_vat"),
        "min_price": round(r["min_price"], 2),
        "max_price": round(r["max_price"], 2),
        "avg_price": round(r["avg_price"], 2),
        "last_price": round(r["last_price"], 2),
        "last_date": r.get("last_date"),
        "purchase_count": r["count"]
    } for r in results]
