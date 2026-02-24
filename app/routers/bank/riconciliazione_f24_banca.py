"""
Router per Riconciliazione F24 con Estratto Conto Bancario
Supporta formato Banco BPM

NOTA: Questo router è registrato con prefix /api/f24-riconciliazione
insieme a f24_riconciliazione.py per gli endpoint banca-specifici.
"""
from fastapi import APIRouter, UploadFile, File, HTTPException
from typing import Optional
from datetime import datetime, timezone
import logging

from app.database import Database
from app.db_collections import (
    COLL_ESTRATTO_CONTO,
    COLL_F24_COMMERCIALISTA,
    QUERY_F24_PATTERN
)
from app.services.estratto_conto_bpm_parser import (
    parse_estratto_conto_bpm,
    riconcilia_f24_con_estratto,
    genera_report_riconciliazione
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/upload-estratto-bpm")
async def upload_estratto_conto_bpm(file: UploadFile = File(...)):
    """
    Carica e parsa un estratto conto Banco BPM (formato CSV).
    Identifica automaticamente i pagamenti F24.
    """
    if not file.filename.endswith(('.csv', '.CSV')):
        raise HTTPException(status_code=400, detail="Il file deve essere in formato CSV")
    
    try:
        content = await file.read()
        # Prova diverse codifiche
        for encoding in ['utf-8', 'latin-1', 'cp1252']:
            try:
                text_content = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise HTTPException(status_code=400, detail="Impossibile decodificare il file")
        
        # Parsa estratto conto
        result = parse_estratto_conto_bpm(text_content)
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        # Salva nel database
        db = Database.get_db()
        documento = {
            "file_name": file.filename,
            "upload_date": datetime.now(timezone.utc),
            "banca": "BANCO BPM",
            "formato": "CSV",
            "conto": result.get("conto", {}),
            "periodo": result.get("periodo", {}),
            "totale_movimenti": result["stats"]["totale_movimenti"],
            "totale_movimenti_f24": result["stats"]["movimenti_f24"],
            "totale_entrate": result["totale_entrate"],
            "totale_uscite": result["totale_uscite"],
            "saldo": result["saldo"],
            "categorie": result["stats"]["categorie"]
        }
        
        await db["estratti_conto"].insert_one(documento.copy())
        
        # Salva movimenti F24 per riconciliazione futura
        if result["movimenti_f24"]:
            for mov in result["movimenti_f24"]:
                mov["estratto_file"] = file.filename
                mov["upload_date"] = datetime.now(timezone.utc)
            await db["movimenti_f24_banca"].insert_many(result["movimenti_f24"])
        
        return {
            "success": True,
            "message": f"Estratto conto caricato: {result['stats']['totale_movimenti']} movimenti",
            "file_name": file.filename,
            "periodo": result["periodo"],
            "conto": result["conto"],
            "stats": {
                "totale_movimenti": result["stats"]["totale_movimenti"],
                "movimenti_f24": result["stats"]["movimenti_f24"],
                "totale_entrate": result["totale_entrate"],
                "totale_uscite": result["totale_uscite"],
                "saldo": result["saldo"]
            },
            "categorie_principali": dict(sorted(
                result["stats"]["categorie"].items(),
                key=lambda x: x[1],
                reverse=True
            )[:10])
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore upload estratto conto: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/movimenti-f24-banca")
async def get_movimenti_f24_banca(
    data_da: Optional[str] = None,
    data_a: Optional[str] = None,
    limit: int = 100
):
    """
    Recupera i movimenti F24 identificati negli estratti conto.
    Cerca nella collezione estratto_conto_movimenti i movimenti con pattern F24
    (I24 AGENZIA ENTRATE, AGENZIA DELLE ENTRATE, etc.)
    """
    db = Database.get_db()
    
    # Usa query pattern centralizzata
    query = QUERY_F24_PATTERN.copy()
    
    # Filtri opzionali per data
    if data_da or data_a:
        date_filter = {}
        if data_da:
            date_filter["$gte"] = data_da
        if data_a:
            date_filter["$lte"] = data_a
        query["data"] = date_filter
    
    movimenti = await db[COLL_ESTRATTO_CONTO].find(
        query,
        {"_id": 0}
    ).sort("data", -1).limit(limit).to_list(limit)
    
    # Calcola totale (in valore assoluto perché sono uscite negative)
    totale = sum(abs(m.get("importo", 0)) for m in movimenti)
    
    return {
        "movimenti": movimenti,
        "count": len(movimenti),
        "totale": round(totale, 2)
    }


@router.post("/riconcilia-f24")
async def riconcilia_f24_con_banca():
    """
    Esegue la riconciliazione tra F24 caricati e movimenti F24 dell'estratto conto.
    
    Confronta:
    - F24 commercialista caricati
    - Movimenti "I24 AGENZIA ENTRATE" dall'estratto conto
    
    Matching basato su importo e data (±3 giorni).
    """
    db = Database.get_db()
    
    try:
        # Recupera F24 commercialista
        f24_list = await db[COLL_F24_COMMERCIALISTA].find(
            {},
            {"_id": 0}
        ).to_list(1000)
        
        # Recupera movimenti F24 dalla collezione estratto_conto_movimenti
        movimenti_f24 = await db[COLL_ESTRATTO_CONTO].find(
            QUERY_F24_PATTERN,
            {"_id": 0}
        ).to_list(1000)
        
        if not f24_list:
            return {
                "success": False,
                "message": "Nessun F24 commercialista caricato",
                "suggerimento": "Carica prima i PDF degli F24 tramite /api/f24-riconciliazione/commercialista/upload"
            }
        
        if not movimenti_f24:
            return {
                "success": False,
                "message": "Nessun movimento F24 trovato nell'estratto conto bancario",
                "suggerimento": "L'estratto conto non contiene movimenti con pattern 'I24 AGENZIA ENTRATE'"
            }
        
        # Esegui riconciliazione
        result = riconcilia_f24_con_estratto(f24_list, movimenti_f24)
        
        # Aggiorna stato F24 nel database
        for f24_pagato in result["f24_riconciliati"]:
            await db[COLL_F24_COMMERCIALISTA].update_one(
                {"id": f24_pagato.get("id")},
                {"$set": {
                    "stato_pagamento": "PAGATO",
                    "data_pagamento_effettivo": f24_pagato.get("data_pagamento_effettivo"),
                    "movimento_bancario_ref": f24_pagato.get("movimento_bancario", {}).get("f24_info", {}).get("riferimento")
                }}
            )
        
        for f24_non_pagato in result["f24_non_pagati"]:
            await db[COLL_F24_COMMERCIALISTA].update_one(
                {"id": f24_non_pagato.get("id")},
                {"$set": {"stato_pagamento": "DA_PAGARE"}}
            )
        
        # Genera report
        report = genera_report_riconciliazione(result)
        
        return {
            "success": True,
            "message": "Riconciliazione completata",
            "stats": result["stats"],
            "f24_riconciliati": [{
                "id": f.get("id"),
                "file_name": f.get("file_name"),
                "importo": f.get("totali", {}).get("saldo_netto"),
                "data_pagamento": f.get("data_pagamento_effettivo"),
                "stato": "PAGATO"
            } for f in result["f24_riconciliati"]],
            "f24_non_pagati": [{
                "id": f.get("id"),
                "file_name": f.get("file_name"),
                "importo": f.get("totali", {}).get("saldo_netto"),
                "stato": "DA_PAGARE"
            } for f in result["f24_non_pagati"]],
            "movimenti_non_associati": [{
                "data": m.get("data_contabile"),
                "importo": abs(m.get("importo", 0)),
                "descrizione": m.get("descrizione", "")[:100]
            } for m in result["movimenti_non_associati"][:20]],
            "report_testuale": report
        }
        
    except Exception as e:
        logger.error(f"Errore riconciliazione F24: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stato-riconciliazione")
async def get_stato_riconciliazione():
    """
    Restituisce lo stato attuale della riconciliazione F24.
    """
    db = Database.get_db()
    
    # Conta F24 per stato
    # Usa campo "status" (valori: "pagato", "eliminato", altri=non classificati)
    f24_pagati = await db[COLL_F24_COMMERCIALISTA].count_documents({"status": "pagato"})
    f24_totali = await db[COLL_F24_COMMERCIALISTA].count_documents({"status": {"$ne": "eliminato"}})
    f24_da_pagare = f24_totali - f24_pagati
    
    # Conta movimenti F24 in banca
    movimenti_f24 = await db[COLL_ESTRATTO_CONTO].count_documents(QUERY_F24_PATTERN)
    
    # Somma importi
    pipeline_f24 = [
        {"$group": {
            "_id": "$status",
            "totale": {"$sum": "$totali.saldo_netto"}
        }}
    ]
    totali_per_stato = {doc["_id"]: doc["totale"] async for doc in db[COLL_F24_COMMERCIALISTA].aggregate(pipeline_f24)}
    
    # Totale movimenti F24 in banca
    pipeline_banca = [
        {"$match": QUERY_F24_PATTERN},
        {"$group": {
            "_id": None,
            "totale": {"$sum": {"$abs": "$importo"}}
        }}
    ]
    totale_banca = 0
    async for doc in db[COLL_ESTRATTO_CONTO].aggregate(pipeline_banca):
        totale_banca = doc.get("totale", 0)
    
    return {
        "f24": {
            "totali": f24_totali,
            "pagati": f24_pagati,
            "da_pagare": f24_da_pagare,
            "non_classificati": f24_totali - f24_pagati - f24_da_pagare
        },
        "importi": {
            "totale_f24_pagati": round(totali_per_stato.get("pagato", 0), 2),
            "totale_f24_da_pagare": round(sum(v for k, v in totali_per_stato.items() if k not in ("pagato", "eliminato", None)), 2),
            "totale_movimenti_banca": round(totale_banca, 2)
        },
        "movimenti_f24_banca": movimenti_f24,
        "percentuale_riconciliazione": round(f24_pagati / max(f24_totali, 1) * 100, 1)
    }


@router.get("/estratti-conto")
async def get_estratti_conto():
    """
    Lista degli estratti conto caricati.
    """
    db = Database.get_db()
    
    estratti = await db["estratti_conto"].find(
        {},
        {"_id": 0}
    ).sort("upload_date", -1).to_list(100)
    
    return {
        "estratti": estratti,
        "count": len(estratti)
    }
