"""
Definizione centralizzata delle collezioni MongoDB.
Questo file serve come UNICA fonte di verità per i nomi delle collezioni.

REGOLA FONDAMENTALE: Ogni router DEVE importare i nomi delle collezioni da qui.
NON usare MAI stringhe hardcoded per i nomi delle collezioni.

CONVENZIONE NOMI (snake_case):
- Tutto minuscolo
- Parole separate da underscore
- Prefisso per modulo (es: f24_, warehouse_)
- Suffisso per tipo (es: _movements, _alerts, _config)

Aggiornato: Gennaio 2026
"""

# ===========================================
# COLLEZIONI CORE - ENTITÀ PRINCIPALI
# ===========================================

# Fatture (fatture ricevute/passive)
COLL_INVOICES = "invoices"  # 3856 docs - Collezione UNICA per fatture passive
COLL_INVOICES_METADATA = "invoice_metadata_templates"
COLL_FAILED_INVOICES = "failed_invoices"
COLL_ALLEGATI_FATTURE = "allegati_fatture"

# Fatture Emesse (fatture attive)
COLL_FATTURE_EMESSE = "fatture_emesse"  # CANONICA (P1 §5.5): unico posto reale per le fatture emesse (writer CRUD + tutti i lettori contabili/IVA/dashboard)
COLL_INVOICES_EMESSE = "invoices_emesse"  # LEGACY/DEPRECATA (P1 §5.5): alias inglese; migrare in fatture_emesse con app/scripts/migra_invoices_emesse_a_fatture.py; NON scrivere qui

# Fornitori
COLL_SUPPLIERS = "fornitori"  # FIX: ora punta a "fornitori" (canonica). "suppliers" era alias inglese deprecato.
COLL_FORNITORI = "fornitori"  # 268 docs - Collezione italiana (dati primari)
COLL_FORNITORI_KEYWORDS = "fornitori_keywords"  # 244 docs - Learning Machine keywords
COLL_FORNITORI_DIZIONARIO = "fornitori_dizionario"

# Clienti
COLL_CLIENTS = "clients"  # Da implementare

# ===========================================
# DIPENDENTI E PAGHE
# ===========================================

# Anagrafica dipendenti
COLL_EMPLOYEES = "dipendenti"  # Regola assoluta: MAI "employees". Era "employees", rinominato.
COLL_DIPENDENTI = "dipendenti"  # Collection canonica (usa questa, identica a COLL_EMPLOYEES)
# DEPRECATA: anagrafica_dipendenti - tutti i dati migrati in employees

# Cedolini/Buste paga
COLL_CEDOLINI = "cedolini"  # 916 docs - Collezione principale
COLL_PAYSLIPS = "payslips"  # 480 docs - LEGACY/DEPRECATA (P1 §5.3): migrare in cedolini con app/scripts/migra_payslips_a_cedolini.py; NON scrivere qui
COLL_CEDOLINI_EMAIL = "cedolini_email_attachments"  # 224 docs
COLL_RIEPILOGO_CEDOLINI = "riepilogo_cedolini"  # 190 docs

# Stipendi e Bonifici
COLL_BONIFICI_STIPENDI = "bonifici_stipendi"  # 736 docs
COLL_PRIMA_NOTA_SALARI = "prima_nota_salari"  # 696 docs
COLL_ACCONTI_STIPENDI = "acconti_stipendi"
COLL_ACCONTI_DIPENDENTI = "acconti_dipendenti"

# TFR
COLL_TFR_ACCANTONAMENTI = "tfr_accantonamenti"
COLL_TFR_LIQUIDAZIONI = "tfr_liquidazioni"

# Presenze e Giustificativi
COLL_PRESENZE = "presenze"
COLL_PRESENZE_MENSILI = "presenze_mensili"  # 211 docs - Da parser Libro Unico
COLL_LIBRO_UNICO_PRESENZE = "libro_unico_presenze"  # LEGACY/ARCHIVIO (§13.2, 2026-07-13): scritta solo dalla famiglia /libro-unico/* rimossa da dipendenti.py (con libro_unico_salaries); il flusso LUL canonico usa presenze_mensili/buste_paga via import-libro-unico
COLL_ATTENDANCE_CALENDARIO = "attendance_presenze_calendario"  # 114 docs
COLL_ATTENDANCE_TIMBRATURE = "attendance_timbrature"
COLL_ATTENDANCE_ASSENZE = "attendance_assenze"
COLL_GIUSTIFICATIVI = "giustificativi"  # Permessi/ferie
COLL_GIUSTIFICATIVI_DIPENDENTE = "giustificativi_dipendente"
COLL_GIUSTIFICATIVI_SALDI_FINALI = "giustificativi_saldi_finali"  # NUOVO: Saldi finali per foglio progressivo
COLL_RICHIESTE_ASSENZA = "richieste_assenza"
COLL_RIPORTI_FERIE = "riporti_ferie"

COLL_TURNI_DIPENDENTI = "turni_dipendenti"
COLL_SHIFTS = "shifts"

# ===========================================
# F24 E TRIBUTI
# ===========================================

COLL_F24 = "f24_unificato"  # 83 docs - Collezione UNICA per F24
COLL_F24_UNIFICATO = "f24_unificato"  # Alias esplicito
COLL_F24_MODELS = "f24_models"  # LEGACY/DEPRECATA (P1 §5.1) - migrare in f24_unificato con app/scripts/migra_f24_unificato.py; NON scrivere qui
COLL_F24_COMMERCIALISTA = "f24_unificato"  # Alias retrocompatibilità
COLL_QUIETANZE_F24 = "quietanze_f24"  # 303 docs
COLL_F24_ALERTS = "f24_riconciliazione_alerts"  # 50 docs
COLL_F24_EMAIL = "f24_email_attachments"
COLL_TRIBUTI_PAGATI = "tributi_pagati"
COLL_RITENUTE_ACCONTO = "ritenute_acconto"

# ===========================================
# BANCA E CONTABILITÀ
# ===========================================

# Estratti Conto
COLL_ESTRATTO_CONTO = "estratto_conto_movimenti"  # CANONICA (P1 §5.6): MOVIMENTI bancari (unica sorgente riconciliazione/saldi) - 4261 docs
COLL_ESTRATTI_CONTO_DOCUMENTI = "estratti_conto"  # SEPARATA (P1 §5.6): registro dei DOCUMENTI estratto conto caricati (file/banca/periodo/saldo), NON i movimenti - come riepilogo_cedolini vs cedolini
COLL_ESTRATTO_CONTO_LEGACY = "estratto_conto"  # LEGACY/DEPRECATA (P1 §5.6): backup archivio senza lettori; NON unire nella canonica (rischio doppio conteggio movimenti/saldi errati)
COLL_ESTRATTO_CONTO_NEXI = "estratto_conto_nexi"  # 52 docs
COLL_ESTRATTO_CONTO_BNL = "estratto_conto_bnl"
COLL_ESTRATTO_CONTO_FORNITORI = "estratto_conto_fornitori"
COLL_BANK_STATEMENTS = "bank_statements"  # LEGACY/DEPRECATA (P1 §5.6): alias inglese senza accessi diretti; usare COLL_ESTRATTO_CONTO. NB Collections.BANK_STATEMENTS risolve già a estratto_conto_movimenti

# Prima Nota
COLL_PRIMA_NOTA_CASSA = "prima_nota_cassa"  # 1428 docs
COLL_PRIMA_NOTA_BANCA = "prima_nota_banca"  # 1138 docs
COLL_PRIMA_NOTA = "prima_nota"  # Unificata (se usata)
COLL_PRIMA_NOTA_RIGHE = "prima_nota_righe"

# Assegni
COLL_ASSEGNI = "assegni"  # 210 docs
COLL_ASSEGNI_LEARNING = "assegni_learning"  # 50 docs
COLL_OCR_ASSEGNI = "ocr_assegni"

# Bonifici
COLL_ARCHIVIO_BONIFICI = "archivio_bonifici"
COLL_BONIFICI_TRANSFERS = "bonifici_transfers"  # 97 docs
COLL_BONIFICI_EMAIL = "bonifici_email_attachments"

# Corrispettivi
COLL_CORRISPETTIVI = "corrispettivi"  # 1051 docs
COLL_CORRISPETTIVI_MANUALI = "corrispettivi_manuali"

# Piano dei Conti e Contabilità
COLL_PIANO_CONTI = "piano_conti"  # 259 docs
COLL_CHART_OF_ACCOUNTS = "chart_of_accounts"  # Alias inglese
COLL_MOVIMENTI_CONTABILI = "movimenti_contabili"
COLL_ACCOUNTING_ENTRIES = "accounting_entries"
COLL_OPENING_BALANCES = "opening_balances"
COLL_CENTRI_COSTO = "centri_costo"
COLL_CESPITI = "cespiti"

# Chiusure e Aperture Esercizio
COLL_CHIUSURE_ESERCIZIO = "chiusure_esercizio"
COLL_APERTURE_ESERCIZIO = "aperture_esercizio"
COLL_SALDI_GIORNALIERI = "saldi_giornalieri"

# IVA
COLL_ALIQUOTE_IVA = "aliquote_iva"  # 55 docs

# Scadenze
COLL_SCADENZARIO = "scadenzario"
COLL_SCADENZIARIO_FORNITORI = "scadenziario_fornitori"  # 903 docs
COLL_SCADENZE = "scadenze"
COLL_NOTIFICHE_SCADENZE = "notifiche_scadenze"
COLL_CALENDARIO_FISCALE = "calendario_fiscale"
COLL_AGEVOLAZIONI_FISCALI = "agevolazioni_fiscali"

# Riconciliazioni
COLL_RICONCILIAZIONI = "riconciliazioni"
COLL_OPERAZIONI_DA_CONFERMARE = "operazioni_da_confermare"  # 277 docs

# ===========================================
# MAGAZZINO E PRODOTTI
# ===========================================

# Inventario
# P1 §5.9: GestionaleCloud NON usa la giacenza fisica. Si mantengono solo i dati per il
# Dizionario Articoli (dizionario_prodotti) e lo storico acquisti (acquisti_prodotti/
# dettaglio_righe_fatture/warehouse_movements). Le collezioni di GIACENZA qui sotto sono
# NO-WRITE: nessuna NUOVA scrittura (insert/update) dal codice. NON cancellare le collezioni
# (condivise con l'app di magazzino).
COLL_WAREHOUSE = "warehouse_inventory"  # 5372 docs - Collezione UNICA (condivisa magazzino)
COLL_WAREHOUSE_INVENTORY = "warehouse_inventory"  # Alias esplicito
COLL_WAREHOUSE_STOCKS = "warehouse_stocks"  # 1484 docs - DEPRECATA (dati errati) · §5.9 NO-WRITE
COLL_WAREHOUSE_PRODUCTS = "warehouse_products"  # §5.9 NO-WRITE (giacenza)
COLL_MAGAZZINO = "magazzino"  # §5.9 NO-WRITE (giacenza)
COLL_MAGAZZINO_ARTICOLI = "magazzino_articoli"  # §5.9 NO-WRITE (giacenza)

# Movimenti
COLL_WAREHOUSE_MOVEMENTS = "warehouse_movements"  # 3935 docs - storico movimenti (lettura)
COLL_MAGAZZINO_MOVIMENTI = "magazzino_movimenti"  # §5.9 NO-WRITE (giacenza)
COLL_MOVIMENTI_MAGAZZINO = "movimenti_magazzino"  # §5.9 NO-WRITE (giacenza)

# Acquisti
COLL_ACQUISTI_PRODOTTI = "acquisti_prodotti"  # 15065 docs
COLL_DETTAGLIO_RIGHE_FATTURE = "dettaglio_righe_fatture"  # 11076 docs

# Dizionario prodotti / cataloghi
COLL_DIZIONARIO_PRODOTTI = "dizionario_prodotti"  # 112 docs
COLL_PRODUCT_CATALOG = "product_catalog"
COLL_PRODUCT_MAPPINGS = "product_mappings"

# Prezzi
COLL_PRICE_HISTORY = "price_history"  # 860 docs
COLL_MAGAZZINO_DIFFERENZE = "magazzino_differenze"
COLL_MAGAZZINO_DOPPIA_VERITA = "magazzino_doppia_verita"
COLL_RIMANENZE = "rimanenze"

# Configurazione
COLL_WAREHOUSE_CONFIG = "warehouse_config"

# ===========================================
# DOCUMENTI E EMAIL
# ===========================================

# Documenti generici
COLL_DOCUMENTS = "documents"
COLL_DOCUMENTS_INBOX = "documents_inbox"  # 803 docs
COLL_DOCUMENTI_CLASSIFICATI = "documenti_classificati"  # CANONICA (P1 §5.8, scelta utente): unica collezione doc classificati (Learning Machine + pipeline email) - 1967 docs
COLL_DOCUMENTS_CLASSIFIED = "documenti_classificati"  # LEGACY/DEPRECATA (P1 §5.8): alias inglese ora unificato sulla canonica; migrare con app/scripts/migra_documents_classified.py
COLL_DOCUMENTI_NON_ASSOCIATI = "documenti_non_associati"  # 285 docs
COLL_INDICE_DOCUMENTI = "indice_documenti"  # DEPRECATA - dati migrati in invoices. Tenere per email_reconciliation index
COLL_EXTRACTED_DOCUMENTS = "extracted_documents"  # LEGACY/ARCHIVIO (P1 §5.8): gli upload AI manuali ora scrivono nella canonica documenti_classificati (fonte="upload_ai"); migrare lo storico con app/scripts/migra_extracted_documents.py. Resta viva SOLO per il flusso "da rivedere" di ai_parser (campo status).
COLL_PORTAL_DOCUMENTS = "portal_documents"

# Email
COLL_DOCUMENTI_EMAIL = "documenti_email"  # 218 docs
COLL_EMAIL_DOCUMENTS = "email_documents"
COLL_EMAIL_ACCOUNTS = "email_accounts"
COLL_FATTURE_EMAIL = "fatture_email_attachments"  # 158 docs

# Elenco canonico di TUTTE le collezioni di allegati email per categoria
# (campo impronta: `pdf_hash`). Usato per il dedup cross-canale con
# documents_inbox (campo impronta: `file_hash`), stesso algoritmo md5.
EMAIL_ATTACHMENT_COLLECTIONS = (
    "f24_email_attachments",
    "fatture_email_attachments",
    "cedolini_email_attachments",
    "estratti_email_attachments",
    "quietanze_email_attachments",
    "bonifici_email_attachments",
    "verbali_email_attachments",
    "certificati_email_attachments",
    "cartelle_email_attachments",
    "avvisi_bonari_email_attachments",
    "dichiarazioni_iva_email_attachments",
    "documenti_non_associati",
)

# Commercialista
COLL_DOCUMENTI_COMMERCIALISTA = "documenti_commercialista"
COLL_COMMERCIALISTA_CONFIG = "commercialista_config"
COLL_COMMERCIALISTA_LOG = "commercialista_log"

# ===========================================
# LEARNING MACHINE E AI
# ===========================================

COLL_LEARNING_FEEDBACK = "learning_feedback"  # Feedback utente
COLL_LEARNING_RULES = "learning_rules"  # Regole apprese
COLL_REGOLE_CATEGORIE = "regole_categorie"
COLL_REGOLE_CATEGORIZZAZIONE_DESC = "regole_categorizzazione_descrizioni"
COLL_REGOLE_CATEGORIZZAZIONE_FORN = "regole_categorizzazione_fornitori"
COLL_ARUBA_ELABORAZIONI = "aruba_elaborazioni"  # 100 docs

# ===========================================
# NOLEGGIO AUTO
# ===========================================

COLL_VEICOLI_NOLEGGIO = "veicoli_noleggio"
COLL_VERBALI_NOLEGGIO = "verbali_noleggio"  # 52 docs
COLL_VERBALI_NOLEGGIO_COMPLETI = "verbali_noleggio_completi"
COLL_FATTURE_NOLEGGIO_XML = "fatture_noleggio_xml"  # 111 docs
COLL_COSTI_NOLEGGIO = "costi_noleggio"

# ===========================================
# CONFIGURAZIONE E SISTEMA
# ===========================================

COLL_CONFIG = "config"
COLL_CONFIGURAZIONI = "configurazioni"
COLL_SETTINGS = "settings"
COLL_SETTINGS_ASSETS = "settings_assets"
COLL_API_CLIENTS = "api_clients"
COLL_NOTIFICATIONS = "notifications"
COLL_ALERTS = "alerts"
COLL_EXPORT_LOG = "export_log"
COLL_SCHEDULED_EXPORTS = "scheduled_exports"

# ===========================================
# FORNITORI - ORDINI E PAGAMENTI
# ===========================================

COLL_SUPPLIER_ORDERS = "supplier_orders"
COLL_SUPPLIER_PAYMENT_METHODS = "supplier_payment_methods"
COLL_SUPPLIER_PAYMENT_HISTORY = "supplier_payment_history"
COLL_COMPARATORE_CART = "comparatore_cart"
COLL_COMPARATORE_EXCLUSIONS = "comparatore_supplier_exclusions"

# ===========================================
# PAYPAL
# ===========================================

COLL_PAYPAL_STATEMENTS = "paypal_statements"
COLL_PAYPAL_TRANSACTIONS = "paypal_transactions"

# ===========================================
# ALTRI
# ===========================================

COLL_NOTE_CREDITO = "note_credito"
COLL_PAGAMENTI_ANTICIPATI = "pagamenti_anticipati"
COLL_INCASSO_REALE = "incasso_reale"
COLL_COSTI_FINANZIARI = "costi_finanziari"
COLL_COSTI_PREVISIONALI = "costi_previsionali"
COLL_UTILE_OBIETTIVO = "utile_obiettivo"
COLL_ABBUONI = "abbuoni_arrotondamenti"
COLL_BUDGET = "budget"
COLL_PLANNING_EVENTS = "planning_events"
COLL_STAFF = "staff"  # LEGACY/DEPRECATA (P1 §5.2): alias anagrafica; migrare in dipendenti con app/scripts/migra_staff_a_dipendenti.py; NON scrivere qui
COLL_CARTS = "carts"
COLL_ADR = "adr_definizione_agevolata"
COLL_DELIBERE_FONSI = "delibere_fonsi"
COLL_DIMISSIONI = "dimissioni"

# ===========================================
# SISTEMA RELAZIONALE — Chat 8
# ===========================================

# Partite Aperte (scadenziario materializzato)
COLL_PARTITE_APERTE = "partite_aperte"

# Riconciliazione Match (N:M tra movimenti e partite)
COLL_RICONCILIAZIONI_MATCH = "riconciliazioni_match"

# Audit Log unificato
COLL_AUDIT_LOG = "audit_log"

# Alert Definitions (catalogo codici)
COLL_ALERT_DEFINITIONS = "alert_definitions"

# ===========================================
# QUERY PATTERNS COMUNI
# ===========================================

QUERY_F24_PATTERN = {
    "$or": [
        {"descrizione_originale": {"$regex": "I24.*AGENZIA", "$options": "i"}},
        {"descrizione_originale": {"$regex": "AGENZIA.*ENTRATE", "$options": "i"}},
        {"descrizione_originale": {"$regex": "F24", "$options": "i"}},
        {"categoria": {"$regex": "Tasse|Imposte|Tributi|F24", "$options": "i"}}
    ]
}

QUERY_STIPENDI_PATTERN = {
    "$or": [
        {"descrizione_originale": {"$regex": "STIP", "$options": "i"}},
        {"descrizione_originale": {"$regex": "SALARIO", "$options": "i"}},
        {"categoria": {"$regex": "Stipendi|Personale", "$options": "i"}}
    ]
}

QUERY_ASSEGNI_PATTERN = {
    "descrizione_originale": {"$regex": "ASSEGNO.*N\\.", "$options": "i"}
}

# ===========================================
# COLLEZIONI DEPRECATE - NON USARE
# ===========================================
"""
Le seguenti collezioni sono DEPRECATE e non devono essere usate:

- "f24" -> usare COLL_F24 (f24_unificato)
- "f24_models" -> usare COLL_F24 (f24_unificato)
- "movimenti_f24_banca" -> vuota, usare COLL_ESTRATTO_CONTO con QUERY_F24_PATTERN
- "estratto_conto" -> usare COLL_ESTRATTO_CONTO (estratto_conto_movimenti)
- "bank_statements" -> alias inglese, usare COLL_ESTRATTO_CONTO (estratto_conto_movimenti)
- "warehouse_stocks" -> dati errati, usare COLL_WAREHOUSE (warehouse_inventory)
- "anagrafica_dipendenti" -> usare COLL_EMPLOYEES (employees)
- "buste_paga" -> usare COLL_CEDOLINI (cedolini)
- "fatture_ricevute" -> vuota, usare COLL_INVOICES (invoices)
"""

# ===========================================
# HELPER FUNCTIONS
# ===========================================

def get_collection_by_entity(entity: str) -> str:
    """
    Restituisce il nome della collezione principale per un'entità.
    
    Args:
        entity: Nome dell'entità (es: 'employees', 'invoices', 'f24')
    
    Returns:
        Nome della collezione principale
    """
    ENTITY_MAP = {
        'employees': COLL_EMPLOYEES,
        'dipendenti': COLL_EMPLOYEES,
        'invoices': COLL_INVOICES,
        'fatture': COLL_INVOICES,
        'suppliers': COLL_FORNITORI,
        'fornitori': COLL_FORNITORI,
        'f24': COLL_F24,
        'cedolini': COLL_CEDOLINI,
        'payslips': COLL_CEDOLINI,
        'warehouse': COLL_WAREHOUSE,
        'magazzino': COLL_WAREHOUSE,
        'estratto_conto': COLL_ESTRATTO_CONTO,
        'bank': COLL_ESTRATTO_CONTO,
        'prima_nota_cassa': COLL_PRIMA_NOTA_CASSA,
        'prima_nota_banca': COLL_PRIMA_NOTA_BANCA,
        'corrispettivi': COLL_CORRISPETTIVI,
    }
    return ENTITY_MAP.get(entity.lower(), entity)


# Lista delle collezioni principali per validazione
MAIN_COLLECTIONS = [
    COLL_INVOICES,
    COLL_FORNITORI,
    COLL_EMPLOYEES,
    COLL_CEDOLINI,
    COLL_F24,
    COLL_ESTRATTO_CONTO,
    COLL_PRIMA_NOTA_CASSA,
    COLL_PRIMA_NOTA_BANCA,
    COLL_CORRISPETTIVI,
    COLL_WAREHOUSE,
    COLL_WAREHOUSE_MOVEMENTS,
    COLL_ACQUISTI_PRODOTTI,
]
