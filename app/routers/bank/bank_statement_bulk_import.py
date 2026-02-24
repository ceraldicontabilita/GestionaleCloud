"""
Bank Statement Bulk Import Router
Endpoint per l'importazione massiva di estratti conto bancari in PDF.
Supporta upload multipli e anteprima dati prima del salvataggio.
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from typing import Dict, Any, List, Optional
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
router = APIRouter()

# Cache temporanea per anteprime (in produzione usare Redis)
PREVIEW_CACHE: Dict[str, Dict[str, Any]] = {}


@router.post("/parse-bulk", summary="Parse multiple bank statement PDFs")
async def parse_bulk_statements(
    files: List[UploadFile] = File(..., description="PDF files to parse")
) -> Dict[str, Any]:
    """
    Parse multipli PDF di estratti conto bancari.
    Restituisce un'anteprima dei dati estratti da tutti i file.
    I dati vengono messi in cache per il successivo salvataggio.
    """
    from app.services.universal_bank_statement_parser import parse_bank_statement
    
    results = []
    all_transactions = []
    total_entrate = 0
    total_uscite = 0
    errors = []
    
    for file in files:
        if not file.filename.lower().endswith('.pdf'):
            errors.append({"file": file.filename, "error": "Non è un file PDF"})
            continue
        
        try:
            content = await file.read()
            result = parse_bank_statement(content)
            
            if result.get("success"):
                file_transactions = result.get("transazioni", [])
                
                # Aggiungi filename a ogni transazione
                for t in file_transactions:
                    t["filename_origine"] = file.filename
                
                all_transactions.extend(file_transactions)
                total_entrate += result.get("totale_entrate", 0)
                total_uscite += result.get("totale_uscite", 0)
                
                results.append({
                    "filename": file.filename,
                    "success": True,
                    "banca": result.get("banca", "SCONOSCIUTA"),
                    "transazioni_count": len(file_transactions),
                    "totale_entrate": result.get("totale_entrate", 0),
                    "totale_uscite": result.get("totale_uscite", 0),
                    "metadata": result.get("metadata", {})
                })
            else:
                errors.append({
                    "file": file.filename,
                    "error": result.get("error", "Errore sconosciuto")
                })
        except Exception as e:
            logger.exception(f"Errore parsing {file.filename}: {e}")
            errors.append({"file": file.filename, "error": str(e)})
    
    # Genera ID cache per questa sessione di anteprima
    preview_id = str(uuid.uuid4())[:12]
    
    # Salva in cache
    PREVIEW_CACHE[preview_id] = {
        "transactions": all_transactions,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files_count": len(results),
        "total_entrate": total_entrate,
        "total_uscite": total_uscite
    }
    
    # Pulisci cache vecchie (> 30 min)
    _cleanup_old_previews()
    
    return {
        "success": True,
        "preview_id": preview_id,
        "files_parsed": results,
        "errors": errors,
        "totale_transazioni": len(all_transactions),
        "totale_entrate": round(total_entrate, 2),
        "totale_uscite": round(total_uscite, 2),
        "transazioni_preview": all_transactions[:100]  # Prime 100 per anteprima
    }


@router.get("/preview/{preview_id}", summary="Get preview data")
async def get_preview(
    preview_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500)
) -> Dict[str, Any]:
    """Recupera i dati di anteprima per un ID specifico."""
    
    if preview_id not in PREVIEW_CACHE:
        raise HTTPException(status_code=404, detail="Preview non trovata o scaduta")
    
    cache_data = PREVIEW_CACHE[preview_id]
    transactions = cache_data["transactions"]
    
    return {
        "success": True,
        "preview_id": preview_id,
        "total": len(transactions),
        "transazioni": transactions[skip:skip + limit],
        "totale_entrate": cache_data.get("total_entrate", 0),
        "totale_uscite": cache_data.get("total_uscite", 0),
        "files_count": cache_data.get("files_count", 0)
    }


@router.post("/commit/{preview_id}", summary="Save previewed transactions to database")
async def commit_preview(
    preview_id: str,
    anno: Optional[int] = Query(None, description="Anno di riferimento (opzionale, usa data transazione)"),
    collection: str = Query("estratto_conto_movimenti", description="Collection di destinazione")
) -> Dict[str, Any]:
    """
    Salva le transazioni in anteprima nel database.
    
    Args:
        preview_id: ID della preview da confermare
        anno: Anno di riferimento (opzionale)
        collection: Collection MongoDB di destinazione
    """
    from app.database import Database
    
    if preview_id not in PREVIEW_CACHE:
        raise HTTPException(status_code=404, detail="Preview non trovata o scaduta")
    
    cache_data = PREVIEW_CACHE[preview_id]
    transactions = cache_data["transactions"]
    
    if not transactions:
        return {"success": False, "message": "Nessuna transazione da salvare", "imported": 0}
    
    db = Database.get_db()
    imported = 0
    skipped = 0
    errors_list = []
    
    import_batch_id = str(uuid.uuid4())[:8]
    import_timestamp = datetime.now(timezone.utc).isoformat()
    
    for tx in transactions:
        try:
            data = tx.get("data")
            if not data:
                skipped += 1
                continue
            
            # Determina anno dalla data se non specificato
            tx_anno = anno
            if not tx_anno and data:
                try:
                    tx_anno = int(data.split("-")[0])
                except Exception:
                    tx_anno = datetime.now().year
            
            # Determina mese
            tx_mese = None
            if data:
                try:
                    tx_mese = int(data.split("-")[1])
                except Exception:
                    pass
            
            # Controlla duplicati
            existing = await db[collection].find_one({
                "data": data,
                "descrizione": tx.get("descrizione", "")[:100],
                "importo": tx.get("importo")
            })
            
            if existing:
                skipped += 1
                continue
            
            # Prepara record
            record = {
                "data": data,
                "data_valuta": tx.get("data_valuta"),
                "descrizione": tx.get("descrizione", "Movimento importato")[:500],
                "entrata": tx.get("entrata"),
                "uscita": tx.get("uscita"),
                "importo": tx.get("importo"),
                "banca": tx.get("banca", "SCONOSCIUTA"),
                "anno": tx_anno,
                "mese": tx_mese,
                "causale_abi": tx.get("causale_abi"),
                "filename_origine": tx.get("filename_origine"),
                "riconciliato": False,
                "stato": "da_riconciliare",
                "import_batch_id": import_batch_id,
                "created_at": import_timestamp
            }
            
            await db[collection].insert_one(record)
            imported += 1
            
        except Exception as e:
            errors_list.append(f"Errore: {str(e)[:50]}")
    
    # Rimuovi dalla cache dopo il commit
    del PREVIEW_CACHE[preview_id]
    
    # ===== RICONCILIAZIONE AUTOMATICA PAGHE (Stipendi + F24) =====
    riconciliazione_paghe = None
    try:
        from app.services.paghe_riconciliazione import esegui_riconciliazione_paghe_completa
        riconciliazione_paghe = await esegui_riconciliazione_paghe_completa(db)
    except Exception as e:
        logger.warning(f"Errore riconciliazione paghe post-import: {e}")
    
    return {
        "success": True,
        "imported": imported,
        "skipped": skipped,
        "total": len(transactions),
        "errors": errors_list[:10] if errors_list else [],
        "import_batch_id": import_batch_id,
        "collection": collection,
        "riconciliazione_paghe": riconciliazione_paghe
    }


@router.delete("/preview/{preview_id}", summary="Cancel preview")
async def cancel_preview(preview_id: str) -> Dict[str, Any]:
    """Cancella un'anteprima senza salvare."""
    
    if preview_id in PREVIEW_CACHE:
        del PREVIEW_CACHE[preview_id]
        return {"success": True, "message": "Preview cancellata"}
    
    return {"success": True, "message": "Preview già scaduta o non esistente"}


@router.post("/parse-single", summary="Parse single bank statement PDF")
async def parse_single_statement(
    file: UploadFile = File(..., description="PDF file to parse")
) -> Dict[str, Any]:
    """
    Parse un singolo PDF di estratto conto bancario.
    Restituisce i dati estratti senza salvarli.
    """
    from app.services.universal_bank_statement_parser import parse_bank_statement
    
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Il file deve essere un PDF")
    
    try:
        content = await file.read()
        result = parse_bank_statement(content)
        
        if result.get("success"):
            return {
                "success": True,
                "filename": file.filename,
                "banca": result.get("banca", "SCONOSCIUTA"),
                "metadata": result.get("metadata", {}),
                "transazioni": result.get("transazioni", []),
                "totale_transazioni": result.get("totale_transazioni", 0),
                "totale_entrate": result.get("totale_entrate", 0),
                "totale_uscite": result.get("totale_uscite", 0),
                "num_pagine": result.get("num_pagine", 0)
            }
        else:
            raise HTTPException(
                status_code=400, 
                detail=result.get("error", "Errore nel parsing del PDF")
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Errore parsing PDF: {e}")
        raise HTTPException(status_code=500, detail=f"Errore parsing: {str(e)}")


@router.post("/import-direct", summary="Parse and import in one step")
async def import_direct(
    files: List[UploadFile] = File(..., description="PDF files to import"),
    anno: Optional[int] = Query(None, description="Anno di riferimento"),
    collection: str = Query("estratto_conto_movimenti", description="Collection di destinazione")
) -> Dict[str, Any]:
    """
    Parse e importa direttamente i PDF senza passare dall'anteprima.
    Utile per importazioni automatiche.
    """
    from app.services.universal_bank_statement_parser import parse_bank_statement
    from app.database import Database
    
    db = Database.get_db()
    total_imported = 0
    total_skipped = 0
    files_results = []
    
    import_batch_id = str(uuid.uuid4())[:8]
    import_timestamp = datetime.now(timezone.utc).isoformat()
    
    for file in files:
        if not file.filename.lower().endswith('.pdf'):
            files_results.append({
                "filename": file.filename,
                "success": False,
                "error": "Non è un file PDF"
            })
            continue
        
        try:
            content = await file.read()
            result = parse_bank_statement(content)
            
            if not result.get("success"):
                files_results.append({
                    "filename": file.filename,
                    "success": False,
                    "error": result.get("error", "Errore parsing")
                })
                continue
            
            transactions = result.get("transazioni", [])
            file_imported = 0
            file_skipped = 0
            
            for tx in transactions:
                try:
                    data = tx.get("data")
                    if not data:
                        file_skipped += 1
                        continue
                    
                    tx_anno = anno or int(data.split("-")[0]) if data else datetime.now().year
                    tx_mese = int(data.split("-")[1]) if data and "-" in data else None
                    
                    # Controlla duplicati
                    existing = await db[collection].find_one({
                        "data": data,
                        "descrizione": tx.get("descrizione", "")[:100],
                        "importo": tx.get("importo")
                    })
                    
                    if existing:
                        file_skipped += 1
                        continue
                    
                    record = {
                        "data": data,
                        "data_valuta": tx.get("data_valuta"),
                        "descrizione": tx.get("descrizione", "Movimento")[:500],
                        "entrata": tx.get("entrata"),
                        "uscita": tx.get("uscita"),
                        "importo": tx.get("importo"),
                        "banca": tx.get("banca", "SCONOSCIUTA"),
                        "anno": tx_anno,
                        "mese": tx_mese,
                        "causale_abi": tx.get("causale_abi"),
                        "filename_origine": file.filename,
                        "riconciliato": False,
                        "stato": "da_riconciliare",
                        "import_batch_id": import_batch_id,
                        "created_at": import_timestamp
                    }
                    
                    await db[collection].insert_one(record)
                    file_imported += 1
                    
                except Exception:
                    file_skipped += 1
            
            total_imported += file_imported
            total_skipped += file_skipped
            
            files_results.append({
                "filename": file.filename,
                "success": True,
                "banca": result.get("banca"),
                "imported": file_imported,
                "skipped": file_skipped
            })
            
        except Exception as e:
            logger.exception(f"Errore import {file.filename}: {e}")
            files_results.append({
                "filename": file.filename,
                "success": False,
                "error": str(e)
            })
    
    return {
        "success": True,
        "total_imported": total_imported,
        "total_skipped": total_skipped,
        "files": files_results,
        "import_batch_id": import_batch_id
    }


def _cleanup_old_previews():
    """Pulisce le preview più vecchie di 30 minuti."""
    from datetime import timedelta
    
    now = datetime.now(timezone.utc)
    expired = []
    
    for pid, data in PREVIEW_CACHE.items():
        try:
            created = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
            if now - created > timedelta(minutes=30):
                expired.append(pid)
        except Exception:
            expired.append(pid)
    
    for pid in expired:
        del PREVIEW_CACHE[pid]
