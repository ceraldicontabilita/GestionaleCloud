"""Magazzino Products router."""
from fastapi import APIRouter, Depends, Query
from typing import Dict, Any, List
from datetime import datetime, timezone
import logging
import uuid
import re

from app.database import Database, Collections
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/products",
    summary="Get magazzino products"
)
async def get_magazzino_products(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Get magazzino products."""
    db = Database.get_db()
    products = await db[Collections.WAREHOUSE_PRODUCTS].find({}, {"_id": 0}).to_list(1000)
    return products


@router.post(
    "/popola-da-fatture",
    summary="Popola magazzino da fatture XML"
)
async def popola_magazzino_da_fatture(
    anno: int = Query(None, description="Anno delle fatture da analizzare"),
    fornitore_piva: str = Query(None, description="P.IVA fornitore specifico"),
    dry_run: bool = Query(False, description="Se True, simula senza salvare")
) -> Dict[str, Any]:
    """
    Estrae i prodotti dalle fatture di acquisto XML e popola il magazzino.
    
    Logica:
    - Legge il campo 'line_items' delle fatture
    - Crea/aggiorna prodotti nel catalogo magazzino
    - Associa fornitore e prezzo di acquisto
    """
    db = Database.get_db()
    
    # Query fatture
    query = {}
    if anno:
        query["$or"] = [
            {"data_ricezione": {"$regex": f"^{anno}"}},
            {"invoice_date": {"$regex": f"^{anno}"}}
        ]
    if fornitore_piva:
        query["cedente_prestatore.partita_iva"] = fornitore_piva
    
    fatture = await db["invoices"].find(query, {"_id": 0}).to_list(10000)
    
    prodotti_estratti = []
    prodotti_creati = 0
    prodotti_aggiornati = 0
    errori = []
    
    for fattura in fatture:
        line_items = fattura.get("line_items", [])
        fornitore = fattura.get("cedente_prestatore", {})
        fornitore_nome = fornitore.get("denominazione", "")
        fornitore_piva_doc = fornitore.get("partita_iva", "")
        
        for item in line_items:
            try:
                descrizione = item.get("description", "") or item.get("descrizione", "")
                if not descrizione or len(descrizione) < 3:
                    continue
                
                # Estrai dati prodotto
                quantita = float(item.get("quantity", 0) or item.get("quantita", 0) or 0)
                prezzo_unitario = float(item.get("unit_price", 0) or item.get("prezzo_unitario", 0) or 0)
                totale = float(item.get("total", 0) or item.get("totale", 0) or 0)
                unita_misura = item.get("unit_of_measure", "") or item.get("unita_misura", "") or "PZ"
                codice = item.get("code", "") or item.get("codice", "") or ""
                aliquota_iva = item.get("tax_rate", 22) or item.get("aliquota_iva", 22)
                
                # Genera codice se non presente
                if not codice:
                    # Crea codice da descrizione
                    codice = _genera_codice_prodotto(descrizione)
                
                # Normalizza descrizione
                descrizione_normalizzata = _normalizza_descrizione(descrizione)
                
                prodotto_info = {
                    "codice": codice,
                    "descrizione": descrizione_normalizzata,
                    "descrizione_originale": descrizione,
                    "quantita_ultima_fattura": quantita,
                    "prezzo_acquisto": prezzo_unitario,
                    "unita_misura": unita_misura,
                    "aliquota_iva": aliquota_iva,
                    "fornitore_nome": fornitore_nome,
                    "fornitore_piva": fornitore_piva_doc,
                    "ultima_fattura_data": fattura.get("data_ricezione") or fattura.get("invoice_date"),
                    "ultima_fattura_numero": fattura.get("numero_documento") or fattura.get("invoice_number")
                }
                
                prodotti_estratti.append(prodotto_info)
                
                if not dry_run:
                    # Cerca prodotto esistente per codice o descrizione simile
                    existing = await db[Collections.WAREHOUSE_PRODUCTS].find_one({
                        "$or": [
                            {"codice": codice},
                            {"descrizione": {"$regex": f"^{re.escape(descrizione_normalizzata[:20])}", "$options": "i"}}
                        ]
                    })
                    
                    if existing:
                        # Aggiorna prodotto esistente
                        update_data = {
                            "prezzo_acquisto": prezzo_unitario,
                            "fornitore_nome": fornitore_nome,
                            "fornitore_piva": fornitore_piva_doc,
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }
                        await db[Collections.WAREHOUSE_PRODUCTS].update_one(
                            {"id": existing.get("id")},
                            {"$set": update_data}
                        )
                        prodotti_aggiornati += 1
                    else:
                        # Crea nuovo prodotto
                        new_product = {
                            "id": str(uuid.uuid4()),
                            "codice": codice,
                            "nome": descrizione_normalizzata,
                            "descrizione": descrizione,
                            "categoria": _identifica_categoria(descrizione),
                            "unita_misura": unita_misura,
                            "prezzo_acquisto": prezzo_unitario,
                            "prezzo_vendita": prezzo_unitario * 1.3,  # Margine default 30%
                            "aliquota_iva": aliquota_iva,
                            "giacenza": 0,
                            "scorta_minima": 0,
                            "fornitore_nome": fornitore_nome,
                            "fornitore_piva": fornitore_piva_doc,
                            "attivo": True,
                            "created_at": datetime.now(timezone.utc).isoformat()
                        }
                        await db[Collections.WAREHOUSE_PRODUCTS].insert_one(new_product.copy())
                        prodotti_creati += 1
                        
            except Exception as e:
                errori.append({"fattura": fattura.get("invoice_number"), "item": str(item)[:50], "errore": str(e)})
    
    return {
        "success": True,
        "dry_run": dry_run,
        "fatture_analizzate": len(fatture),
        "prodotti_estratti": len(prodotti_estratti),
        "prodotti_creati": prodotti_creati if not dry_run else 0,
        "prodotti_aggiornati": prodotti_aggiornati if not dry_run else 0,
        "errori": errori[:10] if errori else [],
        "anteprima_prodotti": prodotti_estratti[:20] if dry_run else []
    }


def _genera_codice_prodotto(descrizione: str) -> str:
    """Genera un codice prodotto dalla descrizione."""
    # Rimuovi caratteri speciali, prendi prime 3 parole
    parole = re.sub(r'[^a-zA-Z0-9\s]', '', descrizione).upper().split()[:3]
    codice_base = ''.join([p[:3] for p in parole if len(p) >= 2])
    # Aggiungi hash per unicità
    import hashlib
    hash_suffix = hashlib.md5(descrizione.encode()).hexdigest()[:4].upper()
    return f"{codice_base}-{hash_suffix}"


def _normalizza_descrizione(descrizione: str) -> str:
    """Normalizza la descrizione del prodotto."""
    # Rimuovi codici, numeri di riferimento, ecc.
    desc = re.sub(r'\b(cod\.|art\.|rif\.)\s*[\w\-]+', '', descrizione, flags=re.IGNORECASE)
    desc = re.sub(r'\s+', ' ', desc).strip()
    # Capitalizza
    return desc.title() if desc else descrizione.title()


def _identifica_categoria(descrizione: str) -> str:
    """Identifica la categoria del prodotto dalla descrizione."""
    desc_lower = descrizione.lower()
    
    categorie = {
        "Alimentari": ["pasta", "olio", "farina", "zucchero", "sale", "riso", "caffè", "tè", "latte", "formaggio", "carne", "pesce", "verdura", "frutta", "pane", "pizza", "salsa", "pomodoro", "tonno", "legumi"],
        "Bevande": ["vino", "birra", "acqua", "succo", "coca", "sprite", "fanta", "energy", "drink", "champagne", "prosecco", "whisky", "vodka", "rum", "gin"],
        "Detergenti": ["detersivo", "sapone", "detergente", "sgrassatore", "candeggina", "ammoniaca", "pulito", "igienizzante"],
        "Carta e Igiene": ["carta", "tovaglioli", "scottex", "fazzoletti", "rotolo", "asciugamani", "guanti"],
        "Attrezzature": ["pentola", "padella", "coltello", "forchetta", "cucchiaio", "piatto", "bicchiere", "contenitore", "vaschetta"],
        "Packaging": ["sacchetto", "busta", "scatola", "cartone", "pellicola", "alluminio", "contenitore"],
        "Condimenti": ["spezie", "pepe", "origano", "basilico", "prezzemolo", "aglio", "cipolla", "aceto", "maionese", "ketchup", "senape"]
    }
    
    for categoria, keywords in categorie.items():
        if any(kw in desc_lower for kw in keywords):
            return categoria
    
    return "Altro"


@router.get(
    "/catalogo",
    summary="Catalogo prodotti magazzino"
)
async def get_catalogo_prodotti(
    categoria: str = Query(None),
    fornitore: str = Query(None),
    search: str = Query(None),
    skip: int = Query(0),
    limit: int = Query(100)
) -> Dict[str, Any]:
    """Ottiene il catalogo prodotti con filtri."""
    db = Database.get_db()
    
    query = {"attivo": {"$ne": False}}
    
    if categoria:
        query["categoria"] = categoria
    if fornitore:
        query["$or"] = [
            {"fornitore_nome": {"$regex": fornitore, "$options": "i"}},
            {"fornitore_piva": fornitore}
        ]
    if search:
        query["$or"] = [
            {"nome": {"$regex": search, "$options": "i"}},
            {"descrizione": {"$regex": search, "$options": "i"}},
            {"codice": {"$regex": search, "$options": "i"}}
        ]
    
    total = await db[Collections.WAREHOUSE_PRODUCTS].count_documents(query)
    prodotti = await db[Collections.WAREHOUSE_PRODUCTS].find(
        query, {"_id": 0}
    ).skip(skip).limit(limit).to_list(limit)
    
    # Ottieni categorie disponibili
    categorie = await db[Collections.WAREHOUSE_PRODUCTS].distinct("categoria")
    
    return {
        "prodotti": prodotti,
        "total": total,
        "skip": skip,
        "limit": limit,
        "categorie_disponibili": [c for c in categorie if c]
    }
