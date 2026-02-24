"""
Suppliers import/export endpoints.
Import da file Excel.
"""
from fastapi import APIRouter, HTTPException, UploadFile, File
from typing import Dict, Any
from datetime import datetime, timezone
import uuid
import io
import logging

from app.database import Database, Collections

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/upload-excel")
async def upload_suppliers_excel(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Import fornitori da file Excel.
    Formato atteso: Partita Iva, Denominazione, Email, Comune, Provincia, etc.
    """
    if not file.filename.endswith(('.xls', '.xlsx')):
        raise HTTPException(status_code=400, detail="Il file deve essere in formato Excel (.xls o .xlsx)")
    
    try:
        import pandas as pd
        
        content = await file.read()
        
        if file.filename.endswith('.xls'):
            df = pd.read_excel(io.BytesIO(content), engine='xlrd')
        else:
            df = pd.read_excel(io.BytesIO(content), engine='openpyxl')
        
        db = Database.get_db()
        results = {
            "imported": 0,
            "updated": 0,
            "skipped": 0,
            "errors": []
        }
        
        for idx, row in df.iterrows():
            try:
                partita_iva = str(row.get('Partita Iva', '')).strip()
                denominazione = str(row.get('Denominazione', '')).strip()
                
                if not partita_iva or partita_iva == 'nan' or not denominazione or denominazione == 'nan':
                    results["skipped"] += 1
                    continue
                
                denominazione = denominazione.strip('"').strip()
                
                supplier_doc = {
                    "partita_iva": partita_iva,
                    "denominazione": denominazione,
                    "codice_fiscale": str(row.get('Codice Fiscale', '')).strip() if pd.notna(row.get('Codice Fiscale')) else "",
                    "email": str(row.get('Email', '')).strip() if pd.notna(row.get('Email')) else "",
                    "pec": str(row.get('PEC', '')).strip() if pd.notna(row.get('PEC')) else "",
                    "telefono": str(row.get('Telefono', '')).strip() if pd.notna(row.get('Telefono')) else "",
                    "indirizzo": str(row.get('Indirizzo', '')).strip() if pd.notna(row.get('Indirizzo')) else "",
                    "cap": str(int(row.get('CAP', 0))) if pd.notna(row.get('CAP')) else "",
                    "comune": str(row.get('Comune', '')).strip() if pd.notna(row.get('Comune')) else "",
                    "provincia": str(row.get('Provincia', '')).strip() if pd.notna(row.get('Provincia')) else "",
                    "nazione": str(row.get('Nazione', 'IT')).strip() if pd.notna(row.get('Nazione')) else "IT",
                    "metodo_pagamento": "bonifico",
                    "termini_pagamento": "30GG",
                    "giorni_pagamento": 30,
                    "iban": "",
                    "banca": "",
                    "attivo": True,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
                
                existing = await db[Collections.SUPPLIERS].find_one({"partita_iva": partita_iva})
                
                if existing:
                    update_fields = {k: v for k, v in supplier_doc.items() 
                                     if k not in ['metodo_pagamento', 'termini_pagamento', 'giorni_pagamento', 'iban', 'banca']}
                    await db[Collections.SUPPLIERS].update_one(
                        {"partita_iva": partita_iva},
                        {"$set": update_fields}
                    )
                    results["updated"] += 1
                else:
                    supplier_doc["id"] = str(uuid.uuid4())
                    supplier_doc["created_at"] = datetime.now(timezone.utc).isoformat()
                    await db[Collections.SUPPLIERS].insert_one(supplier_doc.copy())
                    results["imported"] += 1
                    
                    if partita_iva:
                        await db[Collections.INVOICES].update_many(
                            {"cedente_piva": partita_iva, "supplier_id": {"$exists": False}},
                            {"$set": {
                                "supplier_id": supplier_doc["id"],
                                "supplier_name": supplier_doc.get("denominazione", ""),
                                "updated_at": datetime.now(timezone.utc).isoformat()
                            }}
                        )
                    
            except Exception as e:
                results["errors"].append(f"Riga {idx+2}: {str(e)}")
        
        return {
            "success": True,
            "message": f"Import completato: {results['imported']} nuovi, {results['updated']} aggiornati, {results['skipped']} saltati",
            **results
        }
        
    except Exception as e:
        logger.error(f"Error importing suppliers: {e}")
        raise HTTPException(status_code=500, detail=f"Errore import: {str(e)}")


@router.post("/import-excel")
async def import_suppliers_excel(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Importa fornitori da file Excel (.xls, .xlsx).
    Colonne attese: Denominazione, Partita Iva, Codice Fiscale, Email, PEC, 
                   Telefono, Indirizzo, CAP, Comune, Provincia, Nazione
    """
    import pandas as pd
    
    if not file.filename.endswith(('.xls', '.xlsx')):
        raise HTTPException(status_code=400, detail="File deve essere .xls o .xlsx")
    
    db = Database.get_db()
    
    try:
        contents = await file.read()
        df = pd.read_excel(io.BytesIO(contents))
        
        col_mapping = {
            'denominazione': ['Denominazione', 'denominazione', 'Ragione Sociale', 'Nome'],
            'partita_iva': ['Partita Iva', 'partita_iva', 'P.IVA', 'Partita IVA'],
            'codice_fiscale': ['Codice Fiscale', 'codice_fiscale', 'CF'],
            'email': ['Email', 'email', 'E-mail'],
            'pec': ['PEC', 'pec'],
            'telefono': ['Telefono', 'telefono', 'Tel'],
            'indirizzo': ['Indirizzo', 'indirizzo'],
            'cap': ['CAP', 'cap'],
            'comune': ['Comune', 'comune', 'Città'],
            'provincia': ['Provincia', 'provincia', 'Prov'],
            'nazione': ['Nazione', 'nazione', 'ID Paese', 'Paese'],
            'numero_civico': ['Numero civico', 'numero_civico', 'Civico'],
        }
        
        def find_col(options):
            for opt in options:
                if opt in df.columns:
                    return opt
            return None
        
        imported = 0
        updated = 0
        errors = []
        
        for idx, row in df.iterrows():
            try:
                denom_col = find_col(col_mapping['denominazione'])
                piva_col = find_col(col_mapping['partita_iva'])
                
                denominazione = str(row.get(denom_col, '')).strip() if denom_col else ''
                partita_iva = str(row.get(piva_col, '')).strip() if piva_col else ''
                
                if not denominazione and not partita_iva:
                    continue
                
                partita_iva = partita_iva.replace(' ', '').replace('.', '')
                if partita_iva.lower() == 'nan':
                    partita_iva = ''
                
                indirizzo_parts = []
                indirizzo_col = find_col(col_mapping['indirizzo'])
                num_col = find_col(col_mapping['numero_civico'])
                if indirizzo_col and pd.notna(row.get(indirizzo_col)):
                    indirizzo_parts.append(str(row.get(indirizzo_col)))
                if num_col and pd.notna(row.get(num_col)):
                    indirizzo_parts.append(str(row.get(num_col)))
                
                supplier_data = {
                    "denominazione": denominazione.strip('"'),
                    "partita_iva": partita_iva,
                    "codice_fiscale": str(row.get(find_col(col_mapping['codice_fiscale']), '') or '').strip() if find_col(col_mapping['codice_fiscale']) else '',
                    "email": str(row.get(find_col(col_mapping['email']), '') or '').strip() if find_col(col_mapping['email']) else '',
                    "pec": str(row.get(find_col(col_mapping['pec']), '') or '').strip() if find_col(col_mapping['pec']) else '',
                    "telefono": str(row.get(find_col(col_mapping['telefono']), '') or '').strip() if find_col(col_mapping['telefono']) else '',
                    "indirizzo": ', '.join(indirizzo_parts),
                    "cap": str(row.get(find_col(col_mapping['cap']), '') or '').strip() if find_col(col_mapping['cap']) else '',
                    "comune": str(row.get(find_col(col_mapping['comune']), '') or '').strip() if find_col(col_mapping['comune']) else '',
                    "provincia": str(row.get(find_col(col_mapping['provincia']), '') or '').strip() if find_col(col_mapping['provincia']) else '',
                    "nazione": str(row.get(find_col(col_mapping['nazione']), 'IT') or 'IT').strip() if find_col(col_mapping['nazione']) else 'IT',
                    "attivo": True,
                    "metodo_pagamento": "bonifico",
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
                
                for k, v in supplier_data.items():
                    if str(v).lower() == 'nan' or v == 'None':
                        supplier_data[k] = ''
                
                existing = None
                if partita_iva:
                    existing = await db[Collections.SUPPLIERS].find_one({"partita_iva": partita_iva})
                if not existing and denominazione:
                    existing = await db[Collections.SUPPLIERS].find_one({"denominazione": denominazione})
                
                if existing:
                    update_data = {k: v for k, v in supplier_data.items() if v}
                    await db[Collections.SUPPLIERS].update_one(
                        {"_id": existing["_id"]},
                        {"$set": update_data}
                    )
                    updated += 1
                else:
                    supplier_data["id"] = str(uuid.uuid4())
                    supplier_data["created_at"] = datetime.now(timezone.utc).isoformat()
                    await db[Collections.SUPPLIERS].insert_one(supplier_data.copy())
                    imported += 1
                    
            except Exception as e:
                errors.append(f"Riga {idx + 2}: {str(e)}")
        
        return {
            "success": True,
            "imported": imported,
            "updated": updated,
            "errors": errors[:10] if errors else [],
            "total_processed": imported + updated
        }
        
    except Exception as e:
        logger.error(f"Import fornitori fallito: {e}")
        raise HTTPException(status_code=500, detail=f"Errore import: {str(e)}")
