"""
Handler Eventi F24 — Gestionale Ceraldi Group
===============================================
Quando un F24 viene acquisito → crea partita aperta tipo F24.
Quando viene pagato/riconciliato → risolve alert.
"""
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


async def on_f24_acquisito_crea_partita(event: Dict[str, Any], db) -> Optional[Dict]:
    """Crea partita aperta per F24 acquisito."""
    from app.services.partite_aperte_engine import crea_partita, TipoPartita

    f24_id = event.get("f24_id")
    importo = event.get("importo_totale", 0)
    data_scadenza = event.get("data_scadenza")
    periodo = event.get("periodo", "")
    codice_tributo = event.get("codice_tributo", "")

    if not f24_id or not importo:
        return None

    partita = await crea_partita(
        tipo=TipoPartita.F24,
        documento_id=f24_id,
        documento_collection="f24_unificato",
        controparte_id="agenzia_entrate",
        controparte_nome=f"F24 {codice_tributo} {periodo}",
        importo=abs(importo),
        db=db,
        data_scadenza=data_scadenza,
        data_documento=event.get("data_acquisizione"),
        extra={"codice_tributo": codice_tributo, "periodo": periodo}
    )

    # Alert se scadenza vicina
    if data_scadenza:
        from datetime import datetime
        try:
            scad = datetime.fromisoformat(data_scadenza)
            diff = (scad - datetime.now()).days
            if diff <= 5:
                from app.services.alert_engine import genera_alert
                codice = "F24_SCADUTO" if diff < 0 else "F24_NON_PAGATO"
                await genera_alert(
                    codice, f24_id, "f24_unificato",
                    f"F24 {codice_tributo} {periodo} — scadenza {'superata' if diff < 0 else f'tra {diff} giorni'}",
                    db
                )
        except (ValueError, TypeError):
            pass

    # Audit
    from app.services.audit_logger import log_evento
    await log_evento(
        modulo="f24", azione="acquisito", entita_id=f24_id,
        entita_collection="f24_unificato", db=db,
        nuovo_stato={"importo": importo, "periodo": periodo, "codice_tributo": codice_tributo},
        fonte=event.get("source_module", "f24_import"),
        dettaglio=f"F24 {codice_tributo} {periodo} €{importo:.2f}"
    )

    return {"action": "partita_creata", "partita_id": partita["id"] if partita else None}


async def on_f24_pagato_risolvi(event: Dict[str, Any], db) -> Optional[Dict]:
    """Risolve alert quando F24 viene pagato."""
    from app.services.alert_engine import risolvi_alert

    f24_id = event.get("f24_id", "")
    risolti = 0
    risolti += await risolvi_alert("F24_NON_PAGATO", f24_id, db)
    risolti += await risolvi_alert("F24_SCADUTO", f24_id, db)
    risolti += await risolvi_alert("F24_ATTESO_NON_ACQUISITO", f24_id, db)

    return {"action": "alert_risolti", "count": risolti} if risolti else None
