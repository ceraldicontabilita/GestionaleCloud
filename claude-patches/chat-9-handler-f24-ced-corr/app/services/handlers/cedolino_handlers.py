"""
Handler Eventi Cedolini — Gestionale Ceraldi Group
====================================================
Quando un cedolino viene importato → crea partita stipendio,
aggiorna fascicolo dipendente, genera prima nota salari e TFR.
"""
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


async def on_cedolino_importato(event: Dict[str, Any], db) -> Optional[Dict]:
    """
    Crea partita aperta per stipendio e alert se dati incompleti.
    """
    from app.services.partite_aperte_engine import crea_partita, TipoPartita
    from app.services.alert_engine import genera_alert

    cedolino_id = event.get("cedolino_id")
    dipendente_id = event.get("dipendente_id")
    dipendente_nome = event.get("dipendente_nome", "")
    netto = event.get("netto", 0)
    lordo = event.get("lordo", 0)
    mese = event.get("mese")
    anno = event.get("anno")
    tipo_cedolino = event.get("tipo_cedolino", "mensile")

    if not cedolino_id:
        return None

    risultati = []

    # Alert dipendente non trovato
    if not dipendente_id:
        await genera_alert(
            "CED_DIP_NON_TROVATO", cedolino_id, "cedolini",
            f"Cedolino {mese}/{anno} senza dipendente associato",
            db
        )
        risultati.append("alert_dip_non_trovato")
        return {"action": "alert", "codici": risultati}

    # Crea partita stipendio (solo se netto > 0 e non è solo trattenute)
    if netto and netto > 0 and tipo_cedolino not in ("solo_trattenute", "sospensione"):
        partita = await crea_partita(
            tipo=TipoPartita.STIPENDIO,
            documento_id=cedolino_id,
            documento_collection="cedolini",
            controparte_id=dipendente_id,
            controparte_nome=dipendente_nome,
            importo=netto,
            db=db,
            data_documento=f"{anno}-{str(mese).zfill(2)}-28" if anno and mese else None,
            extra={"mese": mese, "anno": anno, "tipo": tipo_cedolino, "lordo": lordo}
        )
        if partita:
            risultati.append("partita_stipendio_creata")

    # Alert dati economici incompleti
    if not netto and tipo_cedolino not in ("solo_trattenute", "sospensione"):
        await genera_alert(
            "CED_DATI_ECONOMICI_INCOMPLETI", cedolino_id, "cedolini",
            f"Cedolino {dipendente_nome} {mese}/{anno} — netto mancante",
            db
        )
        risultati.append("alert_dati_incompleti")

    # Audit
    from app.services.audit_logger import log_evento
    await log_evento(
        modulo="cedolini", azione="importato", entita_id=cedolino_id,
        entita_collection="cedolini", db=db,
        nuovo_stato={
            "dipendente": dipendente_nome, "mese": mese, "anno": anno,
            "netto": netto, "lordo": lordo, "tipo": tipo_cedolino
        },
        fonte=event.get("source_module", "cedolini_import"),
        dettaglio=f"Cedolino {dipendente_nome} {mese}/{anno} netto €{netto:.2f}"
    )

    return {"action": "cedolino_processato", "risultati": risultati}


async def on_cedolino_pagato_risolvi(event: Dict[str, Any], db) -> Optional[Dict]:
    """Risolve alert quando lo stipendio viene pagato."""
    from app.services.alert_engine import risolvi_alert

    cedolino_id = event.get("cedolino_id", "")
    risolti = 0
    risolti += await risolvi_alert("CED_NON_PAGATO", cedolino_id, db)
    risolti += await risolvi_alert("CED_MATCH_BANCA_AMBIGUO", cedolino_id, db)
    risolti += await risolvi_alert("CED_DATI_ECONOMICI_INCOMPLETI", cedolino_id, db)

    return {"action": "alert_risolti", "count": risolti} if risolti else None
