"""
Nomi campi standardizzati per tutto l'ERP.
USARE SEMPRE QUESTE COSTANTI.
"""


class FieldNames:
    """Nomi campi standardizzati."""
    
    # === IMPORTI (usare sempre questi) ===
    IMPORTO = "importo"           # Per movimenti singoli
    TOTALE = "total_amount"       # Per totali documento
    IVA = "iva"                   # Importo IVA
    IMPONIBILE = "imponibile"     # Importo imponibile
    NETTO = "netto"               # Netto a pagare
    LORDO = "lordo"               # Lordo
    
    # === DATE (usare sempre questi) ===
    DATA_DOCUMENTO = "data_documento"    # Data del documento
    DATA_RICEZIONE = "data_ricezione"    # Data ricezione SDI
    DATA_SCADENZA = "data_scadenza"      # Scadenza pagamento
    DATA_PAGAMENTO = "data_pagamento"    # Data effettivo pagamento
    DATA_EMISSIONE = "data_emissione"    # Data emissione
    CREATED_AT = "created_at"            # Timestamp creazione
    UPDATED_AT = "updated_at"            # Timestamp modifica
    
    # === FORNITORE (usare sempre questi) ===
    FORNITORE_NOME = "supplier_name"     # Ragione sociale
    FORNITORE_PIVA = "supplier_vat"      # P.IVA
    FORNITORE_CF = "supplier_cf"         # Codice fiscale
    FORNITORE_ID = "supplier_id"         # ID interno
    
    # === DIPENDENTE (usare sempre questi) ===
    DIPENDENTE_NOME = "dipendente_nome"  # Nome completo
    DIPENDENTE_ID = "dipendente_id"      # ID interno
    DIPENDENTE_CF = "codice_fiscale"     # Codice fiscale
    
    # === DOCUMENTO (usare sempre questi) ===
    NUMERO_DOCUMENTO = "numero_documento"
    NUMERO_FATTURA = "invoice_number"
    TIPO_DOCUMENTO = "tipo_documento"    # TD01, TD04, etc.
    STATO = "status"                     # Stato del documento
    
    # === BANCA (usare sempre questi) ===
    IBAN = "iban"
    BIC = "bic"
    BANCA_NOME = "banca_nome"
    NUMERO_CONTO = "numero_conto"


# Mapping per normalizzare campi vecchi -> nuovi
FIELD_NORMALIZER = {
    # === IMPORTI ===
    "totale": "total_amount",
    "importo_totale": "total_amount",
    "total": "total_amount",
    "amount": "importo",
    "totale_importo": "total_amount",
    "totale_fattura": "total_amount",
    
    # === DATE ===
    "data": "data_documento",
    "date": "data_documento",
    "invoice_date": "data_documento",
    "data_fattura": "data_documento",
    "data_registrazione": "data_documento",
    "payment_due_date": "data_scadenza",
    "scadenza": "data_scadenza",
    "data_pagato": "data_pagamento",
    
    # === FORNITORE ===
    "fornitore": "supplier_name",
    "ragione_sociale": "supplier_name",
    "fornitore_nome": "supplier_name",
    "nome_fornitore": "supplier_name",
    "denominazione": "supplier_name",
    "partita_iva": "supplier_vat",
    "fornitore_piva": "supplier_vat",
    "piva": "supplier_vat",
    "p_iva": "supplier_vat",
    "codice_fiscale_fornitore": "supplier_cf",
    
    # === DIPENDENTE ===
    "employee_name": "dipendente_nome",
    "nome_dipendente": "dipendente_nome",
    "employee_id": "dipendente_id",
    
    # === DOCUMENTO ===
    "numero": "numero_documento",
    "num_fattura": "invoice_number",
    "fattura_numero": "invoice_number",
    "numero_fatt": "invoice_number",
    "state": "status",
    "stato": "status",
    "stato_pagamento": "status",
}


# Mapping inverso per retrocompatibilità in output
FIELD_DENORMALIZER = {
    "total_amount": ["totale", "importo_totale"],
    "data_documento": ["data", "invoice_date", "data_fattura"],
    "supplier_name": ["fornitore", "ragione_sociale"],
    "supplier_vat": ["partita_iva", "piva"],
}


def normalize_field_name(field: str) -> str:
    """
    Normalizza un nome campo al formato standard.
    
    Args:
        field: Nome campo originale
        
    Returns:
        Nome campo normalizzato
    """
    return FIELD_NORMALIZER.get(field, field)


def normalize_document(doc: dict, keep_original: bool = False) -> dict:
    """
    Normalizza tutti i nomi campi in un documento.
    
    Args:
        doc: Documento originale
        keep_original: Se True, mantiene anche i campi originali
        
    Returns:
        Documento con campi normalizzati
    """
    if not doc:
        return doc
    
    normalized = {}
    for key, value in doc.items():
        new_key = FIELD_NORMALIZER.get(key, key)
        normalized[new_key] = value
        
        # Mantieni anche il campo originale se richiesto
        if keep_original and new_key != key:
            normalized[key] = value
    
    return normalized


def denormalize_document(doc: dict) -> dict:
    """
    Aggiunge campi con nomi vecchi per retrocompatibilità.
    
    Args:
        doc: Documento con campi normalizzati
        
    Returns:
        Documento con anche campi vecchi
    """
    if not doc:
        return doc
    
    denormalized = dict(doc)
    for new_field, old_fields in FIELD_DENORMALIZER.items():
        if new_field in denormalized:
            for old_field in old_fields:
                denormalized[old_field] = denormalized[new_field]
    
    return denormalized


# === HELPER PER QUERY ===

def get_date_query(anno: int, mese: int = None) -> dict:
    """
    Genera query MongoDB per filtrare per anno/mese.
    Supporta diversi formati di data.
    
    Args:
        anno: Anno di riferimento
        mese: Mese (1-12), opzionale
        
    Returns:
        Query MongoDB
    """
    if mese:
        start = f"{anno}-{mese:02d}-01"
        # Calcola ultimo giorno del mese
        import calendar
        last_day = calendar.monthrange(anno, mese)[1]
        end = f"{anno}-{mese:02d}-{last_day}"
    else:
        start = f"{anno}-01-01"
        end = f"{anno}-12-31"
    
    return {
        "$or": [
            {"data_documento": {"$gte": start, "$lte": end}},
            {"data": {"$gte": start, "$lte": end}},
            {"invoice_date": {"$gte": start, "$lte": end}},
            {"created_at": {"$gte": start, "$lte": end}},
        ]
    }


def get_fornitore_query(fornitore: str) -> dict:
    """
    Genera query per cercare fornitore supportando diversi campi.
    
    Args:
        fornitore: Nome o parte del nome fornitore
        
    Returns:
        Query MongoDB
    """
    pattern = {"$regex": fornitore, "$options": "i"}
    return {
        "$or": [
            {"supplier_name": pattern},
            {"fornitore": pattern},
            {"ragione_sociale": pattern},
            {"fornitore_nome": pattern},
        ]
    }
