"""
Operazioni Module - Costanti e modelli condivisi.
"""
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)

# Collections
COL_FATTURE = "invoices"
COL_FORNITORI = "fornitori"
COL_EMAIL_DOCS = "documents_inbox"
COL_PRIMA_NOTA_BANCA = "prima_nota_banca"
COL_PRIMA_NOTA_CASSA = "prima_nota_cassa"
COL_ESTRATTO_CONTO = "estratto_conto_movimenti"


class ConfermaBatchRequest(BaseModel):
    operazioni: List[Dict[str, Any]]


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
