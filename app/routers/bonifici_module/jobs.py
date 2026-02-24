"""
Bonifici Module - Jobs e background processing.
"""
from fastapi import HTTPException, UploadFile, File, BackgroundTasks
from typing import List, Dict, Any
from datetime import datetime, timezone
from pathlib import Path
import uuid
import zipfile
import shutil

from app.database import Database
from .common import (
    UPLOAD_DIR, safe_filename, build_dedup_key,
    parse_filename_data, logger
)
from .pdf_parser import read_pdf_text, extract_transfers_from_text


async def create_job() -> Dict[str, Any]:
    """Crea un nuovo job di import."""
    db = Database.get_db()
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    job_data = {
        'id': job_id,
        'status': 'created',
        'created_at': now.isoformat(),
        'updated_at': now.isoformat(),
        'total_files': 0,
        'processed_files': 0,
        'errors': 0,
        'imported_files': 0,
    }
    await db.bonifici_jobs.insert_one({**job_data}.copy())
    return job_data


async def list_jobs() -> List[Dict[str, Any]]:
    """Lista tutti i job."""
    db = Database.get_db()
    jobs = await db.bonifici_jobs.find({}, {'_id': 0}).sort('created_at', -1).to_list(100)
    return jobs


async def get_job(job_id: str) -> Dict[str, Any]:
    """Ottiene stato di un job."""
    db = Database.get_db()
    job = await db.bonifici_jobs.find_one({'id': job_id}, {'_id': 0})
    if not job:
        raise HTTPException(status_code=404, detail='Job not found')
    return job


async def upload_files(job_id: str, background: BackgroundTasks, files: List[UploadFile] = File(...)) -> Dict[str, Any]:
    """Carica file PDF o ZIP per elaborazione."""
    db = Database.get_db()
    job = await db.bonifici_jobs.find_one({'id': job_id})
    if not job:
        raise HTTPException(status_code=404, detail='Job not found')
    
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    
    pdf_paths: List[Path] = []
    zip_errors: List[str] = []
    
    for f in files:
        name = safe_filename(Path(f.filename).name)
        
        if name.lower().endswith('.zip'):
            zip_path = job_dir / f"temp_{name}"
            try:
                with open(zip_path, 'wb') as fd:
                    while chunk := await f.read(1024 * 1024):
                        fd.write(chunk)
                
                with zipfile.ZipFile(zip_path, 'r') as z:
                    pdf_count = 0
                    for info in z.infolist():
                        if info.is_dir() or not info.filename.lower().endswith('.pdf'):
                            continue
                        
                        pdf_name = safe_filename(Path(info.filename).name)
                        out_path = job_dir / f"{pdf_count:04d}_{pdf_name}"
                        
                        try:
                            with z.open(info) as fsrc, open(out_path, 'wb') as fdst:
                                fdst.write(fsrc.read())
                            pdf_paths.append(out_path)
                            pdf_count += 1
                        except Exception as e:
                            zip_errors.append(f"{info.filename}: {str(e)}")
                
                zip_path.unlink(missing_ok=True)
                
            except zipfile.BadZipFile:
                zip_errors.append(f"{name}: File ZIP corrotto")
            except Exception as e:
                zip_errors.append(f"{name}: {str(e)}")
                
        elif name.lower().endswith('.pdf'):
            out = job_dir / name
            with open(out, 'wb') as fd:
                while chunk := await f.read(1024 * 1024):
                    fd.write(chunk)
            pdf_paths.append(out)
    
    await db.bonifici_jobs.update_one(
        {'id': job_id},
        {'$set': {
            'status': 'queued',
            'total_files': len(pdf_paths),
            'zip_errors': zip_errors[:50],
            'updated_at': datetime.now(timezone.utc).isoformat()
        }}
    )
    
    logger.info(f"Starting background processing for job {job_id} with {len(pdf_paths)} files")
    background.add_task(process_files_background, job_id, pdf_paths)
    
    return {
        'job_id': job_id, 
        'accepted_files': len(pdf_paths),
        'extraction_errors': len(zip_errors),
        'errors_sample': zip_errors[:5] if zip_errors else []
    }


async def process_files_background(job_id: str, file_paths: List[Path]):
    """Elabora i file PDF in background con deduplicazione."""
    logger.info(f"process_files_background started for job {job_id}")
    db = Database.get_db()
    
    await db.bonifici_jobs.update_one({'id': job_id}, {'$set': {'status': 'processing'}})
    
    processed = 0
    errors = 0
    imported = 0
    duplicates = 0
    
    # Carica chiavi esistenti per deduplicazione veloce
    existing_keys = set()
    existing_docs = await db.bonifici_transfers.find({}, {'_id': 0, 'dedup_key': 1}).to_list(50000)
    for doc in existing_docs:
        if doc.get('dedup_key'):
            existing_keys.add(doc['dedup_key'])
    
    for p in file_paths:
        try:
            text = read_pdf_text(p)
            transfers = extract_transfers_from_text(text) if text.strip() else []
            
            # Architettura MongoDB-only: leggi PDF e codifica in Base64
            import base64
            try:
                with open(p, 'rb') as pdf_file:
                    pdf_data = base64.b64encode(pdf_file.read()).decode('utf-8')
            except Exception:
                pdf_data = None
            
            # Fallback: estrai dati dal nome file
            if not transfers or (transfers and not transfers[0].get('importo')):
                filename_data = parse_filename_data(p.name)
                if filename_data:
                    if transfers:
                        transfers[0].update({k: v for k, v in filename_data.items() if v and not transfers[0].get(k)})
                    else:
                        transfers = [filename_data]
            
            if not transfers:
                errors += 1
                continue
            
            for t in transfers:
                t['source_file'] = p.name
                t['job_id'] = job_id
                t['id'] = str(uuid.uuid4())
                t['dedup_key'] = build_dedup_key(t)
                t['pdf_data'] = pdf_data  # Architettura MongoDB-only
                t['created_at'] = datetime.now(timezone.utc).isoformat()
                
                if isinstance(t.get('data'), datetime):
                    t['data'] = t['data'].isoformat()
                
                if t['dedup_key'] in existing_keys:
                    duplicates += 1
                    continue
                
                await db.bonifici_transfers.insert_one(t.copy())
                existing_keys.add(t['dedup_key'])
                imported += 1
                
        except Exception as e:
            errors += 1
            logger.exception(f"Processing failed for {p}: {e}")
        finally:
            processed += 1
            
            if processed % 10 == 0 or processed == len(file_paths):
                await db.bonifici_jobs.update_one(
                    {'id': job_id},
                    {'$set': {
                        'processed_files': processed,
                        'errors': errors,
                        'imported_files': imported,
                        'duplicates_skipped': duplicates,
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }}
                )
            
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass
    
    # Pulisci directory job
    job_dir = UPLOAD_DIR / job_id
    try:
        shutil.rmtree(job_dir, ignore_errors=True)
    except Exception:
        pass
    
    # Auto-associazione
    auto_associated_salari = 0
    auto_associated_fatture = 0
    
    if imported > 0:
        auto_associated_salari, auto_associated_fatture = await _auto_associate_bonifici(db, job_id)
    
    await db.bonifici_jobs.update_one(
        {'id': job_id}, 
        {'$set': {
            'status': 'completed',
            'completed_at': datetime.now(timezone.utc).isoformat(),
            'auto_associated_salari': auto_associated_salari,
            'auto_associated_fatture': auto_associated_fatture
        }}
    )


async def _auto_associate_bonifici(db, job_id: str) -> tuple:
    """Auto-associa bonifici con salari e fatture."""
    auto_salari = 0
    auto_fatture = 0
    
    try:
        new_bonifici = await db.bonifici_transfers.find(
            {"job_id": job_id, "salario_associato": {"$ne": True}, "fattura_associata": {"$ne": True}},
            {"_id": 0}
        ).to_list(500)
        
        for bonifico in new_bonifici:
            importo = abs(bonifico.get("importo", 0))
            beneficiario_nome = ((bonifico.get("beneficiario") or {}).get("nome") or "").lower()
            causale = (bonifico.get("causale") or "").lower()
            
            if importo <= 0:
                continue
            
            # Match SALARI
            salari_match = await db.prima_nota_salari.find_one({
                "salario_associato": {"$ne": True},
                "$or": [
                    {"importo_busta": {"$gte": importo * 0.98, "$lte": importo * 1.02}},
                    {"importo_bonifico": {"$gte": importo * 0.98, "$lte": importo * 1.02}}
                ]
            }, {"_id": 0})
            
            if salari_match:
                dipendente = (salari_match.get("dipendente") or "").lower()
                if dipendente and (dipendente in beneficiario_nome or dipendente in causale or beneficiario_nome in dipendente):
                    await db.bonifici_transfers.update_one(
                        {"id": bonifico["id"]},
                        {"$set": {
                            "salario_associato": True,
                            "operazione_salario_id": salari_match.get("id"),
                            "auto_associated": True,
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }}
                    )
                    await db.prima_nota_salari.update_one(
                        {"id": salari_match.get("id")},
                        {"$set": {"salario_associato": True, "bonifico_id": bonifico["id"]}}
                    )
                    auto_salari += 1
                    continue
            
            # Match FATTURE
            fattura_match = await db.invoices.find_one({
                "fattura_associata": {"$ne": True},
                "$or": [
                    {"total_amount": {"$gte": importo * 0.98, "$lte": importo * 1.02}},
                    {"importo_totale": {"$gte": importo * 0.98, "$lte": importo * 1.02}}
                ]
            }, {"_id": 0})
            
            if fattura_match:
                fornitore = (fattura_match.get("supplier_name") or "").lower()
                if fornitore and (fornitore in beneficiario_nome or fornitore in causale or beneficiario_nome in fornitore):
                    await db.bonifici_transfers.update_one(
                        {"id": bonifico["id"]},
                        {"$set": {
                            "fattura_associata": True,
                            "fattura_id": fattura_match.get("id"),
                            "auto_associated": True,
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }}
                    )
                    await db.invoices.update_one(
                        {"id": fattura_match.get("id")},
                        {"$set": {"bonifico_associato": True, "bonifico_id": bonifico["id"]}}
                    )
                    auto_fatture += 1
    except Exception as e:
        logger.error(f"Auto-association error: {e}")
    
    return auto_salari, auto_fatture
