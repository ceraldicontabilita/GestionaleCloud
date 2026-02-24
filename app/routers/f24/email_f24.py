"""
Router Email F24
Gestisce il download automatico email, parsing allegati e inserimento nel sistema
"""
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from app.database import Database
from app.services.email_downloader import download_and_process_emails, get_mittenti_configurati
from app.services.parser_f24 import parse_f24_commercialista
from app.services.f24_parser import parse_quietanza_f24
from app.services.codici_tributo_db import get_info_codice_tributo
import os
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# Credenziali email (da .env in produzione)
EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS", "ceraldigroupsrl@gmail.com")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "okzo nmhl wrnq jlcf")

# Collections
COLL_EMAIL_LOG = "email_download_log"
COLL_ALLEGATI = "email_allegati"
COLL_F24_COMMERCIALISTA = "f24_commercialista"
COLL_QUIETANZE = "quietanze_f24"


@router.post("/scarica-email")
async def scarica_email_allegati(
    giorni: int = Query(30, description="Scarica email degli ultimi N giorni"),
    background_tasks: BackgroundTasks = None
) -> Dict[str, Any]:
    """
    Scarica gli allegati PDF dalle email dei mittenti configurati.
    - Commercialista (rosaria.marotta@email.it): F24 fiscali
    - Consulenti lavoro (ferrantini): F24 contributivi
    """
    db = Database.get_db()
    
    # Download email
    result = await download_and_process_emails(
        email_address=EMAIL_ADDRESS,
        password=EMAIL_PASSWORD,
        since_days=giorni
    )
    
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("errori", ["Errore sconosciuto"]))
    
    # Log del download
    log_entry = {
        "id": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "giorni_cercati": giorni,
        "email_trovate": result.get("totale_email", 0),
        "allegati_scaricati": result.get("totale_allegati", 0),
        "allegati_fiscali": result.get("allegati_fiscali", 0),
        "allegati_contributivi": result.get("allegati_contributivi", 0)
    }
    await db[COLL_EMAIL_LOG].insert_one(log_entry.copy())
    
    # Salva info allegati nel database
    allegati_processati = []
    for allegato in result.get("allegati", []):
        # Verifica se già processato
        existing = await db[COLL_ALLEGATI].find_one({
            "original_filename": allegato["original_filename"],
            "email_date": allegato["email_date"],
            "email_from": allegato["email_from"]
        }, {"_id": 0})
        
        if existing:
            allegato["status"] = "già_presente"
            allegati_processati.append(allegato)
            continue
        
        # Salva nel database
        allegato["status"] = "da_processare"
        allegato["processato"] = False
        allegato_copy = {k: v for k, v in allegato.items()}  # Copia per evitare modifica
        await db[COLL_ALLEGATI].insert_one(allegato_copy.copy())
        allegati_processati.append(allegato)
    
    return {
        "success": True,
        "message": f"Download completato: {result.get('totale_allegati', 0)} allegati da {result.get('totale_email', 0)} email",
        "statistiche": {
            "email_trovate": result.get("totale_email", 0),
            "allegati_totali": result.get("totale_allegati", 0),
            "allegati_fiscali": result.get("allegati_fiscali", 0),
            "allegati_contributivi": result.get("allegati_contributivi", 0)
        },
        "allegati": allegati_processati
    }


@router.post("/processa-allegati")
async def processa_allegati_f24() -> Dict[str, Any]:
    """
    Processa tutti gli allegati PDF scaricati.
    Identifica se sono F24 o quietanze e li inserisce nel sistema appropriato.
    """
    db = Database.get_db()
    
    # Trova allegati da processare
    allegati = await db[COLL_ALLEGATI].find({
        "processato": False,
        "extension": ".pdf"
    }, {"_id": 0}).to_list(100)
    
    risultati = {
        "processati": 0,
        "f24_commercialista": 0,
        "quietanze": 0,
        "errori": 0,
        "dettagli": []
    }
    
    for allegato in allegati:
        # Architettura MongoDB-only: usa pdf_data
        pdf_data = allegato.get("pdf_data")
        if not pdf_data:
            risultati["errori"] += 1
            risultati["dettagli"].append({
                "file": allegato.get("original_filename"),
                "errore": "PDF non disponibile in MongoDB"
            })
            continue
        
        try:
            # Decodifica PDF da Base64
            import base64
            pdf_content = base64.b64decode(pdf_data)
            
            # Determina il tipo di documento basato sul mittente
            categoria = allegato.get("categoria_f24", "generico")
            mittente_tipo = allegato.get("mittente_tipo", "sconosciuto")
            
            # Prova a parsare come F24 commercialista (architettura MongoDB-only: usa bytes)
            parsed_f24 = parse_f24_commercialista(pdf_content=pdf_content)
            
            # Se ha codici tributo, è un F24
            has_tributi = (
                len(parsed_f24.get("sezione_erario", [])) > 0 or
                len(parsed_f24.get("sezione_inps", [])) > 0 or
                len(parsed_f24.get("sezione_regioni", [])) > 0
            )
            
            if has_tributi and "error" not in parsed_f24:
                # È un F24 della commercialista/consulente
                f24_doc = {
                    "id": allegato.get("id"),
                    "file_name": allegato.get("original_filename"),
                    "pdf_data": pdf_data,  # Architettura MongoDB-only
                    "email_from": allegato.get("email_from"),
                    "email_date": allegato.get("email_date"),
                    "mittente_tipo": mittente_tipo,
                    "categoria_f24": categoria,
                    "dati_generali": parsed_f24.get("dati_generali", {}),
                    "sezione_erario": parsed_f24.get("sezione_erario", []),
                    "sezione_inps": parsed_f24.get("sezione_inps", []),
                    "sezione_regioni": parsed_f24.get("sezione_regioni", []),
                    "sezione_tributi_locali": parsed_f24.get("sezione_tributi_locali", []),
                    "totali": parsed_f24.get("totali", {}),
                    "codici_univoci": parsed_f24.get("codici_univoci", []),
                    "has_ravvedimento": parsed_f24.get("has_ravvedimento", False),
                    "status": "da_pagare",
                    "riconciliato": False,
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
                
                await db[COLL_F24_COMMERCIALISTA].insert_one(f24_doc.copy())
                risultati["f24_commercialista"] += 1
                risultati["dettagli"].append({
                    "file": allegato.get("original_filename"),
                    "tipo": "F24",
                    "categoria": categoria,
                    "importo": parsed_f24.get("totali", {}).get("saldo_netto", 0),
                    "codici": len(parsed_f24.get("codici_univoci", []))
                })
            else:
                # Prova come quietanza (architettura MongoDB-only: usa bytes)
                parsed_quietanza = parse_quietanza_f24(pdf_content=pdf_content)
                
                has_quietanza_data = (
                    len(parsed_quietanza.get("sezione_erario", [])) > 0 or
                    len(parsed_quietanza.get("sezione_inps", [])) > 0
                )
                
                if has_quietanza_data and "error" not in parsed_quietanza:
                    quietanza_doc = {
                        "id": allegato.get("id"),
                        "file_name": allegato.get("original_filename"),
                        "pdf_data": pdf_data,  # Architettura MongoDB-only
                        "email_from": allegato.get("email_from"),
                        "dati_generali": parsed_quietanza.get("dati_generali", {}),
                        "sezione_erario": parsed_quietanza.get("sezione_erario", []),
                        "sezione_inps": parsed_quietanza.get("sezione_inps", []),
                        "sezione_regioni": parsed_quietanza.get("sezione_regioni", []),
                        "sezione_tributi_locali": parsed_quietanza.get("sezione_tributi_locali", []),
                        "totali": parsed_quietanza.get("totali", {}),
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }
                    
                    await db[COLL_QUIETANZE].insert_one(quietanza_doc.copy())
                    risultati["quietanze"] += 1
                    risultati["dettagli"].append({
                        "file": allegato.get("original_filename"),
                        "tipo": "Quietanza",
                        "importo": parsed_quietanza.get("totali", {}).get("saldo_netto", 0)
                    })
                else:
                    # Non riconosciuto
                    risultati["errori"] += 1
                    risultati["dettagli"].append({
                        "file": allegato.get("original_filename"),
                        "tipo": "Non riconosciuto",
                        "errore": "Impossibile identificare come F24 o quietanza"
                    })
            
            # Marca come processato
            await db[COLL_ALLEGATI].update_one(
                {"id": allegato.get("id")},
                {"$set": {
                    "processato": True,
                    "processato_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            risultati["processati"] += 1
            
        except Exception as e:
            logger.error(f"Errore processing {allegato.get('original_filename')}: {e}")
            risultati["errori"] += 1
            risultati["dettagli"].append({
                "file": allegato.get("original_filename"),
                "errore": str(e)
            })
    
    return {
        "success": True,
        "message": f"Processati {risultati['processati']} allegati",
        "risultati": risultati
    }


@router.get("/mittenti")
async def get_mittenti() -> Dict[str, Any]:
    """Restituisce i mittenti email configurati."""
    return {
        "mittenti": get_mittenti_configurati(),
        "email_destinatario": EMAIL_ADDRESS
    }


@router.get("/allegati")
async def list_allegati(
    processato: Optional[bool] = Query(None),
    categoria: Optional[str] = Query(None),
    limit: int = Query(50)
) -> Dict[str, Any]:
    """Lista allegati scaricati."""
    db = Database.get_db()
    
    query = {}
    if processato is not None:
        query["processato"] = processato
    if categoria:
        query["categoria_f24"] = categoria
    
    allegati = await db[COLL_ALLEGATI].find(
        query, {"_id": 0}
    ).sort("downloaded_at", -1).limit(limit).to_list(limit)
    
    return {
        "allegati": allegati,
        "totale": len(allegati)
    }


@router.get("/log-download")
async def get_download_log(limit: int = Query(20)) -> Dict[str, Any]:
    """Log degli ultimi download email."""
    db = Database.get_db()
    
    logs = await db[COLL_EMAIL_LOG].find(
        {}, {"_id": 0}
    ).sort("timestamp", -1).limit(limit).to_list(limit)
    
    return {"logs": logs}


@router.get("/codici-tributo")
async def search_codici_tributo(
    codice: Optional[str] = Query(None),
    categoria: Optional[str] = Query(None),
    fonte: Optional[str] = Query(None, description="commercialista o consulente_lavoro")
) -> Dict[str, Any]:
    """
    Cerca informazioni sui codici tributo.
    """
    from app.services.codici_tributo_db import (
        CODICI_TRIBUTO_ERARIO, CODICI_TRIBUTO_INPS, 
        get_codici_per_categoria, get_codici_per_fonte
    )
    
    if codice:
        info = get_info_codice_tributo(codice)
        return {"codice": codice, "info": info}
    
    if categoria:
        codici = get_codici_per_categoria(categoria)
        return {"categoria": categoria, "codici": codici}
    
    if fonte:
        codici = get_codici_per_fonte(fonte)
        return {"fonte": fonte, "codici": codici}
    
    # Restituisci riepilogo
    return {
        "erario": {
            "count": len(CODICI_TRIBUTO_ERARIO),
            "categorie": list(set(v.get("categoria") for v in CODICI_TRIBUTO_ERARIO.values()))
        },
        "inps": {
            "count": len(CODICI_TRIBUTO_INPS),
            "codici": list(CODICI_TRIBUTO_INPS.keys())
        }
    }


@router.post("/scarica-e-processa")
async def scarica_e_processa(
    giorni: int = Query(7, description="Ultimi N giorni")
) -> Dict[str, Any]:
    """
    Flusso completo: scarica email → processa allegati → inserisce F24.
    Ideale per esecuzione giornaliera automatica.
    """
    # Step 1: Scarica email
    download_result = await scarica_email_allegati(giorni=giorni)
    
    if not download_result.get("success"):
        return {
            "success": False,
            "fase": "download",
            "errore": download_result
        }
    
    # Step 2: Processa allegati
    process_result = await processa_allegati_f24()
    
    return {
        "success": True,
        "message": "Download e processamento completati",
        "download": {
            "email_trovate": download_result.get("statistiche", {}).get("email_trovate", 0),
            "allegati_scaricati": download_result.get("statistiche", {}).get("allegati_totali", 0)
        },
        "processamento": {
            "f24_inseriti": process_result.get("risultati", {}).get("f24_commercialista", 0),
            "quietanze_inserite": process_result.get("risultati", {}).get("quietanze", 0),
            "errori": process_result.get("risultati", {}).get("errori", 0)
        }
    }
