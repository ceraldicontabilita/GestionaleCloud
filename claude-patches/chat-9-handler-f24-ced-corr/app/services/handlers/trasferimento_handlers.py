"""
Handler Eventi Trasferimenti — Gestionale Ceraldi Group
========================================================
Quando viene creato un trasferimento cassa→banca o banca→cassa,
il sistema crea il movimento speculare sull'altro lato.
"""
import logging
import uuid
from typing import Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def on_trasferimento_crea_lato_opposto(event: Dict[str, Any], db) -> Optional[Dict]:
    """
    Crea il movimento speculare per un trasferimento interno.
    Se il movimento è in cassa (uscita versamento), crea l'entrata in banca.
    Se il movimento è in banca (prelievo), crea l'entrata in cassa.
    """
    movimento_id = event.get("movimento_id")
    origine = event.get("origine")  # "cassa" o "banca"
    importo = event.get("importo", 0)
    data = event.get("data", "")
    descrizione = event.get("descrizione", "")

    if not movimento_id or not importo or not origine:
        return None

    # Determina collection di destinazione
    if origine == "cassa":
        dest_coll = "prima_nota_banca"
        dest_tipo = "entrata"
        dest_desc = f"Versamento contanti da cassa - {data}"
    elif origine == "banca":
        dest_coll = "prima_nota_cassa"
        dest_tipo = "entrata"
        dest_desc = f"Prelievo banca per cassa - {data}"
    else:
        return None

    # Idempotenza: controlla se il lato opposto esiste già
    existing = await db[dest_coll].find_one({
        "trasferimento_collegato_id": movimento_id
    })
    if existing:
        return {"action": "lato_opposto_esistente", "id": existing.get("id")}

    lato_opposto_id = str(uuid.uuid4())
    await db[dest_coll].insert_one({
        "id": lato_opposto_id,
        "data": data,
        "descrizione": dest_desc,
        "causale": "trasferimento_interno",
        "importo": round(abs(importo), 2),
        "tipo": dest_tipo,
        "categoria": "trasferimento_interno",
        "stato": "confermato",
        "provvisorio": False,
        "trasferimento_collegato_id": movimento_id,
        "trasferimento_origine": origine,
        "source": "auto_trasferimento",
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    # Aggiorna anche il movimento originale con il collegamento
    orig_coll = "prima_nota_cassa" if origine == "cassa" else "prima_nota_banca"
    await db[orig_coll].update_one(
        {"id": movimento_id},
        {"$set": {"trasferimento_collegato_id": lato_opposto_id}}
    )

    # Risolvi alert trasferimento incompleto
    from app.services.alert_engine import risolvi_alert
    await risolvi_alert("BNK_TRASFERIMENTO_INCOMPLETO", movimento_id, db)
    await risolvi_alert("CAS_DIFFERENZA_SALDO", movimento_id, db)

    # Audit
    from app.services.audit_logger import log_evento
    await log_evento(
        modulo="trasferimenti", azione="lato_opposto_creato",
        entita_id=lato_opposto_id,
        entita_collection=dest_coll, db=db,
        nuovo_stato={"importo": importo, "origine": origine, "collegato_a": movimento_id},
        fonte="auto_trasferimento",
        dettaglio=f"Trasferimento {origine}→{'banca' if origine == 'cassa' else 'cassa'} €{importo:.2f}"
    )

    return {"action": "lato_opposto_creato", "id": lato_opposto_id, "collection": dest_coll}
