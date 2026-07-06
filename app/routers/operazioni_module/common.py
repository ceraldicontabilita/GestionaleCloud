"""
Operazioni Module - Costanti e modelli condivisi.
"""
from datetime import datetime, timezone
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

# Fattura NON pagata: questo modulo usava un campo proprio "pagata" mai letto
# né scritto da nessun'altra parte del gestionale (la fonte di verità reale è
# stato_pagamento/pagato/paid, scritti da fatture_upload.py e prima_nota_module).
# Una fattura confermata pagata da qui restava quindi "da pagare" ovunque
# altro nell'app (Fatture, Dashboard, Prima Nota) — riconciliazione che pareva
# "non fare nulla" perché l'esito non si vedeva da nessun'altra parte.
QUERY_FATTURA_NON_PAGATA = {
    "$and": [
        {"pagato": {"$ne": True}},
        {"stato_pagamento": {"$nin": ["pagata", "paid"]}},
    ]
}


def set_fattura_pagata(extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Campi canonici da scrivere su invoices quando una riconciliazione la salda."""
    now = datetime.now(timezone.utc).isoformat()
    fields = {
        "pagato": True,
        "paid": True,
        "stato_pagamento": "pagata",
        "status": "pagata",
        "data_pagamento": now[:10],
    }
    if extra:
        fields.update(extra)
    return fields


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
