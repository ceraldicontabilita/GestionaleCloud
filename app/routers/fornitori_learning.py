"""
Router Fornitori Learning - Gestione associazioni fornitore-keywords
Permette di memorizzare e apprendere le categorie dei fornitori
"""
from fastapi import APIRouter, HTTPException, Body
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone
from pydantic import BaseModel

from app.database import Database

router = APIRouter(tags=["Fornitori Learning"])

# Collezione MongoDB
COLL_FORNITORI_KEYWORDS = "fornitori_keywords"


class FornitoreKeywordsCreate(BaseModel):
    """Schema per creare/aggiornare associazione fornitore"""
    fornitore_nome: str
    keywords: List[str]
    centro_costo_suggerito: Optional[str] = None
    note: Optional[str] = None


class FornitoreKeywordsResponse(BaseModel):
    """Schema risposta fornitore"""
    id: str
    fornitore_nome: str
    fornitore_nome_normalizzato: str
    keywords: List[str]
    centro_costo_suggerito: Optional[str]
    note: Optional[str]
    fatture_count: int
    totale_fatture: float
    created_at: str
    updated_at: str


def normalizza_nome_fornitore(nome: str) -> str:
    """Normalizza il nome del fornitore per match fuzzy"""
    if not nome:
        return ""
    # Rimuovi caratteri speciali e normalizza
    nome = nome.lower().strip()
    # Rimuovi suffissi comuni
    for suffix in [" s.r.l.", " srl", " s.p.a.", " spa", " s.a.s.", " sas", 
                   " s.n.c.", " snc", " srls", " s.r.l.s.", " unipersonale",
                   " di ", " soc. coop.", " coop.", " onlus"]:
        nome = nome.replace(suffix, "")
    return nome.strip()


@router.get("/stats")
async def get_learning_stats() -> Dict[str, Any]:
    """
    Statistiche complete della Learning Machine.
    """
    db = Database.get_db()
    
    # Conta fornitori configurati
    fornitori_con_keywords = await db[COLL_FORNITORI_KEYWORDS].count_documents({})
    
    # Conta fornitori totali (da fatture)
    fornitori_unici = await db["invoices"].distinct("supplier_name")
    totale_fornitori = len([f for f in fornitori_unici if f])
    
    # Conta fatture
    totale_fatture = await db["invoices"].count_documents({})
    fatture_classificate = await db["invoices"].count_documents({
        "centro_costo_id": {"$exists": True, "$ne": None, "$ne": ""}
    })
    
    # Conta F24
    totale_f24 = await db["f24_unificato"].count_documents({})
    f24_classificati = await db["f24_unificato"].count_documents({
        "centro_costo_id": {"$exists": True, "$ne": None, "$ne": ""}
    })
    
    perc_fatture = round(fatture_classificate / max(totale_fatture, 1) * 100, 1)
    perc_f24 = round(f24_classificati / max(totale_f24, 1) * 100, 1)
    
    return {
        "fornitori_con_keywords": fornitori_con_keywords,
        "totale_fornitori": totale_fornitori,
        "copertura_fornitori": round(fornitori_con_keywords / max(totale_fornitori, 1) * 100, 1),
        "totale_fatture": totale_fatture,
        "fatture_classificate": fatture_classificate,
        "percentuale_fatture": perc_fatture,
        "totale_f24": totale_f24,
        "f24_classificati": f24_classificati,
        "percentuale_f24": perc_f24
    }


@router.get("/lista")
async def lista_fornitori_keywords() -> Dict[str, Any]:
    """
    Lista tutti i fornitori con keywords configurate
    """
    db = Database.get_db()
    
    fornitori = await db[COLL_FORNITORI_KEYWORDS].find(
        {}, {"_id": 0}
    ).sort("fatture_count", -1).to_list(5000)
    
    return {
        "totale": len(fornitori),
        "fornitori": fornitori
    }


@router.get("/non-classificati")
async def fornitori_non_classificati(limit: int = 50) -> Dict[str, Any]:
    """
    Lista i fornitori in 'Altri costi non classificati' che non hanno keywords configurate.
    Mostra i totali REALI del fornitore (tutte le fatture), non solo quelle non classificate.
    """
    db = Database.get_db()
    
    # Trova fornitori già configurati
    configurati = await db[COLL_FORNITORI_KEYWORDS].distinct("fornitore_nome_normalizzato")
    
    # Aggrega fornitori non classificati
    pipeline = [
        {"$match": {
            "centro_costo_nome": "Altri costi non classificati",
            "supplier_name": {"$ne": None, "$ne": ""}
        }},
        {"$group": {
            "_id": "$supplier_name",
            "count_non_class": {"$sum": 1},
            "esempio_linee": {"$first": "$linee"}
        }},
        {"$sort": {"count_non_class": -1}},
        {"$limit": limit}
    ]
    
    fornitori_raw = await db["invoices"].aggregate(pipeline).to_list(limit)
    
    # Per ogni fornitore, calcola i totali REALI (tutte le fatture)
    fornitori = []
    for f in fornitori_raw:
        nome_norm = normalizza_nome_fornitore(f["_id"])
        if nome_norm not in configurati:
            # Calcola totali REALI (tutte le fatture del fornitore)
            totali = await db["invoices"].aggregate([
                {"$match": {"supplier_name": f["_id"]}},
                {"$group": {
                    "_id": None,
                    "count": {"$sum": 1},
                    "totale": {"$sum": "$total_amount"}
                }}
            ]).to_list(1)
            
            count_reale = totali[0]["count"] if totali else f["count_non_class"]
            totale_reale = totali[0]["totale"] if totali else 0
            
            # Estrai prime descrizioni linee per aiutare l'utente
            descrizioni = []
            if f.get("esempio_linee"):
                for linea in f["esempio_linee"][:3]:
                    if isinstance(linea, dict):
                        desc = linea.get("descrizione") or linea.get("description", "")
                        if desc:
                            descrizioni.append(desc[:100])
            
            fornitori.append({
                "fornitore_nome": f["_id"],
                "fornitore_nome_normalizzato": nome_norm,
                "fatture_count": count_reale,  # Totale REALE
                "fatture_non_classificate": f["count_non_class"],
                "totale_fatture": round(totale_reale, 2),  # Totale REALE
                "esempio_descrizioni": descrizioni
            })
    
    # Ordina per numero fatture reali
    fornitori.sort(key=lambda x: x["fatture_count"], reverse=True)
    
    return {
        "totale": len(fornitori),
        "fornitori": fornitori
    }


@router.post("/salva")
async def salva_fornitore_keywords(data: FornitoreKeywordsCreate) -> Dict[str, Any]:
    """
    Salva o aggiorna le keywords associate a un fornitore.
    Questo permette alla Learning Machine di classificare correttamente le fatture future.
    """
    db = Database.get_db()
    
    nome_norm = normalizza_nome_fornitore(data.fornitore_nome)
    
    # Conta fatture per questo fornitore
    fatture_count = await db["invoices"].count_documents({
        "supplier_name": {"$regex": data.fornitore_nome, "$options": "i"}
    })
    totale = 0
    pipeline = [
        {"$match": {"supplier_name": {"$regex": data.fornitore_nome, "$options": "i"}}},
        {"$group": {"_id": None, "tot": {"$sum": "$total_amount"}}}
    ]
    agg = await db["invoices"].aggregate(pipeline).to_list(1)
    if agg:
        totale = agg[0].get("tot", 0)
    
    # Documento da salvare
    doc = {
        "id": f"fk_{nome_norm.replace(' ', '_')}",
        "fornitore_nome": data.fornitore_nome,
        "fornitore_nome_normalizzato": nome_norm,
        "keywords": [k.lower().strip() for k in data.keywords if k.strip()],
        "centro_costo_suggerito": data.centro_costo_suggerito,
        "note": data.note,
        "fatture_count": fatture_count,
        "totale_fatture": round(totale, 2),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Upsert
    existing = await db[COLL_FORNITORI_KEYWORDS].find_one(
        {"fornitore_nome_normalizzato": nome_norm},
        {"_id": 0}
    )
    
    if existing:
        await db[COLL_FORNITORI_KEYWORDS].update_one(
            {"fornitore_nome_normalizzato": nome_norm},
            {"$set": doc}
        )
        return {"success": True, "message": "Fornitore aggiornato", "fornitore": doc}
    else:
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        # Copia del doc per evitare che insert_one aggiunga _id all'originale
        doc_to_insert = doc.copy()
        await db[COLL_FORNITORI_KEYWORDS].insert_one(doc_to_insert)
        return {"success": True, "message": "Fornitore creato", "fornitore": doc}


@router.delete("/{fornitore_id}")
async def elimina_fornitore_keywords(fornitore_id: str) -> Dict[str, Any]:
    """Elimina le keywords di un fornitore"""
    db = Database.get_db()
    
    result = await db[COLL_FORNITORI_KEYWORDS].delete_one({"id": fornitore_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Fornitore non trovato")
    
    return {"success": True, "message": "Fornitore eliminato"}


@router.post("/riclassifica-con-keywords")
async def riclassifica_con_keywords_personalizzate() -> Dict[str, Any]:
    """
    Riclassifica le fatture usando le keywords personalizzate dei fornitori.
    Applica le associazioni memorizzate per migliorare la classificazione automatica.
    """
    db = Database.get_db()
    
    # Carica tutte le keywords configurate
    keywords_config = await db[COLL_FORNITORI_KEYWORDS].find({}).to_list(5000)
    
    if not keywords_config:
        return {
            "success": False,
            "message": "Nessun fornitore configurato. Aggiungi prima le keywords ai fornitori."
        }
    
    # Import classificatore
    import importlib
    import app.services.learning_machine_cdc as lm
    importlib.reload(lm)
    
    riclassificate = 0
    dettaglio = []
    
    for config in keywords_config:
        fornitore_nome = config["fornitore_nome"]
        keywords = config.get("keywords", [])
        centro_suggerito = config.get("centro_costo_suggerito")
        
        if not keywords:
            continue
        
        # Trova fatture di questo fornitore in "Altri costi" o non classificate
        # Usa regex per match parziale e case-insensitive
        # Escape caratteri speciali nel nome per regex
        import re
        nome_escaped = re.escape(fornitore_nome)
        
        fatture = await db["invoices"].find({
            "$and": [
                {"$or": [
                    {"supplier_name": {"$regex": nome_escaped, "$options": "i"}},
                    {"fornitore_nome": {"$regex": nome_escaped, "$options": "i"}}
                ]},
                {"$or": [
                    {"centro_costo_nome": "Altri costi non classificati"},
                    {"centro_costo_id": {"$exists": False}},
                    {"centro_costo_id": None},
                    {"centro_costo_id": ""}
                ]}
            ]
        }).to_list(5000)
        
        for fatt in fatture:
            # Usa le keywords per determinare il centro di costo
            # Prima prova con il centro suggerito
            cdc_id = None
            cdc_config = None
            
            if centro_suggerito:
                # Cerca il centro di costo per chiave interna o per codice
                if centro_suggerito in lm.CENTRI_COSTO:
                    cdc_id = centro_suggerito
                    cdc_config = lm.CENTRI_COSTO[cdc_id]
                else:
                    # Cerca per codice (es. B7.5.3)
                    for key, cfg in lm.CENTRI_COSTO.items():
                        if cfg.get("codice") == centro_suggerito:
                            cdc_id = key
                            cdc_config = cfg
                            break
            
            if not cdc_config:
                # Altrimenti usa la classificazione standard con le keywords
                testo = " ".join(keywords)
                cdc_id, cdc_config, _ = lm.classifica_fattura_per_centro_costo(
                    fornitore_nome, testo, []
                )
            
            # Aggiorna fattura
            await db["invoices"].update_one(
                {"_id": fatt["_id"]},
                {"$set": {
                    "centro_costo_id": cdc_id,
                    "centro_costo_nome": cdc_config["nome"],
                    "classificazione_fonte": "keywords_personalizzate"
                }}
            )
            riclassificate += 1
        
        if fatture:
            dettaglio.append({
                "fornitore": fornitore_nome,
                "fatture_riclassificate": len(fatture),
                "nuovo_centro_costo": cdc_config["nome"] if fatture else None
            })
    
    return {
        "success": True,
        "totale_riclassificate": riclassificate,
        "dettaglio": dettaglio
    }


@router.get("/suggerisci-keywords/{fornitore_nome}")
async def suggerisci_keywords(fornitore_nome: str) -> Dict[str, Any]:
    """
    Suggerisce keywords basandosi sulle descrizioni delle linee fattura del fornitore.
    Aiuta l'utente a configurare rapidamente le keywords.
    """
    db = Database.get_db()
    
    # Trova fatture del fornitore
    fatture = await db["invoices"].find(
        {"supplier_name": {"$regex": fornitore_nome, "$options": "i"}},
        {"_id": 0, "linee": 1, "descrizione": 1}
    ).limit(20).to_list(20)
    
    # Estrai parole frequenti dalle descrizioni
    parole = {}
    stop_words = {"di", "da", "per", "con", "il", "la", "i", "le", "un", "una", "e", "o", 
                  "in", "su", "del", "della", "dei", "delle", "al", "alla", "ai", "alle",
                  "n.", "nr.", "art.", "pz.", "kg.", "lt.", "ml.", "cm.", "mm."}
    
    for fatt in fatture:
        # Descrizione generale
        if fatt.get("descrizione"):
            for parola in fatt["descrizione"].lower().split():
                parola = parola.strip(".,;:!?()[]{}\"'")
                if len(parola) > 3 and parola not in stop_words:
                    parole[parola] = parole.get(parola, 0) + 1
        
        # Linee fattura
        for linea in fatt.get("linee", []):
            if isinstance(linea, dict):
                desc = linea.get("descrizione") or linea.get("description", "")
                for parola in desc.lower().split():
                    parola = parola.strip(".,;:!?()[]{}\"'")
                    if len(parola) > 3 and parola not in stop_words:
                        parole[parola] = parole.get(parola, 0) + 1
    
    # Ordina per frequenza e prendi le top 15
    keywords_suggerite = sorted(parole.items(), key=lambda x: x[1], reverse=True)[:15]
    
    return {
        "fornitore": fornitore_nome,
        "keywords_suggerite": [k for k, _ in keywords_suggerite],
        "frequenze": {k: v for k, v in keywords_suggerite}
    }


@router.get("/centri-costo-disponibili")
async def centri_costo_disponibili() -> List[Dict[str, str]]:
    """
    Lista i centri di costo disponibili per la selezione
    """
    import app.services.learning_machine_cdc as lm
    
    return [
        {"id": cdc_id, "nome": config["nome"], "codice": config["codice"]}
        for cdc_id, config in lm.CENTRI_COSTO.items()
    ]



# ============================================
# ASSOCIAZIONE FORNITORI → MAGAZZINO
# ============================================

# Mappa centri di costo → categorie magazzino
CDC_TO_MAGAZZINO_CATEGORIA = {
    "1.1_CAFFE_BEVANDE_CALDE": "caffe",
    "1.2_BEVANDE_FREDDE_ALCOLICI": "bevande",
    "1.3_MATERIE_PRIME_PASTICCERIA": "dolci",
    "1.4_LATTE_LATTICINI": "latticini",
    "1.5_PANE_PRODOTTI_FORNO": "pane",
    "1.6_PRODOTTI_CONFEZIONATI": "snack",
    "1.7_SALUMI_FORMAGGI": "salumi",
    "2.1_ENERGIA_ELETTRICA": "utenze",
    "5.3_PICCOLE_ATTREZZATURE": "attrezzature",
    "7.3_PULIZIA_IGIENE": "pulizia"
}


@router.post("/associa-magazzino")
async def associa_fornitori_magazzino() -> Dict[str, Any]:
    """
    Associa i prodotti nel magazzino ai fornitori configurati.
    Aggiorna la categoria dei prodotti basandosi sulle keywords del fornitore.
    Questo permette di:
    - Sapere da chi compri la Coca Cola
    - Categorizzare correttamente i prodotti
    - Calcolare le giacenze per fornitore
    """
    db = Database.get_db()
    
    # Carica fornitori configurati
    fornitori_config = await db[COLL_FORNITORI_KEYWORDS].find({}).to_list(5000)
    
    if not fornitori_config:
        return {"success": False, "message": "Nessun fornitore configurato"}
    
    aggiornati = 0
    dettaglio = []
    
    for config in fornitori_config:
        fornitore_nome = config["fornitore_nome"]
        keywords = config.get("keywords", [])
        centro_costo = config.get("centro_costo_suggerito")
        
        # Determina categoria magazzino dal centro di costo
        categoria_magazzino = CDC_TO_MAGAZZINO_CATEGORIA.get(centro_costo, "altro")
        
        # Trova prodotti di questo fornitore nel magazzino
        prodotti = await db["warehouse_inventory"].find({
            "fornitori": {"$regex": fornitore_nome, "$options": "i"}
        }).to_list(5000)
        
        for prod in prodotti:
            # Aggiorna categoria se non è già specificata
            if prod.get("categoria") == "altro" or not prod.get("categoria"):
                await db["warehouse_inventory"].update_one(
                    {"_id": prod["_id"]},
                    {"$set": {
                        "categoria": categoria_magazzino,
                        "fornitore_principale": fornitore_nome,
                        "keywords_fornitore": keywords,
                        "centro_costo_fornitore": centro_costo
                    }}
                )
                aggiornati += 1
        
        if prodotti:
            dettaglio.append({
                "fornitore": fornitore_nome,
                "prodotti_trovati": len(prodotti),
                "categoria_assegnata": categoria_magazzino
            })
    
    return {
        "success": True,
        "prodotti_aggiornati": aggiornati,
        "dettaglio": dettaglio
    }


@router.get("/prodotti-per-fornitore/{fornitore_nome}")
async def prodotti_per_fornitore(fornitore_nome: str) -> Dict[str, Any]:
    """
    Lista tutti i prodotti associati a un fornitore nel magazzino.
    Utile per verificare cosa compri da ciascun fornitore.
    """
    db = Database.get_db()
    
    prodotti = await db["warehouse_inventory"].find(
        {"fornitori": {"$regex": fornitore_nome, "$options": "i"}},
        {"_id": 0, "nome": 1, "categoria": 1, "giacenza": 1, "unita_misura": 1, "prezzi": 1}
    ).sort("nome", 1).to_list(100)
    
    # Raggruppa per categoria
    per_categoria = {}
    for p in prodotti:
        cat = p.get("categoria", "altro")
        if cat not in per_categoria:
            per_categoria[cat] = []
        per_categoria[cat].append(p)
    
    return {
        "fornitore": fornitore_nome,
        "totale_prodotti": len(prodotti),
        "per_categoria": per_categoria,
        "prodotti": prodotti[:50]  # Primi 50
    }


@router.get("/giacenze-fornitore/{fornitore_nome}")
async def giacenze_fornitore(fornitore_nome: str) -> Dict[str, Any]:
    """
    Calcola giacenze totali per un fornitore.
    Es: "Quante Coca Cola ho in magazzino?"
    """
    db = Database.get_db()
    
    # Aggregazione per calcolare giacenze
    pipeline = [
        {"$match": {"fornitori": {"$regex": fornitore_nome, "$options": "i"}}},
        {"$group": {
            "_id": "$categoria",
            "totale_prodotti": {"$sum": 1},
            "giacenza_totale": {"$sum": "$giacenza"},
            "valore_stimato": {"$sum": {"$multiply": ["$giacenza", {"$ifNull": [{"$avg": ["$prezzi.min", "$prezzi.max"]}, 0]}]}}
        }},
        {"$sort": {"totale_prodotti": -1}}
    ]
    
    stats = await db["warehouse_inventory"].aggregate(pipeline).to_list(5000)
    
    totale_giacenza = sum(s.get("giacenza_totale", 0) for s in stats)
    totale_valore = sum(s.get("valore_stimato", 0) for s in stats)
    
    return {
        "fornitore": fornitore_nome,
        "giacenza_totale": totale_giacenza,
        "valore_stimato": round(totale_valore, 2),
        "per_categoria": stats
    }



# ============================================
# CLASSIFICAZIONE F24 (Learning Machine)
# ============================================

@router.post("/classifica-f24")
async def classifica_f24_automatica() -> Dict[str, Any]:
    """
    Classifica automaticamente i documenti F24 nei centri di costo appropriati,
    basandosi sui codici tributo presenti in ciascun documento.
    
    Es:
    - Codici 60xx (IVA) → Centro costo "IVA periodica"
    - Codici 10xx (ritenute dipendenti) → "Costo del personale"
    - Codici 391x (IMU) → "IMU"
    - ecc.
    """
    db = Database.get_db()
    
    import app.services.learning_machine_cdc as lm
    import importlib
    importlib.reload(lm)
    
    # Trova tutti i documenti F24 non ancora classificati
    f24s = await db["f24_unificato"].find(
        {
            "status": {"$ne": "eliminato"},
            "$or": [
                {"centro_costo_id": {"$exists": False}},
                {"centro_costo_id": None},
                {"centro_costo_id": ""}
            ]
        }
    ).to_list(5000)
    
    if not f24s:
        return {
            "success": True,
            "message": "Tutti gli F24 sono già classificati",
            "classificati": 0
        }
    
    classificati = 0
    dettaglio = []
    
    for f24 in f24s:
        # Classifica usando la nuova funzione
        cdc_id, cdc_config, tipo_tributo = lm.classifica_f24_per_centro_costo(f24)
        
        # Aggiorna il documento
        await db["f24_unificato"].update_one(
            {"_id": f24["_id"]},
            {"$set": {
                "centro_costo_id": cdc_id,
                "centro_costo_nome": cdc_config["nome"],
                "centro_costo_codice": cdc_config["codice"],
                "tipo_tributo_principale": tipo_tributo,
                "classificazione_fonte": "learning_machine"
            }}
        )
        classificati += 1
        
        dettaglio.append({
            "id": str(f24.get("id", f24.get("_id"))),
            "anno": f24.get("anno"),
            "tipo_tributo": tipo_tributo,
            "centro_costo": cdc_config["nome"]
        })
    
    return {
        "success": True,
        "classificati": classificati,
        "dettaglio": dettaglio[:20]  # Primi 20 per brevità
    }


@router.get("/f24-statistiche")
async def f24_statistiche() -> Dict[str, Any]:
    """
    Statistiche sulla classificazione degli F24.
    """
    db = Database.get_db()
    
    # Conta totali
    totale = await db["f24_unificato"].count_documents({"status": {"$ne": "eliminato"}})
    classificati = await db["f24_unificato"].count_documents({
        "status": {"$ne": "eliminato"},
        "centro_costo_id": {"$exists": True, "$ne": None, "$ne": ""}
    })
    
    # Aggregazione per centro di costo
    pipeline = [
        {"$match": {"status": {"$ne": "eliminato"}, "centro_costo_nome": {"$exists": True}}},
        {"$group": {
            "_id": "$centro_costo_nome",
            "count": {"$sum": 1},
            "totale_importo": {"$sum": "$saldo_finale"}
        }},
        {"$sort": {"count": -1}}
    ]
    
    per_cdc = await db["f24_unificato"].aggregate(pipeline).to_list(5000)
    
    return {
        "totale_f24": totale,
        "classificati": classificati,
        "non_classificati": totale - classificati,
        "per_centro_costo": per_cdc
    }


@router.post("/riclassifica-f24/{f24_id}")
async def riclassifica_singolo_f24(f24_id: str, data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Riclassifica manualmente un singolo F24.
    
    Body:
        - centro_costo_id: ID del centro di costo da assegnare
    """
    db = Database.get_db()
    
    import app.services.learning_machine_cdc as lm
    
    centro_costo_id = data.get("centro_costo_id")
    if not centro_costo_id:
        raise HTTPException(status_code=400, detail="centro_costo_id richiesto")
    
    # Verifica che il centro di costo esista
    if centro_costo_id not in lm.CENTRI_COSTO:
        # Prova a cercarlo per codice
        for key, cfg in lm.CENTRI_COSTO.items():
            if cfg.get("codice") == centro_costo_id:
                centro_costo_id = key
                break
        else:
            raise HTTPException(status_code=400, detail=f"Centro di costo '{centro_costo_id}' non trovato")
    
    cdc_config = lm.CENTRI_COSTO[centro_costo_id]
    
    result = await db["f24_unificato"].update_one(
        {"id": f24_id},
        {"$set": {
            "centro_costo_id": centro_costo_id,
            "centro_costo_nome": cdc_config["nome"],
            "centro_costo_codice": cdc_config["codice"],
            "classificazione_fonte": "manuale"
        }}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="F24 non trovato")
    
    return {
        "success": True,
        "message": f"F24 classificato come '{cdc_config['nome']}'"
    }
