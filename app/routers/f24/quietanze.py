"""
Router per Gestione Quietanze F24
Upload, parsing e gestione delle quietanze F24 Agenzia delle Entrate
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from app.database import Database
from app.services.f24_parser import parse_quietanza_f24, generate_f24_summary
import os
import uuid
import logging
from app.utils.error_handler import handle_errors

router = APIRouter()
logger = logging.getLogger(__name__)

# DEPRECATED: Directory per compatibilità legacy
UPLOAD_DIR = "/app/uploads/f24"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/upload")
@handle_errors
async def upload_quietanza_f24(
    file: UploadFile = File(...)
) -> Dict[str, Any]:
    """
    Upload e parsing di una quietanza F24 PDF.
    Estrae automaticamente tutti i dati e li salva nel database.
    Architettura MongoDB-only: salva PDF come Base64.
    """
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Il file deve essere un PDF")
    
    # Architettura MongoDB-only: leggi e codifica in Base64
    file_id = str(uuid.uuid4())
    
    try:
        content = await file.read()
        import base64
        pdf_base64 = base64.b64encode(content).decode('utf-8')
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore lettura file: {str(e)}")
    
    # Parsing del PDF con bytes
    try:
        parsed_data = parse_quietanza_f24(pdf_content=content)
    except Exception as e:
        logger.error(f"Errore parsing F24: {e}")
        raise HTTPException(status_code=500, detail=f"Errore parsing PDF: {str(e)}")
    
    if "error" in parsed_data:
        raise HTTPException(status_code=400, detail=parsed_data["error"])
    
    # Prepara documento per MongoDB
    db = Database.get_db()
    
    # Genera chiave univoca per evitare duplicati
    dg = parsed_data.get("dati_generali", {})
    f24_key = f"{dg.get('codice_fiscale', '')}_{dg.get('data_pagamento', '')}_{dg.get('protocollo_telematico', '')}"
    
    # Verifica duplicato
    existing = await db["quietanze_f24"].find_one({"f24_key": f24_key})
    if existing:
        return {
            "success": False,
            "message": "Quietanza già presente nel sistema",
            "existing_id": existing.get("id"),
            "data_pagamento": existing.get("dati_generali", {}).get("data_pagamento")
        }
    
    # Salva nel database con pdf_data (architettura MongoDB-only)
    documento = {
        "id": file_id,
        "f24_key": f24_key,
        "file_name": file.filename,
        "pdf_data": pdf_base64,  # Architettura MongoDB-only
        "dati_generali": parsed_data.get("dati_generali", {}),
        "sezione_erario": parsed_data.get("sezione_erario", []),
        "sezione_inps": parsed_data.get("sezione_inps", []),
        "sezione_inail": parsed_data.get("sezione_inail", []),
        "sezione_regioni": parsed_data.get("sezione_regioni", []),
        "sezione_tributi_locali": parsed_data.get("sezione_tributi_locali", []),
        "totali": parsed_data.get("totali", {}),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db["quietanze_f24"].insert_one(documento.copy())
    
    # Genera riepilogo
    summary = generate_f24_summary(parsed_data)
    
    return {
        "success": True,
        "message": "Quietanza F24 elaborata con successo",
        "id": file_id,
        "file_name": file.filename,
        "dati_generali": parsed_data.get("dati_generali", {}),
        "totali": parsed_data.get("totali", {}),
        "sezioni": {
            "erario": len(parsed_data.get("sezione_erario", [])),
            "inps": len(parsed_data.get("sezione_inps", [])),
            "inail": len(parsed_data.get("sezione_inail", [])),
            "regioni": len(parsed_data.get("sezione_regioni", [])),
            "tributi_locali": len(parsed_data.get("sezione_tributi_locali", []))
        },
        "summary": summary
    }


@router.get("")
@handle_errors
async def list_quietanze_f24(
    skip: int = Query(0),
    limit: int = Query(50),
    anno: Optional[int] = Query(None),
    mese: Optional[int] = Query(None),
    search: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Lista quietanze F24 con filtri."""
    db = Database.get_db()
    
    query = {}
    
    # Filtro per anno
    if anno:
        query["dati_generali.data_pagamento"] = {"$regex": f"^{anno}"}
    
    # Filtro per anno e mese
    if anno and mese:
        mese_str = f"{mese:02d}"
        query["dati_generali.data_pagamento"] = {"$regex": f"^{anno}-{mese_str}"}
    
    # Ricerca testuale
    if search:
        query["$or"] = [
            {"dati_generali.codice_fiscale": {"$regex": search, "$options": "i"}},
            {"dati_generali.ragione_sociale": {"$regex": search, "$options": "i"}},
            {"dati_generali.protocollo_telematico": {"$regex": search, "$options": "i"}}
        ]
    
    # Query con esclusione _id
    quietanze = await db["quietanze_f24"].find(
        query, {"_id": 0}
    ).sort("dati_generali.data_pagamento", -1).skip(skip).limit(limit).to_list(limit)
    
    totale = await db["quietanze_f24"].count_documents(query)
    
    # Statistiche
    stats_pipeline = [
        {"$group": {
            "_id": None,
            "totale_pagato": {"$sum": "$totali.saldo_netto"},
            "totale_debiti": {"$sum": "$totali.totale_debito"},
            "totale_crediti": {"$sum": "$totali.totale_credito"},
            "count": {"$sum": 1}
        }}
    ]
    stats_result = await db["quietanze_f24"].aggregate(stats_pipeline).to_list(1)
    stats = stats_result[0] if stats_result else {}
    
    return {
        "quietanze": quietanze,
        "totale": totale,
        "statistiche": {
            "quietanze_count": stats.get("count", 0),
            "totale_pagato": round(stats.get("totale_pagato", 0), 2),
            "totale_debiti": round(stats.get("totale_debiti", 0), 2),
            "totale_crediti": round(stats.get("totale_crediti", 0), 2)
        }
    }


@router.get("/statistiche/tributi")
@handle_errors
async def statistiche_tributi_quietanze() -> Dict[str, Any]:
    """Statistiche aggregate per tipo di tributo dalle quietanze."""
    db = Database.get_db()
    
    # Tributi Erario
    erario_pipeline = [
        {"$unwind": "$sezione_erario"},
        {"$group": {
            "_id": "$sezione_erario.codice_tributo",
            "totale_debito": {"$sum": "$sezione_erario.importo_debito"},
            "totale_credito": {"$sum": "$sezione_erario.importo_credito"},
            "descrizione": {"$first": "$sezione_erario.descrizione"},
            "count": {"$sum": 1}
        }},
        {"$sort": {"totale_debito": -1}}
    ]
    erario_stats = await db["quietanze_f24"].aggregate(erario_pipeline).to_list(50)
    
    # Contributi INPS
    inps_pipeline = [
        {"$unwind": "$sezione_inps"},
        {"$group": {
            "_id": "$sezione_inps.causale",
            "totale_debito": {"$sum": "$sezione_inps.importo_debito"},
            "descrizione": {"$first": "$sezione_inps.descrizione"},
            "count": {"$sum": 1}
        }},
        {"$sort": {"totale_debito": -1}}
    ]
    inps_stats = await db["quietanze_f24"].aggregate(inps_pipeline).to_list(20)
    
    # Tributi Regionali
    regioni_pipeline = [
        {"$unwind": "$sezione_regioni"},
        {"$group": {
            "_id": "$sezione_regioni.codice_tributo",
            "totale_debito": {"$sum": "$sezione_regioni.importo_debito"},
            "descrizione": {"$first": "$sezione_regioni.descrizione"},
            "count": {"$sum": 1}
        }},
        {"$sort": {"totale_debito": -1}}
    ]
    regioni_stats = await db["quietanze_f24"].aggregate(regioni_pipeline).to_list(20)
    
    return {
        "erario": [{
            "codice": s["_id"], 
            "descrizione": s.get("descrizione", ""),
            "debito": round(s["totale_debito"], 2), 
            "credito": round(s.get("totale_credito", 0), 2), 
            "count": s["count"]
        } for s in erario_stats],
        "inps": [{
            "causale": s["_id"], 
            "descrizione": s.get("descrizione", ""),
            "totale": round(s["totale_debito"], 2), 
            "count": s["count"]
        } for s in inps_stats],
        "regioni": [{
            "codice": s["_id"], 
            "descrizione": s.get("descrizione", ""),
            "totale": round(s["totale_debito"], 2), 
            "count": s["count"]
        } for s in regioni_stats]
    }


@router.get("/statistiche/annuali/{anno}")
@handle_errors
async def statistiche_annuali(anno: int) -> Dict[str, Any]:
    """Statistiche F24 per anno."""
    db = Database.get_db()
    
    query = {"dati_generali.data_pagamento": {"$regex": f"^{anno}"}}
    
    # Totali per mese
    pipeline = [
        {"$match": query},
        {"$addFields": {
            "mese": {"$substr": ["$dati_generali.data_pagamento", 5, 2]}
        }},
        {"$group": {
            "_id": "$mese",
            "totale_pagato": {"$sum": "$totali.saldo_netto"},
            "totale_debiti": {"$sum": "$totali.totale_debito"},
            "totale_crediti": {"$sum": "$totali.totale_credito"},
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]
    
    per_mese = await db["quietanze_f24"].aggregate(pipeline).to_list(12)
    
    # Totale anno
    totale_pipeline = [
        {"$match": query},
        {"$group": {
            "_id": None,
            "totale_pagato": {"$sum": "$totali.saldo_netto"},
            "totale_debiti": {"$sum": "$totali.totale_debito"},
            "totale_crediti": {"$sum": "$totali.totale_credito"},
            "count": {"$sum": 1}
        }}
    ]
    totale_result = await db["quietanze_f24"].aggregate(totale_pipeline).to_list(1)
    totale = totale_result[0] if totale_result else {}
    
    mesi_nomi = ["", "Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]
    
    return {
        "anno": anno,
        "totale_annuo": {
            "pagato": round(totale.get("totale_pagato", 0), 2),
            "debiti": round(totale.get("totale_debiti", 0), 2),
            "crediti": round(totale.get("totale_crediti", 0), 2),
            "quietanze": totale.get("count", 0)
        },
        "per_mese": [{
            "mese": int(m["_id"]) if m["_id"].isdigit() else 0,
            "nome_mese": mesi_nomi[int(m["_id"])] if m["_id"].isdigit() else m["_id"],
            "pagato": round(m["totale_pagato"], 2),
            "debiti": round(m["totale_debiti"], 2),
            "crediti": round(m["totale_crediti"], 2),
            "count": m["count"]
        } for m in per_mese]
    }


@router.get("/{f24_id}")
@handle_errors
async def get_quietanza_f24(f24_id: str) -> Dict[str, Any]:
    """Dettaglio completo di una quietanza F24."""
    db = Database.get_db()
    
    quietanza = await db["quietanze_f24"].find_one({"id": f24_id}, {"_id": 0})
    if not quietanza:
        raise HTTPException(status_code=404, detail="Quietanza non trovata")
    
    # Genera riepilogo
    quietanza["summary"] = generate_f24_summary(quietanza)
    
    return quietanza


@router.delete("/{f24_id}")
@handle_errors
async def delete_quietanza_f24(f24_id: str) -> Dict[str, Any]:
    """
    Elimina una quietanza F24.
    Architettura MongoDB-only: elimina solo dal database.
    """
    db = Database.get_db()
    
    quietanza = await db["quietanze_f24"].find_one({"id": f24_id})
    if not quietanza:
        raise HTTPException(status_code=404, detail="Quietanza non trovata")
    
    # Architettura MongoDB-only: elimina solo dal database
    await db["quietanze_f24"].delete_one({"id": f24_id})
    
    return {
        "success": True,
        "message": "Quietanza eliminata con successo"
    }
