"""
Field Normalizer - Normalizza campi MongoDB con nomi inconsistenti.
Gestisce i vari formati legacy e li converte in formato standard.
"""
from typing import Dict, Any, Optional, List
from datetime import datetime


class FieldNormalizer:
    """
    Normalizza documenti MongoDB con campi inconsistenti.
    """
    
    # === MAPPING CAMPI FATTURE ===
    FATTURA_FIELDS = {
        # numero documento
        "numero_documento": ["numero_documento", "invoice_number", "numero_fattura", "numero", "doc_number"],
        # data documento  
        "data_documento": ["data_documento", "invoice_date", "data_fattura", "data", "date"],
        # importo totale
        "importo_totale": ["importo_totale", "total_amount", "totale", "importo", "amount"],
        # imponibile
        "imponibile": ["imponibile", "taxable_amount", "base_imponibile", "netto"],
        # IVA
        "iva": ["iva", "vat_amount", "imposta", "tax"],
        # fornitore
        "fornitore_ragione_sociale": ["fornitore_ragione_sociale", "supplier_name", "fornitore_nome", "fornitore", "ragione_sociale"],
        "fornitore_partita_iva": ["fornitore_partita_iva", "supplier_vat", "fornitore_piva", "partita_iva", "p_iva"],
        "fornitore_id": ["fornitore_id", "supplier_id", "id_fornitore"],
        # stato
        "stato": ["stato", "status", "stato_pagamento", "payment_status"],
        # pagamento
        "pagato": ["pagato", "paid", "is_paid"],
        "data_pagamento": ["data_pagamento", "payment_date", "paid_date"],
        "metodo_pagamento": ["metodo_pagamento", "payment_method", "metodo"],
    }
    
    # === MAPPING CAMPI DIPENDENTI ===
    DIPENDENTE_FIELDS = {
        "nome": ["nome", "first_name", "firstname"],
        "cognome": ["cognome", "last_name", "lastname", "surname"],
        "codice_fiscale": ["codice_fiscale", "fiscal_code", "cf", "tax_code"],
        "data_nascita": ["data_nascita", "birth_date", "birthdate", "nato_il"],
        "data_assunzione": ["data_assunzione", "hire_date", "assunto_il", "start_date"],
        "stipendio_lordo": ["stipendio_lordo", "gross_salary", "lordo", "ral"],
        "livello": ["livello", "level", "livello_contrattuale"],
        "mansione": ["mansione", "role", "job_title", "ruolo"],
        "reparto": ["reparto", "department", "settore"],
        "in_carico": ["in_carico", "active", "attivo", "is_active"],
    }
    
    # === MAPPING CAMPI MOVIMENTI BANCA ===
    MOVIMENTO_BANCA_FIELDS = {
        "data": ["data", "date", "data_operazione", "data_movimento"],
        "data_valuta": ["data_valuta", "value_date", "valuta"],
        "descrizione": ["descrizione", "description", "causale", "note"],
        "importo": ["importo", "amount", "valore"],
        "tipo": ["tipo", "type", "tipo_movimento"],
        "dare": ["dare", "debit", "uscita", "addebito"],
        "avere": ["avere", "credit", "entrata", "accredito"],
        "saldo": ["saldo", "balance", "saldo_progressivo"],
    }
    
    # === MAPPING CAMPI FORNITORI ===
    FORNITORE_FIELDS = {
        "ragione_sociale": ["ragione_sociale", "name", "nome", "denominazione"],
        "partita_iva": ["partita_iva", "vat", "p_iva", "piva"],
        "codice_fiscale": ["codice_fiscale", "fiscal_code", "cf"],
        "indirizzo": ["indirizzo", "address", "sede"],
        "cap": ["cap", "zip_code", "postal_code"],
        "citta": ["citta", "city", "localita"],
        "provincia": ["provincia", "province", "prov"],
        "email": ["email", "mail", "pec"],
        "telefono": ["telefono", "phone", "tel"],
        "iban": ["iban", "bank_account"],
    }
    
    @classmethod
    def normalize_document(cls, doc: Dict[str, Any], field_mapping: Dict[str, List[str]]) -> Dict[str, Any]:
        """
        Normalizza un documento usando il mapping specificato.
        
        Args:
            doc: Documento originale
            field_mapping: Mapping campo_standard -> [varianti]
            
        Returns:
            Documento normalizzato
        """
        if not doc:
            return {}
            
        normalized = {}
        used_keys = set()
        
        for standard_field, variants in field_mapping.items():
            value = None
            for variant in variants:
                if variant in doc and doc[variant] is not None:
                    value = doc[variant]
                    used_keys.add(variant)
                    break
            normalized[standard_field] = value
        
        # Copia campi non mappati (come _id, created_at, etc.)
        for key, value in doc.items():
            if key not in used_keys and key not in normalized:
                if key != "_id":  # Escludi sempre _id
                    normalized[key] = value
                    
        return normalized
    
    @classmethod
    def normalize_fattura(cls, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Normalizza un documento fattura."""
        normalized = cls.normalize_document(doc, cls.FATTURA_FIELDS)
        
        # Assicura che l'ID sia presente
        if not normalized.get("id"):
            normalized["id"] = str(doc.get("_id", "")) or doc.get("id")
            
        # Estrai anno dalla data se presente
        if normalized.get("data_documento") and not normalized.get("anno"):
            try:
                data = normalized["data_documento"]
                if isinstance(data, str):
                    normalized["anno"] = int(data[:4])
                elif isinstance(data, datetime):
                    normalized["anno"] = data.year
            except:
                pass
                
        return normalized
    
    @classmethod
    def normalize_dipendente(cls, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Normalizza un documento dipendente."""
        normalized = cls.normalize_document(doc, cls.DIPENDENTE_FIELDS)
        
        if not normalized.get("id"):
            normalized["id"] = str(doc.get("_id", "")) or doc.get("id")
            
        # Nome completo
        if normalized.get("nome") and normalized.get("cognome"):
            normalized["nome_completo"] = f"{normalized['nome']} {normalized['cognome']}"
            
        return normalized
    
    @classmethod
    def normalize_movimento_banca(cls, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Normalizza un movimento bancario."""
        normalized = cls.normalize_document(doc, cls.MOVIMENTO_BANCA_FIELDS)
        
        if not normalized.get("id"):
            normalized["id"] = str(doc.get("_id", "")) or doc.get("id")
            
        # Calcola dare/avere da importo se mancanti
        importo = normalized.get("importo", 0)
        if importo and not normalized.get("dare") and not normalized.get("avere"):
            if importo < 0:
                normalized["dare"] = abs(importo)
                normalized["avere"] = 0
            else:
                normalized["dare"] = 0
                normalized["avere"] = importo
                
        return normalized
    
    @classmethod
    def normalize_fornitore(cls, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Normalizza un documento fornitore."""
        normalized = cls.normalize_document(doc, cls.FORNITORE_FIELDS)
        
        if not normalized.get("id"):
            normalized["id"] = str(doc.get("_id", "")) or doc.get("id")
            
        return normalized
    
    @classmethod
    def normalize_list(cls, docs: List[Dict[str, Any]], normalizer_func) -> List[Dict[str, Any]]:
        """
        Normalizza una lista di documenti.
        
        Args:
            docs: Lista documenti
            normalizer_func: Funzione di normalizzazione (es. normalize_fattura)
            
        Returns:
            Lista documenti normalizzati
        """
        return [normalizer_func(doc) for doc in docs if doc]


# Funzioni helper per uso diretto
def normalize_fattura(doc: Dict[str, Any]) -> Dict[str, Any]:
    return FieldNormalizer.normalize_fattura(doc)

def normalize_dipendente(doc: Dict[str, Any]) -> Dict[str, Any]:
    return FieldNormalizer.normalize_dipendente(doc)

def normalize_movimento_banca(doc: Dict[str, Any]) -> Dict[str, Any]:
    return FieldNormalizer.normalize_movimento_banca(doc)

def normalize_fornitore(doc: Dict[str, Any]) -> Dict[str, Any]:
    return FieldNormalizer.normalize_fornitore(doc)
