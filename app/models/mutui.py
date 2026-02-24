"""
Schema MongoDB per Collection MUTUI
===================================

Collection: mutui
Database: azienda_erp_db

Struttura documenti mutui con rate e riconciliazione bancaria
"""

from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class RataMutuo(BaseModel):
    """Singola rata del piano di ammortamento"""
    numero_rata: int
    data_scadenza: str  # Formato: DD/MM/YYYY
    importo_totale: float
    quota_capitale: float
    quota_interessi: float
    stato: Literal["Pagata", "Da pagare", "Scaduta"]
    
    # Riconciliazione bancaria
    riconciliata: bool = False
    movimento_bancario_id: Optional[str] = None
    data_pagamento_effettivo: Optional[str] = None
    note_riconciliazione: Optional[str] = None


class MutuoCreate(BaseModel):
    """Schema per creazione mutuo"""
    mutuo_id: str
    nome: str
    tipo_finanziamento: str
    importo_accordato: float
    numero_delibera: str
    banca: str = "BPM - Banca Popolare di Milano"
    iban: Optional[str] = None
    
    data_erogazione: Optional[str] = None
    data_prima_rata: Optional[str] = None
    data_ultima_rata: Optional[str] = None
    
    rate: List[RataMutuo]
    totale_rate: int
    
    rate_pagate: int = 0
    rate_da_pagare: int = 0
    rate_residue_dichiarate: int = 0
    
    totale_pagato_capitale: float = 0.0
    totale_pagato_interessi: float = 0.0
    totale_pagato: float = 0.0
    
    debito_residuo_capitale: float = 0.0
    debito_residuo_interessi: float = 0.0
    debito_residuo_totale: float = 0.0
    
    prossima_data_scadenza: Optional[str] = None
    prossimo_importo: Optional[float] = None
    
    rate_riconciliate: int = 0
    rate_non_riconciliate: int = 0
    percentuale_riconciliazione: float = 0.0
    
    file_piano_ammortamento: Optional[str] = None
    allegati: List[str] = []
    note: Optional[str] = None


class MutuoUpdate(BaseModel):
    """Schema per aggiornamento mutuo"""
    nome: Optional[str] = None
    tipo_finanziamento: Optional[str] = None
    banca: Optional[str] = None
    iban: Optional[str] = None
    note: Optional[str] = None
    file_piano_ammortamento: Optional[str] = None
    allegati: Optional[List[str]] = None


class RiconciliazioneRequest(BaseModel):
    """Request per riconciliazione automatica"""
    data_inizio: Optional[str] = None
    data_fine: Optional[str] = None
    tolleranza_importo: float = 1.0
    tolleranza_giorni: int = 7


class RiconciliazioneManualRequest(BaseModel):
    """Request per riconciliazione manuale singola rata"""
    movimento_id: str
    note: Optional[str] = None
