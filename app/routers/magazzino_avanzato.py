"""
Magazzino Router - Gestione Completa Magazzino Bar/Pasticceria

Questo router gestisce:
1. Carico automatico da XML fattura (con classificazione categorie)
2. Scarico per produzione (distinta base / ricette)
3. Gestione giacenze e lotti
4. Reportistica per centro di costo

NOTA: Usa warehouse_inventory come collezione principale
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, List
from datetime import datetime, timezone
import logging
import uuid

from app.database import Database, Collections
from app.db_collections import COLL_WAREHOUSE, COLL_WAREHOUSE_MOVEMENTS
from app.services.magazzino_categorie import (
    parse_linea_fattura,
    calcola_scarico_ricetta,
    get_tutte_categorie
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/magazzino", tags=["Magazzino"])


@router.get("/categorie-merceologiche")
async def get_categorie_merceologiche() -> List[Dict[str, Any]]:
    """Restituisce tutte le categorie merceologiche disponibili."""
    return get_tutte_categorie()


@router.post("/carico-da-fattura/{fattura_id}")
async def carico_da_fattura(fattura_id: str) -> Dict[str, Any]:
    """
    Carica automaticamente i prodotti in magazzino leggendo le linee della fattura.
    
    Per ogni linea:
    1. Estrae descrizione, quantità, unità di misura
    2. Classifica nella categoria merceologica corretta
    3. Aggiorna/crea articolo in magazzino
    4. Registra movimento di carico
    """
    db = Database.get_db()
    
    # Cerca fattura
    fattura = await db[Collections.INVOICES].find_one({
        "$or": [{"id": fattura_id}, {"invoice_number": fattura_id}]
    })
    
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    linee = fattura.get("linee", [])
    if not linee:
        raise HTTPException(status_code=400, detail="Fattura senza linee dettaglio")
    
    fornitore = fattura.get("supplier_name", "")
    data_fattura = fattura.get("invoice_date") or fattura.get("data_ricezione") or datetime.now().strftime("%Y-%m-%d")
    numero_fattura = fattura.get("invoice_number", "")
    
    risultato = {
        "fattura_id": fattura_id,
        "numero_fattura": numero_fattura,
        "fornitore": fornitore,
        "data_fattura": data_fattura,
        "linee_processate": 0,
        "articoli_caricati": [],
        "movimenti_registrati": 0,
        "errori": []
    }
    
    for linea in linee:
        try:
            # Parsa linea
            dati_prodotto = parse_linea_fattura(linea, fornitore)
            
            if dati_prodotto["quantita"] <= 0:
                continue
            
            # Genera identificativo articolo dalla descrizione normalizzata
            nome_normalizzato = dati_prodotto['descrizione_normalizzata'].upper().strip()
            
            # Cerca articolo in warehouse_inventory usando nome_normalizzato
            articolo = await db[COLL_WAREHOUSE].find_one({
                "$or": [
                    {"nome_normalizzato": nome_normalizzato},
                    {"nome": {"$regex": nome_normalizzato[:30], "$options": "i"}}
                ]
            })
            
            if articolo:
                # Aggiorna giacenza e prezzo medio ponderato
                giacenza_attuale = articolo.get("giacenza", 0)
                prezzi = articolo.get("prezzi", {})
                prezzo_attuale = prezzi.get("ultimo", prezzi.get("medio", 0))
                
                nuova_giacenza = giacenza_attuale + dati_prodotto["quantita"]
                
                # Prezzo medio ponderato
                if nuova_giacenza > 0:
                    nuovo_prezzo = (
                        (giacenza_attuale * prezzo_attuale) + 
                        (dati_prodotto["quantita"] * dati_prodotto["prezzo_unitario"])
                    ) / nuova_giacenza
                else:
                    nuovo_prezzo = dati_prodotto["prezzo_unitario"]
                
                await db[COLL_WAREHOUSE].update_one(
                    {"id": articolo["id"]},
                    {"$set": {
                        "giacenza": nuova_giacenza,
                        "prezzi.ultimo": round(nuovo_prezzo, 4),
                        "prezzi.medio": round(nuovo_prezzo, 4),
                        "ultimo_acquisto": datetime.now(timezone.utc).isoformat(),
                        "ultimo_fornitore": fornitore,
                        "categoria": dati_prodotto["categoria_nome"],
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
            else:
                # Crea nuovo articolo nel formato warehouse_inventory
                nuovo_articolo = {
                    "id": str(uuid.uuid4()),
                    "nome": dati_prodotto["descrizione_originale"],
                    "nome_normalizzato": nome_normalizzato,
                    "categoria": dati_prodotto["categoria_nome"],
                    "unita_misura": dati_prodotto["unita_misura"],
                    "giacenza": dati_prodotto["quantita"],
                    "giacenza_minima": 0,
                    "prezzi": {
                        "ultimo": dati_prodotto["prezzo_unitario"],
                        "medio": dati_prodotto["prezzo_unitario"],
                        "min": dati_prodotto["prezzo_unitario"],
                        "max": dati_prodotto["prezzo_unitario"]
                    },
                    "fornitori": [fornitore],
                    "ultimo_acquisto": datetime.now(timezone.utc).isoformat(),
                    "ultimo_fornitore": fornitore,
                    "history": [],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
                await db[COLL_WAREHOUSE].insert_one(nuovo_articolo)
            
            # Registra movimento di carico
            movimento = {
                "id": str(uuid.uuid4()),
                "tipo": "carico",
                "data": data_fattura,
                "prodotto_id": articolo.get("id") if articolo else nuovo_articolo.get("id"),
                "prodotto_descrizione": dati_prodotto["descrizione_originale"],
                "quantita": dati_prodotto["quantita"],
                "unita_misura": dati_prodotto["unita_misura"],
                "prezzo_unitario": dati_prodotto["prezzo_unitario"],
                "valore_totale": dati_prodotto["prezzo_totale"],
                "fattura_id": fattura_id,
                "numero_fattura": numero_fattura,
                "fornitore": fornitore,
                "categoria": dati_prodotto["categoria_nome"],
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db[COLL_WAREHOUSE_MOVEMENTS].insert_one(movimento)
            
            risultato["articoli_caricati"].append({
                "nome": dati_prodotto["descrizione_normalizzata"],
                "descrizione": dati_prodotto["descrizione_normalizzata"],
                "quantita": dati_prodotto["quantita"],
                "unita": dati_prodotto["unita_misura"],
                "categoria": dati_prodotto["categoria_nome"],
                "prezzo": dati_prodotto["prezzo_unitario"]
            })
            risultato["linee_processate"] += 1
            risultato["movimenti_registrati"] += 1
            
        except Exception as e:
            risultato["errori"].append({
                "linea": linea.get("descrizione", "N/D")[:50],
                "errore": str(e)
            })
    
    # Aggiorna fattura come processata per magazzino
    await db[Collections.INVOICES].update_one(
        {"_id": fattura["_id"]},
        {"$set": {
            "magazzino_processato": True,
            "magazzino_processato_il": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return risultato


@router.post("/carico-massivo")
async def carico_massivo_fatture(
    anno: int = Query(None),
    forza: bool = Query(False, description="Riprocessa anche fatture già caricate")
) -> Dict[str, Any]:
    """
    Carica in magazzino tutte le fatture con linee dell'anno specificato.
    """
    db = Database.get_db()
    
    if not anno:
        anno = datetime.now().year
    
    # Query fatture con linee non ancora processate
    query = {
        "linee": {"$exists": True, "$ne": []},
        "$or": [
            {"invoice_date": {"$regex": f"^{anno}"}},
            {"data_ricezione": {"$regex": f"^{anno}"}}
        ]
    }
    
    if not forza:
        query["magazzino_processato"] = {"$ne": True}
    
    fatture = await db[Collections.INVOICES].find(query, {"id": 1, "invoice_number": 1}).to_list(5000)
    
    risultato = {
        "anno": anno,
        "fatture_trovate": len(fatture),
        "fatture_processate": 0,
        "articoli_totali": 0,
        "errori": []
    }
    
    for fatt in fatture:
        fatt_id = fatt.get("id") or str(fatt.get("_id"))
        try:
            res = await carico_da_fattura(fatt_id)
            risultato["fatture_processate"] += 1
            risultato["articoli_totali"] += len(res.get("articoli_caricati", []))
        except Exception as e:
            risultato["errori"].append({
                "fattura": fatt.get("invoice_number", fatt_id),
                "errore": str(e)
            })
    
    return risultato


@router.post("/scarico-produzione")
async def scarico_per_produzione(
    ricetta_id: str,
    porzioni_prodotte: int,
    data_produzione: str = None,
    lotto: str = None,
    note: str = None
) -> Dict[str, Any]:
    """
    Scarica dal magazzino gli ingredienti per una produzione.
    
    Esempio: Produzione 100 sfogliatelle
    -> Cerca ricetta sfogliatelle
    -> Calcola ingredienti necessari (proporzionati alle porzioni)
    -> Scarica da magazzino
    -> Registra lotto di produzione
    """
    db = Database.get_db()
    
    # Cerca ricetta
    ricetta = await db["ricette"].find_one({
        "$or": [{"id": ricetta_id}, {"nome": {"$regex": ricetta_id, "$options": "i"}}]
    })
    
    if not ricetta:
        raise HTTPException(status_code=404, detail="Ricetta non trovata")
    
    ingredienti = ricetta.get("ingredienti", [])
    porzioni_ricetta = ricetta.get("porzioni", 1)
    
    if not ingredienti:
        raise HTTPException(status_code=400, detail="Ricetta senza ingredienti")
    
    # Calcola scarichi
    scarichi = calcola_scarico_ricetta(ingredienti, porzioni_prodotte, porzioni_ricetta)
    
    data_prod = data_produzione or datetime.now().strftime("%Y-%m-%d")
    lotto_prod = lotto or f"LOTTO-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    risultato = {
        "ricetta": ricetta.get("nome"),
        "ricetta_id": ricetta_id,
        "porzioni_ricetta": porzioni_ricetta,
        "porzioni_prodotte": porzioni_prodotte,
        "fattore": porzioni_prodotte / porzioni_ricetta,
        "data_produzione": data_prod,
        "lotto": lotto_prod,
        "scarichi_effettuati": [],
        "scarichi_non_disponibili": [],
        "errori": []
    }
    
    for scarico in scarichi:
        ingrediente = scarico["ingrediente"]
        qta_necessaria = scarico["quantita_scarico"]
        unita = scarico["unita_misura"]
        
        try:
            # Cerca articolo in warehouse_inventory (match fuzzy sul nome)
            articolo = await db[COLL_WAREHOUSE].find_one({
                "$or": [
                    {"nome": {"$regex": ingrediente, "$options": "i"}},
                    {"nome_normalizzato": {"$regex": ingrediente.upper()[:10]}}
                ]
            })
            
            if articolo:
                giacenza = articolo.get("giacenza", 0)
                
                if giacenza >= qta_necessaria:
                    # Scarica
                    nuova_giacenza = giacenza - qta_necessaria
                    await db[COLL_WAREHOUSE].update_one(
                        {"id": articolo["id"]},
                        {"$set": {
                            "giacenza": nuova_giacenza,
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }}
                    )
                    
                    # Registra movimento
                    movimento = {
                        "id": str(uuid.uuid4()),
                        "tipo": "scarico_produzione",
                        "data": data_prod,
                        "prodotto_id": articolo.get("id"),
                        "prodotto_descrizione": articolo.get("nome"),
                        "quantita": -qta_necessaria,
                        "unita_misura": unita,
                        "ricetta_id": ricetta_id,
                        "ricetta_nome": ricetta.get("nome"),
                        "lotto_produzione": lotto_prod,
                        "porzioni_prodotte": porzioni_prodotte,
                        "note": note,
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }
                    await db[COLL_WAREHOUSE_MOVEMENTS].insert_one(movimento)
                    
                    risultato["scarichi_effettuati"].append({
                        "ingrediente": ingrediente,
                        "quantita_scaricata": round(qta_necessaria, 3),
                        "unita": unita,
                        "giacenza_residua": round(nuova_giacenza, 3)
                    })
                else:
                    risultato["scarichi_non_disponibili"].append({
                        "ingrediente": ingrediente,
                        "quantita_necessaria": round(qta_necessaria, 3),
                        "giacenza_disponibile": round(giacenza, 3),
                        "unita": unita,
                        "mancante": round(qta_necessaria - giacenza, 3)
                    })
            else:
                risultato["scarichi_non_disponibili"].append({
                    "ingrediente": ingrediente,
                    "quantita_necessaria": round(qta_necessaria, 3),
                    "unita": unita,
                    "motivo": "Articolo non trovato in magazzino"
                })
                
        except Exception as e:
            risultato["errori"].append({
                "ingrediente": ingrediente,
                "errore": str(e)
            })
    
    # Registra lotto di produzione
    lotto_doc = {
        "id": str(uuid.uuid4()),
        "lotto": lotto_prod,
        "ricetta_id": ricetta_id,
        "ricetta_nome": ricetta.get("nome"),
        "categoria": ricetta.get("categoria"),
        "data_produzione": data_prod,
        "porzioni_prodotte": porzioni_prodotte,
        "ingredienti_usati": risultato["scarichi_effettuati"],
        "ingredienti_mancanti": risultato["scarichi_non_disponibili"],
        "note": note,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db["lotti_produzione"].insert_one(lotto_doc)
    
    return risultato


@router.get("/giacenze")
async def get_giacenze(
    categoria: str = Query(None, description="Filtra per categoria"),
    sotto_scorta: bool = Query(False, description="Solo articoli sotto scorta minima")
) -> Dict[str, Any]:
    """Restituisce le giacenze di magazzino dalla collezione warehouse_inventory."""
    db = Database.get_db()
    
    query = {}
    if categoria:
        query["categoria"] = {"$regex": categoria, "$options": "i"}
    if sotto_scorta:
        query["$expr"] = {"$lt": ["$giacenza", "$giacenza_minima"]}
    
    articoli_raw = await db[COLL_WAREHOUSE].find(
        query,
        {"_id": 0}
    ).sort("categoria", 1).to_list(500)
    
    # Trasforma nel formato atteso
    articoli = []
    for art in articoli_raw:
        prezzi = art.get("prezzi", {})
        prezzo = prezzi.get("ultimo", prezzi.get("medio", 0)) if isinstance(prezzi, dict) else 0
        articoli.append({
            "id": art.get("id"),
            "nome": art.get("nome"),
            "descrizione": art.get("nome"),
            "categoria": art.get("categoria", "Altro"),
            "giacenza": art.get("giacenza", 0),
            "giacenza_minima": art.get("giacenza_minima", 0),
            "unita_misura": art.get("unita_misura", "PZ"),
            "prezzo_acquisto": prezzo,
            "ultimo_acquisto": art.get("ultimo_acquisto"),
            "ultimo_fornitore": art.get("ultimo_fornitore")
        })
    
    # Raggruppa per categoria
    per_categoria = {}
    for art in articoli:
        cat = art.get("categoria", "Altro")
        if cat not in per_categoria:
            per_categoria[cat] = {"articoli": [], "valore_totale": 0}
        
        valore = (art.get("giacenza", 0) or 0) * (art.get("prezzo_acquisto", 0) or 0)
        art["valore_giacenza"] = round(valore, 2)
        per_categoria[cat]["articoli"].append(art)
        per_categoria[cat]["valore_totale"] += valore
    
    # Arrotonda totali
    for cat in per_categoria.values():
        cat["valore_totale"] = round(cat["valore_totale"], 2)
        cat["num_articoli"] = len(cat["articoli"])
    
    valore_totale = sum(c["valore_totale"] for c in per_categoria.values())
    
    return {
        "totale_articoli": len(articoli),
        "valore_magazzino": round(valore_totale, 2),
        "per_categoria": per_categoria
    }


@router.get("/riepilogo-per-centro-costo/{anno}")
async def riepilogo_magazzino_per_centro_costo(anno: int) -> Dict[str, Any]:
    """
    Riepilogo acquisti magazzino raggruppati per centro di costo.
    Collegamento diretto con la contabilità.
    """
    db = Database.get_db()
    
    # Aggrega movimenti di carico per centro di costo
    pipeline = [
        {"$match": {
            "tipo": "carico",
            "data": {"$regex": f"^{anno}"}
        }},
        {"$group": {
            "_id": "$centro_costo",
            "categoria_nome": {"$first": "$categoria_nome"},
            "totale_valore": {"$sum": "$valore_totale"},
            "totale_quantita": {"$sum": "$quantita"},
            "num_movimenti": {"$sum": 1}
        }},
        {"$sort": {"totale_valore": -1}}
    ]
    
    centri = await db["movimenti_magazzino"].aggregate(pipeline).to_list(50)
    
    return {
        "anno": anno,
        "centri_costo": [
            {
                "centro_costo": c["_id"],
                "categoria": c["categoria_nome"],
                "valore_acquisti": round(c["totale_valore"], 2),
                "num_movimenti": c["num_movimenti"]
            }
            for c in centri
        ],
        "totale_acquisti": round(sum(c["totale_valore"] for c in centri), 2)
    }


@router.get("/movimenti")
async def get_movimenti(
    tipo: str = Query(None, description="carico | scarico_produzione | scarico_vendita"),
    data_da: str = Query(None),
    data_a: str = Query(None),
    limit: int = Query(100)
) -> List[Dict[str, Any]]:
    """Restituisce i movimenti di magazzino."""
    db = Database.get_db()
    
    query = {}
    if tipo:
        query["tipo"] = tipo
    if data_da:
        query["data"] = {"$gte": data_da}
    if data_a:
        if "data" in query:
            query["data"]["$lte"] = data_a
        else:
            query["data"] = {"$lte": data_a}
    
    movimenti = await db["movimenti_magazzino"].find(
        query,
        {"_id": 0}
    ).sort("data", -1).limit(limit).to_list(limit)
    
    return movimenti


@router.get("/lotti-produzione")
async def get_lotti_produzione(
    data_da: str = Query(None),
    ricetta: str = Query(None)
) -> List[Dict[str, Any]]:
    """Restituisce i lotti di produzione registrati."""
    db = Database.get_db()
    
    query = {}
    if data_da:
        query["data_produzione"] = {"$gte": data_da}
    if ricetta:
        query["ricetta_nome"] = {"$regex": ricetta, "$options": "i"}
    
    lotti = await db["lotti_produzione"].find(
        query,
        {"_id": 0}
    ).sort("data_produzione", -1).limit(100).to_list(100)
    
    return lotti
