"""
Sistema Gestione F24 Avanzato
- F24 Originali vs Ravveduti
- Riconciliazione con estratto conto
- Database codici tributo pagati
- Alert e report mensili
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class StatoF24(str, Enum):
    """Stati possibili di un F24"""
    RICEVUTO = "RICEVUTO"           # Appena caricato
    DA_PAGARE = "DA_PAGARE"         # In attesa di pagamento
    PAGATO = "PAGATO"               # Pagato (riconciliato con banca)
    SOSTITUITO = "SOSTITUITO"       # Sostituito da F24 con ravvedimento
    SCADUTO = "SCADUTO"             # Scadenza superata senza pagamento
    ANNULLATO = "ANNULLATO"         # Annullato manualmente


class TipoF24(str, Enum):
    """Tipi di F24"""
    ORIGINALE = "ORIGINALE"         # F24 standard dalla commercialista
    RAVVEDIMENTO = "RAVVEDIMENTO"   # F24 con ravvedimento operoso
    SOSTITUTIVO = "SOSTITUTIVO"     # F24 che sostituisce un precedente


class CategoriaArchivio(str, Enum):
    """Categorie archivio F24"""
    ATTIVI = "ATTIVI"               # F24 attivi (da pagare o pagati)
    ORIGINALI_SOSTITUITI = "ORIGINALI_SOSTITUITI"  # F24 originali sostituiti da ravvedimento
    RAVVEDUTI = "RAVVEDUTI"         # F24 pagati con ravvedimento
    STORICO = "STORICO"             # Archivio storico


def calcola_scadenza_f24(data_riferimento: str, tipo_tributo: str) -> Optional[datetime]:
    """
    Calcola la scadenza di un F24 in base al tipo di tributo.
    
    Scadenze standard:
    - IVA mensile: 16 del mese successivo
    - Ritenute dipendenti: 16 del mese successivo
    - INPS: 16 del mese successivo
    - INAIL: rate trimestrali
    - IMU: 16 giugno (acconto) e 16 dicembre (saldo)
    """
    if not data_riferimento:
        return None
    
    try:
        # Parse periodo riferimento (es. "10/2025" o "2025")
        if "/" in data_riferimento:
            mese, anno = data_riferimento.split("/")
            mese = int(mese) if mese != "00" else 1
            anno = int(anno)
        else:
            anno = int(data_riferimento)
            mese = 12  # Default dicembre per tributi annuali
        
        # Scadenza standard: 16 del mese successivo
        mese_scadenza = mese + 1 if mese < 12 else 1
        anno_scadenza = anno if mese < 12 else anno + 1
        
        return datetime(anno_scadenza, mese_scadenza, 16)
        
    except Exception as e:
        logger.warning(f"Errore calcolo scadenza: {e}")
        return None


def identifica_f24_correlati(f24_nuovo: Dict, f24_esistenti: List[Dict]) -> Dict[str, Any]:
    """
    Identifica se un F24 nuovo è correlato a F24 esistenti (es. ravvedimento).
    
    Criteri di correlazione:
    1. Stesso codice fiscale
    2. Stessi codici tributo (almeno 70% match)
    3. Stesso periodo di riferimento
    4. Il nuovo ha codici ravvedimento → è un ravvedimento del precedente
    
    Returns:
        {
            "is_ravvedimento": True/False,
            "f24_originale_id": str or None,
            "codici_match": list,
            "differenza_importo": float
        }
    """
    result = {
        "is_ravvedimento": False,
        "f24_originale_id": None,
        "codici_match": [],
        "differenza_importo": 0.0,
        "tipo_suggerito": TipoF24.ORIGINALE.value
    }
    
    # Estrai info dal nuovo F24
    nuovo_cf = f24_nuovo.get("dati_generali", {}).get("codice_fiscale", "")
    nuovo_has_ravv = f24_nuovo.get("has_ravvedimento", False)
    nuovo_codici = set()
    nuovo_periodi = set()
    
    for tributo in f24_nuovo.get("sezione_erario", []):
        nuovo_codici.add(tributo.get("codice_tributo"))
        nuovo_periodi.add(tributo.get("periodo_riferimento"))
    
    for tributo in f24_nuovo.get("sezione_inps", []):
        nuovo_codici.add(tributo.get("causale"))
        nuovo_periodi.add(tributo.get("periodo_riferimento"))
    
    # Cerca correlazioni
    for f24_esistente in f24_esistenti:
        # Skip se stesso F24
        if f24_esistente.get("id") == f24_nuovo.get("id"):
            continue
        
        # Skip se già sostituito
        if f24_esistente.get("stato") == StatoF24.SOSTITUITO.value:
            continue
        
        esistente_cf = f24_esistente.get("dati_generali", {}).get("codice_fiscale", "")
        
        # Check stesso CF
        if nuovo_cf and esistente_cf and nuovo_cf != esistente_cf:
            continue
        
        # Estrai codici esistente
        esistente_codici = set()
        esistente_periodi = set()
        
        for tributo in f24_esistente.get("sezione_erario", []):
            esistente_codici.add(tributo.get("codice_tributo"))
            esistente_periodi.add(tributo.get("periodo_riferimento"))
        
        for tributo in f24_esistente.get("sezione_inps", []):
            esistente_codici.add(tributo.get("causale"))
            esistente_periodi.add(tributo.get("periodo_riferimento"))
        
        # Rimuovi codici ravvedimento per il confronto
        CODICI_RAVV = {'8901', '8902', '8904', '8906', '8907', '8911', '8918', '8926', '1990', '1991', '1993', '1994'}
        nuovo_codici_base = nuovo_codici - CODICI_RAVV
        esistente_codici_base = esistente_codici - CODICI_RAVV
        
        # Calcola match
        if nuovo_codici_base and esistente_codici_base:
            codici_comuni = nuovo_codici_base & esistente_codici_base
            match_percentage = len(codici_comuni) / max(len(esistente_codici_base), 1) * 100
            
            # Periodi comuni
            periodi_comuni = nuovo_periodi & esistente_periodi
            
            # Se il nuovo ha ravvedimento e match >= 50% con stesso periodo
            if nuovo_has_ravv and match_percentage >= 50 and periodi_comuni:
                result["is_ravvedimento"] = True
                result["f24_originale_id"] = f24_esistente.get("id")
                result["codici_match"] = list(codici_comuni)
                result["tipo_suggerito"] = TipoF24.RAVVEDIMENTO.value
                
                # Calcola differenza importo (il ravvedimento è sempre maggiore)
                nuovo_importo = f24_nuovo.get("totali", {}).get("saldo_netto", 0)
                esistente_importo = f24_esistente.get("totali", {}).get("saldo_netto", 0)
                result["differenza_importo"] = round(nuovo_importo - esistente_importo, 2)
                
                break
    
    return result


def riconcilia_f24_avanzato(
    f24_list: List[Dict], 
    movimenti_banca: List[Dict],
    quietanze: List[Dict] = None
) -> Dict[str, Any]:
    """
    Riconciliazione avanzata F24:
    1. Match F24 con movimenti bancari
    2. Se pagato F24 originale → OK
    3. Se pagato F24 ravvedimento → archivia originale come "sostituito"
    4. Genera lista tributi pagati
    
    Returns:
        {
            "f24_pagati": [...],
            "f24_da_pagare": [...],
            "f24_sostituiti": [...],  # Originali sostituiti da ravvedimento
            "tributi_pagati": [...],   # Database tributi
            "alert": [...]
        }
    """
    result = {
        "f24_pagati": [],
        "f24_da_pagare": [],
        "f24_sostituiti": [],
        "tributi_pagati": [],
        "alert": [],
        "stats": {
            "totale_f24": len(f24_list),
            "pagati": 0,
            "da_pagare": 0,
            "sostituiti": 0,
            "totale_pagato": 0.0,
            "totale_da_pagare": 0.0
        }
    }
    
    # Ordina F24 per data upload (più recenti prima per gestire ravvedimenti)
    f24_sorted = sorted(f24_list, key=lambda x: x.get("upload_date", ""), reverse=True)
    
    # Traccia F24 già processati
    f24_processati = set()
    movimenti_usati = set()
    
    for f24 in f24_sorted:
        f24_id = f24.get("id")
        
        if f24_id in f24_processati:
            continue
        
        f24_importo = f24.get("totali", {}).get("saldo_netto", 0)
        f24_is_ravv = f24.get("has_ravvedimento", False)
        f24_originale_id = f24.get("f24_originale_sostituito")
        
        # Cerca match in movimenti bancari
        match_bancario = None
        match_idx = None
        
        for idx, mov in enumerate(movimenti_banca):
            if idx in movimenti_usati:
                continue
            
            mov_importo = abs(mov.get("importo", 0))
            
            # Match per importo ESATTO (tolleranza 0.01€ per arrotondamenti decimali)
            if abs(f24_importo - mov_importo) <= 0.01:
                match_bancario = mov
                match_idx = idx
                break
        
        if match_bancario:
            # F24 PAGATO
            f24_pagato = {
                **f24,
                "stato": StatoF24.PAGATO.value,
                "data_pagamento": match_bancario.get("data_contabile"),
                "movimento_bancario": {
                    "data": match_bancario.get("data_contabile"),
                    "importo": match_bancario.get("importo"),
                    "riferimento": match_bancario.get("f24_info", {}).get("riferimento")
                }
            }
            result["f24_pagati"].append(f24_pagato)
            result["stats"]["pagati"] += 1
            result["stats"]["totale_pagato"] += f24_importo
            
            f24_processati.add(f24_id)
            if match_idx is not None:
                movimenti_usati.add(match_idx)
            
            # Se è un ravvedimento, archivia l'originale come "sostituito"
            if f24_is_ravv and f24_originale_id:
                # Cerca l'F24 originale
                for f24_orig in f24_list:
                    if f24_orig.get("id") == f24_originale_id:
                        f24_sostituito = {
                            **f24_orig,
                            "stato": StatoF24.SOSTITUITO.value,
                            "categoria_archivio": CategoriaArchivio.ORIGINALI_SOSTITUITI.value,
                            "sostituito_da": f24_id,
                            "data_sostituzione": datetime.now(timezone.utc).isoformat()
                        }
                        result["f24_sostituiti"].append(f24_sostituito)
                        result["stats"]["sostituiti"] += 1
                        f24_processati.add(f24_originale_id)
                        break
            
            # Estrai tributi pagati
            for tributo in f24.get("sezione_erario", []):
                result["tributi_pagati"].append({
                    "tipo": "ERARIO",
                    "codice_tributo": tributo.get("codice_tributo"),
                    "descrizione": tributo.get("descrizione"),
                    "periodo": tributo.get("periodo_riferimento"),
                    "anno": tributo.get("anno"),
                    "importo_debito": tributo.get("importo_debito", 0),
                    "importo_credito": tributo.get("importo_credito", 0),
                    "data_pagamento": match_bancario.get("data_contabile"),
                    "f24_id": f24_id,
                    "is_ravvedimento": f24_is_ravv
                })
            
            for tributo in f24.get("sezione_inps", []):
                result["tributi_pagati"].append({
                    "tipo": "INPS",
                    "codice_tributo": tributo.get("causale"),
                    "descrizione": tributo.get("descrizione"),
                    "periodo": tributo.get("periodo_riferimento"),
                    "anno": tributo.get("anno"),
                    "importo_debito": tributo.get("importo_debito", 0),
                    "importo_credito": tributo.get("importo_credito", 0),
                    "data_pagamento": match_bancario.get("data_contabile"),
                    "f24_id": f24_id,
                    "is_ravvedimento": f24_is_ravv
                })
            
            for tributo in f24.get("sezione_inail", []):
                result["tributi_pagati"].append({
                    "tipo": "INAIL",
                    "codice_tributo": tributo.get("causale", "INAIL"),
                    "descrizione": tributo.get("descrizione"),
                    "periodo": f"{tributo.get('anno', '')}",
                    "anno": tributo.get("anno"),
                    "importo_debito": tributo.get("importo_debito", 0),
                    "importo_credito": tributo.get("importo_credito", 0),
                    "data_pagamento": match_bancario.get("data_contabile"),
                    "f24_id": f24_id,
                    "is_ravvedimento": f24_is_ravv
                })
            
            for tributo in f24.get("sezione_regioni", []):
                result["tributi_pagati"].append({
                    "tipo": "REGIONI",
                    "codice_tributo": tributo.get("codice_tributo"),
                    "codice_regione": tributo.get("codice_regione"),
                    "descrizione": tributo.get("descrizione"),
                    "periodo": tributo.get("periodo_riferimento"),
                    "anno": tributo.get("anno"),
                    "importo_debito": tributo.get("importo_debito", 0),
                    "importo_credito": tributo.get("importo_credito", 0),
                    "data_pagamento": match_bancario.get("data_contabile"),
                    "f24_id": f24_id,
                    "is_ravvedimento": f24_is_ravv
                })
            
            for tributo in f24.get("sezione_tributi_locali", []):
                result["tributi_pagati"].append({
                    "tipo": "TRIBUTI_LOCALI",
                    "codice_tributo": tributo.get("codice_tributo"),
                    "codice_comune": tributo.get("codice_comune"),
                    "descrizione": tributo.get("descrizione"),
                    "periodo": tributo.get("periodo_riferimento"),
                    "anno": tributo.get("anno"),
                    "importo_debito": tributo.get("importo_debito", 0),
                    "importo_credito": tributo.get("importo_credito", 0),
                    "data_pagamento": match_bancario.get("data_contabile"),
                    "f24_id": f24_id,
                    "is_ravvedimento": f24_is_ravv
                })
        
        else:
            # F24 NON PAGATO
            f24_non_pagato = {
                **f24,
                "stato": StatoF24.DA_PAGARE.value
            }
            
            # Calcola scadenza e verifica alert
            for tributo in f24.get("sezione_erario", []):
                scadenza = calcola_scadenza_f24(tributo.get("periodo_riferimento"), tributo.get("codice_tributo"))
                if scadenza:
                    f24_non_pagato["scadenza_stimata"] = scadenza.isoformat()
                    
                    # Alert se scadenza vicina o passata
                    oggi = datetime.now(timezone.utc)
                    if scadenza < oggi:
                        result["alert"].append({
                            "tipo": "SCADUTO",
                            "priorita": "ALTA",
                            "f24_id": f24_id,
                            "file_name": f24.get("file_name"),
                            "importo": f24_importo,
                            "scadenza": scadenza.isoformat(),
                            "giorni_ritardo": (oggi - scadenza).days,
                            "messaggio": f"F24 scaduto da {(oggi - scadenza).days} giorni! Importo: €{f24_importo:,.2f}"
                        })
                    elif scadenza <= oggi + timedelta(days=7):
                        result["alert"].append({
                            "tipo": "IN_SCADENZA",
                            "priorita": "MEDIA",
                            "f24_id": f24_id,
                            "file_name": f24.get("file_name"),
                            "importo": f24_importo,
                            "scadenza": scadenza.isoformat(),
                            "giorni_rimanenti": (scadenza - oggi).days,
                            "messaggio": f"F24 in scadenza tra {(scadenza - oggi).days} giorni! Importo: €{f24_importo:,.2f}"
                        })
                    break
            
            result["f24_da_pagare"].append(f24_non_pagato)
            result["stats"]["da_pagare"] += 1
            result["stats"]["totale_da_pagare"] += f24_importo
            f24_processati.add(f24_id)
    
    # Round totali
    result["stats"]["totale_pagato"] = round(result["stats"]["totale_pagato"], 2)
    result["stats"]["totale_da_pagare"] = round(result["stats"]["totale_da_pagare"], 2)
    
    return result


def genera_report_mensile(
    tributi_pagati: List[Dict],
    f24_pagati: List[Dict],
    f24_da_pagare: List[Dict],
    anno: int,
    mese: int
) -> Dict[str, Any]:
    """
    Genera report mensile dei tributi pagati e F24.
    """
    # Filtra per mese/anno
    tributi_mese = [
        t for t in tributi_pagati
        if t.get("data_pagamento", "").startswith(f"{anno}-{mese:02d}")
    ]
    
    # Raggruppa per tipo
    per_tipo = {}
    for tributo in tributi_mese:
        tipo = tributo.get("tipo", "ALTRO")
        if tipo not in per_tipo:
            per_tipo[tipo] = {"count": 0, "totale": 0.0, "tributi": []}
        per_tipo[tipo]["count"] += 1
        per_tipo[tipo]["totale"] += tributo.get("importo_debito", 0) - tributo.get("importo_credito", 0)
        per_tipo[tipo]["tributi"].append(tributo)
    
    # Calcola totali
    totale_pagato = sum(t["totale"] for t in per_tipo.values())
    
    # F24 del mese
    f24_mese_pagati = [
        f for f in f24_pagati
        if f.get("data_pagamento", "").startswith(f"{anno}-{mese:02d}")
    ]
    
    return {
        "periodo": f"{mese:02d}/{anno}",
        "anno": anno,
        "mese": mese,
        "riepilogo_per_tipo": per_tipo,
        "totale_pagato": round(totale_pagato, 2),
        "f24_pagati_nel_mese": len(f24_mese_pagati),
        "f24_da_pagare": len(f24_da_pagare),
        "dettaglio_f24_pagati": [{
            "file_name": f.get("file_name"),
            "importo": f.get("totali", {}).get("saldo_netto"),
            "data_pagamento": f.get("data_pagamento")
        } for f in f24_mese_pagati],
        "generato_il": datetime.now(timezone.utc).isoformat()
    }
