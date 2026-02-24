"""
Piano dei Conti (Chart of Accounts) - Sistema Contabile Completo
Schema per gestione contabilità generale italiana per bar/ristorante
"""

from datetime import datetime, timezone
from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from enum import Enum


class AccountType(str, Enum):
    """Tipologia conto contabile"""
    ATTIVO = "attivo"  # Assets
    PASSIVO = "passivo"  # Liabilities
    PATRIMONIO_NETTO = "patrimonio_netto"  # Equity
    RICAVI = "ricavi"  # Revenue
    COSTI = "costi"  # Expenses


class AccountCategory(str, Enum):
    """Categoria specifica del conto"""
    # ATTIVO
    IMMOBILIZZAZIONI_MATERIALI = "immobilizzazioni_materiali"
    IMMOBILIZZAZIONI_IMMATERIALI = "immobilizzazioni_immateriali"
    CASSA = "cassa"
    BANCA = "banca"
    CREDITI_CLIENTI = "crediti_clienti"
    RIMANENZE_MAGAZZINO = "rimanenze_magazzino"
    ALTRI_CREDITI = "altri_crediti"
    
    # PASSIVO
    DEBITI_FORNITORI = "debiti_fornitori"
    DEBITI_BANCARI = "debiti_bancari"
    DEBITI_TRIBUTARI = "debiti_tributari"
    DEBITI_PREVIDENZIALI = "debiti_previdenziali"
    ALTRI_DEBITI = "altri_debiti"
    
    # PATRIMONIO NETTO
    CAPITALE_SOCIALE = "capitale_sociale"
    RISERVE = "riserve"
    UTILI_PERDITE = "utili_perdite"
    
    # RICAVI
    VENDITE_BAR = "vendite_bar"
    VENDITE_CUCINA = "vendite_cucina"
    ALTRI_RICAVI = "altri_ricavi"
    
    # COSTI
    MERCE_FORNITORI = "merce_fornitori"
    COSTO_PERSONALE = "costo_personale"
    AFFITTI_LOCAZIONI = "affitti_locazioni"
    UTENZE = "utenze"
    AMMORTAMENTI = "ammortamenti"
    CONSULENZE = "consulenze"
    MANUTENZIONI = "manutenzioni"
    TRASPORTI = "trasporti"
    IMPOSTE_TASSE = "imposte_tasse"
    INTERESSI_PASSIVI = "interessi_passivi"
    ALTRI_COSTI = "altri_costi"


class Account(BaseModel):
    """
    Conto del Piano dei Conti
    
    Rappresenta un singolo conto contabile con codifica gerarchica
    """
    id: str = Field(default_factory=lambda: f"ACC-{datetime.now(timezone.utc).timestamp()}")
    user_id: str
    
    # Codifica conto (es: "1.1.01" per Cassa)
    account_code: str  # Codice gerarchico (1.x per Attivo, 2.x per Passivo, etc)
    account_name: str  # Nome del conto (es: "Cassa")
    
    # Classificazione
    account_type: AccountType
    account_category: AccountCategory
    
    # Gerarchia
    parent_code: Optional[str] = None  # Codice del conto padre (None per conti di primo livello)
    level: int = 1  # Livello gerarchico (1, 2, 3)
    
    # Configurazione
    is_active: bool = True
    allow_manual_entry: bool = True  # Permetti registrazioni manuali
    
    # Descrizione e note
    description: Optional[str] = None
    keywords: List[str] = []  # Parole chiave per mappatura automatica
    
    # Metadata
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    # Soft delete
    deleted_at: Optional[str] = None
    deleted_by: Optional[str] = None


class AccountCreate(BaseModel):
    """Schema per creazione nuovo conto"""
    account_code: str
    account_name: str
    account_type: AccountType
    account_category: AccountCategory
    parent_code: Optional[str] = None
    level: int = 1
    description: Optional[str] = None
    keywords: List[str] = []
    allow_manual_entry: bool = True


class AccountUpdate(BaseModel):
    """Schema per aggiornamento conto"""
    account_name: Optional[str] = None
    description: Optional[str] = None
    keywords: Optional[List[str]] = None
    is_active: Optional[bool] = None
    allow_manual_entry: Optional[bool] = None


class JournalEntry(BaseModel):
    """
    Registrazione Prima Nota Generale
    
    Registra ogni movimento contabile con partita doppia
    """
    id: str = Field(default_factory=lambda: f"JE-{datetime.now(timezone.utc).timestamp()}")
    user_id: str
    
    # Riferimenti temporali
    entry_date: str  # Data registrazione (ISO format YYYY-MM-DD)
    document_date: Optional[str] = None  # Data documento origine (fattura, etc)
    
    # Riferimenti documentali
    document_type: Optional[str] = None  # "fattura_fornitore", "corrispettivo", "movimento_bancario", etc
    document_number: Optional[str] = None
    document_id: Optional[str] = None  # ID del documento origine nel database
    
    # Causale
    description: str
    
    # Righe contabili (partita doppia)
    lines: List[dict]  # [{"account_code": str, "debit": float, "credit": float, "notes": str}]
    
    # Stato
    status: Literal["bozza", "registrato", "annullato"] = "bozza"
    registered_at: Optional[str] = None
    registered_by: Optional[str] = None
    
    # Metadata
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    # Soft delete
    deleted_at: Optional[str] = None
    deleted_by: Optional[str] = None


class JournalEntryCreate(BaseModel):
    """Schema per creazione registrazione contabile"""
    entry_date: str
    document_date: Optional[str] = None
    document_type: Optional[str] = None
    document_number: Optional[str] = None
    document_id: Optional[str] = None
    description: str
    lines: List[dict]


class AutoCategorizationRule(BaseModel):
    """
    Regola per categorizzazione automatica
    
    Mappa descrizioni fatture a conti contabili
    """
    id: str = Field(default_factory=lambda: f"RULE-{datetime.now(timezone.utc).timestamp()}")
    user_id: str
    
    # Pattern matching
    keywords: List[str]  # Parole chiave da cercare nella descrizione (es: ["pomodoro", "pelati"])
    supplier_vat: Optional[str] = None  # Se specificato, applica solo a questo fornitore
    
    # Destinazione
    account_code: str  # Conto di destinazione
    
    # Priorità e validità
    priority: int = 50  # Priorità (1-100, default 50)
    confidence: Literal["high", "medium", "low"] = "medium"
    
    # Statistiche utilizzo
    match_count: int = 0
    last_used: Optional[str] = None
    
    # Metadata
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    # Soft delete
    deleted_at: Optional[str] = None
    deleted_by: Optional[str] = None


class AutoCategorizationRuleCreate(BaseModel):
    """Schema per creazione regola categorizzazione"""
    keywords: List[str]
    supplier_vat: Optional[str] = None
    account_code: str
    priority: int = 50
    confidence: Literal["high", "medium", "low"] = "medium"


# ============================================================================
# Piano dei Conti Standard per Bar/Ristorante Italiano
# ============================================================================

STANDARD_CHART_OF_ACCOUNTS = [
    # ========== ATTIVO ==========
    
    # 1. IMMOBILIZZAZIONI (1.1.xx)
    {
        "account_code": "1.1",
        "account_name": "Immobilizzazioni materiali",
        "account_type": "attivo",
        "account_category": "immobilizzazioni_materiali",
        "level": 1,
        "description": "Beni durevoli dell'attività",
        "keywords": [],
        "allow_manual_entry": False
    },
    {
        "account_code": "1.1.01",
        "account_name": "Attrezzature da bar",
        "account_type": "attivo",
        "account_category": "immobilizzazioni_materiali",
        "parent_code": "1.1",
        "level": 2,
        "description": "Macchine caffè, frigoriferi, frullatori, etc",
        "keywords": ["macchina caffè", "frigorifero", "frullatore", "attrezzatura"],
        "allow_manual_entry": True
    },
    {
        "account_code": "1.1.02",
        "account_name": "Mobili e arredi",
        "account_type": "attivo",
        "account_category": "immobilizzazioni_materiali",
        "parent_code": "1.1",
        "level": 2,
        "description": "Tavoli, sedie, bancone, arredamento",
        "keywords": ["tavolo", "sedia", "bancone", "arredamento", "mobile"],
        "allow_manual_entry": True
    },
    {
        "account_code": "1.1.03",
        "account_name": "Impianti",
        "account_type": "attivo",
        "account_category": "immobilizzazioni_materiali",
        "parent_code": "1.1",
        "level": 2,
        "description": "Impianti elettrici, idraulici, climatizzazione",
        "keywords": ["impianto", "climatizzazione", "condizionatore"],
        "allow_manual_entry": True
    },
    
    # 2. ATTIVO CIRCOLANTE (1.2.xx)
    {
        "account_code": "1.2",
        "account_name": "Attivo circolante",
        "account_type": "attivo",
        "account_category": "cassa",
        "level": 1,
        "description": "Liquidità e attività correnti",
        "keywords": [],
        "allow_manual_entry": False
    },
    {
        "account_code": "1.2.01",
        "account_name": "Cassa",
        "account_type": "attivo",
        "account_category": "cassa",
        "parent_code": "1.2",
        "level": 2,
        "description": "Denaro contante in cassa",
        "keywords": ["cassa", "contanti", "contante"],
        "allow_manual_entry": True
    },
    {
        "account_code": "1.2.02",
        "account_name": "Banca c/c",
        "account_type": "attivo",
        "account_category": "banca",
        "parent_code": "1.2",
        "level": 2,
        "description": "Conto corrente bancario",
        "keywords": ["banca", "bonifico", "conto corrente"],
        "allow_manual_entry": True
    },
    {
        "account_code": "1.2.03",
        "account_name": "Crediti verso clienti",
        "account_type": "attivo",
        "account_category": "crediti_clienti",
        "parent_code": "1.2",
        "level": 2,
        "description": "Crediti da clienti",
        "keywords": ["credito cliente", "fattura attiva"],
        "allow_manual_entry": True
    },
    {
        "account_code": "1.2.04",
        "account_name": "Rimanenze di magazzino",
        "account_type": "attivo",
        "account_category": "rimanenze_magazzino",
        "parent_code": "1.2",
        "level": 2,
        "description": "Valore delle merci in giacenza (FIFO consigliato)",
        "keywords": ["rimanenze", "giacenza", "magazzino", "inventario"],
        "allow_manual_entry": True
    },
    {
        "account_code": "1.2.05",
        "account_name": "Ratei attivi",
        "account_type": "attivo",
        "account_category": "altri_crediti",
        "parent_code": "1.2",
        "level": 2,
        "description": "Ricavi maturati ma non ancora incassati",
        "keywords": ["ratei attivi", "competenza"],
        "allow_manual_entry": True
    },
    {
        "account_code": "1.2.06",
        "account_name": "Risconti attivi",
        "account_type": "attivo",
        "account_category": "altri_crediti",
        "parent_code": "1.2",
        "level": 2,
        "description": "Costi pagati ma di competenza futura",
        "keywords": ["risconti attivi", "competenza futura"],
        "allow_manual_entry": True
    },
    
    # ========== PASSIVO ==========
    
    # 3. DEBITI (2.1.xx)
    {
        "account_code": "2.1",
        "account_name": "Debiti",
        "account_type": "passivo",
        "account_category": "debiti_fornitori",
        "level": 1,
        "description": "Obbligazioni verso terzi",
        "keywords": [],
        "allow_manual_entry": False
    },
    {
        "account_code": "2.1.01",
        "account_name": "Debiti verso fornitori",
        "account_type": "passivo",
        "account_category": "debiti_fornitori",
        "parent_code": "2.1",
        "level": 2,
        "description": "Fatture fornitori da pagare",
        "keywords": ["fornitore", "fattura fornitore"],
        "allow_manual_entry": True
    },
    {
        "account_code": "2.1.02",
        "account_name": "Debiti tributari",
        "account_type": "passivo",
        "account_category": "debiti_tributari",
        "parent_code": "2.1",
        "level": 2,
        "description": "IVA, IRES, IRAP, ritenute",
        "keywords": ["iva", "ires", "irap", "f24", "tributi"],
        "allow_manual_entry": True
    },
    {
        "account_code": "2.1.03",
        "account_name": "Debiti previdenziali",
        "account_type": "passivo",
        "account_category": "debiti_previdenziali",
        "parent_code": "2.1",
        "level": 2,
        "description": "INPS, contributi",
        "keywords": ["inps", "contributi", "previdenza"],
        "allow_manual_entry": True
    },
    {
        "account_code": "2.1.04",
        "account_name": "Debiti bancari",
        "account_type": "passivo",
        "account_category": "debiti_bancari",
        "parent_code": "2.1",
        "level": 2,
        "description": "Mutui, finanziamenti",
        "keywords": ["mutuo", "finanziamento", "prestito"],
        "allow_manual_entry": True
    },
    {
        "account_code": "2.1.05",
        "account_name": "Fondo TFR",
        "account_type": "passivo",
        "account_category": "debiti_previdenziali",
        "parent_code": "2.1",
        "level": 2,
        "description": "Fondo Trattamento Fine Rapporto dipendenti",
        "keywords": ["tfr", "trattamento fine rapporto", "liquidazione"],
        "allow_manual_entry": True
    },
    {
        "account_code": "2.1.06",
        "account_name": "Fondo TFR c/o INPS",
        "account_type": "passivo",
        "account_category": "debiti_previdenziali",
        "parent_code": "2.1",
        "level": 2,
        "description": "TFR versato al Fondo Tesoreria INPS",
        "keywords": ["tfr inps", "fondo tesoreria"],
        "allow_manual_entry": True
    },
    {
        "account_code": "2.1.07",
        "account_name": "Ratei passivi",
        "account_type": "passivo",
        "account_category": "altri_debiti",
        "parent_code": "2.1",
        "level": 2,
        "description": "Costi maturati ma non ancora pagati",
        "keywords": ["ratei passivi", "competenza"],
        "allow_manual_entry": True
    },
    {
        "account_code": "2.1.08",
        "account_name": "Risconti passivi",
        "account_type": "passivo",
        "account_category": "altri_debiti",
        "parent_code": "2.1",
        "level": 2,
        "description": "Ricavi incassati ma di competenza futura",
        "keywords": ["risconti passivi", "competenza futura"],
        "allow_manual_entry": True
    },
    {
        "account_code": "2.1.09",
        "account_name": "Debiti verso soci per dividendi",
        "account_type": "passivo",
        "account_category": "altri_debiti",
        "parent_code": "2.1",
        "level": 2,
        "description": "Dividendi deliberati ma non ancora pagati",
        "keywords": ["dividendi", "distribuzione utili"],
        "allow_manual_entry": True
    },
    {
        "account_code": "2.1.10",
        "account_name": "Fondo manutenzioni cicliche",
        "account_type": "passivo",
        "account_category": "altri_debiti",
        "parent_code": "2.1",
        "level": 2,
        "description": "Accantonamento per manutenzioni programmate",
        "keywords": ["fondo manutenzioni", "accantonamento"],
        "allow_manual_entry": True
    },
    {
        "account_code": "2.1.11",
        "account_name": "Fondo garanzie",
        "account_type": "passivo",
        "account_category": "altri_debiti",
        "parent_code": "2.1",
        "level": 2,
        "description": "Fondo rischi per garanzie clienti",
        "keywords": ["fondo garanzie", "rischi"],
        "allow_manual_entry": True
    },
    {
        "account_code": "2.1.12",
        "account_name": "Fondo cause legali",
        "account_type": "passivo",
        "account_category": "altri_debiti",
        "parent_code": "2.1",
        "level": 2,
        "description": "Accantonamento per contenziosi in corso",
        "keywords": ["fondo cause", "contenziosi", "vertenze"],
        "allow_manual_entry": True
    },
    
    # 4. PATRIMONIO NETTO (2.2.xx)
    {
        "account_code": "2.2",
        "account_name": "Patrimonio netto",
        "account_type": "patrimonio_netto",
        "account_category": "capitale_sociale",
        "level": 1,
        "description": "Capitale proprio dell'azienda",
        "keywords": [],
        "allow_manual_entry": False
    },
    {
        "account_code": "2.2.01",
        "account_name": "Capitale sociale",
        "account_type": "patrimonio_netto",
        "account_category": "capitale_sociale",
        "parent_code": "2.2",
        "level": 2,
        "description": "Capitale versato dai soci",
        "keywords": ["capitale", "conferimento"],
        "allow_manual_entry": True
    },
    {
        "account_code": "2.2.02",
        "account_name": "Riserva legale",
        "account_type": "patrimonio_netto",
        "account_category": "riserve",
        "parent_code": "2.2",
        "level": 2,
        "description": "Riserva obbligatoria (5% utili fino a 20% capitale)",
        "keywords": ["riserva legale", "obbligatoria"],
        "allow_manual_entry": True
    },
    {
        "account_code": "2.2.03",
        "account_name": "Riserva straordinaria",
        "account_type": "patrimonio_netto",
        "account_category": "riserve",
        "parent_code": "2.2",
        "level": 2,
        "description": "Riserva volontaria da utili",
        "keywords": ["riserva straordinaria", "volontaria"],
        "allow_manual_entry": True
    },
    {
        "account_code": "2.2.04",
        "account_name": "Riserve di capitale",
        "account_type": "patrimonio_netto",
        "account_category": "riserve",
        "parent_code": "2.2",
        "level": 2,
        "description": "Sovrapprezzo azioni, conferimenti",
        "keywords": ["riserve capitale", "sovrapprezzo"],
        "allow_manual_entry": True
    },
    {
        "account_code": "2.2.05",
        "account_name": "Riserve in sospensione d'imposta",
        "account_type": "patrimonio_netto",
        "account_category": "riserve",
        "parent_code": "2.2",
        "level": 2,
        "description": "Riserve con benefici fiscali",
        "keywords": ["riserve fiscali", "sospensione imposta"],
        "allow_manual_entry": True
    },
    {
        "account_code": "2.2.06",
        "account_name": "Utili (perdite) portati a nuovo",
        "account_type": "patrimonio_netto",
        "account_category": "utili_perdite",
        "parent_code": "2.2",
        "level": 2,
        "description": "Utili non distribuiti esercizi precedenti",
        "keywords": ["utili portati", "perdite portate"],
        "allow_manual_entry": True
    },
    {
        "account_code": "2.2.07",
        "account_name": "Utile (perdita) dell'esercizio",
        "account_type": "patrimonio_netto",
        "account_category": "utili_perdite",
        "parent_code": "2.2",
        "level": 2,
        "description": "Risultato economico dell'anno corrente",
        "keywords": ["utile esercizio", "perdita esercizio"],
        "allow_manual_entry": False
    },
    
    # ========== RICAVI ==========
    
    # 5. RICAVI (3.1.xx)
    {
        "account_code": "3.1",
        "account_name": "Ricavi delle vendite",
        "account_type": "ricavi",
        "account_category": "vendite_bar",
        "level": 1,
        "description": "Fatturato da vendite",
        "keywords": [],
        "allow_manual_entry": False
    },
    {
        "account_code": "3.1.01",
        "account_name": "Ricavi bar",
        "account_type": "ricavi",
        "account_category": "vendite_bar",
        "parent_code": "3.1",
        "level": 2,
        "description": "Vendite bevande al bar",
        "keywords": ["corrispettivo", "vendita", "incasso"],
        "allow_manual_entry": True
    },
    {
        "account_code": "3.1.02",
        "account_name": "Ricavi cucina",
        "account_type": "ricavi",
        "account_category": "vendite_cucina",
        "parent_code": "3.1",
        "level": 2,
        "description": "Vendite cibo e piatti",
        "keywords": ["vendita cucina", "vendita cibo"],
        "allow_manual_entry": True
    },
    
    # ========== COSTI ==========
    
    # 6. COSTO DEL VENDUTO (4.1.xx)
    {
        "account_code": "4.1",
        "account_name": "Acquisti merce",
        "account_type": "costi",
        "account_category": "merce_fornitori",
        "level": 1,
        "description": "Costo merce acquistata",
        "keywords": [],
        "allow_manual_entry": False
    },
    {
        "account_code": "4.1.01",
        "account_name": "Merce c/fornitori - Alimenti",
        "account_type": "costi",
        "account_category": "merce_fornitori",
        "parent_code": "4.1",
        "level": 2,
        "description": "Acquisti prodotti alimentari",
        "keywords": ["pomodoro", "pasta", "farina", "olio", "verdura", "frutta", "carne", "pesce", "pane", "alimentare", "alimento", "prodotto alimentare"],
        "allow_manual_entry": True
    },
    {
        "account_code": "4.1.02",
        "account_name": "Merce c/fornitori - Bevande",
        "account_type": "costi",
        "account_category": "merce_fornitori",
        "parent_code": "4.1",
        "level": 2,
        "description": "Acquisti bevande (alcoliche e analcoliche)",
        "keywords": ["caffè", "vino", "birra", "acqua", "bibita", "bevanda", "spremuta", "succo"],
        "allow_manual_entry": True
    },
    {
        "account_code": "4.1.03",
        "account_name": "Merce c/fornitori - Materiali di consumo",
        "account_type": "costi",
        "account_category": "merce_fornitori",
        "parent_code": "4.1",
        "level": 2,
        "description": "Piatti, bicchieri, tovaglioli, detergenti",
        "keywords": ["piatto", "bicchiere", "tovagliolo", "detergente", "sapone", "carta", "plastica", "posate"],
        "allow_manual_entry": True
    },
    {
        "account_code": "4.1.04",
        "account_name": "Variazione rimanenze di magazzino",
        "account_type": "costi",
        "account_category": "merce_fornitori",
        "parent_code": "4.1",
        "level": 2,
        "description": "Storno/carico rimanenze iniziali e finali",
        "keywords": ["variazione rimanenze", "inventario"],
        "allow_manual_entry": True
    },
    {
        "account_code": "4.1.05",
        "account_name": "Svalutazione rimanenze",
        "account_type": "costi",
        "account_category": "merce_fornitori",
        "parent_code": "4.1",
        "level": 2,
        "description": "Svalutazione per obsolescenza o scadenza prodotti",
        "keywords": ["svalutazione", "obsolescenza", "scadenza"],
        "allow_manual_entry": True
    },
    
    # 7. COSTI OPERATIVI (4.2.xx)
    {
        "account_code": "4.2",
        "account_name": "Costi operativi",
        "account_type": "costi",
        "account_category": "costo_personale",
        "level": 1,
        "description": "Spese di gestione corrente",
        "keywords": [],
        "allow_manual_entry": False
    },
    {
        "account_code": "4.2.01",
        "account_name": "Costo del personale",
        "account_type": "costi",
        "account_category": "costo_personale",
        "parent_code": "4.2",
        "level": 2,
        "description": "Stipendi, contributi, TFR",
        "keywords": ["stipendio", "salario", "personale", "dipendente", "lavoro"],
        "allow_manual_entry": True
    },
    {
        "account_code": "4.2.02",
        "account_name": "Affitti e locazioni",
        "account_type": "costi",
        "account_category": "affitti_locazioni",
        "parent_code": "4.2",
        "level": 2,
        "description": "Canoni di locazione immobili",
        "keywords": ["affitto", "locazione", "canone"],
        "allow_manual_entry": True
    },
    {
        "account_code": "4.2.03",
        "account_name": "Utenze",
        "account_type": "costi",
        "account_category": "utenze",
        "parent_code": "4.2",
        "level": 2,
        "description": "Energia elettrica, gas, acqua, telefono",
        "keywords": ["energia", "elettricità", "gas", "acqua", "telefono", "internet", "utenza"],
        "allow_manual_entry": True
    },
    {
        "account_code": "4.2.04",
        "account_name": "Manutenzioni e riparazioni",
        "account_type": "costi",
        "account_category": "manutenzioni",
        "parent_code": "4.2",
        "level": 2,
        "description": "Riparazioni attrezzature e impianti",
        "keywords": ["manutenzione", "riparazione", "assistenza tecnica"],
        "allow_manual_entry": True
    },
    {
        "account_code": "4.2.05",
        "account_name": "Consulenze professionali",
        "account_type": "costi",
        "account_category": "consulenze",
        "parent_code": "4.2",
        "level": 2,
        "description": "Commercialista, avvocato, consulenti",
        "keywords": ["commercialista", "avvocato", "consulente", "consulenza", "notaio"],
        "allow_manual_entry": True
    },
    {
        "account_code": "4.2.06",
        "account_name": "Trasporti e carburanti",
        "account_type": "costi",
        "account_category": "trasporti",
        "parent_code": "4.2",
        "level": 2,
        "description": "Spese auto, carburanti, pedaggi",
        "keywords": ["carburante", "benzina", "gasolio", "trasporto", "pedaggio", "auto"],
        "allow_manual_entry": True
    },
    {
        "account_code": "4.2.07",
        "account_name": "Ammortamenti immobilizzazioni",
        "account_type": "costi",
        "account_category": "ammortamenti",
        "parent_code": "4.2",
        "level": 2,
        "description": "Quote ammortamento macchinari, attrezzature, arredamento",
        "keywords": ["ammortamento", "quote ammortamento"],
        "allow_manual_entry": True
    },
    {
        "account_code": "4.2.08",
        "account_name": "Spese di rappresentanza",
        "account_type": "costi",
        "account_category": "altri_costi",
        "parent_code": "4.2",
        "level": 2,
        "description": "Omaggi clienti, spese rappresentanza",
        "keywords": ["omaggi", "rappresentanza", "spese promozionali"],
        "allow_manual_entry": True
    },
    {
        "account_code": "4.2.09",
        "account_name": "Accantonamenti fondi rischi",
        "account_type": "costi",
        "account_category": "altri_costi",
        "parent_code": "4.2",
        "level": 2,
        "description": "Accantonamenti a fondi manutenzioni, garanzie, cause",
        "keywords": ["accantonamento", "fondi rischi"],
        "allow_manual_entry": True
    },
    
    # 8. ONERI FINANZIARI E TRIBUTARI (4.3.xx)
    {
        "account_code": "4.3",
        "account_name": "Oneri finanziari e tributari",
        "account_type": "costi",
        "account_category": "imposte_tasse",
        "level": 1,
        "description": "Interessi, commissioni, imposte",
        "keywords": [],
        "allow_manual_entry": False
    },
    {
        "account_code": "4.3.01",
        "account_name": "Interessi passivi bancari",
        "account_type": "costi",
        "account_category": "interessi_passivi",
        "parent_code": "4.3",
        "level": 2,
        "description": "Interessi su mutui e finanziamenti",
        "keywords": ["interessi", "commissione bancaria"],
        "allow_manual_entry": True
    },
    {
        "account_code": "4.3.02",
        "account_name": "Imposte e tasse",
        "account_type": "costi",
        "account_category": "imposte_tasse",
        "parent_code": "4.3",
        "level": 2,
        "description": "IRES, IRAP, IMU, altre imposte",
        "keywords": ["ires", "irap", "imu", "tassa", "imposta"],
        "allow_manual_entry": True
    },
]


# Regole di categorizzazione automatica standard
# Basato su ricerche web aggiornate 2025 per bar/ristorante italiano
STANDARD_CATEGORIZATION_RULES = [
    # ========== ALIMENTI (4.1.01) - MATERIE PRIME ALIMENTARI ==========
    
    # Carni e salumi
    {
        "keywords": ["carne", "carni", "bovino", "bovini", "manzo", "vitello", "vitella"],
        "account_code": "4.1.01",
        "priority": 90,
        "confidence": "high"
    },
    {
        "keywords": ["pollo", "polli", "gallina", "tacchino", "avicolo", "avicoli"],
        "account_code": "4.1.01",
        "priority": 90,
        "confidence": "high"
    },
    {
        "keywords": ["maiale", "suino", "suini", "porco", "lonza", "pancetta"],
        "account_code": "4.1.01",
        "priority": 90,
        "confidence": "high"
    },
    {
        "keywords": ["salame", "salami", "prosciutto", "speck", "bresaola", "mortadella", "wurstel"],
        "account_code": "4.1.01",
        "priority": 90,
        "confidence": "high"
    },
    
    # Pesce e prodotti ittici
    {
        "keywords": ["pesce", "pesci", "tonno", "salmone", "branzino", "orata", "spigola"],
        "account_code": "4.1.01",
        "priority": 90,
        "confidence": "high"
    },
    {
        "keywords": ["frutti di mare", "gamberi", "gamberetti", "calamari", "cozze", "vongole"],
        "account_code": "4.1.01",
        "priority": 90,
        "confidence": "high"
    },
    
    # Formaggi e latticini
    {
        "keywords": ["formaggio", "formaggi", "mozzarella", "parmigiano", "grana", "gorgonzola"],
        "account_code": "4.1.01",
        "priority": 90,
        "confidence": "high"
    },
    {
        "keywords": ["pecorino", "ricotta", "mascarpone", "scamorza", "provolone"],
        "account_code": "4.1.01",
        "priority": 90,
        "confidence": "high"
    },
    {
        "keywords": ["latte", "panna", "burro", "yogurt"],
        "account_code": "4.1.01",
        "priority": 90,
        "confidence": "high"
    },
    {
        "keywords": ["uova", "uovo"],
        "account_code": "4.1.01",
        "priority": 95,
        "confidence": "high"
    },
    
    # Verdure e ortaggi
    {
        "keywords": ["verdura", "verdure", "ortaggio", "ortaggi", "insalata", "lattuga"],
        "account_code": "4.1.01",
        "priority": 85,
        "confidence": "high"
    },
    {
        "keywords": ["pomodoro", "pomodori", "pelati", "passata", "concentrato", "polpa"],
        "account_code": "4.1.01",
        "priority": 90,
        "confidence": "high"
    },
    {
        "keywords": ["patate", "patata", "carote", "carota", "zucchine", "zucchina"],
        "account_code": "4.1.01",
        "priority": 85,
        "confidence": "high"
    },
    {
        "keywords": ["melanzane", "melanzana", "peperoni", "peperone", "cipolla", "cipolle"],
        "account_code": "4.1.01",
        "priority": 85,
        "confidence": "high"
    },
    {
        "keywords": ["spinaci", "brocoli", "broccoli", "cavolfiore", "cavolo", "verza"],
        "account_code": "4.1.01",
        "priority": 85,
        "confidence": "high"
    },
    
    # Frutta
    {
        "keywords": ["frutta", "mela", "mele", "pera", "pere", "banana", "banane"],
        "account_code": "4.1.01",
        "priority": 85,
        "confidence": "high"
    },
    {
        "keywords": ["arancia", "arance", "limone", "limoni", "mandarino", "mandarini"],
        "account_code": "4.1.01",
        "priority": 85,
        "confidence": "high"
    },
    {
        "keywords": ["fragole", "fragola", "pesche", "pesca", "albicocche", "ciliegie"],
        "account_code": "4.1.01",
        "priority": 85,
        "confidence": "high"
    },
    
    # Pasta, riso, cereali
    {
        "keywords": ["pasta", "spaghetti", "penne", "fusilli", "rigatoni", "farfalle"],
        "account_code": "4.1.01",
        "priority": 90,
        "confidence": "high"
    },
    {
        "keywords": ["riso", "risotto", "arborio", "carnaroli"],
        "account_code": "4.1.01",
        "priority": 90,
        "confidence": "high"
    },
    {
        "keywords": ["farina", "farine", "semola", "semolino"],
        "account_code": "4.1.01",
        "priority": 85,
        "confidence": "high"
    },
    
    # Pane e prodotti da forno
    {
        "keywords": ["pane", "panino", "panini", "focaccia", "grissini", "crackers"],
        "account_code": "4.1.01",
        "priority": 90,
        "confidence": "high"
    },
    {
        "keywords": ["pizza", "pizze", "impasto", "base pizza"],
        "account_code": "4.1.01",
        "priority": 90,
        "confidence": "high"
    },
    
    # Condimenti e spezie
    {
        "keywords": ["olio", "extravergine", "oliva", "semi"],
        "account_code": "4.1.01",
        "priority": 90,
        "confidence": "high"
    },
    {
        "keywords": ["aceto", "balsamico", "sale", "pepe", "spezie"],
        "account_code": "4.1.01",
        "priority": 85,
        "confidence": "high"
    },
    {
        "keywords": ["basilico", "origano", "rosmarino", "salvia", "prezzemolo"],
        "account_code": "4.1.01",
        "priority": 85,
        "confidence": "high"
    },
    
    # Dolci e dessert
    {
        "keywords": ["gelato", "gelati", "sorbetto", "semifreddo"],
        "account_code": "4.1.01",
        "priority": 85,
        "confidence": "high"
    },
    {
        "keywords": ["torta", "torte", "dolce", "dolci", "pasticceria", "tiramisù"],
        "account_code": "4.1.01",
        "priority": 85,
        "confidence": "high"
    },
    {
        "keywords": ["zucchero", "miele", "cioccolato", "cacao", "nutella"],
        "account_code": "4.1.01",
        "priority": 85,
        "confidence": "high"
    },
    
    # ========== BEVANDE (4.1.02) - BEVANDE ALCOLICHE E ANALCOLICHE ==========
    
    # Caffè e bevande calde
    {
        "keywords": ["caffè", "caffe", "espresso", "grani", "miscela", "arabica", "robusta"],
        "account_code": "4.1.02",
        "priority": 95,
        "confidence": "high"
    },
    {
        "keywords": ["cappuccino", "latte macchiato", "caffellatte"],
        "account_code": "4.1.02",
        "priority": 90,
        "confidence": "high"
    },
    {
        "keywords": ["tè", "te", "tisana", "tisane", "camomilla", "infuso"],
        "account_code": "4.1.02",
        "priority": 90,
        "confidence": "high"
    },
    {
        "keywords": ["cioccolata", "cioccolata calda", "orzo", "ginseng"],
        "account_code": "4.1.02",
        "priority": 90,
        "confidence": "high"
    },
    
    # Vini
    {
        "keywords": ["vino", "vini", "rosso", "bianco", "rosato", "rosè"],
        "account_code": "4.1.02",
        "priority": 95,
        "confidence": "high"
    },
    {
        "keywords": ["prosecco", "spumante", "champagne", "franciacorta"],
        "account_code": "4.1.02",
        "priority": 95,
        "confidence": "high"
    },
    {
        "keywords": ["lambrusco", "barbera", "chianti", "montepulciano", "sangiovese"],
        "account_code": "4.1.02",
        "priority": 95,
        "confidence": "high"
    },
    {
        "keywords": ["pinot", "chardonnay", "sauvignon", "cabernet", "merlot"],
        "account_code": "4.1.02",
        "priority": 95,
        "confidence": "high"
    },
    
    # Birre
    {
        "keywords": ["birra", "birre", "lager", "ale", "stout", "weiss"],
        "account_code": "4.1.02",
        "priority": 95,
        "confidence": "high"
    },
    {
        "keywords": ["peroni", "moretti", "nastro azzurro", "corona", "heineken"],
        "account_code": "4.1.02",
        "priority": 95,
        "confidence": "high"
    },
    {
        "keywords": ["artigianale", "craft", "ipa"],
        "account_code": "4.1.02",
        "priority": 90,
        "confidence": "high"
    },
    
    # Spirits e superalcolici
    {
        "keywords": ["whisky", "whiskey", "bourbon", "scotch"],
        "account_code": "4.1.02",
        "priority": 95,
        "confidence": "high"
    },
    {
        "keywords": ["gin", "vodka", "rum", "tequila", "mezcal"],
        "account_code": "4.1.02",
        "priority": 95,
        "confidence": "high"
    },
    {
        "keywords": ["brandy", "cognac", "armagnac", "calvados"],
        "account_code": "4.1.02",
        "priority": 95,
        "confidence": "high"
    },
    {
        "keywords": ["grappa", "acquavite", "distillato"],
        "account_code": "4.1.02",
        "priority": 95,
        "confidence": "high"
    },
    
    # Amari e liquori
    {
        "keywords": ["amaro", "amari", "montenegro", "averna", "cynar", "fernet"],
        "account_code": "4.1.02",
        "priority": 95,
        "confidence": "high"
    },
    {
        "keywords": ["limoncello", "sambuca", "nocino", "amaretto", "baileys"],
        "account_code": "4.1.02",
        "priority": 95,
        "confidence": "high"
    },
    {
        "keywords": ["liquore", "liquori", "crema", "rosolio"],
        "account_code": "4.1.02",
        "priority": 95,
        "confidence": "high"
    },
    {
        "keywords": ["aperol", "campari", "martini", "vermouth", "aperitivo"],
        "account_code": "4.1.02",
        "priority": 95,
        "confidence": "high"
    },
    
    # Acqua
    {
        "keywords": ["acqua", "minerale", "naturale", "frizzante", "effervescente"],
        "account_code": "4.1.02",
        "priority": 95,
        "confidence": "high"
    },
    {
        "keywords": ["san pellegrino", "levissima", "ferrarelle", "panna"],
        "account_code": "4.1.02",
        "priority": 95,
        "confidence": "high"
    },
    
    # Bibite analcoliche
    {
        "keywords": ["coca cola", "coca-cola", "pepsi", "fanta", "sprite"],
        "account_code": "4.1.02",
        "priority": 95,
        "confidence": "high"
    },
    {
        "keywords": ["aranciata", "limonata", "gassosa", "chinotto", "cedrata"],
        "account_code": "4.1.02",
        "priority": 95,
        "confidence": "high"
    },
    {
        "keywords": ["succo", "succhi", "nettare", "spremuta"],
        "account_code": "4.1.02",
        "priority": 90,
        "confidence": "high"
    },
    {
        "keywords": ["energy drink", "red bull", "monster", "gatorade"],
        "account_code": "4.1.02",
        "priority": 90,
        "confidence": "high"
    },
    {
        "keywords": ["tè freddo", "te freddo", "estathè", "fuze tea"],
        "account_code": "4.1.02",
        "priority": 90,
        "confidence": "high"
    },
    
    # ========== MATERIALI DI CONSUMO (4.1.03) ==========
    
    # Stoviglie monouso
    {
        "keywords": ["piatti", "piatto", "monouso", "usa e getta", "disposable"],
        "account_code": "4.1.03",
        "priority": 90,
        "confidence": "high"
    },
    {
        "keywords": ["bicchieri", "bicchiere", "calice", "calici", "flute"],
        "account_code": "4.1.03",
        "priority": 90,
        "confidence": "high"
    },
    {
        "keywords": ["posate", "forchette", "coltelli", "cucchiai", "cucchiaini"],
        "account_code": "4.1.03",
        "priority": 90,
        "confidence": "high"
    },
    {
        "keywords": ["tazzine", "tazzina", "tazza", "tazze"],
        "account_code": "4.1.03",
        "priority": 85,
        "confidence": "high"
    },
    
    # Tovagliato e carta
    {
        "keywords": ["tovaglioli", "tovagliolo", "salviette", "salvietta"],
        "account_code": "4.1.03",
        "priority": 90,
        "confidence": "high"
    },
    {
        "keywords": ["tovaglie", "tovaglia", "runner", "sottopiatto"],
        "account_code": "4.1.03",
        "priority": 85,
        "confidence": "high"
    },
    {
        "keywords": ["carta", "rotoli", "scottex", "regina", "tissue"],
        "account_code": "4.1.03",
        "priority": 85,
        "confidence": "high"
    },
    {
        "keywords": ["pellicola", "alluminio", "domopak", "cuki"],
        "account_code": "4.1.03",
        "priority": 85,
        "confidence": "high"
    },
    
    # Contenitori e packaging
    {
        "keywords": ["contenitori", "contenitore", "vaschette", "vaschetta", "box"],
        "account_code": "4.1.03",
        "priority": 85,
        "confidence": "high"
    },
    {
        "keywords": ["asporto", "take away", "delivery", "packaging"],
        "account_code": "4.1.03",
        "priority": 85,
        "confidence": "high"
    },
    {
        "keywords": ["sacchetti", "sacchetto", "buste", "busta", "shoppers"],
        "account_code": "4.1.03",
        "priority": 85,
        "confidence": "high"
    },
    
    # Prodotti per pulizia e igiene
    {
        "keywords": ["detergente", "detergenti", "detersivo", "sapone", "sgrassatore"],
        "account_code": "4.1.03",
        "priority": 90,
        "confidence": "high"
    },
    {
        "keywords": ["pulizia", "igienizzante", "disinfettante", "sanificante", "amuchina"],
        "account_code": "4.1.03",
        "priority": 90,
        "confidence": "high"
    },
    {
        "keywords": ["candeggina", "varechina", "cloro", "ipoclorito"],
        "account_code": "4.1.03",
        "priority": 90,
        "confidence": "high"
    },
    {
        "keywords": ["brillantante", "lavastoviglie", "finish", "fairy"],
        "account_code": "4.1.03",
        "priority": 85,
        "confidence": "high"
    },
    {
        "keywords": ["spugne", "spugna", "panni", "panno", "strofinacci"],
        "account_code": "4.1.03",
        "priority": 85,
        "confidence": "high"
    },
    {
        "keywords": ["scope", "scopa", "mocio", "secchio", "pattumiera"],
        "account_code": "4.1.03",
        "priority": 80,
        "confidence": "high"
    },
    {
        "keywords": ["guanti", "mascherine", "camici", "dpi", "protezione"],
        "account_code": "4.1.03",
        "priority": 85,
        "confidence": "high"
    },
    
    # ========== UTENZE (4.2.03) ==========
    
    # Energia elettrica
    {
        "keywords": ["energia elettrica", "corrente elettrica", "fornitura elettrica", "kwh"],
        "account_code": "4.2.03",
        "priority": 98,
        "confidence": "high"
    },
    {
        "keywords": ["enel", "eni", "acea", "a2a", "edison", "iren"],
        "account_code": "4.2.03",
        "priority": 98,
        "confidence": "high"
    },
    {
        "keywords": ["bolletta luce", "bolletta elettricità", "fornitura luce"],
        "account_code": "4.2.03",
        "priority": 98,
        "confidence": "high"
    },
    
    # Gas
    {
        "keywords": ["gas", "metano", "gpl", "gas naturale", "smc"],
        "account_code": "4.2.03",
        "priority": 98,
        "confidence": "high"
    },
    {
        "keywords": ["bolletta gas", "fornitura gas", "riscaldamento"],
        "account_code": "4.2.03",
        "priority": 98,
        "confidence": "high"
    },
    
    # Acqua
    {
        "keywords": ["acqua potabile", "fornitura idrica", "bolletta acqua", "acquedotto"],
        "account_code": "4.2.03",
        "priority": 98,
        "confidence": "high"
    },
    {
        "keywords": ["acea", "metropolitana milanese", "veritas", "hera"],
        "account_code": "4.2.03",
        "priority": 95,
        "confidence": "high"
    },
    
    # Telefono e internet
    {
        "keywords": ["telefono", "telefonia", "fisso", "cellulare", "mobile"],
        "account_code": "4.2.03",
        "priority": 95,
        "confidence": "high"
    },
    {
        "keywords": ["internet", "fibra", "adsl", "wifi", "connessione"],
        "account_code": "4.2.03",
        "priority": 95,
        "confidence": "high"
    },
    {
        "keywords": ["tim", "vodafone", "wind", "tre", "fastweb", "iliad"],
        "account_code": "4.2.03",
        "priority": 95,
        "confidence": "high"
    },
    
    # ========== AFFITTI E LOCAZIONI (4.2.02) ==========
    
    {
        "keywords": ["affitto", "locazione", "canone", "fitto"],
        "account_code": "4.2.02",
        "priority": 98,
        "confidence": "high"
    },
    {
        "keywords": ["immobile", "locale", "capannone", "negozio", "ufficio"],
        "account_code": "4.2.02",
        "priority": 95,
        "confidence": "high"
    },
    {
        "keywords": ["noleggio", "leasing", "rent"],
        "account_code": "4.2.02",
        "priority": 90,
        "confidence": "high"
    },
    
    # ========== CONSULENZE PROFESSIONALI (4.2.05) ==========
    
    {
        "keywords": ["commercialista", "consulente fiscale", "studio associato"],
        "account_code": "4.2.05",
        "priority": 98,
        "confidence": "high"
    },
    {
        "keywords": ["avvocato", "legale", "studio legale", "parcella"],
        "account_code": "4.2.05",
        "priority": 98,
        "confidence": "high"
    },
    {
        "keywords": ["notaio", "notarile", "atto notarile"],
        "account_code": "4.2.05",
        "priority": 98,
        "confidence": "high"
    },
    {
        "keywords": ["consulenza", "consulente", "professionista", "prestazione professionale"],
        "account_code": "4.2.05",
        "priority": 90,
        "confidence": "high"
    },
    
    # ========== MANUTENZIONI E RIPARAZIONI (4.2.04) ==========
    
    {
        "keywords": ["manutenzione", "riparazione", "intervento tecnico", "assistenza tecnica"],
        "account_code": "4.2.04",
        "priority": 95,
        "confidence": "high"
    },
    {
        "keywords": ["idraulico", "elettricista", "falegname", "fabbro"],
        "account_code": "4.2.04",
        "priority": 95,
        "confidence": "high"
    },
    {
        "keywords": ["frigorifero", "forno", "lavastoviglie", "cella frigorifera"],
        "account_code": "4.2.04",
        "priority": 90,
        "confidence": "high"
    },
    {
        "keywords": ["condizionatore", "climatizzatore", "impianto", "caldaia"],
        "account_code": "4.2.04",
        "priority": 90,
        "confidence": "high"
    },
    
    # ========== TRASPORTI E CARBURANTI (4.2.06) ==========
    
    {
        "keywords": ["carburante", "benzina", "gasolio", "diesel", "gpl"],
        "account_code": "4.2.06",
        "priority": 95,
        "confidence": "high"
    },
    {
        "keywords": ["rifornimento", "stazione servizio", "distributore"],
        "account_code": "4.2.06",
        "priority": 95,
        "confidence": "high"
    },
    {
        "keywords": ["autostrada", "pedaggio", "telepass", "viacard"],
        "account_code": "4.2.06",
        "priority": 95,
        "confidence": "high"
    },
    {
        "keywords": ["trasporto", "spedizione", "corriere", "consegna"],
        "account_code": "4.2.06",
        "priority": 90,
        "confidence": "high"
    },
    {
        "keywords": ["bollo auto", "assicurazione auto", "rca"],
        "account_code": "4.2.06",
        "priority": 90,
        "confidence": "high"
    },
]
