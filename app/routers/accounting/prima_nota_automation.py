"""
Prima Nota Automation Router - Automazione registrazioni contabili.
API per:
- Processare fatture esistenti e associare metodi di pagamento dai fornitori
- Importare fatture da file Excel come pagate in cassa
- Parsare estratto conto per assegni e associarli alle fatture banca
"""
from fastapi import APIRouter, HTTPException, Body, UploadFile, File, Query
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import uuid
import logging
import io
import re

from app.database import Database, Collections

logger = logging.getLogger(__name__)
router = APIRouter()

# Collections
COLLECTION_PRIMA_NOTA_CASSA = "prima_nota_cassa"
COLLECTION_PRIMA_NOTA_BANCA = "prima_nota_banca"
COLLECTION_ASSEGNI = "assegni"


def parse_italian_amount(amount_str: str) -> float:
    """Converte importo italiano (es. -704,7 o 1.530,9) in float."""
    if not amount_str:
        return 0.0
    # Rimuovi spazi
    amount_str = str(amount_str).strip()
    # Rimuovi punti come separatore migliaia
    amount_str = amount_str.replace(".", "")
    # Sostituisci virgola con punto per decimali
    amount_str = amount_str.replace(",", ".")
    try:
        return float(amount_str)
    except (ValueError, TypeError):
        return 0.0


def parse_italian_date(date_str: str) -> str:
    """Converte data italiana (gg/mm/aaaa) in formato ISO (YYYY-MM-DD)."""
    if not date_str:
        return ""
    try:
        if "/" in date_str:
            parts = date_str.split("/")
            if len(parts) == 3:
                return f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
        return date_str
    except (ValueError, TypeError, IndexError):
        return date_str


# ============== PROCESSAMENTO FATTURE ESISTENTI ==============

@router.post("/process-existing-invoices")
async def process_existing_invoices(
    year_filter: Optional[int] = Body(None, description="Filtra per anno (es. 2026)"),
    auto_move_to_prima_nota: bool = Body(True, description="Spostare automaticamente in prima nota")
) -> Dict[str, Any]:
    """
    Processa tutte le fatture esistenti:
    1. Associa metodo di pagamento dal dizionario fornitori
    2. Sposta in Prima Nota Cassa o Banca in base al metodo pagamento
    
    Per fatture 2026+: operazione automatica.
    """
    db = Database.get_db()
    
    results = {
        "processed": 0,
        "moved_to_cassa": 0,
        "moved_to_banca": 0,
        "skipped_no_supplier": 0,
        "skipped_already_processed": 0,
        "errors": []
    }
    
    # Query base
    query = {"pagato": {"$ne": True}}
    
    # Filtra per anno se specificato
    if year_filter:
        query["$or"] = [
            {"invoice_date": {"$regex": f"^{year_filter}"}},
            {"data_fattura": {"$regex": f"^{year_filter}"}}
        ]
    
    invoices = await db[Collections.INVOICES].find(query, {"_id": 0}).to_list(10000)
    
    for invoice in invoices:
        try:
            # Cerca il fornitore
            supplier_vat = invoice.get("cedente_piva") or invoice.get("supplier_vat")
            
            if not supplier_vat:
                results["skipped_no_supplier"] += 1
                continue
            
            # Cerca metodo pagamento dal fornitore
            supplier = await db[Collections.SUPPLIERS].find_one(
                {"partita_iva": supplier_vat},
                {"_id": 0, "metodo_pagamento": 1, "denominazione": 1}
            )
            
            metodo_pagamento = supplier.get("metodo_pagamento", "bonifico") if supplier else "bonifico"
            
            # Aggiorna fattura con metodo pagamento
            update_data = {
                "metodo_pagamento": metodo_pagamento,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Determina prima nota (cassa o banca)
            if auto_move_to_prima_nota:
                importo = invoice.get("importo_totale") or invoice.get("total_amount", 0)
                data_fattura = invoice.get("data_fattura") or invoice.get("invoice_date", "")
                numero_fattura = invoice.get("numero_fattura") or invoice.get("invoice_number", "")
                fornitore_nome = invoice.get("cedente_denominazione") or invoice.get("supplier_name", "")
                
                descrizione = f"Pagamento fattura {numero_fattura} - {fornitore_nome}"
                
                movimento_base = {
                    "id": str(uuid.uuid4()),
                    "data": data_fattura,
                    "tipo": "uscita",
                    "importo": float(importo or 0),
                    "descrizione": descrizione,
                    "categoria": "Pagamento fornitore",
                    "riferimento": numero_fattura,
                    "fornitore_piva": supplier_vat,
                    "fattura_id": invoice.get("id") or invoice.get("invoice_key"),
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
                
                # Verifica se esiste già movimento
                existing_cassa = await db[COLLECTION_PRIMA_NOTA_CASSA].find_one(
                    {"fattura_id": movimento_base["fattura_id"]}
                )
                existing_banca = await db[COLLECTION_PRIMA_NOTA_BANCA].find_one(
                    {"fattura_id": movimento_base["fattura_id"]}
                )
                
                if existing_cassa or existing_banca:
                    results["skipped_already_processed"] += 1
                    continue
                
                # Registra in prima nota appropriata
                if metodo_pagamento in ["contanti", "cassa"]:
                    await db[COLLECTION_PRIMA_NOTA_CASSA].insert_one(movimento_base.copy())
                    update_data["prima_nota_cassa_id"] = movimento_base["id"]
                    update_data["pagato"] = True
                    update_data["data_pagamento"] = datetime.now(timezone.utc).isoformat()[:10]
                    results["moved_to_cassa"] += 1
                else:
                    await db[COLLECTION_PRIMA_NOTA_BANCA].insert_one(movimento_base.copy())
                    update_data["prima_nota_banca_id"] = movimento_base["id"]
                    update_data["pagato"] = True
                    update_data["data_pagamento"] = datetime.now(timezone.utc).isoformat()[:10]
                    results["moved_to_banca"] += 1
            
            # Aggiorna fattura
            await db[Collections.INVOICES].update_one(
                {"$or": [{"id": invoice.get("id")}, {"invoice_key": invoice.get("invoice_key")}]},
                {"$set": update_data}
            )
            
            results["processed"] += 1
            
        except Exception as e:
            results["errors"].append({
                "invoice": invoice.get("numero_fattura", "N/A"),
                "error": str(e)
            })
    
    return {
        "success": True,
        "message": f"Processate {results['processed']} fatture",
        **results
    }


# ============== IMPORT FATTURE CASSA DA EXCEL ==============

@router.post("/import-cassa-from-excel")
async def import_cassa_from_excel(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Importa fatture da file Excel e le registra come pagate in cassa.
    
    Il file Excel deve avere colonne:
    - Importo
    - Numero (numero fattura)
    - Data documento
    - Fornitore
    - Totale documento (opzionale)
    
    Tutte le fatture trovate vengono:
    1. Cercate nel database
    2. Segnate come pagate per cassa
    3. Registrate in Prima Nota Cassa
    """
    if not file.filename.endswith(('.xls', '.xlsx')):
        raise HTTPException(status_code=400, detail="Il file deve essere in formato Excel")
    
    try:
        import pandas as pd
        
        content = await file.read()
        
        # Leggi Excel
        if file.filename.endswith('.xls'):
            df = pd.read_excel(io.BytesIO(content), engine='xlrd')
        else:
            df = pd.read_excel(io.BytesIO(content), engine='openpyxl')
        
        logger.info(f"Excel colonne: {df.columns.tolist()}")
        
        db = Database.get_db()
        
        results = {
            "processed": 0,
            "matched_invoices": 0,
            "created_in_cassa": 0,
            "already_in_cassa": 0,
            "not_found": [],
            "errors": []
        }
        
        now = datetime.now(timezone.utc).isoformat()
        
        for idx, row in df.iterrows():
            try:
                # Estrai dati
                numero_fattura = str(row.get("Numero", "")).strip()
                fornitore = str(row.get("Fornitore", "")).strip().strip('"')
                importo = float(row.get("Importo", 0) or row.get("Totale documento", 0) or 0)
                
                # Gestisci data
                data_doc = row.get("Data documento", "")
                if pd.notna(data_doc):
                    if isinstance(data_doc, datetime):
                        data_documento = data_doc.strftime("%Y-%m-%d")
                    else:
                        data_documento = str(data_doc)[:10]
                else:
                    data_documento = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                
                if not numero_fattura or numero_fattura == 'nan':
                    continue
                
                results["processed"] += 1
                
                # Cerca fattura nel database per numero fattura
                invoice = await db[Collections.INVOICES].find_one({
                    "$or": [
                        {"numero_fattura": numero_fattura},
                        {"invoice_number": numero_fattura},
                        {"numero_fattura": {"$regex": f"^{re.escape(numero_fattura)}$", "$options": "i"}}
                    ]
                })
                
                # Se non trovata, cerca per fornitore + importo simile
                if not invoice and fornitore:
                    invoice = await db[Collections.INVOICES].find_one({
                        "$and": [
                            {"$or": [
                                {"cedente_denominazione": {"$regex": fornitore[:20], "$options": "i"}},
                                {"supplier_name": {"$regex": fornitore[:20], "$options": "i"}}
                            ]},
                            {"$or": [
                                {"importo_totale": {"$gte": importo * 0.99, "$lte": importo * 1.01}},
                                {"total_amount": {"$gte": importo * 0.99, "$lte": importo * 1.01}}
                            ]}
                        ]
                    })
                
                # Verifica se già in prima nota cassa
                existing = await db[COLLECTION_PRIMA_NOTA_CASSA].find_one({
                    "$or": [
                        {"riferimento": numero_fattura},
                        {"fattura_id": invoice.get("id") if invoice else None}
                    ]
                })
                
                if existing:
                    results["already_in_cassa"] += 1
                    continue
                
                # Crea movimento cassa
                movimento = {
                    "id": str(uuid.uuid4()),
                    "data": data_documento,
                    "tipo": "uscita",
                    "importo": importo,
                    "descrizione": f"Pagamento fattura {numero_fattura} - {fornitore}",
                    "categoria": "Pagamento fornitore",
                    "riferimento": numero_fattura,
                    "fornitore_nome": fornitore,
                    "fattura_id": invoice.get("id") if invoice else None,
                    "fornitore_piva": invoice.get("cedente_piva") if invoice else None,
                    "source": "excel_import",
                    "filename": file.filename,
                    "created_at": now
                }
                
                await db[COLLECTION_PRIMA_NOTA_CASSA].insert_one(movimento.copy())
                results["created_in_cassa"] += 1
                
                # Aggiorna fattura se trovata
                if invoice:
                    results["matched_invoices"] += 1
                    await db[Collections.INVOICES].update_one(
                        {"_id": invoice["_id"]},
                        {"$set": {
                            "pagato": True,
                            "metodo_pagamento": "contanti",
                            "data_pagamento": data_documento,
                            "prima_nota_cassa_id": movimento["id"],
                            "updated_at": now
                        }}
                    )
                else:
                    results["not_found"].append({
                        "numero": numero_fattura,
                        "fornitore": fornitore,
                        "importo": importo
                    })
                
            except Exception as e:
                results["errors"].append({
                    "row": idx + 2,
                    "error": str(e)
                })
        
        return {
            "success": True,
            "message": f"Importate {results['created_in_cassa']} fatture in prima nota cassa",
            **results
        }
        
    except Exception as e:
        logger.error(f"Error importing Excel: {e}")
        raise HTTPException(status_code=500, detail=f"Errore import: {str(e)}")


# ============== IMPORT ESTRATTO CONTO PER ASSEGNI ==============

@router.post("/import-assegni-from-estratto-conto")
async def import_assegni_from_estratto_conto(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Parsa estratto conto CSV/Excel/PDF per trovare prelievi assegno.
    
    Cerca righe con "VOSTRO ASSEGNO" o "PRELIEVO ASSEGNO" e estrae:
    - Numero assegno
    - Importo
    - Data
    
    Se l'assegno esiste già, aggiorna solo i dati mancanti.
    Crea gli assegni nel database e associa alle fatture banca per importo.
    """
    filename = file.filename.lower()
    if not filename.endswith(('.csv', '.xls', '.xlsx', '.pdf')):
        raise HTTPException(status_code=400, detail="Il file deve essere CSV, Excel o PDF")
    
    try:
        import pandas as pd
        
        content = await file.read()
        rows_data = []
        
        # Parse based on file type
        if filename.endswith('.pdf'):
            # Parse PDF
            import pdfplumber
            
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                for page in pdf.pages:
                    tables = page.extract_tables()
                    for table in tables:
                        if not table:
                            continue
                        # Skip header row if present
                        for row in table:
                            if row and len(row) >= 3:
                                # Try to extract data - format varies
                                row_text = ' '.join([str(c) if c else '' for c in row])
                                rows_data.append({
                                    "raw_text": row_text,
                                    "cells": row
                                })
                    
                    # Also extract text for non-table content
                    text = page.extract_text()
                    if text:
                        for line in text.split('\n'):
                            if 'ASSEGNO' in line.upper():
                                rows_data.append({
                                    "raw_text": line,
                                    "cells": None
                                })
            
            logger.info(f"PDF estratto conto: trovate {len(rows_data)} righe")
        
        elif filename.endswith('.csv'):
            for encoding in ['utf-8', 'latin-1', 'cp1252']:
                try:
                    df = pd.read_csv(io.BytesIO(content), sep=';', encoding=encoding)
                    for idx, row in df.iterrows():
                        rows_data.append({
                            "raw_text": str(row.to_dict()),
                            "row_dict": row.to_dict(),
                            "cells": None
                        })
                    break
                except Exception:
                    continue
        else:
            # Excel
            engine = 'xlrd' if filename.endswith('.xls') else 'openpyxl'
            df = pd.read_excel(io.BytesIO(content), engine=engine)
            for idx, row in df.iterrows():
                rows_data.append({
                    "raw_text": str(row.to_dict()),
                    "row_dict": row.to_dict(),
                    "cells": None
                })
        
        db = Database.get_db()
        
        results = {
            "total_rows": len(rows_data),
            "assegni_found": 0,
            "assegni_created": 0,
            "assegni_updated": 0,
            "assegni_already_complete": 0,
            "fatture_matched": 0,
            "assegni": [],
            "errors": []
        }
        
        now = datetime.now(timezone.utc).isoformat()
        
        # Process rows looking for checks
        for idx, row_data in enumerate(rows_data):
            try:
                raw_text = row_data.get("raw_text", "")
                row_dict = row_data.get("row_dict", {})
                cells = row_data.get("cells", [])
                
                # Skip if no check reference
                if "ASSEGNO" not in raw_text.upper():
                    continue
                
                results["assegni_found"] += 1
                
                # Extract check number - multiple patterns
                numero_assegno = None
                patterns = [
                    r'VOSTRO ASSEGNO N\.\s*(\d+)',
                    r'ASSEGNO N\.\s*(\d+)',
                    r'NUM:\s*(\d+)',
                    r'N\.\s*(\d{8,})',
                    r'(\d{10,})'  # Fallback: long number
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, raw_text, re.IGNORECASE)
                    if match:
                        numero_assegno = match.group(1)
                        break
                
                if not numero_assegno:
                    results["errors"].append({
                        "row": idx + 1,
                        "error": "Numero assegno non trovato",
                        "text": raw_text[:100]
                    })
                    continue
                
                # Extract amount
                importo = 0.0
                if row_dict:
                    importo_raw = row_dict.get("Importo") or row_dict.get("USCITE") or row_dict.get("Uscite", 0)
                    importo = abs(parse_italian_amount(str(importo_raw)))
                
                if importo == 0 and cells:
                    # Try to find amount in cells
                    for cell in cells:
                        if cell and re.match(r'^-?\d+[.,]\d+$', str(cell).strip().replace('.', '').replace(' ', '')):
                            importo = abs(parse_italian_amount(str(cell)))
                            if importo > 0:
                                break
                
                if importo == 0:
                    # Try to find amount in raw text
                    amount_match = re.search(r'-?\d{1,3}(?:\.\d{3})*,\d{2}', raw_text)
                    if amount_match:
                        importo = abs(parse_italian_amount(amount_match.group()))
                
                # Extract date
                data = ""
                if row_dict:
                    data_raw = row_dict.get("Data contabile") or row_dict.get("DATA CONTABILE (*1)") or row_dict.get("Data valuta", "")
                    data = parse_italian_date(str(data_raw))
                
                if not data:
                    # Try to find date in raw text (DD/MM/YY or DD/MM/YYYY)
                    date_match = re.search(r'(\d{2}/\d{2}/\d{2,4})', raw_text)
                    if date_match:
                        data = parse_italian_date(date_match.group(1))
                
                # Check if assegno exists
                existing = await db[COLLECTION_ASSEGNI].find_one({"numero": numero_assegno})
                
                if existing:
                    # Update only missing fields
                    update_data = {}
                    if importo > 0 and (not existing.get("importo") or existing.get("importo") == 0):
                        update_data["importo"] = importo
                    if data and not existing.get("data_emissione"):
                        update_data["data_emissione"] = data
                        update_data["data_incasso"] = data
                    if not existing.get("source"):
                        update_data["source"] = "estratto_conto"
                    
                    if update_data:
                        update_data["updated_at"] = now
                        await db[COLLECTION_ASSEGNI].update_one(
                            {"numero": numero_assegno},
                            {"$set": update_data}
                        )
                        results["assegni_updated"] += 1
                        results["assegni"].append({
                            "numero": numero_assegno,
                            "action": "updated",
                            "fields_updated": list(update_data.keys())
                        })
                    else:
                        results["assegni_already_complete"] += 1
                    continue
                
                # Create new assegno
                assegno = {
                    "id": str(uuid.uuid4()),
                    "numero": numero_assegno,
                    "stato": "incassato",
                    "importo": importo,
                    "data_emissione": data,
                    "data_incasso": data,
                    "beneficiario": None,
                    "causale": f"Da estratto conto: {raw_text[:100]}",
                    "fattura_collegata": None,
                    "fornitore_piva": None,
                    "source": "estratto_conto",
                    "filename": file.filename,
                    "created_at": now,
                    "updated_at": now
                }
                
                # Cerca fattura in prima nota banca con importo simile
                # (tolleranza 1%)
                if importo > 0:
                    fattura_banca = await db[COLLECTION_PRIMA_NOTA_BANCA].find_one({
                        "importo": {"$gte": importo * 0.99, "$lte": importo * 1.01},
                        "tipo": "uscita",
                        "assegno_collegato": {"$exists": False}
                    })
                    
                    if fattura_banca:
                        assegno["fattura_collegata"] = fattura_banca.get("fattura_id")
                        assegno["beneficiario"] = fattura_banca.get("descrizione", "")[:100]
                        assegno["fornitore_piva"] = fattura_banca.get("fornitore_piva")
                        
                        # Aggiorna prima nota banca con riferimento assegno
                        await db[COLLECTION_PRIMA_NOTA_BANCA].update_one(
                            {"id": fattura_banca["id"]},
                            {"$set": {
                                "assegno_collegato": numero_assegno,
                                "metodo_pagamento": "assegno",
                                "updated_at": now
                            }}
                        )
                        results["fatture_matched"] += 1
                
                await db[COLLECTION_ASSEGNI].insert_one(assegno.copy())
                results["assegni_created"] += 1
                
                results["assegni"].append({
                    "numero": numero_assegno,
                    "action": "created",
                    "importo": importo,
                    "data": data,
                    "fattura_collegata": assegno.get("fattura_collegata")
                })
                
            except Exception as e:
                results["errors"].append({
                    "row": idx + 1,
                    "error": str(e)
                })
        
        return {
            "success": True,
            "message": f"Trovati {results['assegni_found']} assegni, creati {results['assegni_created']}, aggiornati {results['assegni_updated']}",
            **results
        }
        
    except Exception as e:
        logger.error(f"Error parsing estratto conto: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Errore parsing: {str(e)}")


# ============== ASSOCIA ASSEGNI ESISTENTI ALLE FATTURE BANCA ==============

@router.post("/match-assegni-to-invoices")
async def match_assegni_to_invoices() -> Dict[str, Any]:
    """
    Cerca di associare automaticamente gli assegni esistenti alle fatture banca
    in base all'importo.
    """
    db = Database.get_db()
    
    results = {
        "assegni_processed": 0,
        "matched": 0,
        "already_matched": 0,
        "no_match": 0,
        "matches": []
    }
    
    # Trova assegni senza fattura collegata
    assegni = await db[COLLECTION_ASSEGNI].find(
        {"fattura_collegata": None},
        {"_id": 0}
    ).to_list(1000)
    
    now = datetime.now(timezone.utc).isoformat()
    
    for assegno in assegni:
        results["assegni_processed"] += 1
        importo = assegno.get("importo", 0)
        
        if not importo:
            results["no_match"] += 1
            continue
        
        # Cerca in prima nota banca
        movimento = await db[COLLECTION_PRIMA_NOTA_BANCA].find_one({
            "importo": {"$gte": importo * 0.99, "$lte": importo * 1.01},
            "tipo": "uscita",
            "assegno_collegato": {"$exists": False}
        })
        
        if movimento:
            # Aggiorna assegno
            await db[COLLECTION_ASSEGNI].update_one(
                {"numero": assegno["numero"]},
                {"$set": {
                    "fattura_collegata": movimento.get("fattura_id"),
                    "beneficiario": movimento.get("descrizione", "")[:100],
                    "fornitore_piva": movimento.get("fornitore_piva"),
                    "updated_at": now
                }}
            )
            
            # Aggiorna prima nota banca
            await db[COLLECTION_PRIMA_NOTA_BANCA].update_one(
                {"id": movimento["id"]},
                {"$set": {
                    "assegno_collegato": assegno["numero"],
                    "metodo_pagamento": "assegno",
                    "updated_at": now
                }}
            )
            
            results["matched"] += 1
            results["matches"].append({
                "assegno": assegno["numero"],
                "importo": importo,
                "fattura": movimento.get("riferimento")
            })
        else:
            results["no_match"] += 1
    
    return {
        "success": True,
        "message": f"Associati {results['matched']} assegni alle fatture",
        **results
    }


# ============== SPOSTA FATTURE IN PRIMA NOTA IN BASE A FORNITORE ==============

@router.post("/move-invoices-by-supplier-payment")
async def move_invoices_by_supplier_payment(
    only_unpaid: bool = Body(True),
    year_filter: Optional[int] = Body(None)
) -> Dict[str, Any]:
    """
    Sposta tutte le fatture in Prima Nota Cassa o Banca
    in base al metodo di pagamento configurato per il fornitore.
    """
    db = Database.get_db()
    
    results = {
        "processed": 0,
        "moved_to_cassa": 0,
        "moved_to_banca": 0,
        "skipped_no_supplier": 0,
        "skipped_already_registered": 0,
        "errors": []
    }
    
    # Query base
    query = {}
    if only_unpaid:
        query["pagato"] = {"$ne": True}
    
    if year_filter:
        query["$or"] = [
            {"invoice_date": {"$regex": f"^{year_filter}"}},
            {"data_fattura": {"$regex": f"^{year_filter}"}}
        ]
    
    invoices = await db[Collections.INVOICES].find(query, {"_id": 0}).to_list(10000)
    now = datetime.now(timezone.utc).isoformat()
    
    for invoice in invoices:
        try:
            supplier_vat = invoice.get("cedente_piva") or invoice.get("supplier_vat")
            
            if not supplier_vat:
                results["skipped_no_supplier"] += 1
                continue
            
            # Verifica se già registrata
            invoice_id = invoice.get("id") or invoice.get("invoice_key")
            existing_cassa = await db[COLLECTION_PRIMA_NOTA_CASSA].find_one({"fattura_id": invoice_id})
            existing_banca = await db[COLLECTION_PRIMA_NOTA_BANCA].find_one({"fattura_id": invoice_id})
            
            if existing_cassa or existing_banca:
                results["skipped_already_registered"] += 1
                continue
            
            # Cerca metodo pagamento del fornitore
            supplier = await db[Collections.SUPPLIERS].find_one(
                {"partita_iva": supplier_vat},
                {"metodo_pagamento": 1}
            )
            
            metodo = supplier.get("metodo_pagamento", "bonifico") if supplier else "bonifico"
            
            # Prepara movimento
            importo = invoice.get("importo_totale") or invoice.get("total_amount", 0)
            data = invoice.get("data_fattura") or invoice.get("invoice_date", "")
            numero = invoice.get("numero_fattura") or invoice.get("invoice_number", "")
            fornitore_nome = invoice.get("cedente_denominazione") or invoice.get("supplier_name", "")
            
            movimento = {
                "id": str(uuid.uuid4()),
                "data": data,
                "tipo": "uscita",
                "importo": float(importo or 0),
                "descrizione": f"Pagamento fattura {numero} - {fornitore_nome}",
                "categoria": "Pagamento fornitore",
                "riferimento": numero,
                "fornitore_piva": supplier_vat,
                "fattura_id": invoice_id,
                "metodo_pagamento": metodo,
                "created_at": now
            }
            
            # Inserisci nella collection appropriata
            update_data = {
                "pagato": True,
                "metodo_pagamento": metodo,
                "data_pagamento": now[:10],
                "updated_at": now
            }
            
            if metodo in ["contanti", "cassa"]:
                await db[COLLECTION_PRIMA_NOTA_CASSA].insert_one(movimento.copy())
                update_data["prima_nota_cassa_id"] = movimento["id"]
                results["moved_to_cassa"] += 1
            else:
                await db[COLLECTION_PRIMA_NOTA_BANCA].insert_one(movimento.copy())
                update_data["prima_nota_banca_id"] = movimento["id"]
                results["moved_to_banca"] += 1
            
            # Aggiorna fattura
            await db[Collections.INVOICES].update_one(
                {"_id": invoice["_id"]},
                {"$set": update_data}
            )
            
            results["processed"] += 1
            
        except Exception as e:
            results["errors"].append({
                "invoice": invoice.get("numero_fattura", "N/A"),
                "error": str(e)
            })
    
    return {
        "success": True,
        "message": f"Processate {results['processed']} fatture: {results['moved_to_cassa']} in cassa, {results['moved_to_banca']} in banca",
        **results
    }


# ============== STATISTICHE AUTOMATION ==============

@router.get("/stats")
async def get_automation_stats() -> Dict[str, Any]:
    """Statistiche per automazione prima nota."""
    db = Database.get_db()
    
    # Fatture non processate
    fatture_non_processate = await db[Collections.INVOICES].count_documents({
        "pagato": {"$ne": True}
    })
    
    # Fatture senza metodo pagamento
    fatture_senza_metodo = await db[Collections.INVOICES].count_documents({
        "metodo_pagamento": {"$exists": False}
    })
    
    # Movimenti prima nota
    cassa_count = await db[COLLECTION_PRIMA_NOTA_CASSA].count_documents({})
    banca_count = await db[COLLECTION_PRIMA_NOTA_BANCA].count_documents({})
    
    # Assegni
    assegni_totali = await db[COLLECTION_ASSEGNI].count_documents({})
    assegni_non_associati = await db[COLLECTION_ASSEGNI].count_documents({
        "fattura_collegata": None
    })
    
    # Fornitori con metodo pagamento configurato
    fornitori_con_metodo = await db[Collections.SUPPLIERS].count_documents({
        "metodo_pagamento": {"$exists": True, "$ne": None}
    })
    fornitori_totali = await db[Collections.SUPPLIERS].count_documents({})
    
    return {
        "fatture": {
            "non_processate": fatture_non_processate,
            "senza_metodo_pagamento": fatture_senza_metodo
        },
        "prima_nota": {
            "movimenti_cassa": cassa_count,
            "movimenti_banca": banca_count
        },
        "assegni": {
            "totali": assegni_totali,
            "non_associati": assegni_non_associati
        },
        "fornitori": {
            "totali": fornitori_totali,
            "con_metodo_pagamento": fornitori_con_metodo,
            "senza_metodo_pagamento": fornitori_totali - fornitori_con_metodo
        }
    }


# ============== IMPORT VERSAMENTI ==============

@router.post("/import-versamenti")
async def import_versamenti(
    file: UploadFile = File(..., description="File CSV versamenti formato banca")
) -> Dict[str, Any]:
    """
    Importa versamenti in banca da file CSV.
    
    FORMATO DEFINITIVO (CSV con delimitatore ;):
    - Ragione Sociale
    - Data contabile (DD/MM/YYYY)
    - Data valuta (DD/MM/YYYY)
    - Banca
    - Rapporto
    - Importo
    - Divisa
    - Descrizione
    - Categoria/sottocategoria
    - Hashtag
    """
    import pandas as pd
    
    if not file.filename.lower().endswith(('.xlsx', '.xls', '.csv')):
        raise HTTPException(status_code=400, detail="Solo file Excel o CSV supportati")
    
    content = await file.read()
    db = Database.get_db()
    now = datetime.now(timezone.utc).isoformat()
    
    results = {
        "imported": 0,
        "skipped": 0,
        "errors": [],
        "versamenti": []
    }
    
    try:
        if file.filename.lower().endswith('.csv'):
            # CSV con delimitatore ;
            for encoding in ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']:
                try:
                    df = pd.read_csv(io.BytesIO(content), sep=';', encoding=encoding)
                    break
                except Exception:
                    continue
        else:
            df = pd.read_excel(io.BytesIO(content))
        
        logger.info(f"Versamenti - Colonne trovate: {list(df.columns)}")
        
        for idx, row in df.iterrows():
            try:
                # Data contabile (formato DD/MM/YYYY)
                data_str = str(row.get('Data contabile', '')).strip()
                if not data_str or data_str == 'nan':
                    results["skipped"] += 1
                    continue
                
                data = parse_italian_date(data_str)
                if not data:
                    results["skipped"] += 1
                    continue
                
                # Importo
                importo_val = row.get('Importo', 0)
                if pd.isna(importo_val):
                    results["skipped"] += 1
                    continue
                
                if isinstance(importo_val, (int, float)):
                    importo = float(importo_val)
                else:
                    importo = parse_italian_amount(str(importo_val))
                
                if importo <= 0:
                    results["skipped"] += 1
                    continue
                
                # Descrizione
                descrizione = str(row.get('Descrizione', '')).strip()
                if not descrizione or descrizione == 'nan':
                    descrizione = f"Versamento del {data}"
                
                # CONTROLLO DUPLICATI
                existing_cassa = await db[COLLECTION_PRIMA_NOTA_CASSA].find_one({
                    "data": data,
                    "importo": importo,
                    "categoria": "Versamento"
                })
                
                if existing_cassa:
                    results["skipped"] += 1
                    results["errors"].append({"row": idx + 2, "error": f"Duplicato: versamento del {data} di €{importo}"})
                    continue
                
                # Versamento = USCITA dalla cassa (soldi vanno in banca)
                movimento_cassa = {
                    "id": str(uuid.uuid4()),
                    "data": data,
                    "tipo": "uscita",
                    "importo": importo,
                    "descrizione": descrizione,
                    "categoria": "Versamento",
                    "source": "csv_import",
                    "filename": file.filename,
                    "created_at": now
                }
                
                await db[COLLECTION_PRIMA_NOTA_CASSA].insert_one(movimento_cassa.copy())
                
                results["imported"] += 1
                results["versamenti"].append({
                    "data": data,
                    "importo": importo,
                    "descrizione": descrizione[:50]
                })
                
            except Exception as e:
                results["errors"].append({"row": idx + 2, "error": str(e)})
        
        return {
            "success": True,
            "message": f"Importati {results['imported']} versamenti",
            **results
        }
        
    except Exception as e:
        logger.error(f"Error importing versamenti: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== IMPORT POS ==============

@router.post("/import-pos")
async def import_pos(
    file: UploadFile = File(..., description="File Excel con incassi POS")
) -> Dict[str, Any]:
    """
    Importa incassi POS giornalieri da file Excel.
    
    LOGICA CORRETTA:
    - POS importato da Excel = POS manuale/reale → va in Prima Nota CASSA
    - Questo è il POS che TU hai contato la sera
    - Il confronto sarà poi con:
      1. pagato_elettronico dell'XML RT (controllo discrepanze giornaliere)
      2. accrediti POS in banca dall'estratto conto (riconciliazione bancaria)
    
    FORMATO DEFINITIVO (XLSX):
    - DATA (formato YYYY-MM-DD o datetime)
    - CONTO (sempre "pos")
    - IMPORTO (numero decimale)
    """
    import pandas as pd
    
    if not file.filename.lower().endswith(('.xlsx', '.xls', '.csv')):
        raise HTTPException(status_code=400, detail="Solo file Excel o CSV supportati")
    
    content = await file.read()
    db = Database.get_db()
    now = datetime.now(timezone.utc).isoformat()
    
    results = {
        "imported": 0,
        "skipped": 0,
        "errors": [],
        "pos_entries": []
    }
    
    try:
        if file.filename.lower().endswith('.csv'):
            for encoding in ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']:
                try:
                    df = pd.read_csv(io.BytesIO(content), sep=';', encoding=encoding)
                    break
                except Exception:
                    continue
        else:
            df = pd.read_excel(io.BytesIO(content))
        
        logger.info(f"POS - Colonne trovate: {list(df.columns)}")
        
        for idx, row in df.iterrows():
            try:
                # DATA - colonna esatta
                data_val = row.get('DATA')
                if pd.isna(data_val):
                    results["skipped"] += 1
                    continue
                
                # Se è datetime, formattalo
                if hasattr(data_val, 'strftime'):
                    data = data_val.strftime('%Y-%m-%d')
                else:
                    data = parse_italian_date(str(data_val))
                
                if not data:
                    results["skipped"] += 1
                    continue
                
                # IMPORTO - colonna esatta
                importo_val = row.get('IMPORTO', 0)
                if pd.isna(importo_val):
                    results["skipped"] += 1
                    continue
                
                if isinstance(importo_val, (int, float)):
                    totale = float(importo_val)
                else:
                    totale = parse_italian_amount(str(importo_val))
                
                if totale <= 0:
                    results["skipped"] += 1
                    continue
                
                # CONTROLLO DUPLICATI - nella stessa collection dove salviamo (prima_nota_cassa)
                logger.info(f"Checking for duplicate: data={data}, totale={totale}")
                existing_pos = await db[COLLECTION_PRIMA_NOTA_CASSA].find_one({
                    "data": data,
                    "categoria": "POS",
                    "source": {"$in": ["xlsx_import", "manual_pos", "excel_pos"]}
                })
                logger.info(f"Duplicate check result: {existing_pos}")
                
                if existing_pos:
                    results["skipped"] += 1
                    results["errors"].append({"row": idx + 2, "error": f"Duplicato: POS del {data}"})
                    continue
                
                # POS manuale/Excel → Prima Nota CASSA (uscita dalla cassa, i soldi vanno in banca)
                movimento = {
                    "id": str(uuid.uuid4()),
                    "data": data,
                    "tipo": "uscita",  # AVERE - escono dalla cassa verso banca
                    "importo": totale,
                    "descrizione": f"Incasso POS giornaliero del {data}",
                    "categoria": "POS",
                    "source": "xlsx_import",
                    "filename": file.filename,
                    "created_at": now
                }
                
                await db[COLLECTION_PRIMA_NOTA_CASSA].insert_one(movimento.copy())
                
                results["imported"] += 1
                results["pos_entries"].append({
                    "data": data,
                    "totale": totale
                })
                
            except Exception as e:
                results["errors"].append({"row": idx + 2, "error": str(e)})
        
        return {
            "success": True,
            "message": f"Importati {results['imported']} movimenti POS in Prima Nota Cassa",
            "nota": "POS manuale va in cassa come uscita. L'accredito bancario arriva dall'estratto conto.",
            **results
        }
        
    except Exception as e:
        logger.error(f"Error importing POS: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== IMPORT CORRISPETTIVI XML (NUOVA LOGICA 2026) ==============

@router.post("/import-corrispettivi-xml")
async def import_corrispettivi_xml(
    file: UploadFile = File(..., description="File XML corrispettivi da RT"),
    force_import: bool = Query(False, description="Se True, sovrascrive corrispettivi esistenti")
) -> Dict[str, Any]:
    """
    Importa corrispettivi da file XML del registratore telematico.
    
    LOGICA CORRETTA:
    - I dati XML vanno nella collection 'corrispettivi' (pagato_contanti + pagato_elettronico + IVA)
    - NON vanno in prima_nota_cassa (prima andava il totale lordo, SBAGLIATO)
    - In prima_nota_cassa andrà SOLO il pagato_contanti tramite sync separato
    - Il pagato_elettronico arriva in banca tramite accredito POS (estratto conto)
    
    Con force_import=True, sovrascrive sempre i dati esistenti.
    """
    import xml.etree.ElementTree as ET
    
    if not file.filename.lower().endswith('.xml'):
        raise HTTPException(status_code=400, detail="Solo file XML supportati")
    
    content = await file.read()
    db = Database.get_db()
    now = datetime.now(timezone.utc).isoformat()
    
    results = {
        "aggiornati": 0,
        "creati": 0,
        "skipped": 0,
        "errors": [],
        "dettagli": []
    }
    
    try:
        # Parse XML
        root = ET.fromstring(content)
        
        # Estrai DataOraRilevazione
        data_elem = root.find('.//{*}DataOraRilevazione')
        if data_elem is None:
            data_elem = root.find('.//DataOraRilevazione')
        
        if data_elem is None or not data_elem.text:
            raise HTTPException(status_code=400, detail="DataOraRilevazione non trovata nell'XML")
        
        # Parse data (formato: 2025-01-03T21:50:57+01:00)
        data = data_elem.text[:10]  # Prendi solo YYYY-MM-DD
        
        # Estrai Totali
        totali_elem = root.find('.//{*}Totali')
        if totali_elem is None:
            totali_elem = root.find('.//Totali')
        
        pagato_contanti = 0.0
        pagato_elettronico = 0.0
        
        if totali_elem is not None:
            pc_elem = totali_elem.find('{*}PagatoContanti') or totali_elem.find('PagatoContanti')
            pe_elem = totali_elem.find('{*}PagatoElettronico') or totali_elem.find('PagatoElettronico')
            
            if pc_elem is not None and pc_elem.text:
                pagato_contanti = float(pc_elem.text)
            if pe_elem is not None and pe_elem.text:
                pagato_elettronico = float(pe_elem.text)
        
        totale_xml = pagato_contanti + pagato_elettronico
        
        # Estrai dettaglio IVA dai Riepilogo
        dettaglio_iva = []
        totale_imponibile = 0.0
        totale_imposta = 0.0
        
        for riepilogo in root.findall('.//{*}Riepilogo') or root.findall('.//Riepilogo'):
            iva_elem = riepilogo.find('{*}IVA') or riepilogo.find('IVA')
            ammontare_elem = riepilogo.find('{*}Ammontare') or riepilogo.find('Ammontare')
            
            aliquota = 0.0
            imposta = 0.0
            ammontare = 0.0
            
            if iva_elem is not None:
                aliq_elem = iva_elem.find('{*}AliquotaIVA') or iva_elem.find('AliquotaIVA')
                imp_elem = iva_elem.find('{*}Imposta') or iva_elem.find('Imposta')
                
                if aliq_elem is not None and aliq_elem.text:
                    aliquota = float(aliq_elem.text)
                if imp_elem is not None and imp_elem.text:
                    imposta = float(imp_elem.text)
            
            if ammontare_elem is not None and ammontare_elem.text:
                ammontare = float(ammontare_elem.text)
            
            if ammontare > 0 or imposta > 0:
                dettaglio_iva.append({
                    "aliquota": aliquota,
                    "imponibile": ammontare,
                    "imposta": imposta
                })
                totale_imponibile += ammontare
                totale_imposta += imposta
        
        # CERCA corrispettivo esistente per quella data nella collection CORRISPETTIVI
        existing = await db["corrispettivi"].find_one({"data": data})
        
        corrispettivo_data = {
            "totale": totale_xml,
            "pagato_contanti": pagato_contanti,
            "pagato_elettronico": pagato_elettronico,
            "imponibile": totale_imponibile,
            "imposta": totale_imposta,
            "dettaglio_iva": dettaglio_iva,
            "xml_filename": file.filename,
            "xml_imported_at": now,
            "iva_popolata": True,
            "source": "xml_import",
            "updated_at": now
        }
        
        if existing and not force_import:
            # AGGIORNA i campi
            await db["corrispettivi"].update_one(
                {"data": data},
                {"$set": corrispettivo_data}
            )
            
            results["aggiornati"] += 1
            results["dettagli"].append({
                "data": data,
                "azione": "AGGIORNATO",
                "contanti": pagato_contanti,
                "elettronico": pagato_elettronico,
                "totale": totale_xml
            })
            
        elif existing and force_import:
            # SOVRASCRIVE
            await db["corrispettivi"].update_one(
                {"data": data},
                {"$set": corrispettivo_data}
            )
            
            results["aggiornati"] += 1
            
        else:
            # CREA nuovo corrispettivo
            import uuid as _uuid
            corrispettivo_data.update({
                "id": str(_uuid.uuid4()),
                "data": data,
                "created_at": now
            })
            
            await db["corrispettivi"].insert_one(corrispettivo_data.copy())
            
            results["creati"] += 1
            results["dettagli"].append({
                "data": data,
                "azione": "CREATO",
                "contanti": pagato_contanti,
                "elettronico": pagato_elettronico,
                "totale": totale_xml
            })
        
        # AGGIORNA anche prima_nota_cassa SE esiste un corrispettivo manuale per quella data
        # (aggiorna solo i dettagli IVA, NON l'importo che resta quello manuale)
        existing_cassa = await db[COLLECTION_PRIMA_NOTA_CASSA].find_one({
            "data": data,
            "categoria": "Corrispettivi"
        })
        if existing_cassa:
            await db[COLLECTION_PRIMA_NOTA_CASSA].update_one(
                {"id": existing_cassa["id"]},
                {"$set": {
                    "pagato_contanti": pagato_contanti,
                    "pagato_elettronico": pagato_elettronico,
                    "imponibile": totale_imponibile,
                    "imposta": totale_imposta,
                    "dettaglio_iva": dettaglio_iva,
                    "xml_filename": file.filename,
                    "iva_popolata": True
                }}
            )
        
        return {
            "success": True,
            "message": f"Corrispettivo del {data} salvato in collection corrispettivi (contanti: €{pagato_contanti}, elettronico: €{pagato_elettronico})",
            "nota": "L'XML va nella collection corrispettivi. Solo i contanti andranno in cassa tramite sync.",
            **results
        }
        
    except ET.ParseError as e:
        raise HTTPException(status_code=400, detail=f"Errore parsing XML: {str(e)}")
    except Exception as e:
        logger.error(f"Error importing corrispettivi XML: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import-corrispettivi-xml-multipli")
async def import_corrispettivi_xml_multipli(
    files: List[UploadFile] = File(..., description="File XML corrispettivi multipli")
) -> Dict[str, Any]:
    """Importa multipli file XML corrispettivi."""
    results = {
        "totale_file": len(files),
        "importati": 0,
        "duplicati": 0,
        "errori": 0,
        "dettagli": []
    }
    
    for file in files:
        try:
            # Chiama l'import singolo
            result = await import_corrispettivi_xml(file)
            
            if result.get("success"):
                results["importati"] += 1
            else:
                results["duplicati"] += 1
            
            results["dettagli"].append({
                "filename": file.filename,
                "success": result.get("success"),
                "message": result.get("message")
            })
            
        except HTTPException as e:
            results["errori"] += 1
            results["dettagli"].append({
                "filename": file.filename,
                "success": False,
                "error": e.detail
            })
        except Exception as e:
            results["errori"] += 1
            results["dettagli"].append({
                "filename": file.filename,
                "success": False,
                "error": str(e)
            })
    
    return {
        "success": True,
        "message": f"Importati {results['importati']}/{results['totale_file']} corrispettivi",
        **results
    }

