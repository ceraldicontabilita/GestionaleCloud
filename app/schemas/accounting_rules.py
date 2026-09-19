"""
Regole Avanzate di Contabilità - Sistema Intelligente
Basato su ricerche web approfondite 2025 per standard italiani
"""

from typing import Dict, List, Tuple

# ============================================================================
# CODICI TRIBUTO F24 - ERARIO
# ============================================================================

F24_ERARIO_CODES = {
    # IRES - Imposta sul Reddito delle Società
    "2001": {"descrizione": "IRES - Saldo", "conto": "4.3.02", "tipo": "imposte"},
    "2002": {"descrizione": "IRES - Acconto prima rata", "conto": "4.3.02", "tipo": "imposte"},
    "2003": {"descrizione": "IRES - Acconto seconda rata", "conto": "4.3.02", "tipo": "imposte"},
    "2007": {"descrizione": "IRES - Maggior acconto prima rata", "conto": "4.3.02", "tipo": "imposte"},
    "2008": {"descrizione": "IRES - Maggior acconto seconda rata", "conto": "4.3.02", "tipo": "imposte"},
    
    # IRAP - Imposta Regionale Attività Produttive
    "3800": {"descrizione": "IRAP - Saldo", "conto": "4.3.02", "tipo": "imposte"},
    "3812": {"descrizione": "IRAP - Acconto prima rata", "conto": "4.3.02", "tipo": "imposte"},
    "3813": {"descrizione": "IRAP - Acconto seconda rata", "conto": "4.3.02", "tipo": "imposte"},
    "3881": {"descrizione": "IRAP - Maggior acconto prima rata", "conto": "4.3.02", "tipo": "imposte"},
    "3882": {"descrizione": "IRAP - Maggior acconto seconda rata", "conto": "4.3.02", "tipo": "imposte"},
    
    # IVA
    "6001": {"descrizione": "IVA - Versamento saldo", "conto": "2.1.02", "tipo": "debiti_tributari"},
    "6002": {"descrizione": "IVA - Versamento acconto", "conto": "2.1.02", "tipo": "debiti_tributari"},
    
    # IRPEF (per imprenditori individuali o soci)
    "4001": {"descrizione": "IRPEF - Saldo", "conto": "4.3.02", "tipo": "imposte"},
    "4033": {"descrizione": "IRPEF - Acconto prima rata", "conto": "4.3.02", "tipo": "imposte"},
    "4034": {"descrizione": "IRPEF - Acconto seconda rata", "conto": "4.3.02", "tipo": "imposte"},
    
    # Ritenute d'acconto
    "1001": {"descrizione": "Ritenute IRPEF dipendenti", "conto": "2.1.02", "tipo": "debiti_tributari"},
    "1035": {"descrizione": "Ritenute lavoro autonomo", "conto": "2.1.02", "tipo": "debiti_tributari"},
    "1040": {"descrizione": "Ritenute redditi capitali", "conto": "2.1.02", "tipo": "debiti_tributari"},
    
    # Addizionali Regionali IRPEF
    "3801": {"descrizione": "Addizionale Regionale IRPEF - Saldo (contribuente)", "conto": "4.3.02", "tipo": "imposte"},
    "3802": {"descrizione": "Addizionale Regionale IRPEF - Ritenuta sostituto d'imposta", "conto": "2.1.02", "tipo": "debiti_tributari"},
    
    # Addizionali Comunali IRPEF
    "3843": {"descrizione": "Addizionale Comunale IRPEF - Acconto", "conto": "2.1.02", "tipo": "debiti_tributari"},
    "3848": {"descrizione": "Addizionale Comunale IRPEF - Saldo ritenuta sostituto", "conto": "2.1.02", "tipo": "debiti_tributari"},
}

# ============================================================================
# CODICI TRIBUTO F24 - INPS (CONTRIBUTI)
# ============================================================================

F24_INPS_CODES = {
    # Contributi dipendenti - più comuni per bar/ristorante
    "DM10": {"descrizione": "Contributo previdenziale dipendenti - quota datore", "conto": "4.2.01", "tipo": "costo_personale"},
    "DM11": {"descrizione": "Contributo previdenziale dipendenti - quota lavoratore", "conto": "2.1.03", "tipo": "debiti_previdenziali"},
    "DM12": {"descrizione": "Contributo assistenziale dipendenti - quota datore", "conto": "4.2.01", "tipo": "costo_personale"},
    "DM13": {"descrizione": "Contributo assistenziale dipendenti - quota lavoratore", "conto": "2.1.03", "tipo": "debiti_previdenziali"},
    
    # Gestione separata (collaboratori)
    "DM14": {"descrizione": "Gestione separata - committente", "conto": "4.2.01", "tipo": "costo_personale"},
    "DM15": {"descrizione": "Gestione separata - collaboratore", "conto": "2.1.03", "tipo": "debiti_previdenziali"},
    
    # Ticket licenziamento (contributo NASpI)
    "DLST": {"descrizione": "Ticket licenziamento - contributo NASpI", "conto": "4.2.01", "tipo": "costo_personale"},
    
    # TFR (per aziende +50 dipendenti)
    "TFR0": {"descrizione": "TFR versato al Fondo Tesoreria INPS", "conto": "2.1.06", "tipo": "debiti_previdenziali"},
}

# ============================================================================
# CODICI TRIBUTO INAIL
# ============================================================================

F24_INAIL_CODES = {
    "902025": {
        "descrizione": "Premi INAIL autoliquidazione 2025",
        "conto": "4.2.01",
        "tipo": "costo_personale",
        "centro_costo": "Personale - Assicurazioni",
        "sezione_f24": "INAIL"
    }
}

# ============================================================================
# FUNZIONI HELPER PER RICONOSCIMENTO E CATEGORIZZAZIONE
# ============================================================================
#
# Il riconoscimento F24 e la categorizzazione dei movimenti bancari da
# descrizione vivono in `app/services/categorizzazione_movimenti.py` (unico
# motore, usato dall'import reale in `app/routers/bank/estratto_conto.py`).
# Questo modulo restava con una seconda implementazione parallela — stesso
# nome, mai collegata a nessun percorso di import — eliminata il 19/09/2026
# per la regola "un solo sistema per funzione". I cataloghi codici tributo
# sopra (F24_ERARIO_CODES, F24_INPS_CODES, F24_INAIL_CODES) restano qui: li
# usa `app/schemas/f24_parser.py` per il parsing del modello F24, dominio
# diverso dalla categorizzazione del movimento bancario.
#
# Rimossi il 19/09/2026 (consolidamento motore conti, stessa regola "un solo
# sistema per funzione"): CODICI_LICENZIAMENTO, VOCI_BUSTA_PAGA_F24,
# determina_centro_costo_da_f24, OMAGGI_RULES, determina_conto_omaggio,
# DOUBLE_ENTRY_TEMPLATES, genera_scrittura_partita_doppia. Usavano un piano
# dei conti a 3 cifre (es. "4.1.01", "2.1.01") diverso sia da quello operativo
# (es. "05.01.01") sia dal CEE ufficiale (`app/services/piano_conti_ufficiale.py`),
# e un grep sui nomi esatti confermava zero importatori reali: erano dati
# potenzialmente fuorvianti se mai richiamati per errore, non un motore in uso.


def verifica_quadratura(righe: List[Dict]) -> Tuple[bool, float, float]:
    """
    Verifica che una scrittura contabile sia in quadratura (Dare = Avere)
    
    Returns:
        tuple (quadra: bool, totale_dare: float, totale_avere: float)
    """
    totale_dare = sum(r["dare"] for r in righe)
    totale_avere = sum(r["avere"] for r in righe)
    
    # Tolleranza per errori di arrotondamento
    quadra = abs(totale_dare - totale_avere) < 0.01
    
    return quadra, totale_dare, totale_avere
