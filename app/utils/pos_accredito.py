"""
POS Accredito Date Calculator - Logica sfasamento accrediti POS

Regole di sfasamento:
- Pagamento Lunedì → Accredito Martedì (+1 giorno lavorativo)
- Pagamento Martedì → Accredito Mercoledì (+1 giorno lavorativo)
- Pagamento Mercoledì → Accredito Giovedì (+1 giorno lavorativo)
- Pagamento Giovedì → Accredito Venerdì (+1 giorno lavorativo)
- Pagamento Venerdì → Accredito Lunedì (+3 giorni, salta weekend)
- Pagamento Sabato → Accredito Martedì (+3 giorni)
- Pagamento Domenica → Accredito Martedì (+2 giorni)

Se il giorno di accredito cade in un festivo, slitta al primo giorno lavorativo successivo.
"""

from datetime import date, datetime, timedelta
from typing import Optional, List, Tuple
import logging

logger = logging.getLogger(__name__)

# Festivi fissi italiani (giorno, mese)
FESTIVI_FISSI = [
    (1, 1),   # Capodanno
    (6, 1),   # Epifania
    (25, 4),  # Festa della Liberazione
    (1, 5),   # Festa dei Lavoratori
    (2, 6),   # Festa della Repubblica
    (15, 8),  # Ferragosto (Assunzione)
    (1, 11),  # Ognissanti
    (8, 12),  # Immacolata Concezione
    (25, 12), # Natale
    (26, 12), # Santo Stefano
]

def _calcola_pasqua(anno: int) -> date:
    """
    Calcola la data di Pasqua usando l'algoritmo di Gauss/Meeus.
    """
    a = anno % 19
    b = anno // 100
    c = anno % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mese = (h + l - 7 * m + 114) // 31
    giorno = ((h + l - 7 * m + 114) % 31) + 1
    return date(anno, mese, giorno)


def get_festivi_anno(anno: int) -> List[date]:
    """
    Restituisce la lista di tutti i giorni festivi per un anno specifico.
    Include festivi fissi + Pasqua e Lunedì dell'Angelo (mobili).
    """
    festivi = []
    
    # Festivi fissi
    for giorno, mese in FESTIVI_FISSI:
        festivi.append(date(anno, mese, giorno))
    
    # Pasqua e Lunedì dell'Angelo (Pasquetta)
    pasqua = _calcola_pasqua(anno)
    festivi.append(pasqua)
    festivi.append(pasqua + timedelta(days=1))  # Pasquetta
    
    return sorted(festivi)


def is_giorno_lavorativo(data: date, festivi: Optional[List[date]] = None) -> bool:
    """
    Verifica se una data è un giorno lavorativo (non weekend, non festivo).
    """
    # Weekend (Sabato=5, Domenica=6)
    if data.weekday() >= 5:
        return False
    
    # Festivi
    if festivi is None:
        festivi = get_festivi_anno(data.year)
    
    if data in festivi:
        return False
    
    return True


def prossimo_giorno_lavorativo(data: date, festivi: Optional[List[date]] = None) -> date:
    """
    Trova il prossimo giorno lavorativo a partire dalla data indicata (inclusa).
    """
    if festivi is None:
        festivi = get_festivi_anno(data.year)
        # Aggiungi anche festivi anno successivo se siamo a fine anno
        if data.month == 12:
            festivi.extend(get_festivi_anno(data.year + 1))
    
    while not is_giorno_lavorativo(data, festivi):
        data = data + timedelta(days=1)
        # Se passiamo all'anno successivo, aggiorniamo i festivi
        if data.month == 1 and data.day == 1:
            festivi = get_festivi_anno(data.year)
    
    return data


def calcola_data_accredito_pos(data_pagamento: date) -> Tuple[date, int, str]:
    """
    Calcola la data di accredito POS basata sulla data di pagamento.
    
    Args:
        data_pagamento: Data del pagamento POS
        
    Returns:
        Tuple con:
        - data_accredito: Data prevista di accredito
        - giorni_sfasamento: Numero di giorni di sfasamento
        - note: Descrizione del calcolo
    """
    festivi = get_festivi_anno(data_pagamento.year)
    if data_pagamento.month == 12:
        festivi.extend(get_festivi_anno(data_pagamento.year + 1))
    
    giorno_settimana = data_pagamento.weekday()  # 0=Lunedì, 6=Domenica
    
    # Regole di sfasamento base
    if giorno_settimana <= 3:  # Lunedì-Giovedì
        # Accredito il giorno lavorativo successivo (+1)
        data_accredito_base = data_pagamento + timedelta(days=1)
        note_base = f"Pagamento {['Lunedì', 'Martedì', 'Mercoledì', 'Giovedì'][giorno_settimana]} → +1 giorno"
    elif giorno_settimana == 4:  # Venerdì
        # Accredito Lunedì (+3 giorni, salta weekend)
        data_accredito_base = data_pagamento + timedelta(days=3)
        note_base = "Pagamento Venerdì → Accredito Lunedì (+3 giorni)"
    elif giorno_settimana == 5:  # Sabato
        # Accredito Martedì (+3 giorni)
        data_accredito_base = data_pagamento + timedelta(days=3)
        note_base = "Pagamento Sabato → Accredito Martedì (+3 giorni)"
    else:  # Domenica
        # Accredito Martedì (+2 giorni)
        data_accredito_base = data_pagamento + timedelta(days=2)
        note_base = "Pagamento Domenica → Accredito Martedì (+2 giorni)"
    
    # Verifica se la data di accredito base cade in un festivo
    data_accredito_finale = prossimo_giorno_lavorativo(data_accredito_base, festivi)
    
    # Calcola sfasamento effettivo
    giorni_sfasamento = (data_accredito_finale - data_pagamento).days
    
    # Aggiungi note se c'è stato slittamento per festivi
    if data_accredito_finale != data_accredito_base:
        giorni_extra = (data_accredito_finale - data_accredito_base).days
        note = f"{note_base} + {giorni_extra} giorni (festivo)"
    else:
        note = note_base
    
    return data_accredito_finale, giorni_sfasamento, note


def calcola_sfasamento_periodo(data_inizio: date, data_fine: date) -> List[dict]:
    """
    Calcola lo sfasamento per un intero periodo.
    Utile per la riconciliazione mensile.
    
    Args:
        data_inizio: Data inizio periodo
        data_fine: Data fine periodo
        
    Returns:
        Lista di dizionari con data_pagamento, data_accredito, giorni_sfasamento, note
    """
    risultati = []
    data_corrente = data_inizio
    
    while data_corrente <= data_fine:
        data_accredito, giorni, note = calcola_data_accredito_pos(data_corrente)
        risultati.append({
            "data_pagamento": data_corrente.isoformat(),
            "data_accredito": data_accredito.isoformat(),
            "giorno_settimana_pagamento": ['Lunedì', 'Martedì', 'Mercoledì', 'Giovedì', 'Venerdì', 'Sabato', 'Domenica'][data_corrente.weekday()],
            "giorni_sfasamento": giorni,
            "note": note
        })
        data_corrente += timedelta(days=1)
    
    return risultati


def get_accrediti_attesi_per_data(data_accredito: date, movimenti_pos: List[dict]) -> List[dict]:
    """
    Dato una data di accredito, trova tutti i pagamenti POS che dovrebbero essere accreditati quel giorno.
    
    Args:
        data_accredito: Data di accredito da verificare
        movimenti_pos: Lista di movimenti POS con campo 'data' (data pagamento)
        
    Returns:
        Lista di movimenti che dovrebbero essere accreditati in quella data
    """
    accrediti_attesi = []
    
    for mov in movimenti_pos:
        data_pag_str = mov.get('data') or mov.get('date')
        if not data_pag_str:
            continue
            
        try:
            if isinstance(data_pag_str, str):
                data_pag = datetime.strptime(data_pag_str[:10], '%Y-%m-%d').date()
            else:
                data_pag = data_pag_str
                
            data_accr_calcolata, _, _ = calcola_data_accredito_pos(data_pag)
            
            if data_accr_calcolata == data_accredito:
                accrediti_attesi.append({
                    **mov,
                    "data_pagamento_originale": data_pag.isoformat(),
                    "data_accredito_calcolata": data_accr_calcolata.isoformat()
                })
        except Exception as e:
            logger.warning(f"Errore parsing data {data_pag_str}: {e}")
            continue
    
    return accrediti_attesi


# API Helper per frontend
def get_calendario_sfasamento_mese(anno: int, mese: int) -> dict:
    """
    Genera un calendario con lo sfasamento POS per ogni giorno del mese.
    """
    from calendar import monthrange
    
    _, ultimo_giorno = monthrange(anno, mese)
    data_inizio = date(anno, mese, 1)
    data_fine = date(anno, mese, ultimo_giorno)
    
    festivi = get_festivi_anno(anno)
    festivi_nel_mese = [f for f in festivi if f.month == mese]
    
    giorni = calcola_sfasamento_periodo(data_inizio, data_fine)
    
    return {
        "anno": anno,
        "mese": mese,
        "festivi": [f.isoformat() for f in festivi_nel_mese],
        "giorni": giorni,
        "legenda": {
            "lun_gio": "Accredito giorno lavorativo successivo (+1)",
            "venerdi": "Accredito Lunedì (+3 giorni)",
            "sabato": "Accredito Martedì (+3 giorni)",
            "domenica": "Accredito Martedì (+2 giorni)",
            "festivo": "Slitta al primo giorno lavorativo"
        }
    }
