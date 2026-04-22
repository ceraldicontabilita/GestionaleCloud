"""
Handler Eventi Corrispettivi — Gestionale Ceraldi Group
========================================================
Quando un corrispettivo viene registrato:
- Quota contanti → entrata in cassa
- Quota POS → partita aperta POS attesa in banca
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
    from app.services.partite_aperte_engine import crea_partita, TipoPartita

    corr_id = event.get("corrispettivo_id")
    data = event.get("data", "")
    totale = event.get("totale", 0)
    contanti = event.get("contanti", 0)
    elettronico = event.get("elettronico", 0)

    if not corr_id or not totale:
        return None

    risultati = []

    # Quota contanti → entrata in cassa (idempotente)
    if contanti and contanti > 0:
        existing = await db["prima_nota_cassa"].find_one({
            "corrispettivo_id": corr_id,
            "tipo": "entrata",
            "causale": "corrispettivi_contanti"
        })
        if not existing:
            movimento_id = str(uuid.uuid4())
            await db["prima_nota_cassa"].insert_one({
                "id": movimento_id,
                "data": data,
                "descrizione": f"Corrispettivi contanti {data}",
                "causale": "corrispettivi_contanti",
                "importo": round(contanti, 2),
                "tipo": "entrata",
                "categoria": "corrispettivi",
                "stato": "confermato",
                "provvisorio": False,
                "corrispettivo_id": corr_id,
                "source": "auto_corrispettivo",
                "created_at": datetime.now(timezone.utc).isoformat()
            })
            risultati.append("cassa_contanti_creata")
        else:
            risultati.append("cassa_contanti_esistente")

    # Quota POS → partita aperta per riconciliazione banca
    if elettronico and elettronico > 0:
        partita = await crea_partita(
            tipo=TipoPartita.POS_ATTESO,
            documento_id=corr_id,
            documento_collection="corrispettivi",
            controparte_id="pos_gateway",
            controparte_nome=f"POS corrispettivi {data}",
            importo=round(elettronico, 2),
            db=db,
            data_scadenza=data,  # accredito atteso stesso giorno o giorno dopo
            data_documento=data,
            extra={"tipo": "accredito_pos", "totale_corrispettivo": totale}
        )
        if partita:
            risultati.append("partita_pos_creata")

    # Audit
    from app.services.audit_logger import log_evento
    await log_evento(
        modulo="corrispettivi", azione="registrato", entita_id=corr_id,
        entita_collection="corrispettivi", db=db,
        nuovo_stato={"totale": totale, "contanti": contanti, "elettronico": elettronico},
        fonte=event.get("source_module", "corrispettivi"),
        dettaglio=f"Corrispettivo {data}: €{totale:.2f} (cont.€{contanti:.2f} + POS €{elettronico:.2f})"
    )

    return {"action": "corrispettivo_processato", "risultati": risultati}
