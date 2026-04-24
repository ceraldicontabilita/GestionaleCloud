"""
Router FastAPI per gestione MUTUI
==================================

Endpoints:
- GET /api/mutui - Lista tutti i mutui
- GET /api/mutui/{mutuo_id} - Dettaglio mutuo
- POST /api/mutui - Crea nuovo mutuo
- PUT /api/mutui/{mutuo_id} - Aggiorna mutuo
- DELETE /api/mutui/{mutuo_id} - Elimina mutuo
- GET /api/mutui/statistiche/dashboard - Statistiche generali
- POST /api/mutui/riconcilia - Riconcilia rate con estratto conto
- GET /api/mutui/{mutuo_id}/rate - Rate del mutuo
- PUT /api/mutui/{mutuo_id}/rate/{numero_rata}/riconcilia - Riconcilia singola rata
"""

from fastapi import APIRouter, HTTPException, status, Query, Depends
from fastapi.responses import JSONResponse
from typing import List, Optional
from datetime import datetime, timedelta, timezone
import uuid
from bson import ObjectId
import logging

from app.database import Database

router = APIRouter(tags=["Mutui"], redirect_slashes=False)
logger = logging.getLogger(__name__)


def get_db():
    """Get database instance"""
    return Database.get_db()


def serialize_doc(doc):
    """Serializza documento MongoDB rimuovendo _id o convertendolo"""
    if doc is None:
        return None
    if "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


# ============================================================================
# ENDPOINTS LISTA E DETTAGLIO
# ============================================================================

@router.get("/", summary="Lista tutti i mutui")
@router.get("", summary="Lista tutti i mutui", include_in_schema=False)
async def get_mutui(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
):
    """
    Restituisce la lista di tutti i mutui con statistiche aggregate
    """
    try:
        db = get_db()
        
        # Query mutui
        mutui = await db.mutui.find().skip(skip).limit(limit).to_list(length=limit)
        
        # Serializza
        mutui = [serialize_doc(m) for m in mutui]
        
        # Conta totale
        total_count = await db.mutui.count_documents({})
        
        # Calcola statistiche aggregate
        stats = {
            "totale_mutui": total_count,
            "importo_totale_accordato": 0.0,
            "debito_residuo_totale": 0.0,
            "totale_pagato": 0.0,
            "rate_totali": 0,
            "rate_pagate": 0,
            "rate_da_pagare": 0
        }
        
        for mutuo in mutui:
            stats["importo_totale_accordato"] += mutuo.get("importo_accordato", 0)
            stats["debito_residuo_totale"] += mutuo.get("debito_residuo_totale", 0)
            stats["totale_pagato"] += mutuo.get("totale_pagato", 0)
            stats["rate_totali"] += mutuo.get("totale_rate", 0)
            stats["rate_pagate"] += mutuo.get("rate_pagate", 0)
            stats["rate_da_pagare"] += mutuo.get("rate_da_pagare", 0)
        
        return {
            "success": True,
            "data": mutui,
            "pagination": {
                "skip": skip,
                "limit": limit,
                "total": total_count
            },
            "statistiche": stats
        }
        
    except Exception as e:
        logger.error(f"Errore get_mutui: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistiche/dashboard", summary="Statistiche per dashboard")
async def get_statistiche_mutui():
    """
    Restituisce statistiche aggregate per la dashboard
    """
    try:
        db = get_db()
        
        # Aggrega dati da tutti i mutui
        pipeline = [
            {
                "$group": {
                    "_id": None,
                    "numero_mutui": {"$sum": 1},
                    "importo_totale_accordato": {"$sum": "$importo_accordato"},
                    "debito_residuo_totale": {"$sum": "$debito_residuo_totale"},
                    "totale_pagato_capitale": {"$sum": "$totale_pagato_capitale"},
                    "totale_pagato_interessi": {"$sum": "$totale_pagato_interessi"},
                    "totale_pagato": {"$sum": "$totale_pagato"},
                    "rate_totali": {"$sum": "$totale_rate"},
                    "rate_pagate": {"$sum": "$rate_pagate"},
                    "rate_da_pagare": {"$sum": "$rate_da_pagare"},
                    "rate_riconciliate": {"$sum": "$rate_riconciliate"},
                }
            }
        ]
        
        result = await db.mutui.aggregate(pipeline).to_list(length=1)
        
        if not result:
            return {
                "success": True,
                "data": {
                    "numero_mutui": 0,
                    "importo_totale_accordato": 0,
                    "debito_residuo_totale": 0,
                    "totale_pagato": 0,
                    "percentuale_completamento": 0,
                    "percentuale_riconciliazione": 0,
                    "prossime_scadenze": []
                }
            }
        
        stats = result[0]
        stats.pop("_id", None)
        
        # Calcola percentuali
        if stats["importo_totale_accordato"] > 0:
            stats["percentuale_completamento"] = round(
                (stats["totale_pagato_capitale"] / stats["importo_totale_accordato"]) * 100, 2
            )
        else:
            stats["percentuale_completamento"] = 0
        
        if stats["rate_pagate"] > 0:
            stats["percentuale_riconciliazione"] = round(
                (stats.get("rate_riconciliate", 0) / stats["rate_pagate"]) * 100, 2
            )
        else:
            stats["percentuale_riconciliazione"] = 0
        
        # Trova prossime scadenze (prossimi 30 giorni)
        oggi = datetime.now(timezone.utc)
        
        # Query per rate "Da pagare"
        mutui_con_scadenze = await db.mutui.find(
            {"rate.stato": "Da pagare"},
            {"mutuo_id": 1, "nome": 1, "rate": 1}
        ).to_list(length=100)
        
        prossime_scadenze = []
        for mutuo in mutui_con_scadenze:
            for rata in mutuo.get("rate", []):
                if rata.get("stato") == "Da pagare":
                    try:
                        data_scad = datetime.strptime(rata["data_scadenza"], "%d/%m/%Y")
                        if data_scad >= oggi and data_scad <= oggi + timedelta(days=30):
                            prossime_scadenze.append({
                                "mutuo_id": mutuo["mutuo_id"],
                                "nome": mutuo.get("nome"),
                                "numero_rata": rata["numero_rata"],
                                "data_scadenza": rata["data_scadenza"],
                                "importo_totale": rata["importo_totale"]
                            })
                    except Exception:
                        pass
        
        # Ordina per data
        prossime_scadenze.sort(key=lambda x: datetime.strptime(x["data_scadenza"], "%d/%m/%Y"))
        stats["prossime_scadenze"] = prossime_scadenze[:10]
        
        return {
            "success": True,
            "data": stats
        }
        
    except Exception as e:
        logger.error(f"Errore get_statistiche_mutui: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{mutuo_id}", summary="Dettaglio mutuo")
async def get_mutuo_by_id(mutuo_id: str):
    """
    Restituisce il dettaglio completo di un mutuo incluse tutte le rate
    """
    try:
        db = get_db()
        
        mutuo = await db.mutui.find_one({"mutuo_id": mutuo_id})
        
        if not mutuo:
            raise HTTPException(
                status_code=404,
                detail=f"Mutuo {mutuo_id} non trovato"
            )
        
        return {
            "success": True,
            "data": serialize_doc(mutuo)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore get_mutuo_by_id: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{mutuo_id}/rate", summary="Rate del mutuo")
async def get_rate_mutuo(mutuo_id: str):
    """
    Restituisce tutte le rate di un mutuo specifico
    """
    try:
        db = get_db()
        
        mutuo = await db.mutui.find_one(
            {"mutuo_id": mutuo_id},
            {"rate": 1, "nome": 1, "mutuo_id": 1}
        )
        
        if not mutuo:
            raise HTTPException(
                status_code=404,
                detail=f"Mutuo {mutuo_id} non trovato"
            )
        
        return {
            "success": True,
            "data": {
                "mutuo_id": mutuo["mutuo_id"],
                "nome": mutuo.get("nome"),
                "rate": mutuo.get("rate", [])
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore get_rate_mutuo: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# RICONCILIAZIONE CON ESTRATTO CONTO
# ============================================================================

@router.post("/riconcilia", summary="Riconcilia rate mutui con estratto conto")
async def riconcilia_mutui_con_estratto_conto(
    data_inizio: Optional[str] = None,
    data_fine: Optional[str] = None,
    tolleranza_importo: float = 1.0,
    tolleranza_giorni: int = 7
):
    """
    Riconcilia automaticamente le rate dei mutui con i movimenti bancari
    
    Parametri:
    - data_inizio: data inizio ricerca (DD/MM/YYYY)
    - data_fine: data fine ricerca (DD/MM/YYYY)
    - tolleranza_importo: tolleranza in € per match importo
    - tolleranza_giorni: tolleranza in giorni per match data
    """
    try:
        db = get_db()
        
        # Query per mutui con rate pagate non ancora riconciliate
        mutui = await db.mutui.find({}).to_list(length=None)
        
        riconciliazioni = {
            "totale_rate_processate": 0,
            "riconciliazioni_automatiche": 0,
            "riconciliazioni_manuali_richieste": 0,
            "dettagli": []
        }
        
        for mutuo in mutui:
            mutuo_id = mutuo["mutuo_id"]
            
            for rata in mutuo.get("rate", []):
                if rata["stato"] != "Pagata" or rata.get("riconciliata", False):
                    continue
                
                riconciliazioni["totale_rate_processate"] += 1
                
                # Cerca movimento bancario corrispondente
                try:
                    data_rata = datetime.strptime(rata["data_scadenza"], "%d/%m/%Y")
                except Exception:
                    continue
                    
                data_min = (data_rata - timedelta(days=tolleranza_giorni)).strftime("%Y-%m-%d")
                data_max = (data_rata + timedelta(days=tolleranza_giorni)).strftime("%Y-%m-%d")
                
                importo_min = rata["importo_totale"] - tolleranza_importo
                importo_max = rata["importo_totale"] + tolleranza_importo
                
                # Query movimenti bancari (cerco uscite con importo negativo corrispondente)
                # Match su importo e data (senza filtro descrizione per maggiore precisione)
                query_movimenti = {
                    "data": {"$gte": data_min, "$lte": data_max},
                    "importo": {"$gte": -importo_max, "$lte": -importo_min},
                    "riconciliato": {"$ne": True}
                }
                
                movimento = await db.estratto_conto_movimenti.find_one(query_movimenti)
                
                if movimento:
                    # MATCH TROVATO - Riconcilia automaticamente
                    movimento_id = str(movimento["_id"])
                    data_movimento = movimento.get("data_valuta") or movimento.get("data", "")
                    
                    # Aggiorna rata nel mutuo
                    await db.mutui.update_one(
                        {
                            "mutuo_id": mutuo_id,
                            "rate.numero_rata": rata["numero_rata"]
                        },
                        {
                            "$set": {
                                "rate.$.riconciliata": True,
                                "rate.$.movimento_bancario_id": movimento_id,
                                "rate.$.data_pagamento_effettivo": data_movimento,
                                "rate.$.note_riconciliazione": "Riconciliazione automatica"
                            },
                            "$inc": {
                                "rate_riconciliate": 1
                            }
                        }
                    )
                    
                    # Marca movimento come riconciliato
                    await db.estratto_conto_movimenti.update_one(
                        {"_id": movimento["_id"]},
                        {
                            "$set": {
                                "riconciliato": True,
                                "tipo_documento": "mutuo",
                                "documento_id": mutuo_id,
                                "rata_numero": rata["numero_rata"]
                            }
                        }
                    )
                    
                    riconciliazioni["riconciliazioni_automatiche"] += 1
                    riconciliazioni["dettagli"].append({
                        "mutuo_id": mutuo_id,
                        "mutuo_nome": mutuo.get("nome"),
                        "rata_numero": rata["numero_rata"],
                        "data_scadenza": rata["data_scadenza"],
                        "importo": rata["importo_totale"],
                        "movimento_id": movimento_id,
                        "data_movimento": data_movimento,
                        "status": "riconciliato_automaticamente"
                    })
                    
                    # G2: Crea movimento prima_nota_banca per la rata pagata
                    try:
                        mov_mutuo = {
                            "id": str(uuid.uuid4()),
                            "tipo": "uscita",
                            "importo": rata["importo_totale"],
                            "data": data_movimento,
                            "descrizione": (f"Rata mutuo {mutuo.get('nome', mutuo_id)} n.{rata['numero_rata']} "
                                            f"(cap: {rata.get('quota_capitale', 0):.2f} | "
                                            f"int: {rata.get('quota_interessi', 0):.2f})"),
                            "categoria": "Rata mutuo",
                            "source": "mutuo_rata",
                            "mutuo_id": mutuo_id,
                            "rata_numero": rata["numero_rata"],
                            "quota_capitale": rata.get("quota_capitale", 0),
                            "quota_interessi": rata.get("quota_interessi", 0),
                            "riconciliato": True,
                            "anno": int(data_movimento[:4]) if data_movimento else datetime.now().year,
                            "created_at": datetime.now(timezone.utc).isoformat()
                        }
                        await db["prima_nota_banca"].insert_one(mov_mutuo.copy())
                        await db.mutui.update_one(
                            {"mutuo_id": mutuo_id, "rate.numero_rata": rata["numero_rata"]},
                            {"$set": {"rate.$.prima_nota_banca_id": mov_mutuo["id"]}}
                        )
                    except Exception as e_mutuo:
                        logger.warning(f"Prima nota mutuo fallita: {e_mutuo}")
                    
                else:
                    # Nessun match - richiede riconciliazione manuale
                    riconciliazioni["riconciliazioni_manuali_richieste"] += 1
                    riconciliazioni["dettagli"].append({
                        "mutuo_id": mutuo_id,
                        "mutuo_nome": mutuo.get("nome"),
                        "rata_numero": rata["numero_rata"],
                        "data_scadenza": rata["data_scadenza"],
                        "importo": rata["importo_totale"],
                        "status": "richiede_riconciliazione_manuale"
                    })
        
        # Ricalcola percentuali riconciliazione per ogni mutuo
        async for mutuo in db.mutui.find():
            rate_pagate = mutuo.get("rate_pagate", 0)
            rate_riconciliate = sum(1 for r in mutuo.get("rate", []) if r.get("riconciliata"))
            
            if rate_pagate > 0:
                perc = round((rate_riconciliate / rate_pagate) * 100, 2)
            else:
                perc = 0
                
            await db.mutui.update_one(
                {"mutuo_id": mutuo["mutuo_id"]},
                {"$set": {
                    "rate_riconciliate": rate_riconciliate,
                    "percentuale_riconciliazione": perc
                }}
            )
        
        return {
            "success": True,
            "message": "Riconciliazione completata",
            "data": riconciliazioni
        }
        
    except Exception as e:
        logger.error(f"Errore riconcilia_mutui: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{mutuo_id}/rate/{numero_rata}/riconcilia", summary="Riconcilia singola rata manualmente")
async def riconcilia_rata_manuale(
    mutuo_id: str,
    numero_rata: int,
    movimento_id: str,
    note: Optional[str] = None
):
    """
    Riconcilia manualmente una specifica rata con un movimento bancario
    """
    try:
        db = get_db()
        
        # Verifica esistenza movimento
        try:
            movimento = await db.estratto_conto_movimenti.find_one({"_id": ObjectId(movimento_id)})
        except Exception:
            movimento = await db.estratto_conto_movimenti.find_one({"id": movimento_id})
            
        if not movimento:
            raise HTTPException(status_code=404, detail="Movimento bancario non trovato")
        
        data_movimento = movimento.get("data_valuta") or movimento.get("data", "")
        
        # Aggiorna rata
        result = await db.mutui.update_one(
            {
                "mutuo_id": mutuo_id,
                "rate.numero_rata": numero_rata
            },
            {
                "$set": {
                    "rate.$.riconciliata": True,
                    "rate.$.movimento_bancario_id": movimento_id,
                    "rate.$.data_pagamento_effettivo": data_movimento,
                    "rate.$.note_riconciliazione": note or "Riconciliazione manuale"
                },
                "$inc": {
                    "rate_riconciliate": 1
                }
            }
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="Rata non trovata o già riconciliata")
        
        # Marca movimento come riconciliato
        await db.estratto_conto_movimenti.update_one(
            {"_id": movimento["_id"]},
            {
                "$set": {
                    "riconciliato": True,
                    "tipo_documento": "mutuo",
                    "documento_id": mutuo_id,
                    "rata_numero": numero_rata
                }
            }
        )
        
        # Ricalcola percentuale
        mutuo = await db.mutui.find_one({"mutuo_id": mutuo_id})
        if mutuo:
            rate_pagate = mutuo.get("rate_pagate", 0)
            rate_riconciliate = sum(1 for r in mutuo.get("rate", []) if r.get("riconciliata"))
            perc = round((rate_riconciliate / rate_pagate) * 100, 2) if rate_pagate > 0 else 0
            
            await db.mutui.update_one(
                {"mutuo_id": mutuo_id},
                {"$set": {
                    "rate_riconciliate": rate_riconciliate,
                    "percentuale_riconciliazione": perc
                }}
            )
        
        return {
            "success": True,
            "message": "Rata riconciliata manualmente"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore riconcilia_rata_manuale: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# CRUD OPERAZIONI
# ============================================================================

@router.post("/", summary="Crea nuovo mutuo", status_code=status.HTTP_201_CREATED)
async def create_mutuo(mutuo_data: dict):
    """
    Crea un nuovo mutuo nel database
    """
    try:
        db = get_db()
        
        # Verifica che mutuo_id non esista già
        existing = await db.mutui.find_one({"mutuo_id": mutuo_data.get("mutuo_id")})
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Mutuo con ID {mutuo_data.get('mutuo_id')} già esistente"
            )
        
        # Aggiungi timestamp
        mutuo_data["created_at"] = datetime.now(timezone.utc)
        mutuo_data["updated_at"] = datetime.now(timezone.utc)
        
        result = await db.mutui.insert_one(mutuo_data)
        
        return {
            "success": True,
            "message": "Mutuo creato con successo",
            "mutuo_id": mutuo_data["mutuo_id"],
            "id": str(result.inserted_id)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore create_mutuo: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{mutuo_id}", summary="Aggiorna mutuo")
async def update_mutuo(mutuo_id: str, update_data: dict):
    """
    Aggiorna i dati di un mutuo esistente
    """
    try:
        db = get_db()
        
        # Rimuovi campi che non devono essere aggiornati
        update_data.pop("_id", None)
        update_data.pop("mutuo_id", None)
        update_data.pop("created_at", None)
        
        # Aggiungi timestamp aggiornamento
        update_data["updated_at"] = datetime.now(timezone.utc)
        
        result = await db.mutui.update_one(
            {"mutuo_id": mutuo_id},
            {"$set": update_data}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail=f"Mutuo {mutuo_id} non trovato")
        
        return {
            "success": True,
            "message": "Mutuo aggiornato con successo"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore update_mutuo: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{mutuo_id}", summary="Elimina mutuo")
async def delete_mutuo(mutuo_id: str):
    """
    Elimina un mutuo dal database
    """
    try:
        db = get_db()
        
        result = await db.mutui.delete_one({"mutuo_id": mutuo_id})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail=f"Mutuo {mutuo_id} non trovato")
        
        return {
            "success": True,
            "message": "Mutuo eliminato con successo"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore delete_mutuo: {e}")
        raise HTTPException(status_code=500, detail=str(e))



