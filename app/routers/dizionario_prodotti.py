"""
Dizionario Prodotti - Sistema per Food Cost e Tracciabilità

Questo modulo:
1. Scandaglia tutti i prodotti dalle fatture fornitori
2. Memorizza peso unitario e prezzo al kg/litro/pezzo
3. Permette di associare ingredienti ricette ai prodotti fattura
4. Calcola automaticamente il food cost
"""

from fastapi import APIRouter, HTTPException, Query, Body
from typing import List, Dict, Any, Optional
from app.database import Database
from datetime import datetime, timezone
import uuid
import re
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# Collection names
COLLECTION_DIZIONARIO = "dizionario_prodotti"
COLLECTION_INVOICES = "invoices"
COLLECTION_RICETTE = "ricette"


def parse_peso_da_descrizione(descrizione: str) -> Dict[str, Any]:
    """
    Estrae peso/quantità dalla descrizione del prodotto.
    
    Esempi:
    - "AQV CROI STR CIN CRM BTR 95G 4.94KG" -> peso_totale: 4.94, unita: "kg"
    - "OLIO EXTRAVERGINE 1L" -> peso_totale: 1, unita: "l"
    - "FARINA 00 25KG" -> peso_totale: 25, unita: "kg"
    - "FARINA 00 CAPUTO RINFORZ.KG.25" -> peso_totale: 25, unita: "kg"
    - "DA KG.5" -> peso_totale: 5, unita: "kg"
    """
    desc_upper = descrizione.upper()
    
    # Pattern per peso in kg - supporta:
    # 25KG, 25 KG, KG.25, KG 25, DA KG.5, KG1, 4.94KG
    kg_match = re.search(r'(?:DA\s+)?KG[.\s]*(\d+[.,]?\d*)|(\d+[.,]?\d*)\s*KG(?:\s|$|\.)', desc_upper)
    if kg_match:
        peso_str = kg_match.group(1) or kg_match.group(2)
        peso = float(peso_str.replace(',', '.'))
        return {"peso_totale": peso, "unita_peso": "kg", "peso_grammi": peso * 1000}
    
    # Pattern per peso in grammi (es. 500G, 250 GR, G.500)
    g_match = re.search(r'(?:DA\s+)?G[.\s]*(\d+[.,]?\d*)|(\d+[.,]?\d*)\s*G(?:R)?(?:\s|$|\.)', desc_upper)
    if g_match:
        peso_str = g_match.group(1) or g_match.group(2)
        peso = float(peso_str.replace(',', '.'))
        # Evita match falsi positivi troppo grandi (es. codici prodotto)
        if peso <= 10000:
            return {"peso_totale": peso, "unita_peso": "g", "peso_grammi": peso}
    
    # Pattern per litri (es. 1L, 0.75L, 750ML, LT.5)
    l_match = re.search(r'(?:DA\s+)?L(?:T|TR)?[.\s]*(\d+[.,]?\d*)|(\d+[.,]?\d*)\s*L(?:T|TR)?(?:\s|$|\.)', desc_upper)
    if l_match:
        peso_str = l_match.group(1) or l_match.group(2)
        if peso_str:
            litri = float(peso_str.replace(',', '.'))
            if litri <= 100:  # Evita match falsi positivi
                return {"peso_totale": litri, "unita_peso": "l", "peso_grammi": litri * 1000}
    
    ml_match = re.search(r'(\d+[.,]?\d*)\s*ML', desc_upper)
    if ml_match:
        ml = float(ml_match.group(1).replace(',', '.'))
        return {"peso_totale": ml / 1000, "unita_peso": "l", "peso_grammi": ml}
    
    # Pattern per pezzi (es. DA 180, X20, 10PZ)
    pz_match = re.search(r'(?:DA\s*|X\s*)(\d+)|(\d+)\s*(?:PZ|NR|PEZZI)', desc_upper)
    if pz_match:
        pezzi = int(pz_match.group(1) or pz_match.group(2))
        return {"peso_totale": pezzi, "unita_peso": "pz", "peso_grammi": None}
    
    return {"peso_totale": None, "unita_peso": None, "peso_grammi": None}


def normalizza_nome_prodotto(descrizione: str) -> str:
    """
    Normalizza il nome del prodotto per ricerca e matching.
    Rimuove codici, numeri di lotto, pesi ecc.
    """
    # Rimuovi codici articolo comuni
    desc = re.sub(r'^[A-Z]{2,4}\s+', '', descrizione)
    # Rimuovi pesi e quantità
    desc = re.sub(r'\d+[.,]?\d*\s*(KG|G|GR|L|LT|ML|PZ|NR)\b', '', desc, flags=re.IGNORECASE)
    # Rimuovi numeri isolati
    desc = re.sub(r'\b\d+\b', '', desc)
    # Pulisci spazi multipli
    desc = re.sub(r'\s+', ' ', desc).strip()
    return desc.lower()


# ==================== API ENDPOINTS ====================

@router.get("/prodotti")
async def get_prodotti_dizionario(
    search: Optional[str] = None,
    fornitore_id: Optional[str] = None,
    fornitore_nome: Optional[str] = None,
    solo_senza_peso: bool = False,
    solo_senza_prezzo: bool = False,
    limit: int = 100,
    offset: int = 0
) -> Dict[str, Any]:
    """
    Lista prodotti dal dizionario con prezzi e pesi.
    """
    db = Database.get_db()
    
    # Build query con $and per combinare filtri
    and_conditions = []
    
    if search:
        and_conditions.append({
            "$or": [
                {"descrizione": {"$regex": search, "$options": "i"}},
                {"nome_normalizzato": {"$regex": search.lower(), "$options": "i"}},
                {"aliases": {"$regex": search, "$options": "i"}}
            ]
        })
    
    if fornitore_id:
        and_conditions.append({"fornitore_id": fornitore_id})
    
    if fornitore_nome:
        and_conditions.append({"fornitore_nome": {"$regex": fornitore_nome, "$options": "i"}})
    
    if solo_senza_peso:
        and_conditions.append({"peso_grammi": None})
    
    if solo_senza_prezzo:
        and_conditions.append({
            "$or": [
                {"prezzo_per_kg": None},
                {"prezzo_per_kg": {"$exists": False}},
                {"prezzo_per_kg": 0}
            ]
        })
    
    query = {"$and": and_conditions} if and_conditions else {}
    
    # Count totale per paginazione
    totale = await db[COLLECTION_DIZIONARIO].count_documents(query)
    
    prodotti = await db[COLLECTION_DIZIONARIO].find(
        query, {"_id": 0}
    ).sort("descrizione", 1).skip(offset).limit(limit).to_list(limit)
    
    return {
        "prodotti": prodotti,
        "totale": totale,
        "limit": limit,
        "offset": offset
    }


@router.get("/fornitori")
async def get_fornitori_dizionario() -> Dict[str, Any]:
    """
    Lista fornitori presenti nel dizionario prodotti con conteggio.
    """
    db = Database.get_db()
    
    pipeline = [
        {"$group": {
            "_id": "$fornitore_nome",
            "count": {"$sum": 1},
            "con_prezzo": {"$sum": {"$cond": [{"$gt": ["$prezzo_per_kg", 0]}, 1, 0]}},
            "senza_prezzo": {"$sum": {"$cond": [{"$or": [
                {"$eq": ["$prezzo_per_kg", None]},
                {"$eq": ["$prezzo_per_kg", 0]}
            ]}, 1, 0]}}
        }},
        {"$sort": {"count": -1}},
        {"$limit": 100}
    ]
    
    fornitori = []
    async for doc in db[COLLECTION_DIZIONARIO].aggregate(pipeline):
        fornitori.append({
            "nome": doc["_id"] or "Sconosciuto",
            "totale_prodotti": doc["count"],
            "con_prezzo": doc["con_prezzo"],
            "senza_prezzo": doc["senza_prezzo"]
        })
    
    return {"fornitori": fornitori}


@router.post("/prodotti/scan-fatture")
async def scan_fatture_per_prodotti(
    anno: int = Query(default=2025),
    fornitore_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Scandaglia tutte le fatture e popola il dizionario prodotti.
    Estrae automaticamente peso dalla descrizione.
    """
    db = Database.get_db()
    
    # Query fatture
    query = {"invoice_date": {"$regex": f"^{anno}"}}
    if fornitore_id:
        query["supplier_id"] = fornitore_id
    
    fatture = await db[COLLECTION_INVOICES].find(query, {"_id": 0}).to_list(10000)
    
    prodotti_aggiunti = 0
    prodotti_aggiornati = 0
    prodotti_senza_peso = 0
    now = datetime.now(timezone.utc).isoformat()
    
    for fattura in fatture:
        # Supporta sia 'lines' che 'linee' per compatibilità
        linee_fattura = fattura.get("lines", fattura.get("linee", []))
        supplier_id = fattura.get("supplier_id", fattura.get("id", "unknown"))
        supplier_name = fattura.get("supplier_name", "Fornitore Sconosciuto")
        
        for linea in linee_fattura:
            descrizione = linea.get("descrizione", "").strip()
            if not descrizione or len(descrizione) < 3:
                continue
            
            # Salta linee non-prodotto (spese, sconti, ecc.)
            if any(kw in descrizione.lower() for kw in ['sconto', 'trasporto', 'spese', 'imballo', 'contributo', 'canone', 'servizio', 'nolo']):
                continue
            
            # Estrai dati - gestisce sia stringhe che numeri
            try:
                quantita = float(linea.get("quantita", 1) or 1)
                prezzo_unitario = float(linea.get("prezzo_unitario", 0) or 0)
                prezzo_totale = float(linea.get("prezzo_totale", 0) or prezzo_unitario * quantita)
                unita_misura = linea.get("unita_misura", "").upper().strip()
            except (ValueError, TypeError):
                continue
            
            # Parse peso dalla descrizione (dimensione confezione)
            peso_info = parse_peso_da_descrizione(descrizione)
            
            # Chiave univoca prodotto
            nome_norm = normalizza_nome_prodotto(descrizione)
            prodotto_key = f"{supplier_id}_{nome_norm}"
            
            # LOGICA PREZZO AL KG CORRETTA
            # Se unità misura è KG/LT, il prezzo unitario È GIÀ al kg/lt
            prezzo_per_kg = None
            peso_grammi_effettivo = None
            
            if unita_misura in ["KG", "KGM"]:
                # Prezzo unitario è già €/kg
                prezzo_per_kg = prezzo_unitario
                peso_grammi_effettivo = quantita * 1000  # Quantità in grammi
            elif unita_misura in ["LT", "LTR", "L"]:
                # Prezzo unitario è già €/lt (equivalente a €/kg per liquidi)
                prezzo_per_kg = prezzo_unitario
                peso_grammi_effettivo = quantita * 1000
            elif unita_misura in ["GR", "G"]:
                # Prezzo per grammo, convertire a kg
                prezzo_per_kg = prezzo_unitario * 1000
                peso_grammi_effettivo = quantita
            elif peso_info["peso_grammi"] and prezzo_unitario > 0:
                # Fallback: usa peso estratto dalla descrizione
                # prezzo_unitario è per 1 confezione che pesa peso_grammi
                prezzo_per_kg = (prezzo_unitario / peso_info["peso_grammi"]) * 1000
                peso_grammi_effettivo = peso_info["peso_grammi"] * quantita
            elif unita_misura in ["NR", "PZ", "PCE", "EURO", ""]:
                # Pezzi o altro - non possiamo calcolare prezzo al kg senza peso
                # Proviamo comunque con peso dalla descrizione se disponibile
                if peso_info["peso_grammi"]:
                    prezzo_per_kg = (prezzo_unitario / peso_info["peso_grammi"]) * 1000
                    peso_grammi_effettivo = peso_info["peso_grammi"] * quantita
            
            # Cerca prodotto esistente
            existing = await db[COLLECTION_DIZIONARIO].find_one({"prodotto_key": prodotto_key})
            
            if existing:
                # Aggiorna con ultimo prezzo
                update_data = {
                    "ultimo_prezzo_unitario": prezzo_unitario,
                    "ultimo_prezzo_totale": prezzo_totale,
                    "ultima_quantita": quantita,
                    "unita_misura_fattura": unita_misura,
                    "ultima_fattura_id": fattura.get("id"),
                    "ultima_fattura_data": fattura.get("invoice_date"),
                    "updated_at": now
                }
                if prezzo_per_kg and prezzo_per_kg > 0 and prezzo_per_kg < 10000:  # Sanity check
                    update_data["prezzo_per_kg"] = round(prezzo_per_kg, 4)
                if peso_grammi_effettivo:
                    update_data["peso_grammi_effettivo"] = peso_grammi_effettivo
                
                await db[COLLECTION_DIZIONARIO].update_one(
                    {"prodotto_key": prodotto_key},
                    {"$set": update_data, "$inc": {"conteggio_acquisti": 1}}
                )
                prodotti_aggiornati += 1
            else:
                # Nuovo prodotto
                prodotto = {
                    "id": str(uuid.uuid4()),
                    "prodotto_key": prodotto_key,
                    "descrizione": descrizione,
                    "nome_normalizzato": nome_norm,
                    "aliases": [],  # Sinonimi (es. sugna = strutto)
                    "fornitore_id": supplier_id,
                    "fornitore_nome": supplier_name,
                    "categoria": None,  # Da compilare manualmente
                    # Peso dalla descrizione (dimensione confezione)
                    "peso_totale": peso_info["peso_totale"],
                    "unita_peso": peso_info["unita_peso"],
                    "peso_grammi": peso_info["peso_grammi"],
                    "peso_grammi_effettivo": peso_grammi_effettivo,
                    "peso_confermato": False,  # True quando utente conferma/corregge
                    # Unità misura dalla fattura
                    "unita_misura_fattura": unita_misura,
                    # Prezzi
                    "ultimo_prezzo_unitario": prezzo_unitario,
                    "ultimo_prezzo_totale": prezzo_totale,
                    "ultima_quantita": quantita,
                    "prezzo_per_kg": round(prezzo_per_kg, 4) if (prezzo_per_kg and prezzo_per_kg < 10000) else None,
                    # Riferimento fattura
                    "ultima_fattura_id": fattura.get("id"),
                    "ultima_fattura_data": fattura.get("invoice_date"),
                    "conteggio_acquisti": 1,
                    # Metadata
                    "created_at": now,
                    "updated_at": now
                }
                
                await db[COLLECTION_DIZIONARIO].insert_one(prodotto.copy())
                prodotti_aggiunti += 1
                
                if not peso_info["peso_grammi"]:
                    prodotti_senza_peso += 1
    
    return {
        "success": True,
        "anno": anno,
        "fatture_analizzate": len(fatture),
        "prodotti_aggiunti": prodotti_aggiunti,
        "prodotti_aggiornati": prodotti_aggiornati,
        "prodotti_senza_peso": prodotti_senza_peso,
        "messaggio": f"Analizzate {len(fatture)} fatture. Aggiunti {prodotti_aggiunti} nuovi prodotti, aggiornati {prodotti_aggiornati}."
    }


@router.put("/prodotti/{prodotto_id}/peso")
async def aggiorna_peso_prodotto(
    prodotto_id: str,
    peso_grammi: float = Body(..., description="Peso in grammi (es. 1000 per 1kg)"),
    unita_peso: str = Body(default="g", description="Unità: g, kg, l, ml, pz")
) -> Dict[str, Any]:
    """
    Aggiorna manualmente il peso di un prodotto.
    Ricalcola automaticamente il prezzo al kg.
    """
    db = Database.get_db()
    
    prodotto = await db[COLLECTION_DIZIONARIO].find_one({"id": prodotto_id})
    if not prodotto:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")
    
    # Ricalcola prezzo al kg
    prezzo_per_kg = None
    if peso_grammi > 0 and prodotto.get("ultimo_prezzo_unitario", 0) > 0:
        prezzo_per_kg = (prodotto["ultimo_prezzo_unitario"] / peso_grammi) * 1000
    
    await db[COLLECTION_DIZIONARIO].update_one(
        {"id": prodotto_id},
        {"$set": {
            "peso_grammi": peso_grammi,
            "unita_peso": unita_peso,
            "peso_totale": peso_grammi / 1000 if unita_peso in ["g", "kg"] else peso_grammi,
            "peso_confermato": True,
            "prezzo_per_kg": round(prezzo_per_kg, 4) if prezzo_per_kg else None,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {
        "success": True,
        "prodotto_id": prodotto_id,
        "peso_grammi": peso_grammi,
        "prezzo_per_kg": round(prezzo_per_kg, 4) if prezzo_per_kg else None
    }


@router.put("/prodotti/{prodotto_id}")
async def update_prodotto(
    prodotto_id: str,
    data: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    """
    Aggiorna un prodotto nel dizionario.
    Principalmente per correggere/impostare il prezzo_per_kg manualmente.
    """
    db = Database.get_db()
    
    update_fields = {"updated_at": datetime.now(timezone.utc).isoformat()}
    
    if "prezzo_per_kg" in data and data["prezzo_per_kg"] is not None:
        update_fields["prezzo_per_kg"] = round(float(data["prezzo_per_kg"]), 4)
        update_fields["prezzo_manuale"] = True  # Flag per indicare modifica manuale
    
    if "prezzo_unitario_manuale" in data and data["prezzo_unitario_manuale"] is not None:
        update_fields["prezzo_unitario_manuale"] = float(data["prezzo_unitario_manuale"])
    
    result = await db[COLLECTION_DIZIONARIO].update_one(
        {"id": prodotto_id},
        {"$set": update_fields}
    )
    
    if result.modified_count == 0:
        return {"success": False, "message": "Prodotto non trovato o nessuna modifica"}
    
    return {
        "success": True,
        "prodotto_id": prodotto_id,
        "updated_fields": list(update_fields.keys())
    }


@router.put("/prodotti/{prodotto_id}/alias")
async def aggiungi_alias_prodotto(
    prodotto_id: str,
    alias: str = Body(..., description="Sinonimo del prodotto (es. 'sugna' per 'strutto')")
) -> Dict[str, Any]:
    """
    Aggiunge un alias/sinonimo al prodotto.
    Utile per matching fuzzy (sugna = strutto, zucchero = saccarosio).
    """
    db = Database.get_db()
    
    await db[COLLECTION_DIZIONARIO].update_one(
        {"id": prodotto_id},
        {
            "$addToSet": {"aliases": alias.lower()},
            "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
        }
    )
    
    return {"success": True, "alias_aggiunto": alias}


@router.get("/prodotti/search-per-ingrediente")
async def search_prodotti_per_ingrediente(
    ingrediente: str = Query(..., description="Nome ingrediente da cercare")
) -> Dict[str, Any]:
    """
    Cerca prodotti che matchano un ingrediente.
    Usato nel menu a tendina quando si aggiunge ingrediente a ricetta.
    """
    db = Database.get_db()
    
    # Normalizza ricerca
    search_lower = ingrediente.lower().strip()
    
    # Cerca in descrizione, nome normalizzato e aliases
    prodotti = await db[COLLECTION_DIZIONARIO].find({
        "$or": [
            {"descrizione": {"$regex": search_lower, "$options": "i"}},
            {"nome_normalizzato": {"$regex": search_lower, "$options": "i"}},
            {"aliases": {"$in": [search_lower]}}
        ]
    }, {"_id": 0}).limit(20).to_list(20)
    
    # Ordina per rilevanza (match esatto prima)
    def relevance_score(p):
        desc = p.get("descrizione", "").lower()
        nome = p.get("nome_normalizzato", "").lower()
        if search_lower in p.get("aliases", []):
            return 0
        if nome.startswith(search_lower):
            return 1
        if search_lower in nome:
            return 2
        return 3
    
    prodotti.sort(key=relevance_score)
    
    return {
        "ingrediente_cercato": ingrediente,
        "prodotti": prodotti,
        "totale": len(prodotti)
    }


@router.post("/calcola-food-cost")
async def calcola_food_cost(
    ingredienti: List[Dict[str, Any]] = Body(..., description="Lista ingredienti con quantita")
) -> Dict[str, Any]:
    """
    Calcola il food cost per una lista di ingredienti.
    
    Input: [{"nome": "farina", "quantita_grammi": 500, "prodotto_id": "xxx"}, ...]
    Output: costo totale e dettaglio per ingrediente
    """
    db = Database.get_db()
    
    totale_costo = 0.0
    dettaglio = []
    ingredienti_senza_prezzo = []
    
    for ing in ingredienti:
        nome = ing.get("nome", "")
        quantita_g = float(ing.get("quantita_grammi", 0) or 0)
        prodotto_id = ing.get("prodotto_id")
        
        costo_ingrediente = None
        prodotto = None
        
        if prodotto_id:
            # Cerca per ID prodotto
            prodotto = await db[COLLECTION_DIZIONARIO].find_one({"id": prodotto_id}, {"_id": 0})
        
        if not prodotto and nome:
            # Cerca per nome
            risultati = await db[COLLECTION_DIZIONARIO].find({
                "$or": [
                    {"nome_normalizzato": {"$regex": nome.lower(), "$options": "i"}},
                    {"aliases": {"$in": [nome.lower()]}}
                ]
            }, {"_id": 0}).limit(1).to_list(1)
            if risultati:
                prodotto = risultati[0]
        
        if prodotto and prodotto.get("prezzo_per_kg") and quantita_g > 0:
            # Calcolo: (prezzo_per_kg / 1000) * quantita_grammi
            costo_ingrediente = (prodotto["prezzo_per_kg"] / 1000) * quantita_g
            totale_costo += costo_ingrediente
            
            dettaglio.append({
                "ingrediente": nome,
                "quantita_grammi": quantita_g,
                "prodotto_trovato": prodotto.get("descrizione"),
                "fornitore": prodotto.get("fornitore_nome"),
                "prezzo_per_kg": prodotto.get("prezzo_per_kg"),
                "costo_calcolato": round(costo_ingrediente, 4)
            })
        else:
            ingredienti_senza_prezzo.append({
                "ingrediente": nome,
                "quantita_grammi": quantita_g,
                "motivo": "Prodotto non trovato" if not prodotto else "Manca prezzo/peso"
            })
    
    return {
        "food_cost_totale": round(totale_costo, 2),
        "dettaglio_ingredienti": dettaglio,
        "ingredienti_senza_prezzo": ingredienti_senza_prezzo,
        "completezza": f"{len(dettaglio)}/{len(ingredienti)}"
    }


@router.get("/prodotti/senza-peso")
async def get_prodotti_senza_peso(limit: int = 50) -> Dict[str, Any]:
    """
    Lista prodotti che richiedono inserimento manuale del peso.
    """
    db = Database.get_db()
    
    prodotti = await db[COLLECTION_DIZIONARIO].find(
        {"peso_grammi": None},
        {"_id": 0}
    ).sort("conteggio_acquisti", -1).limit(limit).to_list(limit)
    
    return {
        "prodotti": prodotti,
        "totale": len(prodotti),
        "messaggio": "Questi prodotti richiedono inserimento manuale del peso per calcolare il food cost"
    }


@router.get("/stats")
async def get_dizionario_stats() -> Dict[str, Any]:
    """
    Statistiche del dizionario prodotti.
    """
    db = Database.get_db()
    
    totale = await db[COLLECTION_DIZIONARIO].count_documents({})
    con_peso = await db[COLLECTION_DIZIONARIO].count_documents({"peso_grammi": {"$ne": None}})
    con_prezzo_kg = await db[COLLECTION_DIZIONARIO].count_documents({"prezzo_per_kg": {"$ne": None}})
    confermati = await db[COLLECTION_DIZIONARIO].count_documents({"peso_confermato": True})
    
    return {
        "totale_prodotti": totale,
        "con_peso_rilevato": con_peso,
        "con_prezzo_al_kg": con_prezzo_kg,
        "peso_confermato_manualmente": confermati,
        "senza_peso": totale - con_peso,
        "completezza_percentuale": round((con_prezzo_kg / totale * 100) if totale > 0 else 0, 1)
    }
