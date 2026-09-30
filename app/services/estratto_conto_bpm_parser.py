"""
Parser Estratto Conto Banco BPM
Estrae movimenti bancari dal formato CSV di Banco BPM
e supporta la riconciliazione automatica con F24
"""
import csv
import re
from datetime import datetime
from typing import Dict, Any, Optional
from io import StringIO
import logging

from app.utils.numeri_italiani import parse_importo_ita

logger = logging.getLogger(__name__)


def parse_importo_bpm(value: str) -> float:
    """Converte importo BPM (formato italiano) in float."""
    return parse_importo_ita(value)


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
        except Exception:
            pass
    
    # Estrai riferimento (timestamp univoco)
    ref_match = re.search(r'(\d{4}-\d{2}-\d{2}-\d{2}\.\d{2}\.\d{2}\.\d+)', descrizione)
    if ref_match:
        info["riferimento"] = ref_match.group(1)
    
    return info
