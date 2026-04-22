"""
Parser PDF per Libro Unico del Lavoro (LUL)
============================================

Estrae i dati dal Libro Unico del Lavoro generato da Zucchetti:
- Foglio presenze (pagine dispari)
- Busta paga (pagine pari)

Gestisce la filigrana Zucchetti che interferisce con l'estrazione.
Workflow completo: parsing → anagrafica → presenze → buste paga → scadenze → riconciliazione bancaria
"""

import re
import uuid
import pdfplumber
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple
from fastapi import APIRouter, HTTPException, UploadFile, File
import tempfile
import os
import logging
import calendar

from app.database import Database

router = APIRouter(tags=["Libro Unico Parser"])
logger = logging.getLogger(__name__)

# Pattern per filtrare la filigrana Zucchetti
WATERMARK_PATTERNS = [
    r'^[A-Z]$',  # Singole lettere
    r'^[a-z]{1,4}$',  # Brevi sequenze minuscole
    r'Zucchetti',
    r'zucchetti',
    r'www\.',
    r'http',
    r'\.it',
    r'itte',
    r'ccu',
    r'lle',
    r'rid',
    r'tth',
    r'//:p',
    r'\)ti',
    r'n re',
    r'tn$',
    r'^I o',
    r'^o L',
    r'^id$',
    r'alle',
    r'^d$',
    r'^e ',
    r'ru$',
    r'co$',
    r'rp ',
    r're$',
    r'p o',
]


def is_watermark_line(line: str) -> bool:
    """Verifica se una linea è parte della filigrana"""
    line = line.strip()
    if not line:
        return True
    if len(line) <= 3 and not line.isdigit():
        return True
    for pattern in WATERMARK_PATTERNS:
        if re.search(pattern, line):
            return True
    return False


def clean_text_lines(text: str) -> List[str]:
    """Pulisce il testo rimuovendo le linee della filigrana"""
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        if not is_watermark_line(line):
            cleaned.append(line.strip())
    return [l for l in cleaned if l]


def parse_presenze_line(line: str) -> Optional[Dict]:
    """
    Parsa una linea del foglio presenze.
    Gestisce anche linee con residui della filigrana all'inizio.
    Formato: "[garbage] GG N [ORE] [GIUST] [ORE_GIUST]"
    """
    # Prima pulisci la linea dalla filigrana all'inizio
    # Pattern per estrarre: giorno_settimana numero [giustificativo] [ore]
    
    # Pattern complessi che gestiscono la filigrana
    patterns = [
        # Con giustificativo e ore: "... LU 19 AI 6,40"
        r'.*?([A-Z]{2})\s+(\d{1,2})\s+([A-Z]{2})\s+([\d,]+)$',
        # Solo ore: "... VE 2 6,40"
        r'.*?([A-Z]{2})\s+(\d{1,2})\s+([\d,]+)$',
        # Solo giorno: "... SA 3"
        r'.*?([A-Z]{2})\s+(\d{1,2})$',
    ]
    
    # Lista dei giorni validi
    giorni_validi = ['LU', 'MA', 'ME', 'GI', 'VE', 'SA', 'DO']
    
    for pattern in patterns:
        match = re.search(pattern, line.strip())
        if match:
            groups = match.groups()
            giorno_sett = groups[0]
            
            # Verifica che sia un giorno valido
            if giorno_sett not in giorni_validi:
                continue
                
            result = {
                "giorno_settimana": giorno_sett,
                "giorno": int(groups[1]),
                "ore_ordinarie": None,
                "ore_straordinarie": None,
                "giustificativo": None
            }
            
            if len(groups) == 4:  # Con giustificativo e ore
                result["giustificativo"] = groups[2]
                result["ore_ordinarie"] = groups[3]
            elif len(groups) == 3:  # Solo ore
                # Verifica se il terzo gruppo è un codice giustificativo o ore
                if re.match(r'^[\d,]+$', groups[2]):
                    result["ore_ordinarie"] = groups[2]
                else:
                    result["giustificativo"] = groups[2]
            # len == 2: solo giorno, nessuna ora
            
            return result
    
    return None


def parse_foglio_presenze(text: str) -> Dict:
    """Parsa il foglio presenze (pagina dispari)"""
    lines = clean_text_lines(text)
    
    result = {
        "tipo": "foglio_presenze",
        "azienda": {},
        "dipendente": {},
        "presenze": [],
        "riepilogo_giustificativi": []
    }
    
    # Estrai dati azienda
    for i, line in enumerate(lines):
        if "CERALDI GROUP" in line:
            result["azienda"]["ragione_sociale"] = line
        elif re.match(r'^PIAZZA|^VIA|^CORSO', line) and not result["azienda"].get("indirizzo"):
            result["azienda"]["indirizzo"] = line
        elif re.match(r'^\d{5}\s+[A-Z]+', line) and "NAPOLI" in line:
            # Es: "80143 NAPOLI (NA) Aut. 35685"
            match = re.match(r'^(\d{5})\s+([A-Z]+)\s+\(([A-Z]{2})\)\s*(?:Aut\.\s*(\d+))?', line)
            if match:
                result["azienda"]["cap"] = match.group(1)
                result["azienda"]["citta"] = match.group(2)
                result["azienda"]["provincia"] = match.group(3)
                if match.group(4):
                    result["azienda"]["autorizzazione"] = match.group(4)
        elif "Del " in line and "Sede" in line:
            match = re.search(r'Del\s+([\d-]+)\s+Sede\s+(\d+)', line)
            if match:
                result["azienda"]["data_autorizzazione"] = match.group(1)
                result["azienda"]["sede"] = match.group(2)
        elif line.startswith("Nr."):
            result["azienda"]["nr_documento"] = line.replace("Nr.", "").strip()
        elif re.match(r'^\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2}$', line):
            result["azienda"]["data_stampa"] = line
    
    # Estrai dati dipendente
    for i, line in enumerate(lines):
        if re.match(r'^\d{6}/\d{7}/\d{10}', line):
            result["dipendente"]["codice"] = line.rstrip('/')
        elif re.match(r'^[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]$', line):
            result["dipendente"]["codice_fiscale"] = line
        elif "P.A.T. INAIL" in lines[i-1] if i > 0 else False:
            # La riga dopo "PERIODO DI RIFERIMENTO CODICE FISCALE P.A.T. INAIL"
            match = re.match(r'^([A-Za-z]+\s+\d{4})\s+([A-Z0-9]+)\s+([\d/]+)\s+(.+)$', line)
            if match:
                result["dipendente"]["periodo"] = match.group(1)
                result["dipendente"]["codice_fiscale"] = match.group(2)
                result["dipendente"]["pat_inail"] = match.group(3)
                result["dipendente"]["tipo_rapporto"] = match.group(4)
    
    # Cerca nome dipendente (di solito dopo il codice)
    for i, line in enumerate(lines):
        if result["dipendente"].get("codice") and i > 0:
            # Il nome è tipicamente la riga dopo il codice
            prev_line = lines[i-1] if i > 0 else ""
            if result["dipendente"]["codice"] in prev_line:
                if re.match(r'^[A-Z]+\s+[A-Z]+$', line):
                    result["dipendente"]["cognome_nome"] = line
                    # L'indirizzo è la riga successiva
                    if i + 1 < len(lines):
                        next_line = lines[i+1]
                        if re.match(r'^VIA|^PIAZZA|^CORSO|^VIALE', next_line):
                            result["dipendente"]["indirizzo"] = next_line
                            if i + 2 < len(lines):
                                result["dipendente"]["citta"] = lines[i+2]
                    break
    
    # Estrai presenze giornaliere
    for line in lines:
        presenza = parse_presenze_line(line)
        if presenza:
            result["presenze"].append(presenza)
    
    # Estrai riepilogo giustificativi
    # Pattern: "Ore ordinarie 113,20hm AI Ass.za ingiustif. 6,40hm FE Ferie 40,00hm"
    for line in lines:
        if "Ore ordinarie" in line or "hm" in line.lower():
            # Parse della riga riepilogo
            # Ore ordinarie
            match = re.search(r'Ore ordinarie\s+([\d,]+)hm', line)
            if match:
                result["riepilogo_giustificativi"].append({
                    "codice": "",
                    "descrizione": "Ore ordinarie",
                    "quantita": match.group(1),
                    "unita": "hm"
                })
            
            # Altri giustificativi
            giust_pattern = r'([A-Z]{2})\s+([A-Za-z.\s]+?)\s+([\d,]+)hm'
            for match in re.finditer(giust_pattern, line):
                result["riepilogo_giustificativi"].append({
                    "codice": match.group(1),
                    "descrizione": match.group(2).strip(),
                    "quantita": match.group(3),
                    "unita": "hm"
                })
    
    return result


def parse_euro_amount(text: str) -> float:
    """Converte un importo testuale in float"""
    if not text:
        return 0.0
    # Rimuovi simboli e spazi
    cleaned = re.sub(r'[€\s]', '', text)
    # Gestisci formato italiano (1.234,56)
    cleaned = cleaned.replace('.', '').replace(',', '.')
    try:
        return float(cleaned)
    except Exception:
        return 0.0


def parse_busta_paga(text: str) -> Dict:
    """Parsa la busta paga (pagina pari)"""
    lines = clean_text_lines(text)
    full_text = ' '.join(lines)
    
    result = {
        "tipo": "busta_paga",
        "dipendente": {},
        "competenze": [],
        "trattenute": [],
        "irpef": {},
        "progressivi": {},
        "tfr": {},
        "ratei": {},
        "totali": {},
        "pagamento": {}
    }
    
    # Estrai dati dipendente dalla busta paga
    for i, line in enumerate(lines):
        # Codice dipendente e nome
        match = re.match(r'^(\d{7})\s+([A-Z]+\s+[A-Z]+)\s+([A-Z0-9]+)$', line)
        if match:
            result["dipendente"]["codice"] = match.group(1)
            result["dipendente"]["cognome_nome"] = match.group(2)
            result["dipendente"]["codice_fiscale"] = match.group(3)
        
        # Qualifica e livello
        if "Livello" in line:
            match = re.search(r'(\w+)\s+(\d+)\s+Livello\s+(\w+)', line)
            if match:
                result["dipendente"]["qualifica_codice"] = match.group(1)
                result["dipendente"]["livello_numero"] = match.group(2)
                result["dipendente"]["livello_descrizione"] = match.group(3)
        
        # Mansione
        if "CAMERIERE" in line or "CUOCO" in line or "BARISTA" in line:
            result["dipendente"]["mansione"] = line.strip()
    
    # Estrai competenze
    competenze_patterns = [
        (r'Z00001.*?Retribuzione.*?([\d,]+)', "Retribuzione"),
        (r'Z00250.*?Ferie godute.*?([\d,]+)', "Ferie godute"),
        (r'Z01100.*?Festivita.*?godute.*?([\d,]+)', "Festività godute"),
        (r'Z50000.*?13ma Mensilita.*?([\d,]+)', "13ma Mensilità"),
        (r'Z50022.*?14ma Mensilita.*?([\d,]+)', "14ma Mensilità"),
        (r'ZP9960.*?Arrotond.*?([\d,]+)', "Arrotondamento mese prec."),
    ]
    
    for pattern, nome in competenze_patterns:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            result["competenze"].append({
                "voce": nome,
                "importo": match.group(1)
            })
    
    # Estrai trattenute contributive
    trattenute_patterns = [
        (r'Z00000.*?Contributo IVS.*?([\d.,]+)\s+([\d,]+)%\s+([\d,]+)', "Contributo IVS"),
        (r'Z00054.*?FIS.*?D\.?Lgs\.?148.*?([\d.,]+)\s+([\d,]+)%\s+([\d,]+)', "FIS D.Lgs.148/2015"),
    ]
    
    for pattern, nome in trattenute_patterns:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            result["trattenute"].append({
                "voce": nome,
                "imponibile": match.group(1),
                "aliquota": match.group(2),
                "importo": match.group(3)
            })
    
    # Estrai calcolo IRPEF
    irpef_patterns = [
        (r'F02000.*?Imponibile IRPEF\s+([\d.,]+)', "imponibile"),
        (r'F02010.*?IRPEF lorda\s+([\d.,]+)', "irpef_lorda"),
        (r'F02500.*?Detrazioni lav\.?dip\.?\s+([\d.,]+)', "detrazioni_lavdip"),
        (r'F02703.*?Indennit.*?L\.?207.*?([\d.,]+)', "indennita_l207"),
        (r'F03020.*?Ritenute IRPEF\s+([\d.,]+)', "ritenute_irpef"),
        (r'F06000.*?Imponibile Tass\.?aut\.?\s+([\d.,]+)', "imponibile_tass_aut"),
        (r'F06010.*?IRPEF lorda Tass\.?aut\.?\s+([\d.,]+)', "irpef_lorda_tass_aut"),
        (r'F06020.*?Ritenute IRPEF Tass\.?aut\.?\s+([\d.,]+)', "ritenute_tass_aut"),
    ]
    
    for pattern, campo in irpef_patterns:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            result["irpef"][campo] = match.group(1)
    
    # Estrai addizionali
    add_patterns = [
        (r'F09110.*?Addizionale regionale.*?(\d{4})\s+([A-Z]+).*?Residuo\s+([\d.,]+)\s+([\d.,]+)', "addizionale_regionale"),
        (r'F09130.*?Addizionale comunale.*?(\d{4})\s+([A-Z]+).*?Residuo\s+([\d.,]+)\s+([\d.,]+)', "addizionale_comunale"),
    ]
    
    for pattern, campo in add_patterns:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            result["irpef"][campo] = {
                "anno": match.group(1),
                "regione_comune": match.group(2),
                "residuo": match.group(3),
                "trattenuta": match.group(4)
            }
    
    # Estrai progressivi
    prog_match = re.search(r'Imp\.\s*INPS\s+Imp\.\s*INAIL\s+Imp\.\s*IRPEF\s+IRPEF\s+pagata\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)', full_text)
    if prog_match:
        result["progressivi"] = {
            "imp_inps": prog_match.group(1),
            "imp_inail": prog_match.group(2),
            "imp_irpef": prog_match.group(3),
            "irpef_pagata": prog_match.group(4)
        }
    
    # Estrai TFR
    tfr_match = re.search(r'T\.?F\.?R\.?.*?F\.?do\s*31/12.*?Rivalutaz.*?Imp\.?rival.*?Quota anno.*?TFR a fondi.*?Anticipi\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)', full_text)
    if tfr_match:
        result["tfr"] = {
            "fondo_31_12": tfr_match.group(1),
            "rivalutazione": tfr_match.group(2),
            "imp_rivalutazione": tfr_match.group(3),
            "quota_anno": tfr_match.group(4)
        }
    
    # Estrai ratei ferie e permessi
    ferie_match = re.search(r'Ferie\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+GG', full_text)
    if ferie_match:
        result["ratei"]["ferie"] = {
            "residuo_ap": ferie_match.group(1),
            "maturato": ferie_match.group(2),
            "goduto": ferie_match.group(3),
            "saldo": ferie_match.group(4),
            "unita": "GG"
        }
    
    permessi_match = re.search(r'Permessi\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+ORE', full_text)
    if permessi_match:
        result["ratei"]["permessi"] = {
            "residuo_ap": permessi_match.group(1),
            "maturato": permessi_match.group(2),
            "saldo": permessi_match.group(3),
            "unita": "ORE"
        }
    
    # Estrai totali - Pattern specifici per il formato Zucchetti
    # "RATEI TOTALEsCOMPETENZE 1.754,67"
    totale_comp_match = re.search(r'TOTALE.?COMPETENZE\s+([\d.,]+)', full_text)
    if totale_comp_match:
        result["totali"]["totale_competenze"] = totale_comp_match.group(1)
    
    # "TOTALEsTRATTENUTE 318,75"
    totale_tratt_match = re.search(r'TOTALE.?TRATTENUTE\s+([\d.,]+)', full_text)
    if totale_tratt_match:
        result["totali"]["totale_trattenute"] = totale_tratt_match.group(1)
    
    # "NETTOsDELsMESE" seguito da "1.436,00€"
    netto_match = re.search(r'NETTO.?DEL.?MESE.*?([\d.,]+)\s*€', full_text, re.DOTALL)
    if netto_match:
        result["totali"]["netto_mese"] = netto_match.group(1)
    else:
        # Prova pattern alternativo
        netto_match2 = re.search(r'([\d.,]+)\s*€\s*COMUNICAZIONI', full_text)
        if netto_match2:
            result["totali"]["netto_mese"] = netto_match2.group(1)
    
    # Estrai IBAN pagamento - pattern specifico Zucchetti "IBANIT20C..."
    iban_match = re.search(r'IBAN\s*([A-Z]{2}\d{2}[A-Z0-9]{23})', full_text)
    if not iban_match:
        iban_match = re.search(r'IBAN([A-Z]{2}\d{2}[A-Z0-9]{23})', full_text)  # Senza spazio
    if iban_match:
        result["pagamento"]["iban"] = iban_match.group(1)
    
    banca_match = re.search(r'(BANCO\s+BPM[^I]*)', full_text)
    if banca_match:
        result["pagamento"]["banca"] = banca_match.group(1).strip()
    
    return result


def parse_libro_unico_completo(pdf_path: str) -> Dict:
    """
    Parsa l'intero Libro Unico del Lavoro.
    Ogni dipendente ha 2 pagine: foglio presenze (dispari) e busta paga (pari).
    """
    risultato = {
        "azienda": {},
        "periodo": None,
        "data_elaborazione": None,
        "dipendenti": [],
        "totale_dipendenti": 0,
        "riepilogo": {
            "totale_competenze": 0,
            "totale_trattenute": 0,
            "totale_netto": 0
        }
    }
    
    with pdfplumber.open(pdf_path) as pdf:
        num_pages = len(pdf.pages)
        risultato["totale_dipendenti"] = num_pages // 2
        
        for i in range(0, num_pages, 2):
            dipendente = {
                "foglio_presenze": None,
                "busta_paga": None
            }
            
            # Pagina dispari = Foglio presenze
            if i < num_pages:
                text_presenze = pdf.pages[i].extract_text() or ""
                dipendente["foglio_presenze"] = parse_foglio_presenze(text_presenze)
                
                # Estrai info azienda dalla prima pagina
                if i == 0 and dipendente["foglio_presenze"]:
                    risultato["azienda"] = dipendente["foglio_presenze"].get("azienda", {})
            
            # Pagina pari = Busta paga
            if i + 1 < num_pages:
                text_busta = pdf.pages[i + 1].extract_text() or ""
                dipendente["busta_paga"] = parse_busta_paga(text_busta)
                
                # Aggiorna riepilogo totali
                if dipendente["busta_paga"] and dipendente["busta_paga"].get("totali"):
                    totali = dipendente["busta_paga"]["totali"]
                    risultato["riepilogo"]["totale_competenze"] += parse_euro_amount(totali.get("totale_competenze", "0"))
                    risultato["riepilogo"]["totale_trattenute"] += parse_euro_amount(totali.get("totale_trattenute", "0"))
                    risultato["riepilogo"]["totale_netto"] += parse_euro_amount(totali.get("netto_mese", "0"))
            
            risultato["dipendenti"].append(dipendente)
    
    # Arrotonda totali
    risultato["riepilogo"]["totale_competenze"] = round(risultato["riepilogo"]["totale_competenze"], 2)
    risultato["riepilogo"]["totale_trattenute"] = round(risultato["riepilogo"]["totale_trattenute"], 2)
    risultato["riepilogo"]["totale_netto"] = round(risultato["riepilogo"]["totale_netto"], 2)
    
    return risultato


# ============== API ENDPOINTS ==============

@router.post("/parse-libro-unico", summary="Parsa Libro Unico del Lavoro")
async def parse_libro_unico_endpoint(file: UploadFile = File(...)):
    """
    Carica e parsa un PDF del Libro Unico del Lavoro.
    Estrae fogli presenze e buste paga per tutti i dipendenti.
    """
    try:
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Il file deve essere un PDF")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
        
        try:
            result = parse_libro_unico_completo(tmp_path)
            
            return {
                "success": True,
                "message": f"Libro Unico parsato con successo. Trovati {result['totale_dipendenti']} dipendenti.",
                "data": result
            }
        finally:
            os.unlink(tmp_path)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore parsing Libro Unico: {e}")
        raise HTTPException(status_code=500, detail=f"Errore parsing: {str(e)}")


@router.post("/parse-libro-unico/dipendente/{indice}", summary="Parsa singolo dipendente")
async def parse_singolo_dipendente(
    indice: int,
    file: UploadFile = File(...)
):
    """
    Parsa solo un dipendente specifico dal Libro Unico (0-indexed).
    """
    try:
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Il file deve essere un PDF")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
        
        try:
            with pdfplumber.open(tmp_path) as pdf:
                num_dipendenti = len(pdf.pages) // 2
                
                if indice < 0 or indice >= num_dipendenti:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Indice non valido. Dipendenti disponibili: 0-{num_dipendenti-1}"
                    )
                
                page_presenze = indice * 2
                page_busta = page_presenze + 1
                
                result = {
                    "indice": indice,
                    "foglio_presenze": None,
                    "busta_paga": None
                }
                
                if page_presenze < len(pdf.pages):
                    text = pdf.pages[page_presenze].extract_text() or ""
                    result["foglio_presenze"] = parse_foglio_presenze(text)
                
                if page_busta < len(pdf.pages):
                    text = pdf.pages[page_busta].extract_text() or ""
                    result["busta_paga"] = parse_busta_paga(text)
                
                return {
                    "success": True,
                    "data": result
                }
        finally:
            os.unlink(tmp_path)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore parsing dipendente: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== MAPPA MESI ITALIANI ==============
MESI_IT = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
    "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
    "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12
}


def parse_periodo_italiano(periodo: str) -> Optional[Tuple[int, int]]:
    """Converte 'Gennaio 2026' in (2026, 1). Ritorna None se non parsabile."""
    if not periodo:
        return None
    parts = periodo.strip().lower().split()
    if len(parts) == 2:
        mese_str, anno_str = parts
        mese = MESI_IT.get(mese_str)
        try:
            anno = int(anno_str)
            if mese:
                return (anno, mese)
        except (ValueError, TypeError):
            pass
    return None


def fine_mese_date(anno: int, mese: int) -> str:
    """Ritorna l'ultimo giorno del mese in formato YYYY-MM-DD"""
    ultimo_giorno = calendar.monthrange(anno, mese)[1]
    return f"{anno:04d}-{mese:02d}-{ultimo_giorno:02d}"


async def riconcilia_stipendio_con_banca(
    db, cf: str, cognome_nome: str, netto: float, data_scadenza_str: str
) -> Optional[str]:
    """
    Cerca in prima_nota_banca e estratto_conto_movimenti un pagamento per lo stipendio.
    Ritorna l'id del movimento se trovato, altrimenti None.
    """
    from app.services.paghe_riconciliazione import cerca_in_estratto_conto
    try:
        keywords = ["STIPENDIO", "CEDOLINO"]
        if cognome_nome:
            cognome = cognome_nome.split()[0]
            if len(cognome) > 3:
                keywords.append(cognome.upper())
        
        result = await cerca_in_estratto_conto(
            db, netto, data_scadenza_str,
            giorni_tolleranza=10,
            keywords_descrizione=keywords
        )
        if result:
            return result[0]  # solo l'id
        return None
    except Exception as e:
        logger.warning(f"Errore riconciliazione bancaria stipendio {cf}: {e}")
        return None


@router.post("/import-libro-unico", summary="Importa Libro Unico nel database (workflow completo)")
async def import_libro_unico(
    file: UploadFile = File(...),
    aggiorna_esistenti: bool = True
):
    """
    Parsa e importa il Libro Unico nel database - WORKFLOW COMPLETO.
    
    Per ogni dipendente esegue:
    1. Aggiornamento anagrafica (collection 'employees')
    2. Salvataggio presenze mensili (collection 'presenze_mensili')
    3. Aggiornamento busta paga con stato_pagamento (collection 'buste_paga')
    4. Creazione scadenza stipendio (collection 'scadenze')
    5. Riconciliazione bancaria automatica (prima_nota_banca)
    """
    try:
        db = Database.get_db()
        
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Il file deve essere un PDF")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
        
        try:
            try:
                parsed = parse_libro_unico_completo(tmp_path)
            except Exception as pdf_err:
                raise HTTPException(status_code=400, detail=f"Errore parsing PDF - file non valido o corrotto: {str(pdf_err)}")
            
            importati = 0
            aggiornati = 0
            anagrafica_aggiornata = 0
            presenze_salvate = 0
            scadenze_create = 0
            riconciliati = 0
            errori = []
            
            for i, dip_data in enumerate(parsed["dipendenti"]):
                try:
                    presenze_raw = dip_data.get("foglio_presenze", {}) or {}
                    busta = dip_data.get("busta_paga", {}) or {}
                    
                    # Estrai codice fiscale (da entrambe le fonti)
                    cf = presenze_raw.get("dipendente", {}).get("codice_fiscale") or \
                         busta.get("dipendente", {}).get("codice_fiscale")
                    
                    if not cf:
                        errori.append(f"Dipendente {i}: Codice fiscale non trovato")
                        continue
                    
                    cognome_nome = presenze_raw.get("dipendente", {}).get("cognome_nome") or \
                                   busta.get("dipendente", {}).get("cognome_nome") or ""
                    periodo = presenze_raw.get("dipendente", {}).get("periodo") or ""
                    iban = busta.get("pagamento", {}).get("iban") or ""
                    netto_str = busta.get("totali", {}).get("netto_mese", "0")
                    netto = parse_euro_amount(netto_str)
                    
                    # Parse data fine mese per scadenza
                    data_scadenza_str = None
                    periodo_parsed = parse_periodo_italiano(periodo)
                    if periodo_parsed:
                        anno, mese = periodo_parsed
                        data_scadenza_str = fine_mese_date(anno, mese)
                        periodo_iso = f"{anno:04d}-{mese:02d}"
                    else:
                        periodo_iso = periodo

                    # ========================================================
                    # STEP 1: AGGIORNAMENTO ANAGRAFICA DIPENDENTE (employees)
                    # ========================================================
                    parts = cognome_nome.split(maxsplit=1)
                    cognome = parts[0] if parts else cognome_nome
                    nome = parts[1] if len(parts) > 1 else ""
                    
                    anagrafica_update = {
                        "codice_fiscale": cf,
                        "nome_completo": cognome_nome,
                        "cognome": cognome,
                        "nome": nome,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                    if iban:
                        anagrafica_update["iban"] = iban
                        anagrafica_update["ibans"] = [iban]
                    
                    mansione = busta.get("dipendente", {}).get("mansione") or \
                               presenze_raw.get("dipendente", {}).get("tipo_rapporto")
                    if mansione:
                        anagrafica_update["mansione"] = mansione
                    
                    qualifica_codice = busta.get("dipendente", {}).get("qualifica_codice")
                    if qualifica_codice:
                        anagrafica_update["qualifica"] = qualifica_codice
                    
                    livello = busta.get("dipendente", {}).get("livello_descrizione")
                    if livello:
                        anagrafica_update["livello"] = livello
                    
                    pat_inail = presenze_raw.get("dipendente", {}).get("pat_inail")
                    if pat_inail:
                        anagrafica_update["pat_inail"] = pat_inail
                    
                    # Upsert anagrafica
                    ana_result = await db.employees.update_one(
                        {"codice_fiscale": cf},
                        {
                            "$set": anagrafica_update,
                            "$setOnInsert": {
                                "id": str(uuid.uuid4()),
                                "created_at": datetime.now(timezone.utc).isoformat(),
                                "attivo": True,
                                "in_carico": True
                            }
                        },
                        upsert=True
                    )
                    if ana_result.upserted_id or ana_result.modified_count > 0:
                        anagrafica_aggiornata += 1
                    
                    # ========================================================
                    # STEP 2: PRESENZE MENSILI (presenze_mensili)
                    # ========================================================
                    dettaglio_giorni = presenze_raw.get("presenze", [])
                    riep_giust = presenze_raw.get("riepilogo_giustificativi", [])
                    
                    # Calcola totali dalle giustificative
                    ore_ordinarie_tot = 0.0
                    for g in riep_giust:
                        if g.get("descrizione") == "Ore ordinarie":
                            try:
                                ore_ordinarie_tot = float(g["quantita"].replace(",", "."))
                            except (ValueError, AttributeError):
                                pass
                    
                    presenze_doc = {
                        "codice_fiscale": cf,
                        "dipendente_nome": cognome_nome,
                        "periodo": periodo_iso,
                        "periodo_testo": periodo,
                        "ore_ordinarie_totale": ore_ordinarie_tot,
                        "dettaglio_giornaliero": dettaglio_giorni,
                        "riepilogo_giustificativi": riep_giust,
                        "source_file": file.filename,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                    
                    await db.presenze_mensili.update_one(
                        {"codice_fiscale": cf, "periodo": periodo_iso},
                        {"$set": presenze_doc},
                        upsert=True
                    )
                    presenze_salvate += 1
                    
                    # ========================================================
                    # STEP 3: BUSTA PAGA (buste_paga)
                    # ========================================================
                    busta_id = f"bp_{cf}_{periodo_iso}".replace(" ", "_")
                    
                    busta_doc = {
                        "busta_id": busta_id,
                        "codice_fiscale": cf,
                        "dipendente_nome": cognome_nome,
                        "periodo": periodo_iso,
                        "periodo_testo": periodo,
                        "competenze": busta.get("competenze", []),
                        "trattenute": busta.get("trattenute", []),
                        "irpef": busta.get("irpef", {}),
                        "progressivi": busta.get("progressivi", {}),
                        "tfr": busta.get("tfr", {}),
                        "ratei": busta.get("ratei", {}),
                        "totali": busta.get("totali", {}),
                        "pagamento": busta.get("pagamento", {}),
                        "netto_mese": netto,
                        "iban_pagamento": iban,
                        "stato_pagamento": "DA_PAGARE",
                        "data_pagamento": None,
                        "movimento_bancario_id": None,
                        "acconti": [],
                        "source_file": file.filename,
                        "imported_at": datetime.now(timezone.utc).isoformat(),
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                    
                    busta_result = await db.buste_paga.update_one(
                        {"codice_fiscale": cf, "periodo": periodo_iso},
                        {"$set": busta_doc},
                        upsert=True
                    )
                    if busta_result.upserted_id:
                        importati += 1
                    else:
                        aggiornati += 1
                    
                    # ========================================================
                    # STEP 4: SCADENZA STIPENDIO (scadenze)
                    # ========================================================
                    if data_scadenza_str and netto > 0:
                        scad_doc = {
                            "titolo": f"Stipendio {periodo} - {cognome_nome}",
                            "tipo": "STIPENDIO",
                            "data_scadenza": data_scadenza_str,
                            "importo": netto,
                            "descrizione": f"Pagamento stipendio {periodo} per {cognome_nome} (CF: {cf})",
                            "documento_id": busta_id,
                            "codice_fiscale": cf,
                            "completata": False,
                            "priorita": "ALTA",
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }
                        
                        await db.scadenze.update_one(
                            {"documento_id": busta_id},
                            {"$set": scad_doc},
                            upsert=True
                        )
                        scadenze_create += 1
                    
                    # ========================================================
                    # STEP 5: RICONCILIAZIONE BANCARIA AUTOMATICA
                    # ========================================================
                    if netto > 0 and data_scadenza_str:
                        mov_id = await riconcilia_stipendio_con_banca(
                            db, cf, cognome_nome, netto, data_scadenza_str
                        )
                        if mov_id:
                            # Marca busta come PAGATA
                            await db.buste_paga.update_one(
                                {"codice_fiscale": cf, "periodo": periodo_iso},
                                {"$set": {
                                    "stato_pagamento": "PAGATO",
                                    "data_pagamento": datetime.now(timezone.utc).isoformat(),
                                    "movimento_bancario_id": mov_id
                                }}
                            )
                            # Marca scadenza come completata
                            await db.scadenze.update_one(
                                {"documento_id": busta_id},
                                {"$set": {"completata": True}}
                            )
                            # Marca movimento come riconciliato
                            await db.prima_nota_banca.update_one(
                                {"id": mov_id},
                                {"$set": {
                                    "riconciliato_stipendio": True,
                                    "documento_stipendio_id": busta_id
                                }}
                            )
                            riconciliati += 1
                            
                except Exception as e:
                    errori.append(f"Dipendente {i} ({cf if 'cf' in dir() else '?'}): {str(e)}")
                    logger.warning(f"Errore workflow dipendente {i}: {e}")
            
            return {
                "success": True,
                "message": (
                    f"Workflow LUL completato: {importati} buste nuove, {aggiornati} aggiornate, "
                    f"{anagrafica_aggiornata} anagrafiche, {presenze_salvate} presenze, "
                    f"{scadenze_create} scadenze, {riconciliati} pagamenti riconciliati"
                ),
                "data": {
                    "totale_dipendenti": parsed["totale_dipendenti"],
                    "buste_importate": importati,
                    "buste_aggiornate": aggiornati,
                    "anagrafica_aggiornata": anagrafica_aggiornata,
                    "presenze_salvate": presenze_salvate,
                    "scadenze_create": scadenze_create,
                    "pagamenti_riconciliati": riconciliati,
                    "errori": errori,
                    "riepilogo": parsed["riepilogo"]
                }
            }
        finally:
            os.unlink(tmp_path)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore import Libro Unico: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/riconcilia-stipendi", summary="Riconcilia stipendi con movimenti bancari")
async def riconcilia_stipendi(
    anno: int = None,
    mese: int = None
):
    """
    Riesegue la riconciliazione bancaria per tutti gli stipendi DA_PAGARE.
    Normalmente avviene automaticamente al caricamento dell'estratto conto.
    """
    try:
        db = Database.get_db()
        from app.services.paghe_riconciliazione import riconcilia_tutti_stipendi
        result = await riconcilia_tutti_stipendi(db, anno=anno, mese=mese)
        return {
            "success": True,
            "message": f"Riconciliazione completata: {result['riconciliati']} saldati, {result['non_trovati']} da saldare",
            "data": result
        }
    except Exception as e:
        logger.error(f"Errore riconciliazione stipendi: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/buste-paga", summary="Lista buste paga importate")
async def get_buste_paga(
    anno: Optional[int] = None,
    mese: Optional[int] = None,
    stato: Optional[str] = None,
    codice_fiscale: Optional[str] = None
):
    """Lista buste paga con filtri opzionali."""
    try:
        db = Database.get_db()
        
        query = {}
        if anno and mese:
            query["periodo"] = f"{anno:04d}-{mese:02d}"
        elif anno:
            query["periodo"] = {"$regex": f"^{anno:04d}-"}
        if stato:
            query["stato_pagamento"] = stato
        if codice_fiscale:
            query["codice_fiscale"] = codice_fiscale
        
        buste = await db.buste_paga.find(
            query,
            {"_id": 0, "busta_id": 1, "codice_fiscale": 1, "dipendente_nome": 1,
             "periodo": 1, "netto_mese": 1, "stato_pagamento": 1, "data_pagamento": 1,
             "movimento_bancario_id": 1, "imported_at": 1}
        ).sort("periodo", -1).to_list(length=500)
        
        return {
            "success": True,
            "data": buste,
            "count": len(buste)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



# ============================================================
# ENDPOINT: PRESENZE MENSILI
# ============================================================

@router.get("/presenze-mensili", summary="Lista presenze mensili (da LUL)")
async def get_presenze_mensili(
    anno: Optional[int] = None,
    mese: Optional[int] = None,
    codice_fiscale: Optional[str] = None
):
    """
    Lista presenze mensili importate dal Libro Unico.
    Restituisce riepilogo per ogni dipendente (ore totali, ferie, assenze).
    """
    try:
        db = Database.get_db()
        query = {"codice_fiscale": {"$exists": True}}
        if anno and mese:
            query["periodo"] = f"{anno:04d}-{mese:02d}"
        elif anno:
            query["periodo"] = {"$regex": f"^{anno:04d}-"}
        if codice_fiscale:
            query["codice_fiscale"] = codice_fiscale

        presenze = await db.presenze_mensili.find(
            query,
            {"_id": 0, "codice_fiscale": 1, "dipendente_nome": 1, "periodo": 1,
             "periodo_testo": 1, "ore_ordinarie_totale": 1, "riepilogo_giustificativi": 1,
             "source_file": 1, "updated_at": 1}
        ).sort([("periodo", -1), ("dipendente_nome", 1)]).to_list(length=500)

        return {"success": True, "data": presenze, "count": len(presenze)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/presenze-mensili/{codice_fiscale}/{periodo}", summary="Dettaglio presenze dipendente")
async def get_presenze_dettaglio(codice_fiscale: str, periodo: str):
    """
    Dettaglio completo presenze mensili di un dipendente (calendario giornaliero + giustificativi).
    Periodo formato: YYYY-MM (es. 2026-01)
    """
    try:
        db = Database.get_db()
        doc = await db.presenze_mensili.find_one(
            {"codice_fiscale": codice_fiscale, "periodo": periodo},
            {"_id": 0}
        )
        if not doc:
            raise HTTPException(status_code=404, detail="Presenze non trovate")
        return {"success": True, "data": doc}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# ENDPOINT: ACCONTI MENSILI
# ============================================================

@router.get("/acconti", summary="Lista acconti dipendenti")
async def get_acconti(
    anno: Optional[int] = None,
    mese: Optional[int] = None,
    codice_fiscale: Optional[str] = None
):
    """Lista buste paga con il dettaglio degli acconti."""
    try:
        db = Database.get_db()
        query = {}
        if anno and mese:
            query["periodo"] = f"{anno:04d}-{mese:02d}"
        elif anno:
            query["periodo"] = {"$regex": f"^{anno:04d}-"}
        if codice_fiscale:
            query["codice_fiscale"] = codice_fiscale

        buste = await db.buste_paga.find(
            query,
            {"_id": 0, "busta_id": 1, "codice_fiscale": 1, "dipendente_nome": 1,
             "periodo": 1, "periodo_testo": 1, "netto_mese": 1, "acconti": 1,
             "stato_pagamento": 1}
        ).sort([("periodo", -1), ("dipendente_nome", 1)]).to_list(length=500)

        # Calcola totale acconti e residuo per ogni busta
        for b in buste:
            acconti = b.get("acconti") or []
            tot_acconti = sum(float(a.get("importo", 0)) for a in acconti)
            b["totale_acconti"] = round(tot_acconti, 2)
            b["residuo_da_pagare"] = round((b.get("netto_mese") or 0) - tot_acconti, 2)

        return {"success": True, "data": buste, "count": len(buste)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/acconti/{busta_id}", summary="Aggiungi acconto a una busta paga")
async def aggiungi_acconto(busta_id: str, body: dict):
    """
    Aggiunge un acconto alla busta paga specificata.
    Body: { importo: float, data: "YYYY-MM-DD", nota: str, tipo: "ACCONTO|ANTICIPO|ALTRO" }
    """
    try:
        db = Database.get_db()
        importo = float(body.get("importo", 0))
        if importo <= 0:
            raise HTTPException(status_code=400, detail="Importo deve essere positivo")

        acconto = {
            "id": str(uuid.uuid4())[:8],
            "importo": importo,
            "data": body.get("data", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
            "nota": body.get("nota", ""),
            "tipo": body.get("tipo", "ACCONTO").upper(),
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        result = await db.buste_paga.update_one(
            {"busta_id": busta_id},
            {"$push": {"acconti": acconto},
             "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}}
        )

        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail=f"Busta {busta_id} non trovata")

        # Ricalcola residuo
        busta = await db.buste_paga.find_one({"busta_id": busta_id}, {"_id": 0, "acconti": 1, "netto_mese": 1})
        acconti = busta.get("acconti") or []
        tot = sum(float(a.get("importo", 0)) for a in acconti)
        residuo = round((busta.get("netto_mese") or 0) - tot, 2)

        return {
            "success": True,
            "message": "Acconto aggiunto",
            "acconto": acconto,
            "totale_acconti": round(tot, 2),
            "residuo_da_pagare": residuo
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/acconti/{busta_id}/{acconto_id}", summary="Elimina acconto")
async def elimina_acconto(busta_id: str, acconto_id: str):
    """Elimina un acconto dalla busta paga per ID."""
    try:
        db = Database.get_db()
        result = await db.buste_paga.update_one(
            {"busta_id": busta_id},
            {"$pull": {"acconti": {"id": acconto_id}},
             "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Busta non trovata")

        return {"success": True, "message": "Acconto eliminato"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
