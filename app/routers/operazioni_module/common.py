"""
Operazioni Module - Costanti e modelli condivisi.
"""
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)

# Collections
COL_FATTURE = "invoices"
COL_FORNITORI = "suppliers"
COL_EMAIL_DOCS = "documents_inbox"
COL_PRIMA_NOTA_BANCA = "prima_nota_banca"
COL_PRIMA_NOTA_CASSA = "prima_nota_cassa"
COL_ESTRATTO_CONTO = "estratto_conto_movimenti"


class ConfermaBatchRequest(BaseModel):
    operazioni: List[Dict[str, Any]]


class ConfermaArubaRequest(BaseModel):
    message_id: str
    metodo_pagamento: str
    note: Optional[str] = None
    tipo: str = "fattura"
    importo_override: Optional[float] = None
    fornitore_override: Optional[str] = None
    piva_override: Optional[str] = None
    crea_movimento_prima_nota: bool = False
    crea_scadenza: bool = False


class RifiutaArubaRequest(BaseModel):
    message_id: str
    motivo: Optional[str] = None


class RiconciliaManuale(BaseModel):
    movimento_id: str
    tipo_operazione: str
    entita_id: str
    note: Optional[str] = None


class RiconciliaCartaRequest(BaseModel):
    transazione_id: str
    tipo: str
    entita_id: str
    note: Optional[str] = None
