"""
Stati Unificati per tutto l'ERP.

REGOLA D'ORO: Usare SEMPRE questi enum invece di stringhe hardcoded.
"""
from enum import Enum


class StatoPagamento(str, Enum):
    """
    Stato di pagamento per fatture, scadenze, F24, cedolini.
    """
    DA_PAGARE = "da_pagare"
    IN_SCADENZA = "in_scadenza"      # Scade entro 7 giorni
    SCADUTO = "scaduto"               # Scadenza passata
    PARZIALE = "parziale"             # Pagato parzialmente
    PAGATO = "pagato"
    ANNULLATO = "annullato"
    
    @classmethod
    def is_da_pagare(cls, stato: str) -> bool:
        """Verifica se lo stato indica 'da pagare' (normalizza vecchi stati)."""
        stati_da_pagare = [
            cls.DA_PAGARE.value, cls.IN_SCADENZA.value, cls.SCADUTO.value,
            # Vecchi stati da normalizzare
            "pending", "non_pagata", "to_pay", "DA_PAGARE", "aperto"
        ]
        return stato in stati_da_pagare if stato else True
    
    @classmethod
    def is_pagato(cls, stato: str) -> bool:
        """Verifica se lo stato indica 'pagato' (normalizza vecchi stati)."""
        stati_pagati = [
            cls.PAGATO.value, cls.PARZIALE.value,
            # Vecchi stati da normalizzare
            "paid", "pagata", "Pagata", "Pagato", "PAGATO", "saldato"
        ]
        return stato in stati_pagati if stato else False
    
    @classmethod
    def normalize(cls, stato: str) -> str:
        """Normalizza un vecchio stato al nuovo formato."""
        if not stato:
            return cls.DA_PAGARE.value
        
        stato_lower = stato.lower().strip()
        
        # Mapping vecchi → nuovi
        mapping = {
            "pending": cls.DA_PAGARE.value,
            "non_pagata": cls.DA_PAGARE.value,
            "to_pay": cls.DA_PAGARE.value,
            "aperto": cls.DA_PAGARE.value,
            "paid": cls.PAGATO.value,
            "pagata": cls.PAGATO.value,
            "saldato": cls.PAGATO.value,
            "annullata": cls.ANNULLATO.value,
            "cancelled": cls.ANNULLATO.value,
        }
        
        return mapping.get(stato_lower, stato_lower)


class StatoRiconciliazione(str, Enum):
    """
    Stato di riconciliazione per movimenti banca, assegni, bonifici.
    """
    NON_RICONCILIATO = "non_riconciliato"
    PROPOSTA = "proposta"              # Match suggerito, da confermare
    RICONCILIATO = "riconciliato"
    PARZIALE = "parziale"              # Riconciliato parzialmente
    ERRORE = "errore"                  # Riconciliazione fallita
    
    @classmethod
    def is_riconciliato(cls, stato: str) -> bool:
        """Verifica se riconciliato (normalizza vecchi stati)."""
        stati_ok = [
            cls.RICONCILIATO.value, cls.PARZIALE.value,
            "reconciled", "collegato", "associato", True, "true", "True"
        ]
        return stato in stati_ok if stato else False


class StatoDocumento(str, Enum):
    """
    Stato del ciclo di vita di un documento.
    """
    BOZZA = "bozza"
    ATTIVO = "attivo"
    IN_ELABORAZIONE = "in_elaborazione"
    COMPLETATO = "completato"
    ARCHIVIATO = "archiviato"
    ELIMINATO = "eliminato"


class StatoAssegno(str, Enum):
    """
    Stato specifico per gli assegni.
    """
    VUOTO = "vuoto"
    COMPILATO = "compilato"
    EMESSO = "emesso"
    INCASSATO = "incassato"
    ANNULLATO = "annullato"
    SCADUTO = "scaduto"


class StatoCedolino(str, Enum):
    """
    Stato specifico per i cedolini.
    """
    IMPORTATO = "importato"
    VERIFICATO = "verificato"
    DA_PAGARE = "da_pagare"
    PAGATO = "pagato"
    RICONCILIATO = "riconciliato"


class StatoF24(str, Enum):
    """
    Stato specifico per modelli F24.
    """
    BOZZA = "bozza"
    GENERATO = "generato"
    DA_PAGARE = "da_pagare"
    PAGATO = "pagato"
    ANNULLATO = "annullato"


# ============== HELPER FUNCTIONS ==============

def normalizza_stato_pagamento(stato: str) -> str:
    """Helper per normalizzare stati di pagamento."""
    return StatoPagamento.normalize(stato)


def is_da_pagare(stato: str) -> bool:
    """Helper per verificare se da pagare."""
    return StatoPagamento.is_da_pagare(stato)


def is_pagato(stato: str) -> bool:
    """Helper per verificare se pagato."""
    return StatoPagamento.is_pagato(stato)


def is_riconciliato(stato: str) -> bool:
    """Helper per verificare se riconciliato."""
    return StatoRiconciliazione.is_riconciliato(stato)


# ============== COSTANTI PER QUERY ==============

STATI_DA_PAGARE = [
    StatoPagamento.DA_PAGARE.value,
    StatoPagamento.IN_SCADENZA.value,
    StatoPagamento.SCADUTO.value,
    "pending", "non_pagata", "to_pay", "aperto"
]

STATI_PAGATI = [
    StatoPagamento.PAGATO.value,
    StatoPagamento.PARZIALE.value,
    "paid", "pagata", "Pagata", "Pagato", "saldato"
]

STATI_RICONCILIATI = [
    StatoRiconciliazione.RICONCILIATO.value,
    StatoRiconciliazione.PARZIALE.value,
    "reconciled", "collegato", "associato"
]
