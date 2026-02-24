"""
Mappatura centralizzata delle collection MongoDB.
USARE SEMPRE QUESTE COSTANTI, MAI STRINGHE HARDCODED.

IMPORTANTE: Questo file è la SINGLE SOURCE OF TRUTH per i nomi delle collezioni.
"""


class Collections:
    """Nomi collection standardizzati."""
    
    # === FATTURE ===
    FATTURE_RICEVUTE = "invoices"  # Collection UNICA per fatture ricevute
    FATTURE_EMESSE = "invoices_emesse"  # Fatture emesse (vendite)
    DETTAGLIO_RIGHE = "dettaglio_righe_fatture"  # Righe fattura
    FATTURE_EMAIL_ATTACHMENTS = "fatture_email_attachments"
    NOTE_CREDITO = "note_credito"
    
    # === FORNITORI ===
    FORNITORI = "suppliers"  # Collection UNICA per fornitori
    FORNITORI_LEARNING = "fornitori_learning"  # Keywords per classificazione
    SUPPLIER_PAYMENT_HISTORY = "supplier_payment_history"
    SUPPLIER_PAYMENT_METHODS = "supplier_payment_methods"
    
    # === F24 ===
    F24 = "f24_unificato"  # Collection UNICA per F24
    F24_QUIETANZE = "quietanze_f24"  # Ricevute pagamento
    MOVIMENTI_F24_BANCA = "movimenti_f24_banca"
    TRIBUTI_PAGATI = "tributi_pagati"
    CALENDARIO_FISCALE = "calendario_fiscale"
    
    # === DIPENDENTI ===
    DIPENDENTI = "employees"  # Collection UNICA
    CEDOLINI = "cedolini"
    CEDOLINI_PARSED = "cedolini_parsed"
    CEDOLINI_EMAIL_ATTACHMENTS = "cedolini_email_attachments"
    PRESENZE = "presenze"  # Presenze giornaliere
    PRESENZE_MENSILI = "presenze_mensili"
    PRESENZE_TIMBRATURE = "attendance_timbrature"
    ASSENZE = "attendance_assenze"
    TURNI = "turni"
    TURNI_DIPENDENTI = "turni_dipendenti"
    CONTRATTI = "contratti_dipendenti"
    TFR = "tfr_accantonamenti"
    TFR_LIQUIDAZIONI = "tfr_liquidazioni"
    GIUSTIFICATIVI = "giustificativi"
    ACCONTI_DIPENDENTI = "acconti_dipendenti"
    RICHIESTE_ASSENZA = "richieste_assenza"
    RIPORTI_FERIE = "riporti_ferie"
    LIBRETTI_SANITARI = "libretti_sanitari"
    
    # === PRIMA NOTA ===
    PRIMA_NOTA_CASSA = "prima_nota_cassa"
    PRIMA_NOTA_BANCA = "prima_nota_banca"
    PRIMA_NOTA_SALARI = "prima_nota_salari"
    PRIMA_NOTA_RIGHE = "prima_nota_righe"
    
    # === BANCA ===
    MOVIMENTI_BANCA = "estratto_conto_movimenti"
    ESTRATTO_CONTO = "estratto_conto"
    ASSEGNI = "assegni"
    OCR_ASSEGNI = "ocr_assegni"
    BONIFICI = "bonifici_generati"
    BONIFICI_STIPENDI = "bonifici_stipendi"
    BONIFICI_EMAIL_ATTACHMENTS = "bonifici_email_attachments"
    ARCHIVIO_BONIFICI = "archivio_bonifici"
    RICONCILIAZIONI = "riconciliazioni"
    OPERAZIONI_DA_CONFERMARE = "operazioni_da_confermare"
    
    # === SCADENZARIO ===
    SCADENZARIO = "scadenzario"
    SCADENZARIO_FORNITORI = "scadenzario_fornitori"
    SCADENZE = "scadenze"
    
    # === MAGAZZINO ===
    MAGAZZINO = "warehouse_inventory"
    MAGAZZINO_ARTICOLI = "magazzino_articoli"
    MAGAZZINO_MOVIMENTI = "movimenti_magazzino"
    MAGAZZINO_DOPPIA_VERITA = "magazzino_doppia_verita"
    MAGAZZINO_DIFFERENZE = "magazzino_differenze"
    RICETTE = "ricette"
    LOTTI = "lotti"
    ORDINI_FORNITORI = "supplier_orders"
    WAREHOUSE_CONFIG = "warehouse_config"
    WAREHOUSE_PRODUCTS = "warehouse_products"
    WAREHOUSE_STOCKS = "warehouse_stocks"
    SCHEDE_TECNICHE = "schede_tecniche_prodotti"
    ACQUISTI_PRODOTTI = "acquisti_prodotti"
    PRODUCT_CATALOG = "product_catalog"
    PRODUCT_MAPPINGS = "product_mappings"
    PRICE_HISTORY = "price_history"
    
    # === DOCUMENTI ===
    DOCUMENTI_INBOX = "documents_inbox"
    DOCUMENTI_CLASSIFICATI = "documents_classified"
    DOCUMENTI = "documents"
    DOCUMENTI_EMAIL = "documenti_email"
    DOCUMENTI_DA_RIVEDERE = "documenti_da_rivedere"
    DOCUMENTI_NON_ASSOCIATI = "documenti_non_associati"
    EMAIL_ALLEGATI = "email_allegati"
    
    # === CONTABILITÀ ===
    CORRISPETTIVI = "corrispettivi"
    CORRISPETTIVI_MANUALI = "corrispettivi_manuali"
    PIANO_CONTI = "piano_conti"
    CENTRI_COSTO = "centri_costo"
    CESPITI = "cespiti"
    MOVIMENTI_CONTABILI = "movimenti_contabili"
    ACCOUNTING_ENTRIES = "accounting_entries"
    APERTURE_ESERCIZIO = "aperture_esercizio"
    CHIUSURE_ESERCIZIO = "chiusure_esercizio"
    OPENING_BALANCES = "opening_balances"
    ALIQUOTE_IVA = "aliquote_iva"
    RITENUTE_ACCONTO = "ritenute_acconto"
    ABBUONI_ARROTONDAMENTI = "abbuoni_arrotondamenti"
    
    # === PAGAMENTI SALARI ===
    PAGAMENTI_SALARI = "pagamenti_salari"
    RIEPILOGO_CEDOLINI = "riepilogo_cedolini"
    BUSTE_PAGA = "buste_paga"
    COSTI_DIPENDENTI = "costi_dipendenti"
    
    # === VERBALI / NOLEGGIO ===
    VERBALI_NOLEGGIO = "verbali_noleggio"
    VERBALI_NOLEGGIO_COMPLETI = "verbali_noleggio_completi"
    VEICOLI_NOLEGGIO = "veicoli_noleggio"
    VEICOLI = "veicoli"
    CONTRATTI_NOLEGGIO = "contratti_noleggio"
    STORICO_ASSEGNAZIONI = "storico_assegnazioni_veicoli"
    COSTI_NOLEGGIO = "costi_noleggio"
    
    # === SISTEMA ===
    AUDIT_LOG = "audit_log"
    SETTINGS = "settings"
    UTENTI = "users"
    CONFIGURAZIONI = "configurazioni"
    CONFIG = "config"
    EMAIL_ACCOUNTS = "email_accounts"
    NOTIFICHE_SCADENZE = "notifiche_scadenze"
    NOTIFICATIONS = "notifications"
    ALERTS = "alerts"
    USER_PREFERENCES = "user_preferences"
    API_CLIENTS = "api_clients"
    EXPORT_LOG = "export_log"
    SCHEDULED_EXPORTS = "scheduled_exports"
    MIGRATION_REPORTS = "_migration_reports"
    
    # === ALERT F24 ===
    ALERT_F24 = "alert_f24"
    ALERT_SCADENZE_F24 = "alert_scadenze_f24"
    
    # === BUDGET / PREVISIONI ===
    BUDGET = "budget"
    COSTI_PREVISIONALI = "costi_previsionali"
    UTILE_OBIETTIVO = "utile_obiettivo"
    
    # === COMMERCIALISTA ===
    COMMERCIALISTA_CONFIG = "commercialista_config"
    COMMERCIALISTA_LOG = "commercialista_log"
    DOCUMENTI_COMMERCIALISTA = "documenti_commercialista"
    
    # === AGEVOLAZIONI ===
    AGEVOLAZIONI_FISCALI = "agevolazioni_fiscali"
    ADR_DEFINIZIONE_AGEVOLATA = "adr_definizione_agevolata"


# Alias per retrocompatibilità (da rimuovere gradualmente)
COLLECTION_ALIASES = {
    # Fatture
    "fatture_ricevute": Collections.FATTURE_RICEVUTE,
    "fatture_contabili": Collections.FATTURE_RICEVUTE,
    "fatture": Collections.FATTURE_RICEVUTE,
    "invoices_v2": Collections.FATTURE_RICEVUTE,
    
    # Fornitori
    "fornitori": Collections.FORNITORI,
    "fornitori_dizionario": Collections.FORNITORI,
    "supplier": Collections.FORNITORI,
    
    # F24
    "f24_models": Collections.F24,
    "f24_commercialista": Collections.F24,
    "f24_documents": Collections.F24,
    "f24_payments": Collections.F24,
    
    # Dipendenti
    "dipendenti": Collections.DIPENDENTI,
    "anagrafica_dipendenti": Collections.DIPENDENTI,
    "employee": Collections.DIPENDENTI,
    "staff": Collections.DIPENDENTI,
    "payslips": Collections.CEDOLINI,
    
    # Prima Nota
    "prima_nota": Collections.PRIMA_NOTA_CASSA,
    
    # Banca
    "movimenti_banca": Collections.MOVIMENTI_BANCA,
    "bank_movements": Collections.MOVIMENTI_BANCA,
    "bank_statements": Collections.MOVIMENTI_BANCA,
    "estratti_conto": Collections.ESTRATTO_CONTO,
    
    # Magazzino
    "warehouse_inventory": Collections.MAGAZZINO,
    "warehouse_movements": Collections.MAGAZZINO_MOVIMENTI,
    "magazzino": Collections.MAGAZZINO,
    
    # TFR
    "tfr_dipendenti": Collections.TFR,
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
