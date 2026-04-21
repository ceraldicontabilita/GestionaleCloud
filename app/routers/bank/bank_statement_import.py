"""
Bank Statement Import Router - Import estratto conto bancario.
Parsa PDF/Excel/CSV estratto conto e riconcilia con Prima Nota Banca.
Supporta formati: Intesa Sanpaolo, UniCredit, BNL, Banca Sella, generico.
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import uuid
import logging
import io
import re

from app.database import Database
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()

# Collections
COLLECTION_PRIMA_NOTA_BANCA = "prima_nota_banca"
COLLECTION_BANK_STATEMENTS = "bank_statements_imported"


# ============== UTILITY FUNCTIONS ==============

def parse_italian_amount(amount_str: str) -> float:
    """Converte importo italiano (es. -704,7 o 1.530,9) in float."""
    if not amount_str:
        return 0.0
    amount_str = str(amount_str).strip()
    # Rimuovi simbolo valuta e spazi
    amount_str = re.sub(r'[€EUR\s]', '', amount_str)
    # Gestisci segno negativo in diverse posizioni
    is_negative = '-' in amount_str or amount_str.endswith('-')
    amount_str = amount_str.replace('-', '')
    # Rimuovi punti come separatore migliaia
    amount_str = amount_str.replace(".", "")
    # Sostituisci virgola con punto per decimali
    amount_str = amount_str.replace(",", ".")
    try:
        value = float(amount_str)
        return -value if is_negative else value
    except (ValueError, TypeError):
        return 0.0


def parse_italian_date(date_str: str) -> str:
    """Converte data italiana (gg/mm/aaaa o gg-mm-aaaa) in formato ISO (YYYY-MM-DD)."""
    if not date_str:
        return ""
    try:
        date_str = str(date_str).strip()
        
        # Formato gg/mm/aaaa o gg/mm/aa
        if "/" in date_str:
            parts = date_str.split("/")
            if len(parts) == 3:
                day, month, year = parts[0][:2], parts[1][:2], parts[2][:4]
                if len(year) == 2:
                    year = "20" + year if int(year) < 50 else "19" + year
                return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        
        # Formato gg-mm-aaaa
        elif "-" in date_str:
            parts = date_str.split("-")
            if len(parts) == 3:
                # Check if already ISO format
                if len(parts[0]) == 4:
                    return date_str[:10]
                day, month, year = parts[0][:2], parts[1][:2], parts[2][:4]
                if len(year) == 2:
                    year = "20" + year if int(year) < 50 else "19" + year
                return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        
        # Formato ggmmaaaa (senza separatori)
        elif len(date_str) == 8 and date_str.isdigit():
            return f"{date_str[4:8]}-{date_str[2:4]}-{date_str[0:2]}"
        
        return date_str
    except (ValueError, TypeError, IndexError):
        return date_str


def detect_bank_format(text: str, tables: List) -> str:
    """Rileva il formato bancario dal contenuto."""
    text_upper = text.upper() if text else ""
    
    if "INTESA SANPAOLO" in text_upper or "GRUPPO INTESA" in text_upper:
        return "intesa"
    elif "UNICREDIT" in text_upper:
        return "unicredit"
    elif "BNL" in text_upper or "PARIBAS" in text_upper:
        return "bnl"
    elif "BANCA SELLA" in text_upper:
        return "sella"
    elif "CREDITO EMILIANO" in text_upper or "CREDEM" in text_upper:
        return "credem"
    elif "MONTE DEI PASCHI" in text_upper or "MPS" in text_upper:
        return "mps"
    else:
        return "generic"


# ============== BANK-SPECIFIC PARSERS ==============

def parse_intesa_row(row: List[Any]) -> Optional[Dict[str, Any]]:
    """Parser per formato Intesa Sanpaolo."""
    # Formato tipico: Data Contabile | Data Valuta | Descrizione | Dare | Avere | Saldo
    if len(row) < 4:
        return None
    
    data = None
    descrizione = ""
    importo = 0.0
    tipo = "uscita"
    
    for idx, cell in enumerate(row):
        if not cell:
            continue
        cell_str = str(cell).strip()
        
        # Prima e seconda colonna sono date
        if idx < 2 and not data:
            date_match = re.search(r'(\d{2}[/-]\d{2}[/-]\d{2,4})', cell_str)
            if date_match:
                data = parse_italian_date(date_match.group(1))
        
        # Colonna descrizione (solitamente la 3a)
        elif idx == 2 or (len(cell_str) > 10 and not cell_str.replace('.', '').replace(',', '').replace('-', '').replace(' ', '').isdigit()):
            descrizione = cell_str[:400]
        
        # Colonne Dare/Avere (importi)
        elif idx >= 3:
            parsed = parse_italian_amount(cell_str)
            if abs(parsed) > 0:
                if idx == 3:  # Dare = uscita
                    tipo = "uscita"
                    importo = abs(parsed)
                elif idx == 4:  # Avere = entrata
                    tipo = "entrata"
                    importo = abs(parsed)
    
    if data and importo > 0:
        return {"data": data, "descrizione": descrizione, "importo": importo, "tipo": tipo}
    return None


def parse_unicredit_row(row: List[Any]) -> Optional[Dict[str, Any]]:
    """Parser per formato UniCredit."""
    # Formato tipico: Data | Valuta | Descrizione Operazione | Importo
    if len(row) < 3:
        return None
    
    data = None
    descrizione = ""
    importo = 0.0
    tipo = "uscita"
    
    for idx, cell in enumerate(row):
        if not cell:
            continue
        cell_str = str(cell).strip()
        
        if idx == 0:
            date_match = re.search(r'(\d{2}[/-]\d{2}[/-]\d{2,4})', cell_str)
            if date_match:
                data = parse_italian_date(date_match.group(1))
        elif idx == 2:
            descrizione = cell_str[:400]
        elif idx >= 3:
            parsed = parse_italian_amount(cell_str)
            if abs(parsed) > 0:
                importo = abs(parsed)
                tipo = "uscita" if parsed < 0 or '-' in cell_str else "entrata"
    
    if data and importo > 0:
        return {"data": data, "descrizione": descrizione, "importo": importo, "tipo": tipo}
    return None


def parse_generic_row(row: List[Any]) -> Optional[Dict[str, Any]]:
    """Parser generico per qualsiasi formato."""
    if not row or len(row) < 3:
        return None
    
    data = None
    descrizione = ""
    importo = 0.0
    tipo = "uscita"
    
    for idx, cell in enumerate(row):
        if not cell:
            continue
        cell_str = str(cell).strip()
        
        # Cerca data
        if not data:
            date_match = re.search(r'(\d{2}[/-]\d{2}[/-]\d{2,4})', cell_str)
            if date_match:
                data = parse_italian_date(date_match.group(1))
                continue
        
        # Cerca importo (pattern numerico)
        amount_match = re.match(r'^-?\s*\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?$', cell_str.replace(' ', ''))
        if amount_match:
            parsed = parse_italian_amount(cell_str)
            if abs(parsed) > 0.01:  # Ignora importi troppo piccoli
                if parsed < 0 or '-' in cell_str:
                    tipo = "uscita"
                else:
                    tipo = "entrata"
                importo = abs(parsed)
                continue
        
        # Descrizione (testo lungo non numerico)
        if len(cell_str) > 5 and not cell_str.replace('.', '').replace(',', '').replace('-', '').replace(' ', '').isdigit():
            descrizione = (descrizione + " " + cell_str).strip()[:400]
    
    if data and importo > 0:
        return {"data": data, "descrizione": descrizione or "Movimento estratto conto", "importo": importo, "tipo": tipo}
    return None


# ============== PDF EXTRACTION ==============

def extract_movements_from_pdf(content: bytes) -> List[Dict[str, Any]]:
    """Estrae movimenti da PDF estratto conto con rilevamento automatico formato."""
    import pdfplumber
    
    movements = []
    bank_format = "generic"
    all_text = ""
    
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        # Prima passata: rileva il formato
        for page in pdf.pages[:2]:
            text = page.extract_text()
            if text:
                all_text += text
        
        bank_format = detect_bank_format(all_text, [])
        logger.info(f"Detected bank format: {bank_format}")
        
        # Seconda passata: estrai movimenti
        for page in pdf.pages:
            tables = page.extract_tables()
            
            for table in tables:
                if not table:
                    continue
                
                header_found = False
                for row in table:
                    if not row or len(row) < 3:
                        continue
                    
                    row_text = ' '.join([str(c) if c else '' for c in row]).upper()
                    
                    # Skip header rows
                    if any(h in row_text for h in ['DATA CONTABILE', 'DATA VALUTA', 'DESCRIZIONE', 'OPERAZIONE', 'SALDO']):
                        header_found = True
                        continue
                    
                    # Skip empty or summary rows
                    if 'SALDO INIZIALE' in row_text or 'SALDO FINALE' in row_text or 'TOTALE' in row_text:
                        continue
                    
                    # Parse row based on detected format
                    movement = None
                    if bank_format == "intesa":
                        movement = parse_intesa_row(row)
                    elif bank_format == "unicredit":
                        movement = parse_unicredit_row(row)
                    else:
                        movement = parse_generic_row(row)
                    
                    if movement:
                        movement["bank_format"] = bank_format
                        movements.append(movement)
            
            # Fallback: parse text line by line
            if not movements:
                text = page.extract_text()
                if text:
                    text_movements = parse_text_movements(text, bank_format)
                    movements.extend(text_movements)
    
    return movements


def parse_text_movements(text: str, bank_format: str = "generic") -> List[Dict[str, Any]]:
    """Parsa movimenti da testo estratto conto (fallback)."""
    movements = []
    lines = text.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line or len(line) < 15:
            continue
        
        # Skip headers and footers
        line_upper = line.upper()
        if any(h in line_upper for h in ['DATA CONTABILE', 'SALDO INIZIALE', 'SALDO FINALE', 'TOTALE MOVIMENTI', 'PAGINA']):
            continue
        
        # Pattern: cerca data e importo nella stessa riga
        date_match = re.search(r'(\d{2}[/-]\d{2}[/-]\d{2,4})', line)
        amount_match = re.search(r'(-?\s*\d{1,3}(?:\.\d{3})*,\d{2})\s*$', line)
        
        if date_match and amount_match:
            data = parse_italian_date(date_match.group(1))
            importo_str = amount_match.group(1)
            importo = parse_italian_amount(importo_str)
            
            if abs(importo) > 0.01:
                # Estrai descrizione (tra data e importo)
                start = date_match.end()
                end = amount_match.start()
                descrizione = line[start:end].strip()[:400]
                
                # Rimuovi eventuali date extra dalla descrizione
                descrizione = re.sub(r'\d{2}[/-]\d{2}[/-]\d{2,4}', '', descrizione).strip()
                
                tipo = "uscita" if importo < 0 or '-' in importo_str else "entrata"
                
                movements.append({
                    "data": data,
                    "descrizione": descrizione or "Movimento estratto conto",
                    "importo": abs(importo),
                    "tipo": tipo,
                    "bank_format": bank_format
                })
    
    return movements


# ============== EXCEL/CSV EXTRACTION ==============

def extract_movements_from_excel(content: bytes, filename: str) -> List[Dict[str, Any]]:
    """Estrae movimenti da Excel/CSV estratto conto."""
    import pandas as pd
    
    movements = []
    
    try:
        # Load file
        if filename.lower().endswith('.csv'):
            for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
                for sep in [';', ',', '\t']:
                    try:
                        df = pd.read_csv(io.BytesIO(content), sep=sep, encoding=encoding)
                        if len(df.columns) >= 3:
                            break
                    except Exception:
                        continue
                if len(df.columns) >= 3:
                    break
        elif filename.lower().endswith('.xls'):
            df = pd.read_excel(io.BytesIO(content), engine='xlrd')
        else:
            df = pd.read_excel(io.BytesIO(content), engine='openpyxl')
        
        # Normalize column names
        df.columns = df.columns.str.lower().str.strip().str.replace(' ', '_')
        
        # Map columns
        col_mapping = identify_columns(df.columns.tolist())
        
        for idx, row in df.iterrows():
            try:
                movement = extract_row_data(row, col_mapping)
                if movement:
                    movements.append(movement)
            except Exception as e:
                logger.warning(f"Error parsing row {idx}: {e}")
                continue
                
    except Exception as e:
        logger.error(f"Error parsing Excel/CSV: {e}")
    
    return movements


def identify_columns(columns: List[str]) -> Dict[str, str]:
    """Identifica le colonne rilevanti nel file Excel/CSV."""
    mapping = {
        "date": None,
        "description": None,
        "amount": None,
        "debit": None,
        "credit": None,
        "type": None,
        "category": None
    }
    
    # Normalizza nomi colonne
    normalized = [c.lower().strip() for c in columns]
    
    for idx, col in enumerate(normalized):
        orig_col = columns[idx]
        
        # Date columns
        if 'data_contabile' in col or col == 'data_contabile':
            mapping["date"] = orig_col
        elif 'data_valuta' in col and not mapping["date"]:
            mapping["date"] = orig_col
        elif 'data' in col and not mapping["date"]:
            mapping["date"] = orig_col
        
        # Description
        elif 'descrizione' in col or 'causale' in col or 'operazione' in col:
            mapping["description"] = orig_col
        
        # Amount (single column)
        elif col == 'importo' or 'importo' in col:
            mapping["amount"] = orig_col
        
        # Dare/Avere separate
        elif 'dare' in col or 'uscite' in col or 'addebito' in col:
            mapping["debit"] = orig_col
        elif 'avere' in col or 'entrate' in col or 'accredito' in col:
            mapping["credit"] = orig_col
        
        # Category
        elif 'categoria' in col or 'sottocategoria' in col:
            mapping["category"] = orig_col
    
    return mapping


def extract_row_data(row, col_mapping: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Estrae dati da una riga usando il mapping colonne."""
    import pandas as pd
    
    # Get date
    data = None
    if col_mapping["date"]:
        val = row.get(col_mapping["date"])
        if pd.notna(val):
            if isinstance(val, datetime):
                data = val.strftime("%Y-%m-%d")
            else:
                data = parse_italian_date(str(val))
    
    if not data:
        return None
    
    # Get description
    descrizione = ""
    if col_mapping["description"]:
        val = row.get(col_mapping["description"])
        if pd.notna(val):
            descrizione = str(val)[:400]
    
    # Get amount and type
    importo = 0.0
    tipo = "uscita"
    
    # Try debit/credit columns first
    if col_mapping["debit"] or col_mapping["credit"]:
        if col_mapping["debit"]:
            val = row.get(col_mapping["debit"])
            if pd.notna(val):
                parsed = parse_italian_amount(str(val))
                if abs(parsed) > 0:
                    importo = abs(parsed)
                    tipo = "uscita"
        
        if col_mapping["credit"] and importo == 0:
            val = row.get(col_mapping["credit"])
            if pd.notna(val):
                parsed = parse_italian_amount(str(val))
                if abs(parsed) > 0:
                    importo = abs(parsed)
                    tipo = "entrata"
    
    # Fallback to single amount column
    if importo == 0 and col_mapping["amount"]:
        val = row.get(col_mapping["amount"])
        if pd.notna(val):
            parsed = parse_italian_amount(str(val))
            if abs(parsed) > 0:
                importo = abs(parsed)
                # Determina tipo dalla categoria o descrizione
                categoria = str(row.get(col_mapping.get("category", ""), "") or "").lower()
                desc_lower = descrizione.lower() if descrizione else ""
                desc_upper = descrizione.upper() if descrizione else ""
                
                # ============ REGOLE TIPO MOVIMENTO ============
                # USCITE CERTE (sempre addebiti):
                # - VOSTRA DISPOSIZIONE = addebito automatico
                # - VS.DISP = addebito automatico
                # - BONIFICO A FAVORE = pagamento verso terzi
                # - F24 = pagamento tasse
                # - RID = addebito diretto
                # - MAV/RAV = pagamenti
                # - PRELIEVO
                if any(k in desc_upper for k in ['VOSTRA DISPOSIZIONE', 'VS.DISP', 'VS DISP', 
                                                  'BONIFICO A FAVORE', 'F24', 'RID ', 'MAV ', 'RAV ',
                                                  'PRELIEVO', 'ADDEBITO', 'PAGAMENTO']):
                    tipo = "uscita"
                # ENTRATE CERTE (sempre accrediti):
                # - INC.POS / INCAS. TRAMITE P.O.S = accredito incassi POS
                # - ACCREDITO
                # - BONIFICO DA / BONIFICO A VS FAVORE = ricezione
                # - GIRO DA = giroconto in entrata
                elif any(k in desc_upper for k in ['INC.POS', 'INCAS.', 'INC. POS', 'INCASSO POS',
                                                    'TRAMITE P.O.S', 'ACCREDITO', 'STIPENDIO',
                                                    'A VS FAVORE', 'A VOSTRO FAVORE', 'GIRO DA']):
                    tipo = "entrata"
                # Regole da categoria
                elif any(k in categoria for k in ['ricavi', 'incasso', 'accredito']):
                    tipo = "entrata"
                elif any(k in categoria for k in ['costi', 'pagament', 'addebito']):
                    tipo = "uscita"
                else:
                    # Default: valore negativo = uscita, positivo = entrata
                    tipo = "uscita" if parsed < 0 else "entrata"
    
    if data and importo > 0:
        # Determina categoria automatica basata sulla descrizione
        categoria_auto = None
        desc_upper = descrizione.upper() if descrizione else ""
        
        # Riconosci movimenti POS
        if any(k in desc_upper for k in ['INC.POS', 'INCAS.', 'INC. POS', 'INCASSO POS',
                                          'TRAMITE P.O.S', 'P.O.S.', 'POS ', ' POS']):
            categoria_auto = "POS"
        # Riconosci bonifici
        elif any(k in desc_upper for k in ['BONIFICO', 'BONIF.', 'BON.']):
            categoria_auto = "BONIFICO"
        # Riconosci F24
        elif 'F24' in desc_upper:
            categoria_auto = "F24"
        
        return {
            "data": data,
            "descrizione": descrizione or f"Movimento del {data}",
            "importo": importo,
            "tipo": tipo,
            "categoria": categoria_auto or (str(row.get(col_mapping.get("category", ""), "")) if col_mapping.get("category") else None)
        }
    
    return None


# ============== RECONCILIATION ==============

async def reconcile_movement(db, movement: Dict[str, Any], tolerance: float = 0.01) -> Optional[Dict[str, Any]]:
    """Riconcilia un movimento con Prima Nota Banca."""
    data = movement["data"]
    importo = movement["importo"]
    tipo = movement["tipo"]
    
    # Search in Prima Nota Banca with same date, type and similar amount
    query = {
        "data": data,
        "tipo": tipo,
        "importo": {"$gte": importo * (1 - tolerance), "$lte": importo * (1 + tolerance)},
        "riconciliato": {"$ne": True}
    }
    
    match = await db[COLLECTION_PRIMA_NOTA_BANCA].find_one(query)
    
    if match:
        # Mark as reconciled
        await db[COLLECTION_PRIMA_NOTA_BANCA].update_one(
            {"id": match["id"]},
            {"$set": {
                "riconciliato": True,
                "data_riconciliazione": datetime.now(timezone.utc).isoformat()
            }}
        )
        return match
    
    return None


# Collection per estratto conto
COLLECTION_ESTRATTO_CONTO = "estratto_conto_movimenti"

@router.get("/movements")
@handle_errors
async def get_bank_statement_movements(
    data_da: Optional[str] = Query(None),
    data_a: Optional[str] = Query(None),
    limit: int = Query(1000, ge=1, le=5000)
) -> Dict[str, Any]:
    """
    Recupera i movimenti importati dall'estratto conto.
    Accetta date ISO (YYYY-MM-DD) e filtra su data_contabile / data_valuta / data
    gestendo formati italiani (gg/mm/yyyy) e ISO.
    """
    db = Database.get_db()

    query: Dict[str, Any] = {}

    def _iso_to_it(iso_str: Optional[str]) -> Optional[str]:
        """Converte 2026-01-01 → 01/01/2026"""
        if not iso_str: return None
        try:
            y, m, d = iso_str.split("-")
            return f"{d}/{m}/{y}"
        except Exception:
            return None

    if data_da or data_a:
        anni = set()
        for s in (data_da, data_a):
            if s and len(s) >= 4:
                anni.add(s[:4])
        # Filtro per anno (regex su campi in formato italiano)
        or_conditions = []
        for anno in anni:
            or_conditions.extend([
                {"data_contabile": {"$regex": f"/{anno}$"}},
                {"data_valuta":    {"$regex": f"/{anno}$"}},
                {"data":           {"$regex": f"^{anno}-"}},  # ISO
                {"data":           {"$regex": f"/{anno}$"}},  # IT
            ])
        if or_conditions:
            query["$or"] = or_conditions

    movements = await db[COLLECTION_ESTRATTO_CONTO].find(
        query, {"_id": 0}
    ).sort("data_contabile", -1).limit(limit).to_list(limit)

    # Normalizza: aggiungi campo `data` in formato ISO per ogni movimento (se possibile)
    for m in movements:
        if not m.get("data"):
            dt = m.get("data_contabile") or m.get("data_valuta") or ""
            if dt and "/" in dt:
                parts = dt.split("/")
                if len(parts) == 3:
                    m["data"] = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
        # Deriva tipo da importo se manca
        if not m.get("tipo"):
            imp = float(m.get("importo") or 0)
            m["tipo"] = "entrata" if imp > 0 else "uscita"
        # Normalizza importo assoluto se il campo è negativo
        if m.get("tipo") == "uscita" and float(m.get("importo") or 0) < 0:
            m["importo"] = abs(float(m["importo"]))

    # Filtro fine granularità per range
    if data_da:
        movements = [m for m in movements if (m.get("data") or "") >= data_da]
    if data_a:
        movements = [m for m in movements if (m.get("data") or "9999-99-99") <= data_a]

    totale_entrate = sum(float(m.get("importo") or 0) for m in movements if m.get("tipo") == "entrata")
    totale_uscite  = sum(float(m.get("importo") or 0) for m in movements if m.get("tipo") == "uscita")

    return {
        "movements": movements,
        "count": len(movements),
        "totale_entrate": round(totale_entrate, 2),
        "totale_uscite":  round(totale_uscite, 2),
        "saldo":          round(totale_entrate - totale_uscite, 2)
    }


# ============== API ENDPOINTS ==============

@router.post("/import")
@handle_errors
async def import_bank_statement(
    file: UploadFile = File(...),
    auto_reconcile: bool = Query(True, description="Riconcilia automaticamente con Prima Nota")
) -> Dict[str, Any]:
    """
    Importa estratto conto bancario e riconcilia con Prima Nota Banca.
    
    Supporta formati:
    - PDF (Intesa Sanpaolo, UniCredit, BNL, generico)
    - Excel (.xlsx, .xls)
    - CSV
    
    Returns:
        - Movimenti estratti
        - Movimenti riconciliati
        - Movimenti non trovati in Prima Nota
    """
    filename = file.filename.lower()
    if not filename.endswith(('.pdf', '.xlsx', '.xls', '.csv')):
        raise HTTPException(status_code=400, detail="Formato non supportato. Usa PDF, Excel o CSV.")
    
    content = await file.read()
    
    # Extract movements based on file type
    movements = []
    
    try:
        if filename.endswith('.pdf'):
            movements = extract_movements_from_pdf(content)
        else:
            movements = extract_movements_from_excel(content, filename)
    except Exception as e:
        logger.error(f"Error extracting movements: {e}")
        raise HTTPException(status_code=500, detail=f"Errore parsing file: {str(e)}")
    
    if not movements:
        return {
            "success": False,
            "message": "Nessun movimento trovato nel file",
            "movements_found": 0,
            "movements": []
        }
    
    # Remove duplicates
    seen = set()
    unique_movements = []
    for m in movements:
        key = f"{m['data']}_{m['tipo']}_{m['importo']:.2f}"
        if key not in seen:
            seen.add(key)
            unique_movements.append(m)
    
    movements = unique_movements
    
    db = Database.get_db()
    now = datetime.now(timezone.utc).isoformat()
    
    results = {
        "success": True,
        "filename": file.filename,
        "movements_found": len(movements),
        "reconciled": 0,
        "not_found": 0,
        "movements": [],
        "reconciled_details": [],
        "not_found_details": []
    }
    
    # Save imported statement
    statement_id = str(uuid.uuid4())
    statement_record = {
        "id": statement_id,
        "filename": file.filename,
        "import_date": now,
        "movements_count": len(movements),
        "created_at": now
    }
    await db[COLLECTION_BANK_STATEMENTS].insert_one(statement_record.copy())
    
    # Process each movement
    for movement in movements:
        movement["id"] = str(uuid.uuid4())
        movement["statement_id"] = statement_id
        movement["source"] = "estratto_conto_import"
        movement["created_at"] = now
        
        if auto_reconcile:
            match = await reconcile_movement(db, movement)
            if match:
                movement["riconciliato"] = True
                movement["prima_nota_match"] = match
                results["reconciled"] += 1
                results["reconciled_details"].append({
                    "estratto_conto": {
                        "data": movement["data"],
                        "descrizione": movement["descrizione"][:50],
                        "importo": movement["importo"],
                        "tipo": movement["tipo"]
                    },
                    "prima_nota": match
                })
            else:
                movement["riconciliato"] = False
                results["not_found"] += 1
                results["not_found_details"].append({
                    "data": movement["data"],
                    "descrizione": movement["descrizione"][:50],
                    "importo": movement["importo"],
                    "tipo": movement["tipo"]
                })
        
        results["movements"].append({
            "data": movement["data"],
            "descrizione": movement["descrizione"][:50],
            "importo": movement["importo"],
            "tipo": movement["tipo"],
            "riconciliato": movement.get("riconciliato", False)
        })
        
        # Salva nella collection estratto_conto per il confronto
        estratto_doc = {
            "id": movement["id"],
            "data": movement["data"],
            "descrizione": movement["descrizione"],
            "importo": movement["importo"],
            "tipo": movement["tipo"],
            "categoria": movement.get("categoria"),
            "statement_id": statement_id,
            "source": "estratto_conto_import",
            "created_at": now
        }
        await db[COLLECTION_ESTRATTO_CONTO].insert_one(estratto_doc.copy())
    
    # Summary message
    if results["reconciled"] > 0:
        results["message"] = f"Importati {len(movements)} movimenti. Riconciliati: {results['reconciled']}, Non trovati: {results['not_found']}"
    else:
        results["message"] = f"Importati {len(movements)} movimenti. Nessuna corrispondenza trovata in Prima Nota."
    
    return results


@router.get("/stats")
@handle_errors
async def get_import_stats() -> Dict[str, Any]:
    """Statistiche importazioni estratto conto."""
    db = Database.get_db()
    
    # Count imported statements
    statements_count = await db[COLLECTION_BANK_STATEMENTS].count_documents({})
    
    # Count Prima Nota movements
    total_banca = await db[COLLECTION_PRIMA_NOTA_BANCA].count_documents({})
    riconciliati = await db[COLLECTION_PRIMA_NOTA_BANCA].count_documents({"riconciliato": True})
    
    return {
        "estratti_conto_importati": statements_count,
        "movimenti_banca_totali": total_banca,
        "movimenti_riconciliati": riconciliati,
        "movimenti_non_riconciliati": total_banca - riconciliati,
        "percentuale_riconciliazione": round((riconciliati / total_banca * 100) if total_banca > 0 else 0, 1)
    }


@router.post("/riconcilia-manuale")
@handle_errors
async def manual_reconcile(
    estratto_conto_movimento_id: str = Query(..., description="ID movimento estratto conto"),
    prima_nota_movimento_id: str = Query(..., description="ID movimento Prima Nota Banca")
) -> Dict[str, Any]:
    """Riconcilia manualmente un movimento estratto conto con Prima Nota."""
    db = Database.get_db()
    
    # Update Prima Nota Banca
    result = await db[COLLECTION_PRIMA_NOTA_BANCA].update_one(
        {"id": prima_nota_movimento_id},
        {"$set": {
            "riconciliato": True,
            "data_riconciliazione": datetime.now(timezone.utc).isoformat(),
            "estratto_conto_ref": estratto_conto_movimento_id
        }}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Movimento Prima Nota non trovato")
    
    return {
        "success": True,
        "message": "Riconciliazione completata",
        "prima_nota_id": prima_nota_movimento_id,
        "estratto_conto_id": estratto_conto_movimento_id
    }


@router.get("/formati-supportati")
@handle_errors
async def get_supported_formats() -> Dict[str, Any]:
    """Lista formati bancari supportati."""
    return {
        "pdf": {
            "banche": ["Intesa Sanpaolo", "UniCredit", "BNL", "Banca Sella", "MPS", "Credem", "Generico"],
            "note": "Rilevamento automatico del formato"
        },
        "excel": {
            "formati": [".xlsx", ".xls"],
            "colonne_riconosciute": ["data", "data_contabile", "valuta", "descrizione", "causale", "dare", "avere", "importo"]
        },
        "csv": {
            "separatori": [";", ",", "TAB"],
            "encoding": ["UTF-8", "Latin-1", "CP1252"]
        }
    }
