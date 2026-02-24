"""
Router PagoPA - Associazione ricevute PagoPA con movimenti estratto conto.

Logica:
1. Le ricevute PagoPA contengono un "Identificativo bolletta" (es. 180071110618697515)
2. I movimenti estratto conto contengono lo stesso codice nella descrizione (CBILL xxxxxxx)
3. Associamo automaticamente ricevuta <-> movimento usando questo codice
"""
from fastapi import APIRouter, HTTPException, UploadFile, File
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import uuid
import logging
import re

from app.database import Database
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/pagopa", tags=["PagoPA"])

# Collection per ricevute PagoPA
COLLECTION_RICEVUTE = "ricevute_pagopa"


@router.get("/ricevute")
@handle_errors
async def list_ricevute(
    anno: int = None,
    associata: bool = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Lista ricevute PagoPA caricate."""
    db = Database.get_db()
    
    query = {}
    if anno:
        query["data_pagamento"] = {"$regex": f"^{anno}"}
    if associata is not None:
        if associata:
            query["movimento_id"] = {"$exists": True, "$ne": None}
        else:
            query["movimento_id"] = {"$in": [None, ""]}
    
    ricevute = await db[COLLECTION_RICEVUTE].find(
        query, {"_id": 0}
    ).sort("data_pagamento", -1).limit(limit).to_list(limit)
    
    return ricevute


@router.post("/ricevute/upload")
@handle_errors
async def upload_ricevuta(
    file: UploadFile = File(...),
    importo: float = None,
    data_pagamento: str = None,
    identificativo_bolletta: str = None,
    beneficiario: str = None,
    note: str = None
) -> Dict[str, Any]:
    """
    Carica una ricevuta PagoPA e cerca automaticamente il movimento corrispondente.
    
    Parametri opzionali se non si riesce a parsare il PDF:
    - importo: importo pagato
    - data_pagamento: data nel formato YYYY-MM-DD
    - identificativo_bolletta: codice univoco (es. 180071110618697515)
    - beneficiario: es. "AGENZIA DELLE ENTRATE - RISCOSSIONE"
    """
    db = Database.get_db()
    
    # Salva file
    content = await file.read()
    
    ricevuta_id = str(uuid.uuid4())
    ricevuta = {
        "id": ricevuta_id,
        "filename": file.filename,
        "content_type": file.content_type,
        "size": len(content),
        "importo": importo,
        "data_pagamento": data_pagamento,
        "identificativo_bolletta": identificativo_bolletta,
        "beneficiario": beneficiario or "AGENZIA DELLE ENTRATE - RISCOSSIONE",
        "note": note,
        "movimento_id": None,
        "associazione_automatica": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Se abbiamo l'identificativo bolletta, cerca il movimento
    if identificativo_bolletta:
        movimento = await cerca_movimento_per_bolletta(db, identificativo_bolletta)
        if movimento:
            ricevuta["movimento_id"] = movimento.get("id")
            ricevuta["associazione_automatica"] = True
            ricevuta["movimento_data"] = movimento.get("data")
            ricevuta["movimento_importo"] = movimento.get("importo")
            
            # Aggiorna anche il movimento con riferimento alla ricevuta
            await db.estratto_conto_movimenti.update_one(
                {"id": movimento["id"]},
                {"$set": {
                    "ricevuta_pagopa_id": ricevuta_id,
                    "ricevuta_filename": file.filename,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
    
    await db[COLLECTION_RICEVUTE].insert_one(ricevuta)
    
    return {
        "id": ricevuta_id,
        "filename": file.filename,
        "associata": ricevuta["movimento_id"] is not None,
        "movimento_id": ricevuta["movimento_id"],
        "movimento_importo": ricevuta.get("movimento_importo")
    }


@router.post("/ricevute/associa-manuale")
@handle_errors
async def associa_manuale(data: Dict[str, Any]) -> Dict[str, Any]:
    """Associa manualmente una ricevuta a un movimento."""
    db = Database.get_db()
    
    ricevuta_id = data.get("ricevuta_id")
    movimento_id = data.get("movimento_id")
    
    if not ricevuta_id or not movimento_id:
        raise HTTPException(status_code=400, detail="ricevuta_id e movimento_id sono obbligatori")
    
    # Aggiorna ricevuta
    result = await db[COLLECTION_RICEVUTE].update_one(
        {"id": ricevuta_id},
        {"$set": {
            "movimento_id": movimento_id,
            "associazione_automatica": False,
            "associazione_manuale": True,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Ricevuta non trovata")
    
    # Aggiorna movimento
    await db.estratto_conto_movimenti.update_one(
        {"id": movimento_id},
        {"$set": {
            "ricevuta_pagopa_id": ricevuta_id,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {"success": True, "ricevuta_id": ricevuta_id, "movimento_id": movimento_id}


@router.post("/auto-associa")
@handle_errors
async def auto_associa_ricevute() -> Dict[str, Any]:
    """
    LOGICA INTELLIGENTE: Cerca e associa automaticamente tutte le ricevute PagoPA
    non ancora associate con i movimenti dell'estratto conto.
    
    Usa l'identificativo bolletta (codice CBILL) per il match.
    """
    db = Database.get_db()
    
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ricevute_analizzate": 0,
        "associazioni_trovate": 0,
        "gia_associate": 0,
        "non_trovate": [],
        "errori": []
    }
    
    # Trova ricevute non associate
    ricevute = await db[COLLECTION_RICEVUTE].find({
        "$or": [
            {"movimento_id": None},
            {"movimento_id": ""},
            {"movimento_id": {"$exists": False}}
        ],
        "identificativo_bolletta": {"$exists": True, "$ne": None}
    }, {"_id": 0}).to_list(1000)
    
    risultati["ricevute_analizzate"] = len(ricevute)
    
    for ricevuta in ricevute:
        cod_bolletta = ricevuta.get("identificativo_bolletta")
        if not cod_bolletta:
            continue
        
        movimento = await cerca_movimento_per_bolletta(db, cod_bolletta)
        
        if movimento:
            try:
                # Associa
                await db[COLLECTION_RICEVUTE].update_one(
                    {"id": ricevuta["id"]},
                    {"$set": {
                        "movimento_id": movimento["id"],
                        "movimento_data": movimento.get("data"),
                        "movimento_importo": movimento.get("importo"),
                        "associazione_automatica": True,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                
                await db.estratto_conto_movimenti.update_one(
                    {"id": movimento["id"]},
                    {"$set": {
                        "ricevuta_pagopa_id": ricevuta["id"],
                        "ricevuta_filename": ricevuta.get("filename"),
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                
                risultati["associazioni_trovate"] += 1
            except Exception as e:
                risultati["errori"].append(f"Errore {ricevuta['id']}: {str(e)}")
        else:
            risultati["non_trovate"].append({
                "ricevuta_id": ricevuta["id"],
                "codice_bolletta": cod_bolletta
            })
    
    return risultati


@router.post("/cerca-movimenti-pagopa")
@handle_errors
async def cerca_movimenti_pagopa(
    anno: int = None,
    solo_non_associati: bool = True
) -> Dict[str, Any]:
    """
    Cerca tutti i movimenti PagoPA/CBILL nell'estratto conto.
    Utile per vedere quali pagamenti Agenzia Entrate - Riscossione esistono.
    """
    db = Database.get_db()
    
    query = {
        "$or": [
            {"descrizione_originale": {"$regex": "CBILL|PAGOPA|AGENZIA.DELLE.ENTRATE.*R|RISCOSSIONE", "$options": "i"}},
            {"descrizione": {"$regex": "CBILL|PAGOPA|AGENZIA.DELLE.ENTRATE.*R|RISCOSSIONE", "$options": "i"}}
        ]
    }
    
    if anno:
        query["data"] = {"$regex": f"^{anno}"}
    
    if solo_non_associati:
        query["ricevuta_pagopa_id"] = {"$in": [None, ""]}
    
    movimenti = await db.estratto_conto_movimenti.find(
        query, {"_id": 0}
    ).sort("data", -1).to_list(500)
    
    # Estrai codice bolletta da ogni movimento
    for mov in movimenti:
        desc = mov.get("descrizione_originale") or mov.get("descrizione") or ""
        # Pattern: CBILL seguito da numeri (15-18 cifre)
        match = re.search(r"CBILL\s*(\d{15,18})", desc)
        if match:
            mov["codice_bolletta_estratto"] = match.group(1)
    
    # Raggruppa per beneficiario
    beneficiari = {}
    for mov in movimenti:
        desc = mov.get("descrizione_originale") or ""
        if "AGENZIA DELLE ENTRATE" in desc.upper():
            ben = "Agenzia delle Entrate - Riscossione"
        elif "INPS" in desc.upper():
            ben = "INPS"
        elif "INAIL" in desc.upper():
            ben = "INAIL"
        else:
            ben = "Altro Ente"
        
        if ben not in beneficiari:
            beneficiari[ben] = {"count": 0, "totale": 0}
        beneficiari[ben]["count"] += 1
        beneficiari[ben]["totale"] += abs(mov.get("importo", 0))
    
    return {
        "movimenti": movimenti,
        "totale": len(movimenti),
        "per_beneficiario": beneficiari
    }


@router.get("/stats")
@handle_errors
async def stats_pagopa(anno: int = None) -> Dict[str, Any]:
    """Statistiche PagoPA."""
    db = Database.get_db()
    
    query_mov = {
        "descrizione_originale": {"$regex": "CBILL|PAGOPA|AGENZIA.DELLE.ENTRATE.*R", "$options": "i"}
    }
    if anno:
        query_mov["data"] = {"$regex": f"^{anno}"}
    
    # Movimenti PagoPA totali
    tot_movimenti = await db.estratto_conto_movimenti.count_documents(query_mov)
    
    # Movimenti con ricevuta
    query_mov["ricevuta_pagopa_id"] = {"$exists": True, "$ne": None}
    con_ricevuta = await db.estratto_conto_movimenti.count_documents(query_mov)
    
    # Ricevute caricate
    query_ric = {}
    if anno:
        query_ric["data_pagamento"] = {"$regex": f"^{anno}"}
    tot_ricevute = await db[COLLECTION_RICEVUTE].count_documents(query_ric)
    
    query_ric["movimento_id"] = {"$exists": True, "$ne": None}
    ricevute_associate = await db[COLLECTION_RICEVUTE].count_documents(query_ric)
    
    # Totale importi
    pipeline = [
        {"$match": {
            "descrizione_originale": {"$regex": "CBILL|AGENZIA.DELLE.ENTRATE.*R", "$options": "i"},
            **({"data": {"$regex": f"^{anno}"}} if anno else {})
        }},
        {"$group": {"_id": None, "totale": {"$sum": {"$abs": "$importo"}}}}
    ]
    agg = await db.estratto_conto_movimenti.aggregate(pipeline).to_list(1)
    totale_importi = agg[0]["totale"] if agg else 0
    
    return {
        "anno": anno or "tutti",
        "movimenti_pagopa": tot_movimenti,
        "movimenti_con_ricevuta": con_ricevuta,
        "movimenti_senza_ricevuta": tot_movimenti - con_ricevuta,
        "ricevute_caricate": tot_ricevute,
        "ricevute_associate": ricevute_associate,
        "totale_pagato": round(totale_importi, 2)
    }


async def cerca_movimento_per_bolletta(db, codice_bolletta: str) -> Optional[Dict[str, Any]]:
    """
    Cerca un movimento nell'estratto conto usando il codice bolletta.
    Il codice appare nella descrizione come "CBILL 180071110618697515"
    """
    if not codice_bolletta:
        return None
    
    # Cerca il codice nella descrizione
    movimento = await db.estratto_conto_movimenti.find_one({
        "$or": [
            {"descrizione_originale": {"$regex": codice_bolletta}},
            {"descrizione": {"$regex": codice_bolletta}}
        ]
    }, {"_id": 0})
    
    return movimento


# Alias per compatibilità
@router.get("/movimenti-agenzia-entrate")
@handle_errors
async def movimenti_agenzia_entrate(anno: int = None) -> Dict[str, Any]:
    """
    Lista movimenti Agenzia delle Entrate - Riscossione.
    Rinomina ADER -> Agenzia delle Entrate - Riscossione
    """
    return await cerca_movimenti_pagopa(anno=anno, solo_non_associati=False)
