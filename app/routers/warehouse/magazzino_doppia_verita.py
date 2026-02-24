"""
Magazzino Doppia Verità Router
Gestione giacenze teoriche vs reali con classificazione differenze
"""
from fastapi import APIRouter, HTTPException, Query, Body
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from app.database import Database, Collections
import uuid

router = APIRouter()

# Tipi di differenza inventariale
TIPI_DIFFERENZA = {
    "spreco": "Prodotto deteriorato o scaduto",
    "furto": "Ammanco sospetto furto",
    "errore": "Errore di registrazione/conteggio",
    "rettifica": "Rettifica documentata",
    "consumo_interno": "Consumo interno non registrato",
    "omaggio": "Omaggio a cliente",
    "rottura": "Rottura/danneggiamento"
}


@router.get("/prodotti")
async def list_prodotti_magazzino(
    skip: int = Query(0),
    limit: int = Query(100),
    search: Optional[str] = Query(None),
    solo_differenze: bool = Query(False, description="Mostra solo prodotti con differenze"),
    solo_scorte_basse: bool = Query(False),
    categoria: Optional[str] = Query(None),
    anno: Optional[int] = Query(None, description="Filtra per anno di creazione prodotto")
) -> Dict[str, Any]:
    """
    Lista prodotti con giacenza teorica e reale.
    Filtra per anno se specificato.
    """
    db = Database.get_db()
    
    query = {}
    if search:
        query["$or"] = [
            {"nome": {"$regex": search, "$options": "i"}},
            {"codice": {"$regex": search, "$options": "i"}},
            {"fornitore": {"$regex": search, "$options": "i"}},
            {"fornitore_principale": {"$regex": search, "$options": "i"}}
        ]
    
    if solo_differenze:
        query["$expr"] = {"$ne": ["$giacenza_teorica", "$giacenza_reale"]}
    
    if solo_scorte_basse:
        query["$expr"] = {"$lte": ["$giacenza_teorica", "$scorta_minima"]}
    
    if categoria:
        query["categoria"] = categoria
    
    # Filtra per anno se specificato
    if anno:
        query["created_at"] = {"$regex": f"^{anno}"}
    
    prodotti = await db["magazzino_doppia_verita"].find(
        query, {"_id": 0}
    ).sort("nome", 1).skip(skip).limit(limit).to_list(limit)
    
    # Calcola statistiche
    stats_pipeline = [
        {"$group": {
            "_id": None,
            "totale_prodotti": {"$sum": 1},
            "valore_teorico": {"$sum": {"$multiply": ["$giacenza_teorica", "$costo_medio"]}},
            "valore_reale": {"$sum": {"$multiply": ["$giacenza_reale", "$costo_medio"]}},
            "con_differenze": {"$sum": {"$cond": [{"$ne": ["$giacenza_teorica", "$giacenza_reale"]}, 1, 0]}},
            "scorte_basse": {"$sum": {"$cond": [{"$lte": ["$giacenza_teorica", "$scorta_minima"]}, 1, 0]}}
        }}
    ]
    stats_result = await db["magazzino_doppia_verita"].aggregate(stats_pipeline).to_list(1)
    stats = stats_result[0] if stats_result else {}
    
    return {
        "prodotti": prodotti,
        "totale": await db["magazzino_doppia_verita"].count_documents(query),
        "statistiche": {
            "totale_prodotti": stats.get("totale_prodotti", 0),
            "valore_teorico": round(stats.get("valore_teorico", 0), 2),
            "valore_reale": round(stats.get("valore_reale", 0), 2),
            "differenza_valore": round(stats.get("valore_teorico", 0) - stats.get("valore_reale", 0), 2),
            "prodotti_con_differenze": stats.get("con_differenze", 0),
            "prodotti_scorte_basse": stats.get("scorte_basse", 0)
        }
    }


@router.get("/prodotti/{prodotto_id}")
async def get_prodotto(prodotto_id: str) -> Dict[str, Any]:
    """Dettaglio prodotto con storico movimenti e differenze."""
    db = Database.get_db()
    
    prodotto = await db["magazzino_doppia_verita"].find_one(
        {"id": prodotto_id}, {"_id": 0}
    )
    
    if not prodotto:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")
    
    # Recupera storico differenze
    differenze = await db["magazzino_differenze"].find(
        {"prodotto_id": prodotto_id}, {"_id": 0}
    ).sort("data", -1).limit(50).to_list(50)
    
    # Recupera movimenti recenti
    movimenti = await db["magazzino_movimenti"].find(
        {"prodotto_id": prodotto_id}, {"_id": 0}
    ).sort("data", -1).limit(50).to_list(50)
    
    prodotto["storico_differenze"] = differenze
    prodotto["movimenti_recenti"] = movimenti
    
    return prodotto


@router.post("/prodotti")
async def create_prodotto(data: Dict[str, Any] = Body(...)) -> Dict[str, str]:
    """Crea nuovo prodotto in magazzino."""
    db = Database.get_db()
    
    prodotto = {
        "id": str(uuid.uuid4()),
        "codice": data.get("codice", ""),
        "nome": data.get("nome"),
        "descrizione": data.get("descrizione", ""),
        "categoria": data.get("categoria", "altro"),
        "unita_misura": data.get("unita_misura", "pz"),
        "giacenza_teorica": data.get("giacenza_iniziale", 0),
        "giacenza_reale": data.get("giacenza_iniziale", 0),
        "scorta_minima": data.get("scorta_minima", 0),
        "scorta_massima": data.get("scorta_massima", 0),
        "costo_medio": data.get("costo_unitario", 0),
        "ultimo_costo": data.get("costo_unitario", 0),
        "fornitore_principale": data.get("fornitore", ""),
        "fornitore_piva": data.get("fornitore_piva", ""),
        "lotto": data.get("lotto", ""),
        "scadenza": data.get("scadenza", ""),
        "centro_costo": data.get("centro_costo", "CDC-03"),  # Default laboratorio
        "attivo": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    if not prodotto["nome"]:
        raise HTTPException(status_code=400, detail="Nome prodotto obbligatorio")
    
    await db["magazzino_doppia_verita"].insert_one(prodotto.copy())
    
    return {"message": f"Prodotto {prodotto['nome']} creato", "id": prodotto["id"]}


@router.post("/prodotti/{prodotto_id}/carico")
async def carico_magazzino(
    prodotto_id: str,
    data: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    """
    Registra carico magazzino da fattura o manuale.
    Aggiorna giacenza TEORICA.
    """
    db = Database.get_db()
    
    prodotto = await db["magazzino_doppia_verita"].find_one({"id": prodotto_id})
    if not prodotto:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")
    
    quantita = data.get("quantita", 0)
    costo_unitario = data.get("costo_unitario", prodotto.get("costo_medio", 0))
    
    # Aggiorna giacenza teorica
    nuova_giacenza = prodotto.get("giacenza_teorica", 0) + quantita
    
    # Ricalcola costo medio ponderato
    giacenza_attuale = prodotto.get("giacenza_teorica", 0)
    costo_attuale = prodotto.get("costo_medio", 0)
    
    if giacenza_attuale + quantita > 0:
        nuovo_costo_medio = (
            (giacenza_attuale * costo_attuale) + (quantita * costo_unitario)
        ) / (giacenza_attuale + quantita)
    else:
        nuovo_costo_medio = costo_unitario
    
    await db["magazzino_doppia_verita"].update_one(
        {"id": prodotto_id},
        {"$set": {
            "giacenza_teorica": nuova_giacenza,
            "costo_medio": round(nuovo_costo_medio, 4),
            "ultimo_costo": costo_unitario,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    # Registra movimento
    movimento = {
        "id": str(uuid.uuid4()),
        "prodotto_id": prodotto_id,
        "tipo": "carico",
        "quantita": quantita,
        "costo_unitario": costo_unitario,
        "fattura_id": data.get("fattura_id"),
        "fornitore": data.get("fornitore", ""),
        "lotto": data.get("lotto", ""),
        "scadenza": data.get("scadenza", ""),
        "note": data.get("note", ""),
        "data": datetime.now(timezone.utc).isoformat(),
        "utente": data.get("utente", "system")
    }
    await db["magazzino_movimenti"].insert_one(movimento.copy())
    
    return {
        "message": f"Caricato {quantita} {prodotto.get('unita_misura', 'pz')} di {prodotto.get('nome')}",
        "giacenza_teorica": nuova_giacenza,
        "costo_medio": round(nuovo_costo_medio, 4)
    }


@router.post("/prodotti/{prodotto_id}/scarico")
async def scarico_magazzino(
    prodotto_id: str,
    data: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    """
    Registra scarico magazzino (vendita, produzione, consumo).
    Aggiorna giacenza TEORICA.
    """
    db = Database.get_db()
    
    prodotto = await db["magazzino_doppia_verita"].find_one({"id": prodotto_id})
    if not prodotto:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")
    
    quantita = data.get("quantita", 0)
    motivo = data.get("motivo", "vendita")  # vendita, produzione, consumo_interno
    
    # Aggiorna giacenza teorica
    nuova_giacenza = prodotto.get("giacenza_teorica", 0) - quantita
    
    await db["magazzino_doppia_verita"].update_one(
        {"id": prodotto_id},
        {"$set": {
            "giacenza_teorica": nuova_giacenza,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    # Registra movimento
    movimento = {
        "id": str(uuid.uuid4()),
        "prodotto_id": prodotto_id,
        "tipo": "scarico",
        "motivo": motivo,
        "quantita": -quantita,
        "costo_unitario": prodotto.get("costo_medio", 0),
        "valore": quantita * prodotto.get("costo_medio", 0),
        "ricetta_id": data.get("ricetta_id"),
        "vendita_id": data.get("vendita_id"),
        "note": data.get("note", ""),
        "data": datetime.now(timezone.utc).isoformat(),
        "utente": data.get("utente", "system")
    }
    await db["magazzino_movimenti"].insert_one(movimento.copy())
    
    return {
        "message": f"Scaricato {quantita} {prodotto.get('unita_misura', 'pz')} di {prodotto.get('nome')}",
        "giacenza_teorica": nuova_giacenza,
        "costo_scarico": round(quantita * prodotto.get("costo_medio", 0), 2)
    }


@router.post("/inventario")
async def registra_inventario(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Registra inventario fisico e aggiorna giacenza REALE.
    Calcola e classifica le differenze.
    """
    db = Database.get_db()
    
    prodotto_id = data.get("prodotto_id")
    giacenza_reale = data.get("giacenza_reale", 0)
    tipo_differenza = data.get("tipo_differenza", "errore")
    note = data.get("note", "")
    
    prodotto = await db["magazzino_doppia_verita"].find_one({"id": prodotto_id})
    if not prodotto:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")
    
    giacenza_teorica = prodotto.get("giacenza_teorica", 0)
    differenza = giacenza_teorica - giacenza_reale
    
    # Aggiorna giacenza reale
    await db["magazzino_doppia_verita"].update_one(
        {"id": prodotto_id},
        {"$set": {
            "giacenza_reale": giacenza_reale,
            "ultimo_inventario": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    # Se c'è differenza, registrala
    if differenza != 0:
        record_differenza = {
            "id": str(uuid.uuid4()),
            "prodotto_id": prodotto_id,
            "prodotto_nome": prodotto.get("nome"),
            "data": datetime.now(timezone.utc).isoformat(),
            "giacenza_teorica": giacenza_teorica,
            "giacenza_reale": giacenza_reale,
            "differenza": differenza,
            "differenza_valore": round(differenza * prodotto.get("costo_medio", 0), 2),
            "tipo": tipo_differenza,
            "tipo_descrizione": TIPI_DIFFERENZA.get(tipo_differenza, ""),
            "note": note,
            "utente": data.get("utente", "system"),
            "risolto": False
        }
        await db["magazzino_differenze"].insert_one(record_differenza.copy())
    
    return {
        "message": f"Inventario registrato per {prodotto.get('nome')}",
        "giacenza_teorica": giacenza_teorica,
        "giacenza_reale": giacenza_reale,
        "differenza": differenza,
        "differenza_valore": round(differenza * prodotto.get("costo_medio", 0), 2),
        "tipo_differenza": tipo_differenza if differenza != 0 else None
    }


@router.post("/inventario/bulk")
async def registra_inventario_bulk(data: List[Dict[str, Any]] = Body(...)) -> Dict[str, Any]:
    """Registra inventario per più prodotti contemporaneamente."""
    results = []
    
    for item in data:
        try:
            result = await registra_inventario(item)
            results.append({"prodotto_id": item.get("prodotto_id"), "status": "ok", **result})
        except Exception as e:
            results.append({"prodotto_id": item.get("prodotto_id"), "status": "error", "error": str(e)})
    
    return {
        "message": f"Inventario bulk completato: {len([r for r in results if r['status'] == 'ok'])}/{len(data)} prodotti",
        "results": results
    }


@router.post("/allinea-teorico-reale")
async def allinea_giacenze(
    prodotto_id: Optional[str] = Query(None, description="Se vuoto, allinea tutti"),
    direzione: str = Query("teorico_to_reale", description="teorico_to_reale o reale_to_teorico")
) -> Dict[str, Any]:
    """
    Allinea le giacenze dopo verifica inventario.
    Usare con cautela - genera movimento di rettifica.
    """
    db = Database.get_db()
    
    query = {}
    if prodotto_id:
        query["id"] = prodotto_id
    else:
        # Solo prodotti con differenze
        query["$expr"] = {"$ne": ["$giacenza_teorica", "$giacenza_reale"]}
    
    prodotti = await db["magazzino_doppia_verita"].find(query).to_list(1000)
    
    allineati = 0
    for prodotto in prodotti:
        if direzione == "teorico_to_reale":
            # Imposta teorico = reale
            await db["magazzino_doppia_verita"].update_one(
                {"id": prodotto["id"]},
                {"$set": {
                    "giacenza_teorica": prodotto.get("giacenza_reale", 0),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
        else:
            # Imposta reale = teorico
            await db["magazzino_doppia_verita"].update_one(
                {"id": prodotto["id"]},
                {"$set": {
                    "giacenza_reale": prodotto.get("giacenza_teorica", 0),
                    "ultimo_inventario": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
        allineati += 1
    
    return {
        "message": f"Allineati {allineati} prodotti ({direzione})",
        "prodotti_allineati": allineati
    }


@router.get("/differenze")
async def list_differenze(
    skip: int = Query(0),
    limit: int = Query(100),
    solo_non_risolte: bool = Query(True),
    tipo: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Lista tutte le differenze inventariali."""
    db = Database.get_db()
    
    query = {}
    if solo_non_risolte:
        query["risolto"] = False
    if tipo:
        query["tipo"] = tipo
    
    differenze = await db["magazzino_differenze"].find(
        query, {"_id": 0}
    ).sort("data", -1).skip(skip).limit(limit).to_list(limit)
    
    # Statistiche
    stats_pipeline = [
        {"$match": {"risolto": False}},
        {"$group": {
            "_id": "$tipo",
            "count": {"$sum": 1},
            "valore_totale": {"$sum": "$differenza_valore"}
        }}
    ]
    stats = await db["magazzino_differenze"].aggregate(stats_pipeline).to_list(20)
    
    return {
        "differenze": differenze,
        "totale": await db["magazzino_differenze"].count_documents(query),
        "per_tipo": {s["_id"]: {"count": s["count"], "valore": round(s["valore_totale"], 2)} for s in stats},
        "tipi_disponibili": TIPI_DIFFERENZA
    }


@router.put("/differenze/{differenza_id}/risolvi")
async def risolvi_differenza(
    differenza_id: str,
    data: Dict[str, Any] = Body(...)
) -> Dict[str, str]:
    """Marca una differenza come risolta."""
    db = Database.get_db()
    
    result = await db["magazzino_differenze"].update_one(
        {"id": differenza_id},
        {"$set": {
            "risolto": True,
            "risoluzione_note": data.get("note", ""),
            "risolto_da": data.get("utente", "system"),
            "risolto_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Differenza non trovata")
    
    return {"message": "Differenza marcata come risolta"}


@router.get("/report/valore-magazzino")
async def report_valore_magazzino() -> Dict[str, Any]:
    """Report valore magazzino teorico vs reale per categoria."""
    db = Database.get_db()
    
    pipeline = [
        {"$group": {
            "_id": "$categoria",
            "prodotti": {"$sum": 1},
            "giacenza_teorica_totale": {"$sum": "$giacenza_teorica"},
            "giacenza_reale_totale": {"$sum": "$giacenza_reale"},
            "valore_teorico": {"$sum": {"$multiply": ["$giacenza_teorica", "$costo_medio"]}},
            "valore_reale": {"$sum": {"$multiply": ["$giacenza_reale", "$costo_medio"]}}
        }},
        {"$sort": {"valore_teorico": -1}}
    ]
    
    per_categoria = await db["magazzino_doppia_verita"].aggregate(pipeline).to_list(50)
    
    totale_teorico = sum(c.get("valore_teorico", 0) for c in per_categoria)
    totale_reale = sum(c.get("valore_reale", 0) for c in per_categoria)
    
    return {
        "per_categoria": [{
            "categoria": c["_id"] or "altro",
            "prodotti": c["prodotti"],
            "giacenza_teorica": c["giacenza_teorica_totale"],
            "giacenza_reale": c["giacenza_reale_totale"],
            "valore_teorico": round(c["valore_teorico"], 2),
            "valore_reale": round(c["valore_reale"], 2),
            "differenza": round(c["valore_teorico"] - c["valore_reale"], 2)
        } for c in per_categoria],
        "totali": {
            "valore_teorico": round(totale_teorico, 2),
            "valore_reale": round(totale_reale, 2),
            "differenza": round(totale_teorico - totale_reale, 2),
            "percentuale_differenza": round((totale_teorico - totale_reale) / totale_teorico * 100, 2) if totale_teorico > 0 else 0
        }
    }


@router.post("/migra-da-warehouse")
async def migra_da_warehouse_inventory() -> Dict[str, Any]:
    """
    Migra i prodotti esistenti da warehouse_inventory a magazzino_doppia_verita.
    """
    db = Database.get_db()
    
    # Recupera prodotti esistenti
    prodotti_esistenti = await db["warehouse_inventory"].find({}).to_list(10000)
    
    migrati = 0
    errori = 0
    aggiornati = 0
    
    for prod in prodotti_esistenti:
        try:
            # Verifica se già migrato
            existing = await db["magazzino_doppia_verita"].find_one({
                "$or": [
                    {"codice": prod.get("codice")},
                    {"nome": prod.get("nome")}
                ]
            })
            
            giacenza = prod.get("giacenza", 0) or 0
            costo_medio = 0
            if prod.get("prezzi") and prod["prezzi"].get("avg"):
                costo_medio = prod["prezzi"]["avg"]
            
            if existing:
                # Aggiorna giacenze se già esiste
                await db["magazzino_doppia_verita"].update_one(
                    {"id": existing["id"]},
                    {"$set": {
                        "giacenza_teorica": giacenza,
                        "giacenza_reale": giacenza,
                        "costo_medio": costo_medio,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                aggiornati += 1
                continue
            
            nuovo_prodotto = {
                "id": str(uuid.uuid4()),
                "codice": prod.get("codice", ""),
                "nome": prod.get("nome") or prod.get("descrizione", "Prodotto"),
                "descrizione": prod.get("descrizione", ""),
                "categoria": prod.get("categoria", "altro"),
                "unita_misura": prod.get("unita_misura", "pz"),
                "giacenza_teorica": giacenza,
                "giacenza_reale": giacenza,  # Inizialmente uguale
                "scorta_minima": prod.get("giacenza_minima", 0) or 0,
                "scorta_massima": 0,
                "costo_medio": costo_medio,
                "ultimo_costo": costo_medio,
                "fornitore_principale": prod.get("ultimo_fornitore", ""),
                "fornitore_piva": prod.get("fornitore_piva", ""),
                "centro_costo": "CDC-03",  # Default laboratorio
                "attivo": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            await db["magazzino_doppia_verita"].insert_one(nuovo_prodotto.copy())
            migrati += 1
            
        except Exception:
            errori += 1
    
    return {
        "message": f"Migrazione completata: {migrati} nuovi, {aggiornati} aggiornati, {errori} errori",
        "migrati": migrati,
        "aggiornati": aggiornati,
        "errori": errori
    }


@router.post("/pulizia-fornitori-esclusi")
async def pulizia_fornitori_esclusi(
    dry_run: bool = Query(default=True, description="Se True, mostra solo anteprima senza rimuovere")
) -> Dict[str, Any]:
    """
    Rimuove dal magazzino tutti i prodotti appartenenti a fornitori 
    che hanno il flag esclude_magazzino=True.
    
    - dry_run=True: mostra anteprima dei prodotti che verrebbero rimossi
    - dry_run=False: esegue la rimozione effettiva
    """
    db = Database.get_db()
    
    # 1. Trova tutti i fornitori con esclude_magazzino=True
    fornitori_esclusi = []
    
    # Cerca in suppliers
    async for s in db[Collections.SUPPLIERS].find({"esclude_magazzino": True}, {"_id": 0}):
        fornitori_esclusi.append({
            "nome": s.get("ragione_sociale", ""),
            "partita_iva": s.get("partita_iva", ""),
            "id": s.get("id", "")
        })
    
    # Cerca anche in fornitori
    async for f in db["suppliers"].find({"esclude_magazzino": True}, {"_id": 0}):
        nome = f.get("ragione_sociale", "")
        # Evita duplicati
        if not any(x["nome"] == nome for x in fornitori_esclusi):
            fornitori_esclusi.append({
                "nome": nome,
                "partita_iva": f.get("partita_iva", ""),
                "id": f.get("id", "")
            })
    
    if not fornitori_esclusi:
        return {
            "message": "Nessun fornitore con esclude_magazzino=True trovato",
            "fornitori_esclusi": 0,
            "prodotti_trovati": 0,
            "prodotti_rimossi": 0
        }
    
    # 2. Estrai i nomi dei fornitori
    nomi_fornitori = [f["nome"] for f in fornitori_esclusi if f["nome"]]
    partite_iva = [f["partita_iva"] for f in fornitori_esclusi if f["partita_iva"]]
    
    # 3. Trova prodotti nel magazzino di questi fornitori
    query_prodotti = {"$or": []}
    
    if nomi_fornitori:
        query_prodotti["$or"].append({"ultimo_fornitore": {"$in": nomi_fornitori}})
        query_prodotti["$or"].append({"fornitori": {"$in": nomi_fornitori}})
        query_prodotti["$or"].append({"fornitore_principale": {"$in": nomi_fornitori}})
        query_prodotti["$or"].append({"fornitore": {"$in": nomi_fornitori}})
    
    if partite_iva:
        query_prodotti["$or"].append({"supplier_vat": {"$in": partite_iva}})
        query_prodotti["$or"].append({"fornitore_piva": {"$in": partite_iva}})
    
    if not query_prodotti["$or"]:
        return {
            "message": "Nessun criterio di ricerca valido",
            "fornitori_esclusi": len(fornitori_esclusi),
            "prodotti_trovati": 0,
            "prodotti_rimossi": 0
        }
    
    # Cerca in warehouse_inventory
    prodotti_wh = await db["warehouse_inventory"].find(
        query_prodotti,
        {"_id": 0, "id": 1, "nome": 1, "ultimo_fornitore": 1, "giacenza": 1}
    ).to_list(10000)
    
    # Cerca in magazzino_doppia_verita
    prodotti_dv = await db["magazzino_doppia_verita"].find(
        query_prodotti,
        {"_id": 0, "id": 1, "nome": 1, "fornitore_principale": 1, "giacenza_teorica": 1}
    ).to_list(10000)
    
    # 4. Se dry_run, restituisci solo l'anteprima
    if dry_run:
        return {
            "message": "Anteprima pulizia magazzino (dry_run=True)",
            "fornitori_esclusi": len(fornitori_esclusi),
            "fornitori_dettaglio": fornitori_esclusi,
            "prodotti_warehouse_inventory": len(prodotti_wh),
            "prodotti_doppia_verita": len(prodotti_dv),
            "totale_prodotti": len(prodotti_wh) + len(prodotti_dv),
            "anteprima_prodotti": [
                {"nome": p.get("nome"), "fornitore": p.get("ultimo_fornitore") or p.get("fornitore_principale"), "giacenza": p.get("giacenza") or p.get("giacenza_teorica", 0)}
                for p in (prodotti_wh + prodotti_dv)[:50]
            ],
            "dry_run": True
        }
    
    # 5. Esegui la rimozione effettiva
    risultato_wh = await db["warehouse_inventory"].delete_many(query_prodotti)
    risultato_dv = await db["magazzino_doppia_verita"].delete_many(query_prodotti)
    
    totale_rimossi = risultato_wh.deleted_count + risultato_dv.deleted_count
    
    return {
        "message": f"Pulizia completata: rimossi {totale_rimossi} prodotti",
        "fornitori_esclusi": len(fornitori_esclusi),
        "fornitori_dettaglio": fornitori_esclusi,
        "prodotti_rimossi_warehouse_inventory": risultato_wh.deleted_count,
        "prodotti_rimossi_doppia_verita": risultato_dv.deleted_count,
        "totale_prodotti_rimossi": totale_rimossi,
        "dry_run": False
    }


@router.get("/fornitori-esclusi")
async def get_fornitori_esclusi_magazzino() -> Dict[str, Any]:
    """
    Restituisce la lista di tutti i fornitori che hanno il flag esclude_magazzino=True.
    Mostra anche il conteggio dei prodotti presenti nel magazzino per ciascuno.
    """
    db = Database.get_db()
    
    fornitori_esclusi = []
    
    # Cerca in suppliers
    async for s in db[Collections.SUPPLIERS].find({"esclude_magazzino": True}, {"_id": 0}):
        nome = s.get("ragione_sociale", "")
        # Conta prodotti nel magazzino
        count_wh = await db["warehouse_inventory"].count_documents({
            "$or": [
                {"ultimo_fornitore": nome},
                {"fornitori": nome}
            ]
        })
        count_dv = await db["magazzino_doppia_verita"].count_documents({
            "$or": [
                {"fornitore_principale": nome},
                {"fornitore": nome}
            ]
        })
        fornitori_esclusi.append({
            "id": s.get("id"),
            "ragione_sociale": nome,
            "partita_iva": s.get("partita_iva", ""),
            "prodotti_warehouse_inventory": count_wh,
            "prodotti_doppia_verita": count_dv,
            "source": "suppliers"
        })
    
    # Cerca in fornitori
    async for f in db["suppliers"].find({"esclude_magazzino": True}, {"_id": 0}):
        nome = f.get("ragione_sociale", "")
        # Evita duplicati
        if any(x["ragione_sociale"] == nome for x in fornitori_esclusi):
            continue
        count_wh = await db["warehouse_inventory"].count_documents({
            "$or": [
                {"ultimo_fornitore": nome},
                {"fornitori": nome}
            ]
        })
        count_dv = await db["magazzino_doppia_verita"].count_documents({
            "$or": [
                {"fornitore_principale": nome},
                {"fornitore": nome}
            ]
        })
        fornitori_esclusi.append({
            "id": f.get("id"),
            "ragione_sociale": nome,
            "partita_iva": f.get("partita_iva", ""),
            "prodotti_warehouse_inventory": count_wh,
            "prodotti_doppia_verita": count_dv,
            "source": "fornitori"
        })
    
    totale_prodotti = sum(f["prodotti_warehouse_inventory"] + f["prodotti_doppia_verita"] for f in fornitori_esclusi)
    
    return {
        "fornitori": fornitori_esclusi,
        "totale_fornitori": len(fornitori_esclusi),
        "totale_prodotti_da_rimuovere": totale_prodotti
    }

