"""
Mappatura centralizzata delle collection MongoDB.
USARE SEMPRE QUESTE COSTANTI, MAI STRINGHE HARDCODED.
"""


class Collections:
    """Nomi collection standardizzati."""
    
    # === FATTURE ===
    FATTURE_RICEVUTE = "invoices"  # Collection UNICA per fatture ricevute
    FATTURE_EMESSE = "invoices_emesse"  # Fatture emesse (vendite)
    DETTAGLIO_RIGHE = "dettaglio_righe_fatture"  # Righe fattura
    # DEPRECATE: fatture_ricevute, fatture_contabili
    
    # === FORNITORI ===
    FORNITORI = "suppliers"  # Collection UNICA per fornitori
    FORNITORI_LEARNING = "fornitori_learning"  # Keywords per classificazione
    # DEPRECATE: fornitori, fornitori_dizionario
    
    # === F24 ===
    F24 = "f24_unificato"  # Collection UNICA per F24
    F24_QUIETANZE = "quietanze_f24"  # Ricevute pagamento
    # DEPRECATE: f24_models, f24_commercialista, f24_documents
    
    # === DIPENDENTI ===
    DIPENDENTI = "employees"  # Collection UNICA
    CEDOLINI = "cedolini"
    PRESENZE = "presenze"  # Presenze giornaliere
    PRESENZE_TIMBRATURE = "attendance_timbrature"
    ASSENZE = "attendance_assenze"
    CONTRATTI = "contratti_dipendenti"
    TFR = "tfr_dipendenti"
    GIUSTIFICATIVI = "giustificativi"
    # DEPRECATE: dipendenti, anagrafica_dipendenti, employee_contracts
    
    # === PRIMA NOTA ===
    PRIMA_NOTA_CASSA = "prima_nota_cassa"
    PRIMA_NOTA_BANCA = "prima_nota_banca"
    PRIMA_NOTA_SALARI = "prima_nota_salari"
    # DEPRECATE: prima_nota (generica)
    
    # === BANCA ===
    MOVIMENTI_BANCA = "estratto_conto_movimenti"
    ASSEGNI = "assegni"
    BONIFICI = "bonifici_generati"
    BONIFICI_STIPENDI = "bonifici_stipendi"
    
    # === SCADENZARIO ===
    SCADENZARIO = "scadenzario"
    SCADENZARIO_FORNITORI = "scadenzario_fornitori"
    
    # === MAGAZZINO ===
    MAGAZZINO = "warehouse_inventory"
    RICETTE = "ricette"
    LOTTI = "registro_lotti"
    ORDINI_FORNITORI = "ordini_fornitori"
    MOVIMENTI_MAGAZZINO = "movimenti_magazzino"
    
    # === DOCUMENTI ===
    DOCUMENTI_INBOX = "documents_inbox"
    DOCUMENTI_CLASSIFICATI = "documents_classified"
    
    # === CONTABILITÀ ===
    CORRISPETTIVI = "corrispettivi"
    PIANO_CONTI = "piano_conti"
    CENTRI_COSTO = "centri_costo"
    CESPITI = "cespiti"
    
    # === SISTEMA ===
    AUDIT_LOG = "audit_log"
    SETTINGS = "settings"
    UTENTI = "users"
    CONFIGURAZIONI = "configurazioni"
    EMAIL_ACCOUNTS = "email_accounts"
    NOTIFICHE_SCADENZE = "notifiche_scadenze"
    
    # === VERBALI / NOLEGGIO ===
    VERBALI_NOLEGGIO = "verbali_noleggio"
    VEICOLI_NOLEGGIO = "veicoli_noleggio"
    CONTRATTI_NOLEGGIO = "contratti_noleggio"
    STORICO_ASSEGNAZIONI = "storico_assegnazioni_veicoli"
    
    # === PAGAMENTI SALARI ===
    PAGAMENTI_SALARI = "pagamenti_salari"
    RIEPILOGO_CEDOLINI = "riepilogo_cedolini"
    ANAGRAFICA_DIPENDENTI = "anagrafica_dipendenti"
    
    # === ALERT ===
    ALERT_F24 = "alert_f24"
    ALERT_SCADENZE_F24 = "alert_scadenze_f24"


# Alias per retrocompatibilità (da rimuovere gradualmente)
COLLECTION_ALIASES = {
    # Fatture
    "fatture_ricevute": Collections.FATTURE_RICEVUTE,
    "fatture_contabili": Collections.FATTURE_RICEVUTE,
    "fatture": Collections.FATTURE_RICEVUTE,
    
    # Fornitori
    "fornitori": Collections.FORNITORI,
    "fornitori_dizionario": Collections.FORNITORI,
    "supplier": Collections.FORNITORI,
    
    # F24
    "f24_models": Collections.F24,
    "f24_commercialista": Collections.F24,
    "f24_documents": Collections.F24,
    
    # Dipendenti
    "dipendenti": Collections.DIPENDENTI,
    "anagrafica_dipendenti": Collections.DIPENDENTI,
    "employee": Collections.DIPENDENTI,
    
    # Prima Nota
    "prima_nota": Collections.PRIMA_NOTA_CASSA,
    
    # Banca
    "movimenti_banca": Collections.MOVIMENTI_BANCA,
    "bank_movements": Collections.MOVIMENTI_BANCA,
}


def get_collection_name(alias: str) -> str:
    """
    Risolve alias deprecati alla collection corretta.
    
    Args:
        alias: Nome collection (può essere deprecato)
        
    Returns:
        Nome collection corretto
    """
    return COLLECTION_ALIASES.get(alias, alias)


def get_collection(db, name: str):
    """
    Ottiene la collection risolvendo eventuali alias.
    
    Args:
        db: Database MongoDB
        name: Nome collection (può essere deprecato)
        
    Returns:
        Collection MongoDB
    """
    resolved_name = get_collection_name(name)
    return db[resolved_name]
