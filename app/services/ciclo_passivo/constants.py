"""
Costanti per il modulo Ciclo Passivo.
"""

# ==================== COLLECTIONS ====================
FATTURE_COLLECTION = "invoices"
FORNITORI_COLLECTION = "fornitori"
RIGHE_COLLECTION = "dettaglio_righe_fatture"
MAGAZZINO_COLLECTION = "warehouse_stocks"
MOVIMENTI_MAG_COLLECTION = "warehouse_movements"
LOTTI_COLLECTION = "haccp_lotti"
PRIMA_NOTA_CASSA_COLLECTION = "prima_nota_cassa"
PRIMA_NOTA_BANCA_COLLECTION = "prima_nota_banca"
PRIMA_NOTA_COLLECTION = "prima_nota_banca"  # Alias
SCADENZIARIO_COLLECTION = "scadenziario_fornitori"
BANK_TRANSACTIONS_COLLECTION = "bank_transactions"
RICONCILIAZIONI_COLLECTION = "riconciliazioni"
CENTRI_COSTO_COLLECTION = "centri_costo"

# ==================== MAPPATURE METODI PAGAMENTO ====================
METODI_PAGAMENTO = {
    "MP01": {"desc": "Contanti", "tipo": "contanti", "giorni_default": 0},
    "MP02": {"desc": "Assegno", "tipo": "assegno", "giorni_default": 0},
    "MP03": {"desc": "Assegno circolare", "tipo": "assegno", "giorni_default": 0},
    "MP04": {"desc": "Contanti c/o Tesoreria", "tipo": "contanti", "giorni_default": 0},
    "MP05": {"desc": "Bonifico", "tipo": "bonifico", "giorni_default": 30},
    "MP06": {"desc": "Vaglia cambiario", "tipo": "altro", "giorni_default": 30},
    "MP07": {"desc": "Bollettino bancario", "tipo": "bonifico", "giorni_default": 30},
    "MP08": {"desc": "Carta di pagamento", "tipo": "carta", "giorni_default": 0},
    "MP09": {"desc": "RID", "tipo": "rid", "giorni_default": 30},
    "MP10": {"desc": "RID utenze", "tipo": "rid", "giorni_default": 30},
    "MP11": {"desc": "RID veloce", "tipo": "rid", "giorni_default": 30},
    "MP12": {"desc": "RIBA", "tipo": "riba", "giorni_default": 60},
    "MP13": {"desc": "MAV", "tipo": "mav", "giorni_default": 30},
    "MP14": {"desc": "Quietanza erario", "tipo": "altro", "giorni_default": 0},
    "MP15": {"desc": "Giroconto", "tipo": "giroconto", "giorni_default": 0},
    "MP16": {"desc": "Domiciliazione bancaria", "tipo": "rid", "giorni_default": 30},
    "MP17": {"desc": "Domiciliazione postale", "tipo": "rid", "giorni_default": 30},
    "MP18": {"desc": "Bollettino di c/c postale", "tipo": "postale", "giorni_default": 30},
    "MP19": {"desc": "SEPA Direct Debit", "tipo": "sepa", "giorni_default": 30},
    "MP20": {"desc": "SEPA Direct Debit CORE", "tipo": "sepa", "giorni_default": 30},
    "MP21": {"desc": "SEPA Direct Debit B2B", "tipo": "sepa", "giorni_default": 30},
    "MP22": {"desc": "Trattenuta su somme", "tipo": "altro", "giorni_default": 0},
    "MP23": {"desc": "PagoPA", "tipo": "pagopa", "giorni_default": 0},
}

# Categorie fornitore -> Centro di costo
CATEGORIE_CENTRO_COSTO = {
    "alimentari": "FOOD",
    "bevande": "BEVERAGE",
    "beverage": "BEVERAGE",
    "food": "FOOD",
    "utenze": "UTILITIES",
    "energia": "UTILITIES",
    "gas": "UTILITIES",
    "acqua": "UTILITIES",
    "telefonia": "UTILITIES",
    "pulizie": "SERVICES",
    "manutenzione": "MAINTENANCE",
    "affitto": "RENT",
    "locazione": "RENT",
    "personale": "STAFF",
    "consulenza": "PROFESSIONAL",
    "marketing": "MARKETING",
    "default": "GENERAL"
}

# ==================== CONTI CONTABILI ====================
CONTI_DARE = {
    "merci": "05.01.01",
    "servizi": "05.02.01",
    "utenze": "05.03.01",
    "affitti": "05.04.01",
    "ammortamenti": "05.05.01",
    "personale": "05.06.01",
    "imposte": "05.07.01",
    "diversi": "05.08.01",
    "iva_credito": "02.04.01"
}

CONTI_AVERE = {
    "fornitori": "03.01.01",
    "banca": "01.02.01",
    "cassa": "01.01.01",
    "iva_debito": "03.04.01"
}
