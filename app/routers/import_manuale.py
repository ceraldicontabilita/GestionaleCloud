"""
Router per import manuale di file Excel/CSV

IMPORTANTE - DISTINZIONE DATI:
- pos.xlsx = CHIUSURE POS MANUALI (registratore di cassa) -> collection: chiusure_pos_manuali
- estratto conto = ACCREDITI POS BANCARI (movimenti reali in banca) -> collection: prima_nota_banca

NON confondere mai i due tipi di dati!
"""
from fastapi import APIRouter, HTTPException, UploadFile, File
from typing import Dict, Any, List
from datetime import datetime, timezone, timedelta
from app.database import Database
import pandas as pd
import io
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# COLLECTION DEDICATA per chiusure POS manuali (da registratore di cassa)
# NON sono movimenti bancari - sono registrazioni interne del negozio
COLLECTION_CHIUSURE_POS = "chiusure_pos_manuali"


def excel_serial_to_date(serial: int) -> str:
    """Converte data Excel serial in stringa YYYY-MM-DD"""
    if isinstance(serial, (int, float)) and serial > 40000:
        # Excel serial date: giorni dal 1899-12-30
        base = datetime(1899, 12, 30)
        delta = timedelta(days=int(serial))
        return (base + delta).strftime("%Y-%m-%d")
    return None


@router.post("/import-pos")
async def import_pos_excel(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Importa file POS Excel (chiusure manuali dal registratore di cassa).
    
    ATTENZIONE: Questi NON sono accrediti bancari!
    Sono le chiusure giornaliere POS registrate manualmente.
    Vengono salvati in 'chiusure_pos_manuali', NON in 'prima_nota_banca'.
    
    Colonne attese: DATA, IMPORTO
    Le date possono essere in formato Excel serial.
    """
    db = Database.get_db()
    
    try:
        contents = await file.read()
        df = pd.read_excel(io.BytesIO(contents))
        
        # Normalizza nomi colonne
        df.columns = [str(c).strip().upper() for c in df.columns]
        
        if 'DATA' not in df.columns or 'IMPORTO' not in df.columns:
            raise HTTPException(400, f"File deve avere colonne DATA e IMPORTO. Trovate: {list(df.columns)}")
        
        inserted = 0
        duplicati = 0
        errori = []
        
        for _, row in df.iterrows():
            try:
                # Converti data Excel serial
                data_raw = row['DATA']
                data = excel_serial_to_date(data_raw) if isinstance(data_raw, (int, float)) else str(data_raw)[:10]
                
                if not data:
                    continue
                
                importo = float(row['IMPORTO']) if pd.notna(row['IMPORTO']) else 0
                
                if importo <= 0:
                    continue
                
                # Verifica duplicato nella collection CORRETTA
                exists = await db[COLLECTION_CHIUSURE_POS].find_one({
                    "data": data,
                    "importo": importo
                })
                
                if exists:
                    duplicati += 1
                    continue
                
                # Inserisci nella collection CORRETTA (chiusure_pos_manuali)
                # NON in prima_nota_banca!
                doc = {
                    "data": data,
                    "importo": importo,
                    "note": f"Chiusura POS - Import da {file.filename}",
                    "source_file": file.filename,
                    "tipo": "chiusura_giornaliera",
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
                
                await db[COLLECTION_CHIUSURE_POS].insert_one(doc)
                inserted += 1
                
            except Exception as e:
                errori.append(str(e))
        
        return {
            "success": True,
            "message": f"Chiusure POS importate in '{COLLECTION_CHIUSURE_POS}' (NON in prima_nota_banca)",
            "file": file.filename,
            "righe_lette": len(df),
            "chiusure_inserite": inserted,
            "duplicati_saltati": duplicati,
            "errori": errori[:5] if errori else [],
            "nota": "Questi dati sono chiusure manuali del registratore, NON accrediti bancari"
        }
        
    except Exception as e:
        logger.error(f"Errore import chiusure POS: {e}")
        raise HTTPException(500, str(e))


@router.get("/chiusure-pos")
async def get_chiusure_pos(
    anno: int = None,
    data_da: str = None,
    data_a: str = None
) -> Dict[str, Any]:
    """
    Restituisce le chiusure POS manuali importate.
    """
    db = Database.get_db()
    
    query = {}
    if anno:
        query["data"] = {"$gte": f"{anno}-01-01", "$lte": f"{anno}-12-31"}
    if data_da:
        query.setdefault("data", {})["$gte"] = data_da
    if data_a:
        query.setdefault("data", {})["$lte"] = data_a
    
    chiusure = await db[COLLECTION_CHIUSURE_POS].find(query, {"_id": 0}).sort("data", -1).to_list(1000)
    
    totale = sum(c.get("importo", 0) for c in chiusure)
    
    return {
        "chiusure": chiusure,
        "count": len(chiusure),
        "totale": round(totale, 2),
        "collection": COLLECTION_CHIUSURE_POS
    }


@router.delete("/chiusure-pos/pulisci")
async def pulisci_chiusure_pos() -> Dict[str, Any]:
    """
    Elimina tutte le chiusure POS manuali (per reimportazione).
    """
    db = Database.get_db()
    result = await db[COLLECTION_CHIUSURE_POS].delete_many({})
    return {
        "success": True,
        "deleted": result.deleted_count,
        "message": f"Eliminate {result.deleted_count} chiusure POS manuali"
    }


@router.post("/import-versamenti")
async def import_versamenti_csv(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Importa file versamenti CSV con separatore ;
    Colonne: Data contabile, Importo, Descrizione, ecc.
    """
    db = Database.get_db()
    
    try:
        contents = await file.read()
        # Prova diversi encoding
        for encoding in ['utf-8', 'latin-1', 'iso-8859-1']:
            try:
                df = pd.read_csv(io.BytesIO(contents), sep=';', encoding=encoding)
                break
            except Exception:
                continue
        
        # Normalizza nomi colonne
        df.columns = [str(c).strip().lower().replace(' ', '_') for c in df.columns]
        
        # Trova colonne chiave
        col_data = next((c for c in df.columns if 'data' in c and 'contabil' in c), 
                       next((c for c in df.columns if 'data' in c), None))
        col_importo = next((c for c in df.columns if 'importo' in c), None)
        col_desc = next((c for c in df.columns if 'descr' in c), None)
        col_cat = next((c for c in df.columns if 'categ' in c), None)
        col_banca = next((c for c in df.columns if 'banca' in c), None)
        
        if not col_data or not col_importo:
            raise HTTPException(400, f"File deve avere colonne data e importo. Trovate: {list(df.columns)}")
        
        inserted = 0
        duplicati = 0
        errori = []
        
        for _, row in df.iterrows():
            try:
                # Converti data
                data_raw = row[col_data]
                if pd.isna(data_raw):
                    continue
                
                # Parse data DD/MM/YYYY
                if isinstance(data_raw, str) and '/' in data_raw:
                    parts = data_raw.split('/')
                    if len(parts) == 3:
                        data = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
                    else:
                        data = data_raw
                else:
                    data = str(data_raw)[:10]
                
                importo = float(row[col_importo]) if pd.notna(row[col_importo]) else 0
                descrizione = str(row[col_desc]) if col_desc and pd.notna(row.get(col_desc)) else "VERS. CONTANTI"
                categoria = str(row[col_cat]) if col_cat and pd.notna(row.get(col_cat)) else "Versamento"
                banca = str(row[col_banca]) if col_banca and pd.notna(row.get(col_banca)) else "BANCO BPM"
                
                if importo == 0:
                    continue
                
                # Cerca duplicato
                exists = await db["prima_nota_banca"].find_one({
                    "data": data,
                    "importo": importo,
                    "descrizione": {"$regex": descrizione[:20], "$options": "i"}
                })
                
                if exists:
                    duplicati += 1
                    continue
                
                # Inserisci
                doc = {
                    "data": data,
                    "importo": importo,
                    "descrizione": descrizione,
                    "categoria": categoria,
                    "tipo": "entrata" if importo > 0 else "uscita",
                    "banca": banca[:30] if banca else "BANCO BPM",
                    "source": "import_manuale_versamenti",
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
                
                await db["prima_nota_banca"].insert_one(doc)
                inserted += 1
                
            except Exception as e:
                errori.append(f"Riga: {str(e)}")
        
        return {
            "success": True,
            "file": file.filename,
            "righe_lette": len(df),
            "movimenti_inseriti": inserted,
            "duplicati_saltati": duplicati,
            "errori": errori[:5] if errori else []
        }
        
    except Exception as e:
        logger.error(f"Errore import versamenti: {e}")
        raise HTTPException(500, str(e))


@router.post("/import-finanziamento-soci")
async def import_finanziamento_soci(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Importa file finanziamento soci Excel.
    """
    db = Database.get_db()
    
    try:
        contents = await file.read()
        df = pd.read_excel(io.BytesIO(contents))
        
        # Normalizza nomi colonne
        df.columns = [str(c).strip().lower().replace(' ', '_') for c in df.columns]
        
        col_data = next((c for c in df.columns if 'data' in c), None)
        col_entrate = next((c for c in df.columns if 'entrat' in c), None)
        col_uscite = next((c for c in df.columns if 'uscit' in c), None)
        col_desc = next((c for c in df.columns if 'descr' in c or 'fornitor' in c), None)
        
        inserted = 0
        errori = []
        
        for _, row in df.iterrows():
            try:
                # Data
                data_raw = row.get(col_data) if col_data else None
                if data_raw and isinstance(data_raw, (int, float)) and data_raw > 40000:
                    data = excel_serial_to_date(data_raw)
                elif data_raw:
                    data = str(data_raw)[:10]
                else:
                    data = datetime.now().strftime("%Y-%m-%d")
                
                # Importo
                entrata = float(row.get(col_entrate, 0)) if col_entrate and pd.notna(row.get(col_entrate)) else 0
                uscita = float(row.get(col_uscite, 0)) if col_uscite and pd.notna(row.get(col_uscite)) else 0
                
                # Salta se dati non validi (numeri troppo grandi = date Excel)
                if entrata > 40000:
                    entrata = 0
                if uscita > 40000:
                    uscita = 0
                
                importo = entrata if entrata > 0 else -uscita
                
                if importo == 0:
                    continue
                
                descrizione = str(row.get(col_desc, "Finanziamento soci")) if col_desc else "Finanziamento soci"
                
                doc = {
                    "data": data,
                    "importo": importo,
                    "descrizione": f"FINANZIAMENTO SOCI - {descrizione}",
                    "categoria": "Finanziamento soci",
                    "tipo": "entrata" if importo > 0 else "uscita",
                    "source": "import_manuale_fin_soci",
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
                
                await db["prima_nota_banca"].insert_one(doc)
                inserted += 1
                
            except Exception as e:
                errori.append(str(e))
        
        return {
            "success": True,
            "file": file.filename,
            "righe_lette": len(df),
            "movimenti_inseriti": inserted,
            "errori": errori[:5] if errori else []
        }
        
    except Exception as e:
        logger.error(f"Errore import finanziamento: {e}")
        raise HTTPException(500, str(e))


@router.get("/preview-import")
async def preview_import_status() -> Dict[str, Any]:
    """Mostra statistiche import."""
    db = Database.get_db()
    
    stats = {}
    for source in ["import_manuale_pos", "import_manuale_versamenti", "import_manuale_fin_soci"]:
        count = await db["prima_nota_banca"].count_documents({"source": source})
        stats[source] = count
    
    return {"import_stats": stats}
