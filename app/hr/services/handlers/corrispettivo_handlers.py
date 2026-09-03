"""
Handler Eventi Corrispettivi — Gestionale Ceraldi Group
========================================================
NOTA: La creazione dei movimenti prima nota è gestita direttamente
da corrispettivi.py (_crea_movimenti_prima_nota) con logica dare/avere:
  - DARE  = totale corrispettivo (entrata cassa)
  - AVERE = quota elettronica/POS (uscita cassa → banca)
  - Saldo cassa netto = contanti (differenza)
Questo handler NON deve creare movimenti prima nota per evitare duplicati.
"""
import logging
import uuid
from typing import Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def on_corrispettivo_split(event: Dict[str, Any], db) -> Optional[Dict]:
    """
    Splitta il corrispettivo in quota contanti (→ cassa) e quota POS (→ partita).
    """
    from app.hr.services.partite_aperte_engine import crea_partita, TipoPartita

    corr_id = event.get("corrispettivo_id")
    data = event.get("data", "")
    totale = event.get("totale", 0)
    contanti = event.get("contanti", 0)
    elettronico = event.get("elettronico", 0)

    if not corr_id or not totale:
        return None

    risultati = []
    # I movimenti prima nota (dare/avere) sono creati direttamente da corrispettivi.py
    # Questo handler si limita al solo audit log per evitare duplicati.

    # Audit
    from app.hr.services.audit_logger import log_evento
    await log_evento(
        modulo="corrispettivi", azione="registrato", entita_id=corr_id,
        entita_collection="corrispettivi", db=db,
        nuovo_stato={"totale": totale, "contanti": contanti, "elettronico": elettronico},
        fonte=event.get("source_module", "corrispettivi"),
        dettaglio=f"Corrispettivo {data}: €{totale:.2f} (cont.€{contanti:.2f} + POS €{elettronico:.2f})"
    )

    return {"action": "corrispettivo_processato", "risultati": risultati}
