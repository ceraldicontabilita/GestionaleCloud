"""
Parser PDF per Piani di Ammortamento Mutui
==========================================

Estrae le rate dai PDF BPM (Banca Popolare di Milano)
e le importa nel database MongoDB.
"""

import re
import pdfplumber
from datetime import datetime
from typing import List, Dict, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
import tempfile
import os
import logging
import uuid

from app.database import Database

router = APIRouter(tags=["Mutui Parser PDF"])
logger = logging.getLogger(__name__)


def parse_mutuo_pdf(pdf_path: str) -> Dict:
    """
    Parsa un PDF di piano ammortamento BPM e estrae tutti i dati.
    
    Returns:
        Dict con dati mutuo e lista rate
    """
    mutuo_data = {
        "intestatario": None,
        "tipo_finanziamento": None,
        "importo_accordato": 0.0,
        "numero_delibera": None,
        "rate_residue_dichiarate": 0,
        "rate": []
    }
    
    all_text = ""
    
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                all_text += text + "\n"
    
    # Estrai intestatario
    match = re.search(r'Rag\.Soc\./Intestatario:\s*(.+?)(?:\n|Tipo)', all_text)
    if match:
        mutuo_data["intestatario"] = match.group(1).strip()
    
    # Estrai tipo finanziamento
    match = re.search(r'Tipo finanziamento:\s*(.+?)\s*Importo accordato', all_text)
    if match:
        mutuo_data["tipo_finanziamento"] = match.group(1).strip()
    
    # Estrai importo accordato
    match = re.search(r'Importo accordato:\s*([\d.,]+)\s*EUR', all_text)
    if match:
        importo_str = match.group(1).replace('.', '').replace(',', '.')
        mutuo_data["importo_accordato"] = float(importo_str)
    
    # Estrai numero delibera
    match = re.search(r'Numero delibera:\s*(\d+)', all_text)
    if match:
        mutuo_data["numero_delibera"] = match.group(1)
    
    # Estrai rate residue
    match = re.search(r'Rate residue:\s*(\d+)', all_text)
    if match:
        mutuo_data["rate_residue_dichiarate"] = int(match.group(1))
    
    # Pattern per le rate:
    # Numero rata | Scadenza | Importo | Quota capitale | Quota interessi | Stato
    # Esempio: "1 17/03/2021 4.908,98 EUR 4.558,42 EUR 347,81 EUR Pagata"
    rate_pattern = re.compile(
        r'(\d+)\s+'  # Numero rata
        r'(\d{2}/\d{2}/\d{4})\s+'  # Data scadenza
        r'([\d.,]+)\s*EUR\s+'  # Importo totale
        r'([\d.,]+)\s*EUR\s+'  # Quota capitale
        r'([\d.,]+)\s*EUR\s+'  # Quota interessi
        r'(Pagata|Da pagare|Scaduta)',  # Stato
        re.IGNORECASE
    )
    
    for match in rate_pattern.finditer(all_text):
        numero_rata = int(match.group(1))
        data_scadenza = match.group(2)
        importo_totale = float(match.group(3).replace('.', '').replace(',', '.'))
        quota_capitale = float(match.group(4).replace('.', '').replace(',', '.'))
        quota_interessi = float(match.group(5).replace('.', '').replace(',', '.'))
        stato = match.group(6).capitalize()
        
        rata = {
            "numero_rata": numero_rata,
            "data_scadenza": data_scadenza,
            "importo_totale": importo_totale,
            "quota_capitale": quota_capitale,
            "quota_interessi": quota_interessi,
            "stato": stato,
            "riconciliata": False,
            "movimento_bancario_id": None,
            "data_pagamento_effettivo": None,
            "note_riconciliazione": None
        }
        mutuo_data["rate"].append(rata)
    
    # Ordina rate per numero
    mutuo_data["rate"].sort(key=lambda x: x["numero_rata"])
    
    # Calcola statistiche
    rate_pagate = sum(1 for r in mutuo_data["rate"] if r["stato"] == "Pagata")
    rate_da_pagare = sum(1 for r in mutuo_data["rate"] if r["stato"] == "Da pagare")
    
    totale_pagato_capitale = sum(r["quota_capitale"] for r in mutuo_data["rate"] if r["stato"] == "Pagata")
    totale_pagato_interessi = sum(r["quota_interessi"] for r in mutuo_data["rate"] if r["stato"] == "Pagata")
    totale_pagato = sum(r["importo_totale"] for r in mutuo_data["rate"] if r["stato"] == "Pagata")
    
    debito_residuo_capitale = sum(r["quota_capitale"] for r in mutuo_data["rate"] if r["stato"] != "Pagata")
    debito_residuo_interessi = sum(r["quota_interessi"] for r in mutuo_data["rate"] if r["stato"] != "Pagata")
    debito_residuo_totale = sum(r["importo_totale"] for r in mutuo_data["rate"] if r["stato"] != "Pagata")
    
    # Trova prossima rata da pagare
    prossima_rata = None
    for rata in mutuo_data["rate"]:
        if rata["stato"] == "Da pagare":
            prossima_rata = rata
            break
    
    mutuo_data["statistiche"] = {
        "totale_rate": len(mutuo_data["rate"]),
        "rate_pagate": rate_pagate,
        "rate_da_pagare": rate_da_pagare,
        "totale_pagato_capitale": round(totale_pagato_capitale, 2),
        "totale_pagato_interessi": round(totale_pagato_interessi, 2),
        "totale_pagato": round(totale_pagato, 2),
        "debito_residuo_capitale": round(debito_residuo_capitale, 2),
        "debito_residuo_interessi": round(debito_residuo_interessi, 2),
        "debito_residuo_totale": round(debito_residuo_totale, 2),
        "prossima_rata": prossima_rata
    }
    
    return mutuo_data


@router.post("/parse-pdf", summary="Parsa PDF piano ammortamento")
async def parse_mutuo_pdf_endpoint(file: UploadFile = File(...)):
    """
    Carica un PDF di piano ammortamento e lo parsa per estrarre le rate.
    NON salva nel database, restituisce solo i dati estratti per review.
    """
    try:
        # Verifica estensione
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Il file deve essere un PDF")
        
        # Salva temporaneamente
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
        
        try:
            # Parsa il PDF
            result = parse_mutuo_pdf(tmp_path)
            
            return {
                "success": True,
                "message": f"PDF parsato con successo. Trovate {len(result['rate'])} rate.",
                "data": result
            }
            
        finally:
            # Pulisci file temporaneo
            os.unlink(tmp_path)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore parsing PDF: {e}")
        raise HTTPException(status_code=500, detail=f"Errore parsing PDF: {str(e)}")


@router.post("/import-pdf", summary="Importa mutuo da PDF nel database")
async def import_mutuo_from_pdf(
    file: UploadFile = File(...),
    nome_mutuo: Optional[str] = None,
    aggiorna_esistente: bool = False
):
    """
    Parsa un PDF di piano ammortamento e importa/aggiorna il mutuo nel database.
    
    Parametri:
    - file: PDF del piano ammortamento
    - nome_mutuo: Nome descrittivo (opzionale, default dal PDF)
    - aggiorna_esistente: Se True, aggiorna mutuo esistente con stesso numero_delibera
    """
    try:
        db = Database.get_db()
        
        # Verifica estensione
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Il file deve essere un PDF")
        
        # Salva temporaneamente
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
        
        try:
            # Parsa il PDF
            parsed = parse_mutuo_pdf(tmp_path)
            
            if not parsed["numero_delibera"]:
                raise HTTPException(status_code=400, detail="Impossibile estrarre numero delibera dal PDF")
            
            # Genera ID mutuo
            mutuo_id = f"mutuo_{parsed['numero_delibera']}"
            
            # Verifica se esiste già
            existing = await db.mutui.find_one({"mutuo_id": mutuo_id})
            
            if existing and not aggiorna_esistente:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Mutuo con delibera {parsed['numero_delibera']} già esistente. Usa aggiorna_esistente=true per aggiornare."
                )
            
            # Prepara documento
            stats = parsed["statistiche"]
            documento = {
                "mutuo_id": mutuo_id,
                "nome": nome_mutuo or f"Mutuo {parsed['tipo_finanziamento'] or 'Generico'}",
                "tipo_finanziamento": parsed["tipo_finanziamento"],
                "importo_accordato": parsed["importo_accordato"],
                "numero_delibera": parsed["numero_delibera"],
                "banca": "BPM - Banca Popolare di Milano",
                "intestatario": parsed["intestatario"],
                
                "rate": parsed["rate"],
                "totale_rate": stats["totale_rate"],
                
                "rate_pagate": stats["rate_pagate"],
                "rate_da_pagare": stats["rate_da_pagare"],
                "rate_residue_dichiarate": parsed["rate_residue_dichiarate"],
                
                "totale_pagato_capitale": stats["totale_pagato_capitale"],
                "totale_pagato_interessi": stats["totale_pagato_interessi"],
                "totale_pagato": stats["totale_pagato"],
                
                "debito_residuo_capitale": stats["debito_residuo_capitale"],
                "debito_residuo_interessi": stats["debito_residuo_interessi"],
                "debito_residuo_totale": stats["debito_residuo_totale"],
                
                "prossima_data_scadenza": stats["prossima_rata"]["data_scadenza"] if stats["prossima_rata"] else None,
                "prossimo_importo": stats["prossima_rata"]["importo_totale"] if stats["prossima_rata"] else None,
                
                "rate_riconciliate": 0,
                "rate_non_riconciliate": stats["rate_pagate"],
                "percentuale_riconciliazione": 0.0,
                
                "updated_at": datetime.now(),
                "file_piano_ammortamento": file.filename,
                "allegati": [],
                "note": f"Importato da PDF il {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            }
            
            if existing:
                # Aggiorna
                documento.pop("created_at", None)
                await db.mutui.update_one(
                    {"mutuo_id": mutuo_id},
                    {"$set": documento}
                )
                action = "aggiornato"
            else:
                # Inserisci
                documento["created_at"] = datetime.now()
                documento["created_by"] = "import_pdf"
                await db.mutui.insert_one(documento)
                action = "importato"
            
            return {
                "success": True,
                "message": f"Mutuo {action} con successo",
                "data": {
                    "mutuo_id": mutuo_id,
                    "nome": documento["nome"],
                    "numero_delibera": parsed["numero_delibera"],
                    "importo_accordato": parsed["importo_accordato"],
                    "rate_totali": stats["totale_rate"],
                    "rate_pagate": stats["rate_pagate"],
                    "rate_da_pagare": stats["rate_da_pagare"],
                    "totale_pagato": stats["totale_pagato"],
                    "debito_residuo": stats["debito_residuo_totale"]
                }
            }
            
        finally:
            os.unlink(tmp_path)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore import PDF: {e}")
        raise HTTPException(status_code=500, detail=f"Errore import: {str(e)}")


@router.post("/parse-multiple", summary="Parsa multipli PDF")
async def parse_multiple_pdfs(files: List[UploadFile] = File(...)):
    """
    Parsa multipli PDF di piani ammortamento in un'unica chiamata.
    Restituisce i dati estratti senza salvare nel database.
    """
    results = []
    
    for file in files:
        try:
            if not file.filename.lower().endswith('.pdf'):
                results.append({
                    "filename": file.filename,
                    "success": False,
                    "error": "Non è un file PDF"
                })
                continue
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                content = await file.read()
                tmp.write(content)
                tmp_path = tmp.name
            
            try:
                parsed = parse_mutuo_pdf(tmp_path)
                results.append({
                    "filename": file.filename,
                    "success": True,
                    "data": parsed
                })
            finally:
                os.unlink(tmp_path)
                
        except Exception as e:
            results.append({
                "filename": file.filename,
                "success": False,
                "error": str(e)
            })
    
    return {
        "success": True,
        "total_files": len(files),
        "parsed_successfully": sum(1 for r in results if r["success"]),
        "results": results
    }
