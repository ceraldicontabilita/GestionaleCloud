"""
Parser Estratto Conto Banco BPM
Estrae movimenti bancari dal formato CSV di Banco BPM
e supporta la riconciliazione automatica con F24
"""
import csv
import re
from datetime import datetime
from typing import Dict, List, Any, Optional
from io import StringIO
import logging

logger = logging.getLogger(__name__)


def parse_importo_bpm(value: str) -> float:
    """Converte importo BPM (formato italiano) in float."""
    if not value:
        return 0.0
    # Rimuovi spazi e converti virgola in punto
    value = str(value).strip().replace('.', '').replace(',', '.')
    try:
        return float(value)
    except ValueError:
        return 0.0


def parse_data_bpm(value: str) -> Optional[datetime]:
    """Converte data BPM (dd/mm/yyyy) in datetime."""
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%d/%m/%Y")
    except ValueError:
        return None


def parse_estratto_conto_bpm(file_content: str) -> Dict[str, Any]:
    """
    Parsa un estratto conto CSV di Banco BPM.
    
    Formato BPM:
    Ragione Sociale;Data contabile;Data valuta;Banca;Rapporto;Importo;Divisa;Descrizione;Categoria/sottocategoria;Hashtag
    
    Returns:
        Dict con:
        - movimenti: lista di tutti i movimenti
        - movimenti_f24: movimenti identificati come pagamenti F24
        - totale_entrate: somma entrate
        - totale_uscite: somma uscite
        - saldo: differenza
        - periodo: {da, a}
    """
    result = {
        "movimenti": [],
        "movimenti_f24": [],
        "totale_entrate": 0.0,
        "totale_uscite": 0.0,
        "saldo": 0.0,
        "periodo": {"da": None, "a": None},
        "conto": {},
        "stats": {
            "totale_movimenti": 0,
            "movimenti_f24": 0,
            "categorie": {}
        }
    }
    
    try:
        # Leggi CSV con delimitatore ;
        reader = csv.DictReader(StringIO(file_content), delimiter=';')
        
        date_min = None
        date_max = None
        categorie_count = {}
        
        for row in reader:
            try:
                # Estrai campi
                data_contabile = parse_data_bpm(row.get('Data contabile', ''))
                data_valuta = parse_data_bpm(row.get('Data valuta', ''))
                importo = parse_importo_bpm(row.get('Importo', '0'))
                descrizione = row.get('Descrizione', '').strip()
                categoria = row.get('Categoria/sottocategoria', '').strip()
                ragione_sociale = row.get('Ragione Sociale', '').strip()
                banca = row.get('Banca', '').strip()
                rapporto = row.get('Rapporto', '').strip()
                divisa = row.get('Divisa', 'EUR').strip()
                
                if not data_contabile:
                    continue
                
                # Aggiorna periodo
                if date_min is None or data_contabile < date_min:
                    date_min = data_contabile
                if date_max is None or data_contabile > date_max:
                    date_max = data_contabile
                
                # Conta categorie
                if categoria:
                    cat_base = categoria.split(' - ')[0] if ' - ' in categoria else categoria
                    categorie_count[cat_base] = categorie_count.get(cat_base, 0) + 1
                
                # Determina tipo movimento
                tipo = "entrata" if importo > 0 else "uscita"
                
                # Calcola totali
                if importo > 0:
                    result["totale_entrate"] += importo
                else:
                    result["totale_uscite"] += abs(importo)
                
                # Crea record movimento
                movimento = {
                    "data_contabile": data_contabile.strftime("%Y-%m-%d") if data_contabile else None,
                    "data_valuta": data_valuta.strftime("%Y-%m-%d") if data_valuta else None,
                    "importo": round(importo, 2),
                    "importo_abs": round(abs(importo), 2),
                    "tipo": tipo,
                    "descrizione": descrizione,
                    "categoria": categoria,
                    "divisa": divisa,
                    "ragione_sociale": ragione_sociale,
                    "banca": banca,
                    "rapporto": rapporto,
                    "is_f24": False,
                    "f24_match": None
                }
                
                # Identifica pagamenti F24
                if is_pagamento_f24(descrizione):
                    movimento["is_f24"] = True
                    movimento["f24_info"] = extract_f24_info(descrizione, data_contabile)
                    result["movimenti_f24"].append(movimento)
                
                result["movimenti"].append(movimento)
                
            except Exception as e:
                logger.warning(f"Errore parsing riga: {e}")
                continue
        
        # Calcola statistiche finali
        result["saldo"] = round(result["totale_entrate"] - result["totale_uscite"], 2)
        result["totale_entrate"] = round(result["totale_entrate"], 2)
        result["totale_uscite"] = round(result["totale_uscite"], 2)
        
        if date_min:
            result["periodo"]["da"] = date_min.strftime("%Y-%m-%d")
        if date_max:
            result["periodo"]["a"] = date_max.strftime("%Y-%m-%d")
        
        result["stats"]["totale_movimenti"] = len(result["movimenti"])
        result["stats"]["movimenti_f24"] = len(result["movimenti_f24"])
        result["stats"]["categorie"] = categorie_count
        
        # Info conto dalla prima riga
        if result["movimenti"]:
            first = result["movimenti"][0]
            result["conto"] = {
                "ragione_sociale": first.get("ragione_sociale"),
                "banca": first.get("banca"),
                "rapporto": first.get("rapporto")
            }
        
        logger.info(f"Estratto BPM parsato: {len(result['movimenti'])} movimenti, {len(result['movimenti_f24'])} F24")
        
    except Exception as e:
        logger.error(f"Errore parsing estratto conto BPM: {e}")
        result["error"] = str(e)
    
    return result


def is_pagamento_f24(descrizione: str) -> bool:
    """Verifica se la descrizione indica un pagamento F24."""
    if not descrizione:
        return False
    
    descrizione_upper = descrizione.upper()
    
    # Pattern per pagamenti F24
    f24_patterns = [
        "I24 AGENZIA ENTRATE",
        "F24 AGENZIA ENTRATE",
        "PAG.TO TELEMATICO",
        "PAGAMENTO F24",
        "DELEGA F24",
        "VERSAMENTO F24",
        "TRIBUTI F24"
    ]
    
    return any(pattern in descrizione_upper for pattern in f24_patterns)


def extract_f24_info(descrizione: str, data: datetime) -> Dict[str, Any]:
    """
    Estrae informazioni F24 dalla descrizione del movimento bancario.
    
    Esempio BPM:
    "I24 AGENZIA ENTRATE - PAG.TO TELEMATICO - DATA INCASSO 15/01/2025 2025-01-15-22.40.17.970858001084"
    """
    info = {
        "tipo": "F24",
        "data_incasso": None,
        "riferimento": None,
        "raw_descrizione": descrizione
    }
    
    # Estrai data incasso
    data_match = re.search(r'DATA INCASSO (\d{2}/\d{2}/\d{4})', descrizione)
    if data_match:
        try:
            info["data_incasso"] = datetime.strptime(data_match.group(1), "%d/%m/%Y").strftime("%Y-%m-%d")
        except:
            pass
    
    # Estrai riferimento (timestamp univoco)
    ref_match = re.search(r'(\d{4}-\d{2}-\d{2}-\d{2}\.\d{2}\.\d{2}\.\d+)', descrizione)
    if ref_match:
        info["riferimento"] = ref_match.group(1)
    
    return info


def riconcilia_f24_con_estratto(f24_list: List[Dict], movimenti_f24: List[Dict]) -> Dict[str, Any]:
    """
    Riconcilia gli F24 caricati con i movimenti F24 dell'estratto conto.
    
    Matching basato su:
    1. Importo (tolleranza ±0.01€)
    2. Data (tolleranza ±3 giorni)
    
    Returns:
        Dict con:
        - f24_riconciliati: F24 con movimento bancario trovato
        - f24_non_pagati: F24 senza movimento bancario
        - movimenti_non_associati: Movimenti F24 senza F24 corrispondente
        - stats: statistiche riconciliazione
    """
    result = {
        "f24_riconciliati": [],
        "f24_non_pagati": [],
        "movimenti_non_associati": [],
        "stats": {
            "totale_f24": len(f24_list),
            "totale_movimenti_f24": len(movimenti_f24),
            "riconciliati": 0,
            "non_pagati": 0,
            "non_associati": 0
        }
    }
    
    # Copia movimenti per tracking
    movimenti_disponibili = movimenti_f24.copy()
    
    for f24 in f24_list:
        f24_importo = f24.get("totali", {}).get("saldo_netto", 0)
        f24_data_str = f24.get("dati_generali", {}).get("data_versamento")
        
        if f24_data_str:
            try:
                f24_data = datetime.strptime(f24_data_str, "%Y-%m-%d")
            except:
                f24_data = None
        else:
            f24_data = None
        
        # Cerca movimento corrispondente
        match_found = None
        match_index = -1
        
        for idx, mov in enumerate(movimenti_disponibili):
            mov_importo = abs(mov.get("importo", 0))
            mov_data_str = mov.get("data_contabile") or mov.get("f24_info", {}).get("data_incasso")
            
            if mov_data_str:
                try:
                    mov_data = datetime.strptime(mov_data_str, "%Y-%m-%d")
                except:
                    mov_data = None
            else:
                mov_data = None
            
            # Check importo (tolleranza 0.01€)
            importo_match = abs(f24_importo - mov_importo) <= 0.01
            
            # Check data (tolleranza 3 giorni)
            data_match = True
            if f24_data and mov_data:
                data_match = abs((f24_data - mov_data).days) <= 3
            
            if importo_match and data_match:
                match_found = mov
                match_index = idx
                break
        
        if match_found:
            # F24 riconciliato
            f24_riconciliato = {
                **f24,
                "stato_pagamento": "PAGATO",
                "movimento_bancario": match_found,
                "data_pagamento_effettivo": match_found.get("data_contabile")
            }
            result["f24_riconciliati"].append(f24_riconciliato)
            result["stats"]["riconciliati"] += 1
            
            # Rimuovi movimento usato
            if match_index >= 0:
                movimenti_disponibili.pop(match_index)
        else:
            # F24 non pagato
            f24_non_pagato = {
                **f24,
                "stato_pagamento": "DA_PAGARE",
                "movimento_bancario": None
            }
            result["f24_non_pagati"].append(f24_non_pagato)
            result["stats"]["non_pagati"] += 1
    
    # Movimenti non associati
    result["movimenti_non_associati"] = movimenti_disponibili
    result["stats"]["non_associati"] = len(movimenti_disponibili)
    
    return result


def genera_report_riconciliazione(riconciliazione: Dict) -> str:
    """Genera report testuale della riconciliazione."""
    lines = []
    lines.append("=" * 60)
    lines.append("REPORT RICONCILIAZIONE F24 - ESTRATTO CONTO")
    lines.append("=" * 60)
    lines.append("")
    
    stats = riconciliazione.get("stats", {})
    lines.append(f"F24 Caricati: {stats.get('totale_f24', 0)}")
    lines.append(f"Movimenti F24 in Banca: {stats.get('totale_movimenti_f24', 0)}")
    lines.append("")
    lines.append(f"✅ Riconciliati: {stats.get('riconciliati', 0)}")
    lines.append(f"❌ Non Pagati: {stats.get('non_pagati', 0)}")
    lines.append(f"❓ Movimenti Non Associati: {stats.get('non_associati', 0)}")
    lines.append("")
    
    # F24 non pagati
    if riconciliazione.get("f24_non_pagati"):
        lines.append("-" * 40)
        lines.append("F24 DA PAGARE:")
        for f24 in riconciliazione["f24_non_pagati"]:
            importo = f24.get("totali", {}).get("saldo_netto", 0)
            nome = f24.get("file_name", "N/A")
            lines.append(f"  • {nome}: €{importo:,.2f}")
    
    # Movimenti non associati
    if riconciliazione.get("movimenti_non_associati"):
        lines.append("-" * 40)
        lines.append("MOVIMENTI F24 SENZA F24 CORRISPONDENTE:")
        for mov in riconciliazione["movimenti_non_associati"][:10]:  # Max 10
            importo = abs(mov.get("importo", 0))
            data = mov.get("data_contabile", "N/A")
            lines.append(f"  • {data}: €{importo:,.2f}")
    
    lines.append("")
    lines.append("=" * 60)
    
    return "\n".join(lines)
