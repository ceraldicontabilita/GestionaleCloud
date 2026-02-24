"""
Bank Statement PDF Parser Router
Parser per estratti conto BANCO BPM
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from typing import Dict, Any, List, Optional
import logging
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
router = APIRouter()


def parse_date(date_str: str) -> Optional[str]:
    """Converte data da formato DD/MM/YY a YYYY-MM-DD"""
    if not date_str:
        return None
    try:
        date_str = date_str.strip()
        if re.match(r'^\d{2}/\d{2}/\d{2}$', date_str):
            parts = date_str.split('/')
            day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
            full_year = 2000 + year if year < 50 else 1900 + year
            return f"{full_year}-{month:02d}-{day:02d}"
        if re.match(r'^\d{2}\.\d{2}\.\d{4}$', date_str):
            parts = date_str.split('.')
            day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
            return f"{year}-{month:02d}-{day:02d}"
        return None
    except (ValueError, TypeError, IndexError):
        return None


def parse_amount(amount_str: str) -> Optional[float]:
    """Converte importo da formato italiano a float"""
    if not amount_str:
        return None
    try:
        amount_str = amount_str.strip()
        is_negative = amount_str.startswith('-') or amount_str.startswith('- ')
        amount_str = amount_str.replace('-', '').replace(' ', '').replace('€', '')
        amount_str = amount_str.replace('.', '').replace(',', '.')
        value = float(amount_str)
        return -value if is_negative else value
    except (ValueError, TypeError):
        return None


def is_date_line(line: str) -> bool:
    """Verifica se la linea è una data DD/MM/YY"""
    return bool(re.match(r'^\d{2}/\d{2}/\d{2}$', line.strip()))


def is_amount_line(line: str) -> bool:
    """Verifica se la linea è un importo"""
    line = line.strip()
    # Pattern: "- 1.234,56" o "1.234,56" o "- 12,34"
    return bool(re.match(r'^-?\s*\d{1,3}(?:\.\d{3})*,\d{2}$', line))


def extract_banco_bpm_transactions(text: str) -> List[Dict[str, Any]]:
    """
    Estrae le transazioni dal testo BANCO BPM.
    
    Struttura tipica (ogni transazione su più righe):
    - DATA_CONTABILE (DD/MM/YY)
    - DATA_VALUTA (DD/MM/YY)
    - DESCRIZIONE (testo)
    - IMPORTO (- X.XXX,XX per uscite, X.XXX,XX per entrate)
    - DATA_DISPONIBILE (DD/MM/YY)
    - [eventuali altre righe di descrizione]
    """
    transactions = []
    lines = text.split('\n')
    lines = [line.strip() for line in lines if line.strip()]
    
    i = 0
    while i < len(lines) - 4:  # Minimo 5 righe per una transazione
        line = lines[i]
        
        # Cerca una data come inizio di transazione
        if is_date_line(line):
            data_contabile = line
            
            # Verifica se la prossima riga è anche una data (data valuta)
            if i + 1 < len(lines) and is_date_line(lines[i + 1]):
                data_valuta = lines[i + 1]
                
                # Cerca la descrizione e l'importo nelle righe successive
                descrizione_parts = []
                importo = None
                data_disponibile = None
                j = i + 2
                
                while j < len(lines) and j < i + 10:  # Max 10 righe per transazione
                    current_line = lines[j]
                    
                    if is_amount_line(current_line):
                        importo = parse_amount(current_line)
                        j += 1
                        # La prossima riga potrebbe essere data disponibile
                        if j < len(lines) and is_date_line(lines[j]):
                            data_disponibile = lines[j]
                            j += 1
                        break
                    elif is_date_line(current_line):
                        # Nuova transazione inizia qui
                        break
                    else:
                        # È parte della descrizione
                        # Ignora righe che sembrano header
                        if current_line not in ['DATA', 'CONTABILE', 'VALUTA', 'DISPONIBILE', 
                                                '*1', '*2', '*3', 'USCITE', 'ENTRATE',
                                                'ATM', 'WEB', 'APP', 'DESCRIZIONE DELLE OPERAZIONI']:
                            descrizione_parts.append(current_line)
                    j += 1
                
                # Se abbiamo trovato un importo, crea la transazione
                if importo is not None:
                    descrizione = ' '.join(descrizione_parts)
                    
                    # Salta le righe "SALDO INIZIALE"
                    if 'SALDO INIZIALE' in descrizione.upper():
                        i = j
                        continue
                    
                    transaction = {
                        "data_contabile": parse_date(data_contabile),
                        "data_valuta": parse_date(data_valuta),
                        "data_disponibile": parse_date(data_disponibile) if data_disponibile else None,
                        "uscita": abs(importo) if importo < 0 else None,
                        "entrata": importo if importo > 0 else None,
                        "descrizione": descrizione[:500] if descrizione else "Movimento",
                    }
                    
                    if transaction["data_contabile"]:
                        transactions.append(transaction)
                    
                    i = j
                    continue
        
        i += 1
    
    return transactions


def parse_banco_bpm_statement(text: str) -> Dict[str, Any]:
    """Parser per estratti conto BANCO BPM"""
    result = {
        "banca": "BANCO BPM",
        "tipo_documento": "ESTRATTO CONTO CORRENTE",
        "intestatario": None,
        "iban": None,
        "periodo_riferimento": None,
        "saldo_iniziale": None,
        "saldo_finale": None,
        "movimenti": [],
        "totale_entrate": 0,
        "totale_uscite": 0,
    }
    
    # Estrai intestatario
    if "CERALDI GROUP" in text.upper():
        result["intestatario"] = "CERALDI GROUP S.R.L."
    else:
        match = re.search(r'Intestato a[:\s\n]+([A-Z][A-Z0-9\s.]+(?:S\.?R\.?L\.?|S\.?P\.?A\.?))', text, re.IGNORECASE)
        if match:
            result["intestatario"] = match.group(1).strip()
    
    # Estrai IBAN
    iban_text = text.replace('\n', ' ')
    iban_match = re.search(r'IT\s*\d{2}\s*[A-Z]\s*\d{5}\s*\d{5}\s*\d{12}', iban_text)
    if iban_match:
        result["iban"] = iban_match.group(0).replace(' ', '')
    
    # Estrai periodo
    periodo_match = re.search(r'AL\s+(\d{2}\.\d{2}\.\d{4})', text)
    if periodo_match:
        result["periodo_riferimento"] = parse_date(periodo_match.group(1))
    
    # Estrai saldo iniziale
    saldo_match = re.search(r'SALDO\s+INIZIALE[^\d]*([\d.,]+)', text, re.IGNORECASE)
    if saldo_match:
        result["saldo_iniziale"] = parse_amount(saldo_match.group(1))
    
    # Estrai saldo finale
    for pattern in [r'Saldo\s+liquido\s+finale[^\d]*([\d.,]+)', 
                    r'SALDO\s+CONTABILE\s+FINALE[^\d]*([\d.,]+)']:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["saldo_finale"] = parse_amount(match.group(1))
            break
    
    # Estrai movimenti
    result["movimenti"] = extract_banco_bpm_transactions(text)
    
    # Calcola totali
    for mov in result["movimenti"]:
        if mov.get("entrata"):
            result["totale_entrate"] += mov["entrata"]
        if mov.get("uscita"):
            result["totale_uscite"] += mov["uscita"]
    
    return result


@router.post("/parse", summary="Parse bank statement PDF")
async def parse_bank_statement(file: UploadFile = File(...)) -> Dict[str, Any]:
    """Analizza un PDF di estratto conto bancario"""
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Il file deve essere un PDF")
    
    try:
        content = await file.read()
        
        import fitz
        pdf_document = fitz.open(stream=content, filetype="pdf")
        text = ""
        num_pages = len(pdf_document)
        for page_num in range(num_pages):
            page = pdf_document[page_num]
            text += page.get_text() + "\n"
        pdf_document.close()
        
        result = parse_banco_bpm_statement(text)
        result["filename"] = file.filename
        result["pagine_totali"] = num_pages
        
        return {
            "success": True,
            "data": result,
            "message": f"Estratte {len(result['movimenti'])} transazioni da {num_pages} pagine"
        }
        
    except Exception as e:
        logger.error(f"Errore parsing PDF: {e}")
        raise HTTPException(status_code=500, detail=f"Errore parsing PDF: {str(e)}")


@router.post("/import", summary="Import bank statement to Prima Nota")
async def import_bank_statement(
    file: UploadFile = File(...),
    anno: int = Query(..., description="Anno di riferimento"),
    auto_riconcilia: bool = Query(False)
) -> Dict[str, Any]:
    """Importa l'estratto conto nella Prima Nota Banca"""
    from app.database import Database
    
    await file.seek(0)
    parse_result = await parse_bank_statement(file)
    
    if not parse_result["success"]:
        raise HTTPException(status_code=400, detail="Errore nel parsing del PDF")
    
    data = parse_result["data"]
    movimenti = data.get("movimenti", [])
    
    if not movimenti:
        return {"success": False, "message": "Nessun movimento trovato", "imported": 0}
    
    db = Database.get_db()
    imported = 0
    skipped = 0
    errors = []
    
    for mov in movimenti:
        try:
            data_contabile = mov.get("data_contabile")
            importo = mov.get("entrata") or mov.get("uscita")
            
            if not data_contabile or not importo:
                skipped += 1
                continue
            
            existing = await db["prima_nota"].find_one({
                "data": data_contabile,
                "importo": importo,
                "tipo": "banca"
            })
            
            if existing:
                skipped += 1
                continue
            
            tipo_movimento = "entrata" if mov.get("entrata") else "uscita"
            importo_finale = mov.get("entrata") or mov.get("uscita")
            
            prima_nota_record = {
                "data": data_contabile,
                "data_valuta": mov.get("data_valuta"),
                "tipo": "banca",
                "tipo_movimento": tipo_movimento,
                "importo": importo_finale,
                "descrizione": mov.get("descrizione", "Movimento importato"),
                "anno": anno,
                "mese": int(data_contabile.split('-')[1]) if data_contabile else None,
                "fonte": "estratto_conto_import",
                "filename_origine": data.get("filename"),
                "riconciliato": False,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            await db["prima_nota"].insert_one(prima_nota_record.copy())
            imported += 1
            
        except Exception as e:
            errors.append(f"Errore: {str(e)[:50]}")
    
    return {
        "success": True,
        "imported": imported,
        "skipped": skipped,
        "total": len(movimenti),
        "errors": errors[:10],
        "saldo_iniziale": data.get("saldo_iniziale"),
        "saldo_finale": data.get("saldo_finale"),
        "totale_entrate": data.get("totale_entrate"),
        "totale_uscite": data.get("totale_uscite")
    }


@router.get("/preview", summary="Info endpoint")
async def preview_statement() -> Dict[str, Any]:
    return {
        "message": "Usa POST /api/estratto-conto/parse per caricare un PDF",
        "supported_banks": ["BANCO BPM", "Nexi Carta di Credito"],
        "expected_format": "Estratto conto corrente ordinario PDF o estratto conto carta Nexi"
    }


@router.post("/parse-nexi", summary="Parse Nexi credit card statement PDF")
async def parse_nexi_statement(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Analizza un PDF di estratto conto carta di credito Nexi/Banco BPM.
    
    Estrae:
    - Metadata (data, intestatario, numero carta, totali)
    - Lista transazioni con categorizzazione automatica
    """
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Il file deve essere un PDF")
    
    try:
        from app.parsers.estratto_conto_nexi_parser import parse_estratto_conto_nexi
        
        content = await file.read()
        result = parse_estratto_conto_nexi(content)
        result["filename"] = file.filename
        
        if result.get("success"):
            return {
                "success": True,
                "data": result,
                "message": f"Estratte {result.get('totale_transazioni', 0)} transazioni"
            }
        else:
            raise HTTPException(status_code=400, detail=result.get("error", "Errore nel parsing"))
        
    except Exception as e:
        logger.error(f"Errore parsing Nexi PDF: {e}")
        raise HTTPException(status_code=500, detail=f"Errore parsing PDF: {str(e)}")


@router.post("/import-nexi", summary="Import Nexi statement to database")
async def import_nexi_statement(
    file: UploadFile = File(...),
    anno: int = Query(..., description="Anno di riferimento")
) -> Dict[str, Any]:
    """
    Importa l'estratto conto carta Nexi nel database.
    
    Salva le transazioni in una collezione dedicata 'estratto_conto_nexi'
    per successiva riconciliazione.
    """
    from app.database import Database
    from datetime import datetime, timezone
    import uuid
    
    # Prima fai il parsing
    await file.seek(0)
    parse_result = await parse_nexi_statement(file)
    
    if not parse_result.get("success"):
        raise HTTPException(status_code=400, detail="Errore nel parsing del PDF")
    
    data = parse_result["data"]
    transazioni = data.get("transazioni", [])
    metadata = data.get("metadata", {})
    
    if not transazioni:
        return {"success": False, "message": "Nessuna transazione trovata", "imported": 0}
    
    db = Database.get_db()
    imported = 0
    skipped = 0
    errors = []
    
    # ID univoco per questo import
    import_id = str(uuid.uuid4())[:8]
    import_timestamp = datetime.now(timezone.utc).isoformat()
    
    for tx in transazioni:
        try:
            data_tx = tx.get("data")
            importo = tx.get("importo")
            descrizione = tx.get("descrizione", "")
            
            if not data_tx or importo is None:
                skipped += 1
                continue
            
            # Controlla duplicati
            existing = await db["estratto_conto_nexi"].find_one({
                "data": data_tx,
                "importo": importo,
                "descrizione": descrizione
            })
            
            if existing:
                skipped += 1
                continue
            
            record = {
                "id": f"nexi-{import_id}-{imported}",
                "data": data_tx,
                "data_originale": tx.get("data_originale"),
                "descrizione": descrizione,
                "importo": importo,
                "tipo": tx.get("tipo", "addebito"),
                "categoria": tx.get("categoria", "Altro"),
                "anno": anno,
                "mese": int(data_tx.split('-')[1]) if data_tx and '-' in data_tx else None,
                "fonte": "estratto_conto_nexi",
                "filename_origine": data.get("filename"),
                "numero_carta": metadata.get("numero_carta_mascherato"),
                "riconciliato": False,
                "fattura_id": None,
                "import_id": import_id,
                "created_at": import_timestamp
            }
            
            await db["estratto_conto_nexi"].insert_one(record.copy())
            imported += 1
            
        except Exception as e:
            errors.append(f"Errore riga: {str(e)[:50]}")
    
    return {
        "success": True,
        "imported": imported,
        "skipped": skipped,
        "total": len(transazioni),
        "errors": errors[:10] if errors else [],
        "import_id": import_id,
        "metadata": metadata,
        "totale_importo": data.get("totale_importo", 0)
    }


@router.get("/nexi/movimenti", summary="Lista movimenti Nexi importati")
async def get_nexi_movimenti(
    anno: Optional[int] = Query(None),
    mese: Optional[int] = Query(None),
    categoria: Optional[str] = Query(None),
    riconciliato: Optional[bool] = Query(None),
    limit: int = Query(100, le=500),
    skip: int = Query(0)
) -> Dict[str, Any]:
    """Recupera i movimenti Nexi importati con filtri opzionali."""
    from app.database import Database
    
    db = Database.get_db()
    query = {}
    
    if anno:
        query["anno"] = anno
    if mese:
        query["mese"] = mese
    if categoria:
        query["categoria"] = categoria
    if riconciliato is not None:
        query["riconciliato"] = riconciliato
    
    cursor = db["estratto_conto_nexi"].find(query, {"_id": 0}).sort("data", -1).skip(skip).limit(limit)
    movimenti = await cursor.to_list(limit)
    
    total = await db["estratto_conto_nexi"].count_documents(query)
    
    # Statistiche per categoria
    pipeline = [
        {"$match": query},
        {"$group": {
            "_id": "$categoria",
            "count": {"$sum": 1},
            "totale": {"$sum": "$importo"}
        }}
    ]
    stats_cursor = db["estratto_conto_nexi"].aggregate(pipeline)
    stats = await stats_cursor.to_list(100)
    
    return {
        "success": True,
        "movimenti": movimenti,
        "total": total,
        "statistiche_categoria": {s["_id"]: {"count": s["count"], "totale": s["totale"]} for s in stats}
    }
