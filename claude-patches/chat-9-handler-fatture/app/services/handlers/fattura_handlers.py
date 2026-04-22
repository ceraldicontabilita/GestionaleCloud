"""
Handler Eventi Fatture — Gestionale Ceraldi Group
===================================================
Handler che si attivano quando una fattura viene creata o aggiornata.
Registrati nell'event bus per il tipo "fattura.created".

Questi handler AGGIUNGONO funzionalità relazionali senza modificare
il flusso esistente in import_xml.py (che già fa auto-routing,
scadenziario e magazzino).

Cosa aggiungono:
1. Creazione partita aperta materializzata
2. Alert strutturati (MP mancante, IBAN mancante, fornitore nuovo)
3. Audit log dell'operazione
4. Risoluzione alert quando la fattura viene pagata
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# ============================================================
# HANDLER 1: Crea partita aperta da fattura
# ============================================================
async def on_fattura_created_crea_partita(event: Dict[str, Any], db) -> Optional[Dict]:
    """
    Quando arriva una fattura, crea una partita aperta nel scadenziario
    materializzato. Le note credito TD04 creano partite con importo negativo.
    """
    from app.services.partite_aperte_engine import crea_partita, TipoPartita

    fattura_id = event.get("fattura_id")
    tipo_doc = event.get("tipo_documento", "TD01")
    importo = event.get("importo_totale", 0)
    fornitore_id = event.get("fornitore_id")
    fornitore_nome = event.get("fornitore_ragione_sociale", "")
    data_doc = event.get("data_documento", "")
    data_scadenza = event.get("data_scadenza")  # può essere None
    metodo = event.get("metodo_pagamento", "")
    gia_pagata = event.get("pagato", False)

    if not fattura_id or not importo:
        return None

    # Se la fattura è già stata auto-confermata (contanti/bonifico con MP noto),
    # la partita nasce già chiusa — ma la creiamo lo stesso per storico
    if gia_pagata:
        logger.debug(f"Fattura {fattura_id} già pagata, skip partita aperta")
        return {"action": "skip", "reason": "già pagata"}

    # Note credito → importo negativo, tipo diverso
    if tipo_doc in ("TD04", "TD08"):
        tipo_partita = "nota_credito"
        importo = -abs(importo)
    else:
        tipo_partita = TipoPartita.FATTURA_FORNITORE

    partita = await crea_partita(
        tipo=tipo_partita,
        documento_id=fattura_id,
        documento_collection="invoices",
        controparte_id=fornitore_id or "",
        controparte_nome=fornitore_nome,
        importo=abs(importo),  # residuo sempre positivo
        db=db,
        data_scadenza=data_scadenza,
        data_documento=data_doc,
        extra={
            "tipo_documento": tipo_doc,
            "metodo_pagamento": metodo,
            "importo_con_segno": importo
        }
    )

    if partita:
        return {"action": "partita_creata", "partita_id": partita["id"]}
    return {"action": "partita_gia_esistente"}


# ============================================================
# HANDLER 2: Genera alert per fornitore incompleto
# ============================================================
async def on_fattura_created_alert_fornitore(event: Dict[str, Any], db) -> Optional[Dict]:
    """
    Genera alert strutturati se il fornitore ha dati incompleti:
    - FORN_MP_MANCANTE: metodo pagamento non definito
    - FORN_IBAN_MANCANTE: metodo bancario ma senza IBAN
    - FORN_NUOVO_INCOMPLETO: fornitore creato automaticamente
    """
    from app.services.alert_engine import genera_alert

    fornitore_id = event.get("fornitore_id", "")
    fornitore_nome = event.get("fornitore_ragione_sociale", "")
    metodo = (event.get("metodo_pagamento", "") or "").lower()
    fornitore_nuovo = event.get("fornitore_nuovo", False)
    fornitore_iban = event.get("fornitore_iban")

    alerts_generati = []

    # Alert metodo pagamento mancante
    if not metodo or metodo in ("", "da_configurare", "none"):
        alert = await genera_alert(
            "FORN_MP_MANCANTE",
            fornitore_id,
            "fornitori",
            f"Fornitore '{fornitore_nome}' senza metodo pagamento. "
            f"Le fatture restano in provvisori fino alla configurazione.",
            db
        )
        if alert:
            alerts_generati.append("FORN_MP_MANCANTE")

        # Alert anche sulla fattura
        await genera_alert(
            "FAT_MP_NON_DEFINITO",
            event.get("fattura_id", ""),
            "invoices",
            f"Fattura sospesa — fornitore '{fornitore_nome}' senza metodo pagamento",
            db
        )

    # Alert IBAN mancante per fornitore bancario
    metodi_bancari = ("bonifico", "banca", "sepa", "rid", "sdd")
    if metodo in metodi_bancari and not fornitore_iban:
        alert = await genera_alert(
            "FORN_IBAN_MANCANTE",
            fornitore_id,
            "fornitori",
            f"Fornitore '{fornitore_nome}' con metodo '{metodo}' ma senza IBAN",
            db
        )
        if alert:
            alerts_generati.append("FORN_IBAN_MANCANTE")

    # Alert fornitore nuovo da completare
    if fornitore_nuovo:
        alert = await genera_alert(
            "FORN_NUOVO_INCOMPLETO",
            fornitore_id,
            "fornitori",
            f"Fornitore '{fornitore_nome}' creato automaticamente da fattura. "
            f"Verificare e completare anagrafica.",
            db
        )
        if alert:
            alerts_generati.append("FORN_NUOVO_INCOMPLETO")

    if alerts_generati:
        return {"action": "alert_generati", "codici": alerts_generati}
    return None


# ============================================================
# HANDLER 3: Audit log della fattura
# ============================================================
async def on_fattura_created_audit(event: Dict[str, Any], db) -> Optional[Dict]:
    """Registra l'operazione di creazione fattura nell'audit log."""
    from app.services.audit_logger import log_evento

    audit_id = await log_evento(
        modulo="fatture",
        azione="creata",
        entita_id=event.get("fattura_id", ""),
        entita_collection="invoices",
        db=db,
        nuovo_stato={
            "stato": event.get("stato", "importata"),
            "importo": event.get("importo_totale"),
            "fornitore": event.get("fornitore_ragione_sociale"),
            "metodo_pagamento": event.get("metodo_pagamento"),
            "tipo_documento": event.get("tipo_documento", "TD01"),
            "pagato": event.get("pagato", False)
        },
        fonte=event.get("source_module", "import_xml"),
        utente=event.get("user", "sistema"),
        dettaglio=f"Fattura {event.get('numero_documento', '')} da {event.get('fornitore_ragione_sociale', '')}"
    )

    return {"action": "audit_log", "audit_id": audit_id}


# ============================================================
# HANDLER 4: Quando una fattura viene pagata → risolvi alert
# ============================================================
async def on_fattura_pagata_risolvi(event: Dict[str, Any], db) -> Optional[Dict]:
    """
    Quando una fattura viene pagata, risolve gli alert collegati
    e aggiorna la partita aperta.
    """
    from app.services.alert_engine import risolvi_alert
    from app.services.audit_logger import log_evento

    fattura_id = event.get("fattura_id", "")

    # Risolvi alert fattura
    risolti = 0
    risolti += await risolvi_alert("FAT_MP_NON_DEFINITO", fattura_id, db)
    risolti += await risolvi_alert("FAT_DA_PAGARE_SCADUTA", fattura_id, db)
    risolti += await risolvi_alert("FAT_DATI_INCOMPLETI", fattura_id, db)

    # Audit
    await log_evento(
        modulo="fatture",
        azione="pagata",
        entita_id=fattura_id,
        entita_collection="invoices",
        db=db,
        vecchio_stato={"pagato": False},
        nuovo_stato={
            "pagato": True,
            "metodo": event.get("metodo_pagamento"),
            "data_pagamento": event.get("data_pagamento")
        },
        fonte=event.get("source_module", ""),
        dettaglio=f"Fattura pagata via {event.get('metodo_pagamento', 'N/D')}"
    )

    return {"action": "alert_risolti", "count": risolti}


# ============================================================
# HANDLER 5: Quando il fornitore viene aggiornato → risolvi alert
# ============================================================
async def on_fornitore_aggiornato_risolvi(event: Dict[str, Any], db) -> Optional[Dict]:
    """
    Quando il fornitore viene aggiornato (es. MP impostato),
    risolve gli alert collegati.
    """
    from app.services.alert_engine import risolvi_alert

    fornitore_id = event.get("fornitore_id", "")
    metodo = (event.get("metodo_pagamento", "") or "").lower()
    iban = event.get("iban")

    risolti = 0

    # Se ora ha metodo pagamento → risolvi FORN_MP_MANCANTE
    if metodo and metodo not in ("", "da_configurare"):
        risolti += await risolvi_alert("FORN_MP_MANCANTE", fornitore_id, db)

        # Risolvi anche gli alert FAT_MP_NON_DEFINITO sulle fatture di questo fornitore
        fatture = await db["invoices"].find(
            {"fornitore_id": fornitore_id, "pagato": {"$ne": True}},
            {"_id": 0, "id": 1}
        ).to_list(100)
        for f in fatture:
            risolti += await risolvi_alert("FAT_MP_NON_DEFINITO", f["id"], db)

    # Se ora ha IBAN → risolvi FORN_IBAN_MANCANTE
    if iban:
        risolti += await risolvi_alert("FORN_IBAN_MANCANTE", fornitore_id, db)

    # Se i campi minimi sono completi → risolvi FORN_NUOVO_INCOMPLETO
    if metodo and metodo not in ("", "da_configurare"):
        risolti += await risolvi_alert("FORN_NUOVO_INCOMPLETO", fornitore_id, db)

    if risolti > 0:
        from app.services.audit_logger import log_evento
        await log_evento(
            modulo="fornitori",
            azione="alert_risolti",
            entita_id=fornitore_id,
            entita_collection="fornitori",
            db=db,
            dettaglio=f"{risolti} alert risolti dopo aggiornamento fornitore"
        )

    return {"action": "alert_risolti", "count": risolti} if risolti > 0 else None
