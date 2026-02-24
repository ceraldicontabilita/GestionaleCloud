"""
Sistema Contabile Avanzato Completo - Basato su Ricerche Approfondite 2025
Include: Patrimonio Netto, TFR, Ratei/Risconti, Rimanenze, Ammortamenti, Chiusura
"""

from typing import Dict, List
from datetime import date
from enum import Enum

# ============================================================================
# PATRIMONIO NETTO - STRUTTURA COMPLETA SRL
# ============================================================================

class TipoRiserva(str, Enum):
    """Tipologie di riserve secondo normativa italiana"""
    LEGALE = "legale"  # Riserva obbligatoria 5% utili fino a 20% capitale
    STRAORDINARIA = "straordinaria"  # Riserva volontaria da utili
    CAPITALE = "capitale"  # Riserve di capitale (es. sovrapprezzo azioni)
    SOSPENSIONE_IMPOSTA = "sospensione_imposta"  # Riserve con benefici fiscali
    UTILI_PORTATI_NUOVO = "utili_portati_nuovo"  # Utili non distribuiti anni precedenti
    RIVALUTAZIONE = "rivalutazione"  # Da rivalutazione monetaria

PATRIMONIO_NETTO_STRUCTURE = {
    "2.2.01": {
        "nome": "Capitale sociale",
        "descrizione": "Capitale versato dai soci (prima voce PN)",
        "tipo": "capitale",
        "ordine": 1
    },
    "2.2.02": {
        "nome": "Riserva legale",
        "descrizione": "Riserva obbligatoria (5% utili fino a 20% capitale sociale)",
        "tipo": "riserva",
        "sottotipo": TipoRiserva.LEGALE,
        "ordine": 2
    },
    "2.2.03": {
        "nome": "Riserva straordinaria",
        "descrizione": "Riserva volontaria da utili non distribuiti",
        "tipo": "riserva",
        "sottotipo": TipoRiserva.STRAORDINARIA,
        "ordine": 3
    },
    "2.2.04": {
        "nome": "Riserve di capitale",
        "descrizione": "Es. sovrapprezzo azioni, conferimenti",
        "tipo": "riserva",
        "sottotipo": TipoRiserva.CAPITALE,
        "ordine": 4
    },
    "2.2.05": {
        "nome": "Riserve in sospensione d'imposta",
        "descrizione": "Riserve con benefici fiscali",
        "tipo": "riserva",
        "sottotipo": TipoRiserva.SOSPENSIONE_IMPOSTA,
        "ordine": 5
    },
    "2.2.06": {
        "nome": "Utili (perdite) portati a nuovo",
        "descrizione": "Utili non distribuiti esercizi precedenti",
        "tipo": "utili_precedenti",
        "sottotipo": TipoRiserva.UTILI_PORTATI_NUOVO,
        "ordine": 6
    },
    "2.2.07": {
        "nome": "Utile (perdita) dell'esercizio",
        "descrizione": "Risultato economico anno corrente",
        "tipo": "utile_esercizio",
        "ordine": 7
    }
}

# ============================================================================
# TFR - TRATTAMENTO FINE RAPPORTO
# ============================================================================

TFR_CONFIG = {
    "coefficiente_rivalutazione_2025": 1.998752,  # INPS 2025
    "conto_costo": "4.2.01",  # Costo del personale
    "conto_fondo": "2.1.05",  # Fondo TFR (passività)
    "conto_fondo_inps": "2.1.06",  # Fondo TFR c/o INPS
}

TFR_TEMPLATES = {
    "accantonamento_annuale": {
        "descrizione": "Accantonamento TFR annuale",
        "righe": [
            {"conto": "4.2.01", "dare": "importo_tfr", "avere": 0, "descrizione": "Accantonamento TFR dipendenti"},
            {"conto": "2.1.05", "dare": 0, "avere": "importo_tfr", "descrizione": "Fondo TFR"},
        ]
    },
    "rivalutazione_tfr": {
        "descrizione": "Rivalutazione annuale fondo TFR",
        "righe": [
            {"conto": "4.2.01", "dare": "importo_rivalutazione", "avere": 0, "descrizione": "Rivalutazione TFR"},
            {"conto": "2.1.05", "dare": 0, "avere": "importo_rivalutazione", "descrizione": "Fondo TFR"},
        ]
    },
    "versamento_tfr_inps": {
        "descrizione": "Versamento TFR al Fondo Tesoreria INPS",
        "righe": [
            {"conto": "4.2.01", "dare": "importo_tfr", "avere": 0, "descrizione": "TFR dipendenti"},
            {"conto": "1.2.02", "dare": 0, "avere": "importo_tfr", "descrizione": "Banca c/c (versamento INPS)"},
        ]
    },
    "pagamento_tfr_dipendente": {
        "descrizione": "Liquidazione TFR alla cessazione rapporto",
        "righe": [
            {"conto": "2.1.05", "dare": "importo_tfr", "avere": 0, "descrizione": "Fondo TFR"},
            {"conto": "1.2.02", "dare": 0, "avere": "importo_tfr", "descrizione": "Banca c/c (pagamento TFR)"},
        ]
    }
}

def calcola_tfr_annuale(retribuzione_lorda_annua: float) -> float:
    """Calcola quota TFR annuale: circa 7.41% della retribuzione lorda"""
    return retribuzione_lorda_annua / 13.5

def calcola_rivalutazione_tfr(fondo_tfr: float, coefficiente: float = TFR_CONFIG["coefficiente_rivalutazione_2025"]) -> float:
    """Calcola rivalutazione annuale TFR"""
    return fondo_tfr * (coefficiente / 100)

# ============================================================================
# RATEI E RISCONTI
# ============================================================================

class TipoRateoRisconto(str, Enum):
    RATEO_ATTIVO = "rateo_attivo"  # Ricavi maturati ma non incassati
    RATEO_PASSIVO = "rateo_passivo"  # Costi maturati ma non pagati
    RISCONTO_ATTIVO = "risconto_attivo"  # Costi pagati ma competenza futura
    RISCONTO_PASSIVO = "risconto_passivo"  # Ricavi incassati ma competenza futura

RATEI_RISCONTI_CONFIG = {
    "rateo_attivo": {
        "conto_patrimoniale": "1.2.05",  # Attivo circolante
        "natura": "attivo",
        "descrizione": "Quote di ricavi maturati ma non ancora incassati"
    },
    "rateo_passivo": {
        "conto_patrimoniale": "2.1.07",  # Passività
        "natura": "passivo",
        "descrizione": "Quote di costi maturati ma non ancora pagati"
    },
    "risconto_attivo": {
        "conto_patrimoniale": "1.2.06",  # Attivo circolante
        "natura": "attivo",
        "descrizione": "Quote di costi già pagati ma di competenza futura"
    },
    "risconto_passivo": {
        "conto_patrimoniale": "2.1.08",  # Passività
        "natura": "passivo",
        "descrizione": "Quote di ricavi già incassati ma di competenza futura"
    }
}

RATEI_RISCONTI_TEMPLATES = {
    "rateo_attivo": {
        "descrizione": "Rilevazione rateo attivo (ricavo maturato)",
        "righe": [
            {"conto": "1.2.05", "dare": "importo", "avere": 0, "descrizione": "Ratei attivi"},
            {"conto": "conto_ricavo", "dare": 0, "avere": "importo", "descrizione": "Ricavi di competenza"},
        ]
    },
    "rateo_passivo": {
        "descrizione": "Rilevazione rateo passivo (costo maturato)",
        "righe": [
            {"conto": "conto_costo", "dare": "importo", "avere": 0, "descrizione": "Costi di competenza"},
            {"conto": "2.1.07", "dare": 0, "avere": "importo", "descrizione": "Ratei passivi"},
        ]
    },
    "risconto_attivo": {
        "descrizione": "Rilevazione risconto attivo (costo anticipato)",
        "righe": [
            {"conto": "1.2.06", "dare": "importo", "avere": 0, "descrizione": "Risconti attivi"},
            {"conto": "conto_costo", "dare": 0, "avere": "importo", "descrizione": "Storno costo futuro"},
        ]
    },
    "risconto_passivo": {
        "descrizione": "Rilevazione risconto passivo (ricavo anticipato)",
        "righe": [
            {"conto": "conto_ricavo", "dare": "importo", "avere": 0, "descrizione": "Storno ricavo futuro"},
            {"conto": "2.1.08", "dare": 0, "avere": "importo", "descrizione": "Risconti passivi"},
        ]
    }
}

def calcola_rateo_risconto(importo_totale: float, data_inizio: date, data_fine: date, data_chiusura: date) -> float:
    """
    Calcola l'importo del rateo o risconto
    
    Args:
        importo_totale: Importo totale del costo o ricavo
        data_inizio: Data inizio competenza
        data_fine: Data fine competenza
        data_chiusura: Data chiusura esercizio (es. 31/12)
    
    Returns:
        Importo da rilevare come rateo o risconto
    """
    giorni_totali = (data_fine - data_inizio).days
    
    if data_chiusura < data_fine:
        # Risconto: giorni futuri rispetto alla chiusura
        giorni_futuri = (data_fine - data_chiusura).days
        return (importo_totale / giorni_totali) * giorni_futuri
    else:
        # Rateo: giorni maturati fino alla chiusura
        giorni_maturati = (data_chiusura - data_inizio).days
        return (importo_totale / giorni_totali) * giorni_maturati

# ============================================================================
# RIMANENZE DI MAGAZZINO
# ============================================================================

class MetodoValutazioneRimanenze(str, Enum):
    FIFO = "fifo"  # First In First Out (più usato in ristorazione)
    LIFO = "lifo"  # Last In First Out
    COSTO_MEDIO = "costo_medio"  # Costo medio ponderato

RIMANENZE_CONFIG = {
    "conto_rimanenze_iniziali": "1.2.04",  # Attivo circolante
    "conto_rimanenze_finali": "1.2.04",
    "conto_variazione_rimanenze": "4.1.04",  # Costi / Variazione rimanenze
    "metodo_valutazione_consigliato": MetodoValutazioneRimanenze.FIFO  # Per bar/ristorante
}

RIMANENZE_TEMPLATES = {
    "chiusura_rimanenze_iniziali": {
        "descrizione": "Chiusura rimanenze iniziali a inizio esercizio",
        "righe": [
            {"conto": "4.1.04", "dare": "importo", "avere": 0, "descrizione": "Variazione rimanenze (storno iniziali)"},
            {"conto": "1.2.04", "dare": 0, "avere": "importo", "descrizione": "Rimanenze di magazzino"},
        ]
    },
    "apertura_rimanenze_finali": {
        "descrizione": "Rilevazione rimanenze finali a fine esercizio",
        "righe": [
            {"conto": "1.2.04", "dare": "importo", "avere": 0, "descrizione": "Rimanenze di magazzino"},
            {"conto": "4.1.04", "dare": 0, "avere": "importo", "descrizione": "Variazione rimanenze (carico finali)"},
        ]
    },
    "svalutazione_rimanenze": {
        "descrizione": "Svalutazione rimanenze per obsolescenza o scadenza",
        "righe": [
            {"conto": "4.1.05", "dare": "importo", "avere": 0, "descrizione": "Svalutazione rimanenze"},
            {"conto": "1.2.04", "dare": 0, "avere": "importo", "descrizione": "Rimanenze di magazzino"},
        ]
    }
}

# ============================================================================
# AMMORTAMENTI IMMOBILIZZAZIONI
# ============================================================================

ALIQUOTE_AMMORTAMENTO = {
    "macchinari_generici": {
        "aliquota": 12.5,
        "descrizione": "Macchinari generici per preparazione alimenti",
        "conto_immobilizzazione": "1.1.01",
        "conto_fondo": "1.1.01.F",  # Fondo ammortamento (rettifica)
        "conto_costo": "4.2.07"  # Ammortamenti
    },
    "attrezzature_bar": {
        "aliquota": 20.0,
        "descrizione": "Macchine caffè, frigoriferi, attrezzature specifiche",
        "conto_immobilizzazione": "1.1.01",
        "conto_fondo": "1.1.01.F",
        "conto_costo": "4.2.07"
    },
    "arredamento": {
        "aliquota": 12.0,
        "descrizione": "Mobili, tavoli, sedie, bancone",
        "conto_immobilizzazione": "1.1.02",
        "conto_fondo": "1.1.02.F",
        "conto_costo": "4.2.07"
    },
    "attrezzature_varie": {
        "aliquota": 25.0,
        "descrizione": "Attrezzatura minuta, stampi, utensili",
        "conto_immobilizzazione": "1.1.03",
        "conto_fondo": "1.1.03.F",
        "conto_costo": "4.2.07"
    },
    "impianti": {
        "aliquota": 15.0,
        "descrizione": "Impianti elettrici, idraulici, climatizzazione",
        "conto_immobilizzazione": "1.1.04",
        "conto_fondo": "1.1.04.F",
        "conto_costo": "4.2.07"
    }
}

AMMORTAMENTO_TEMPLATE = {
    "descrizione": "Rilevazione quota ammortamento annuale",
    "righe": [
        {"conto": "4.2.07", "dare": "importo_quota", "avere": 0, "descrizione": "Ammortamento immobilizzazioni"},
        {"conto": "conto_fondo", "dare": 0, "avere": "importo_quota", "descrizione": "Fondo ammortamento"},
    ]
}

def calcola_ammortamento(valore_cespite: float, aliquota: float, mesi_utilizzo: int = 12) -> float:
    """
    Calcola quota di ammortamento
    
    Args:
        valore_cespite: Valore storico del bene
        aliquota: Aliquota percentuale annua
        mesi_utilizzo: Mesi di utilizzo nell'esercizio (per primo anno)
    
    Returns:
        Quota ammortamento
    """
    quota_annua = valore_cespite * (aliquota / 100)
    
    # Proporzionale ai mesi di utilizzo
    if mesi_utilizzo < 12:
        return quota_annua * (mesi_utilizzo / 12)
    
    return quota_annua

# ============================================================================
# CHIUSURA E RIAPERTURA CONTI
# ============================================================================

CHIUSURA_TEMPLATES = {
    "chiusura_costi": {
        "descrizione": "Chiusura conti di costo a Conto Economico",
        "righe": [
            {"conto": "conto_economico", "dare": "totale_costi", "avere": 0, "descrizione": "Chiusura costi"},
            {"conto": "conti_costi", "dare": 0, "avere": "importi_costi", "descrizione": "Storno costi"},
        ]
    },
    "chiusura_ricavi": {
        "descrizione": "Chiusura conti di ricavo a Conto Economico",
        "righe": [
            {"conto": "conti_ricavi", "dare": "importi_ricavi", "avere": 0, "descrizione": "Storno ricavi"},
            {"conto": "conto_economico", "dare": 0, "avere": "totale_ricavi", "descrizione": "Chiusura ricavi"},
        ]
    },
    "rilevazione_utile": {
        "descrizione": "Rilevazione utile di esercizio (Ricavi > Costi)",
        "righe": [
            {"conto": "conto_economico", "dare": "utile", "avere": 0, "descrizione": "Chiusura Conto Economico"},
            {"conto": "2.2.07", "dare": 0, "avere": "utile", "descrizione": "Utile dell'esercizio"},
        ]
    },
    "rilevazione_perdita": {
        "descrizione": "Rilevazione perdita di esercizio (Costi > Ricavi)",
        "righe": [
            {"conto": "2.2.07", "dare": "perdita", "avere": 0, "descrizione": "Perdita dell'esercizio"},
            {"conto": "conto_economico", "dare": 0, "avere": "perdita", "descrizione": "Chiusura Conto Economico"},
        ]
    },
    "destinazione_utile_riserva_legale": {
        "descrizione": "Destinazione 5% utile a riserva legale",
        "righe": [
            {"conto": "2.2.07", "dare": "quota_riserva", "avere": 0, "descrizione": "Utile dell'esercizio"},
            {"conto": "2.2.02", "dare": 0, "avere": "quota_riserva", "descrizione": "Riserva legale"},
        ]
    },
    "distribuzione_dividendi": {
        "descrizione": "Distribuzione dividendi ai soci",
        "righe": [
            {"conto": "2.2.07", "dare": "importo_dividendi", "avere": 0, "descrizione": "Utile dell'esercizio"},
            {"conto": "2.1.09", "dare": 0, "avere": "importo_dividendi", "descrizione": "Debiti verso soci per dividendi"},
        ]
    },
    "utili_portati_nuovo": {
        "descrizione": "Utili non distribuiti portati a nuovo",
        "righe": [
            {"conto": "2.2.07", "dare": "importo_utili", "avere": 0, "descrizione": "Utile dell'esercizio"},
            {"conto": "2.2.06", "dare": 0, "avere": "importo_utili", "descrizione": "Utili portati a nuovo"},
        ]
    }
}

def calcola_riserva_legale(utile_esercizio: float, capitale_sociale: float, riserva_legale_attuale: float) -> float:
    """
    Calcola quota da destinare a riserva legale
    
    Regola: 5% dell'utile fino a raggiungere 20% del capitale sociale
    
    Returns:
        Importo da accantonare a riserva legale
    """
    limite_riserva = capitale_sociale * 0.20
    
    if riserva_legale_attuale >= limite_riserva:
        return 0  # Riserva già al limite
    
    quota_5_percento = utile_esercizio * 0.05
    spazio_disponibile = limite_riserva - riserva_legale_attuale
    
    return min(quota_5_percento, spazio_disponibile)

# ============================================================================
# FONDI RISCHI E ONERI
# ============================================================================

FONDI_RISCHI_CONFIG = {
    "fondo_manutenzioni": {
        "conto_fondo": "2.1.10",
        "conto_accantonamento": "4.2.09",
        "descrizione": "Fondo per manutenzioni cicliche"
    },
    "fondo_garanzie": {
        "conto_fondo": "2.1.11",
        "conto_accantonamento": "4.2.09",
        "descrizione": "Fondo garanzie prodotti"
    },
    "fondo_cause_legali": {
        "conto_fondo": "2.1.12",
        "conto_accantonamento": "4.2.09",
        "descrizione": "Fondo per contenziosi in corso"
    }
}

FONDI_TEMPLATE = {
    "accantonamento_fondo": {
        "descrizione": "Accantonamento a fondo rischi",
        "righe": [
            {"conto": "4.2.09", "dare": "importo", "avere": 0, "descrizione": "Accantonamento fondi rischi"},
            {"conto": "conto_fondo", "dare": 0, "avere": "importo", "descrizione": "Fondo rischi e oneri"},
        ]
    },
    "utilizzo_fondo": {
        "descrizione": "Utilizzo fondo rischi per costo effettivo",
        "righe": [
            {"conto": "conto_fondo", "dare": "importo", "avere": 0, "descrizione": "Fondo rischi e oneri"},
            {"conto": "conto_costo", "dare": 0, "avere": "importo", "descrizione": "Costo coperto da fondo"},
        ]
    }
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def genera_piano_ammortamento(valore_cespite: float, aliquota: float, anni: int = 5) -> List[Dict]:
    """
    Genera piano di ammortamento pluriennale
    
    Returns:
        Lista di dict con anno, quota, fondo cumulato, valore residuo
    """
    piano = []
    fondo_cumulato = 0
    
    for anno in range(1, anni + 1):
        quota = calcola_ammortamento(valore_cespite, aliquota)
        fondo_cumulato += quota
        valore_residuo = valore_cespite - fondo_cumulato
        
        piano.append({
            "anno": anno,
            "quota_ammortamento": round(quota, 2),
            "fondo_ammortamento_cumulato": round(fondo_cumulato, 2),
            "valore_residuo": round(max(valore_residuo, 0), 2)
        })
    
    return piano
