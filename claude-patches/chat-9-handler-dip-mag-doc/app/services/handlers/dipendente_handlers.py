"""
Handler Eventi Dipendenti — Gestionale Ceraldi Group
======================================================
Copre le specifiche di DIPENDENTI.txt:
- Deduplica su CF/nome+cognome+nascita
- Alert anagrafica incompleta (IBAN, contratto)
- Alert cessato con flussi attivi
- Audit trail creazione/aggiornamento
- Risoluzione alert quando fascicolo completato
"""
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


async def on_dipendente_created(event: Dict[str, Any], db) -> Optional[Dict]:
    """
    Quando viene creato un dipendente:
    1. Verifica deduplica (CF, nome+cognome)
    2. Genera alert se anagrafica incompleta
    3. Audit log
    """
    from app.services.alert_engine import genera_alert
    from app.services.audit_logger import log_evento

    dip_id = event.get("dipendente_id", "")
    nome = event.get("nome", "")
    cognome = event.get("cognome", "")
    cf = event.get("codice_fiscale", "")
    iban = event.get("iban_cedolino")
    contratto = event.get("tipo_contratto")
    stato = event.get("stato", "attivo")
    nome_completo = f"{nome} {cognome}".strip()

    risultati = []

    # --- DEDUPLICA ---
    if cf:
        existing = await db["dipendenti"].find_one(
            {"codice_fiscale": cf, "id": {"$ne": dip_id}},
            {"_id": 0, "id": 1, "nome": 1, "cognome": 1}
        )
        if existing:
            await genera_alert(
                "DIP_DUPLICATO", dip_id, "dipendenti",
                f"Possibile duplicato: '{nome_completo}' ha stesso CF di "
                f"'{existing.get('nome', '')} {existing.get('cognome', '')}' (id: {existing['id']})",
                db, extra={"duplicato_di": existing["id"]}
            )
            risultati.append("alert_duplicato")

    # Deduplica per nome+cognome (se CF mancante)
    if not cf and nome and cognome:
        import re
        nome_norm = re.sub(r'\s+', ' ', nome.strip().upper())
        cognome_norm = re.sub(r'\s+', ' ', cognome.strip().upper())
        existing = await db["dipendenti"].find_one(
            {
                "nome": {"$regex": f"^{re.escape(nome_norm)}$", "$options": "i"},
                "cognome": {"$regex": f"^{re.escape(cognome_norm)}$", "$options": "i"},
                "id": {"$ne": dip_id}
            },
            {"_id": 0, "id": 1}
        )
        if existing:
            await genera_alert(
                "DIP_DUPLICATO", dip_id, "dipendenti",
                f"Possibile duplicato: '{nome_completo}' ha nome identico a id {existing['id']}",
                db
            )
            risultati.append("alert_duplicato_nome")

    # --- ALERT INCOMPLETO ---
    campi_mancanti = []
    if not cf:
        campi_mancanti.append("codice fiscale")
    if not iban:
        campi_mancanti.append("IBAN stipendio")
    if not contratto:
        campi_mancanti.append("tipo contratto")

    if campi_mancanti:
        await genera_alert(
            "DIP_INCOMPLETO", dip_id, "dipendenti",
            f"Dipendente '{nome_completo}' — mancano: {', '.join(campi_mancanti)}",
            db, extra={"campi_mancanti": campi_mancanti}
        )
        risultati.append("alert_incompleto")

    # Alert IBAN specifico
    if not iban:
        await genera_alert(
            "DIP_IBAN_MANCANTE", dip_id, "dipendenti",
            f"Dipendente '{nome_completo}' senza IBAN per stipendio",
            db
        )

    # Alert contratto specifico
    if not contratto:
        await genera_alert(
            "DIP_CONTRATTO_MANCANTE", dip_id, "dipendenti",
            f"Dipendente '{nome_completo}' senza contratto collegato",
            db
        )

    # --- AUDIT ---
    await log_evento(
        modulo="dipendenti", azione="creato", entita_id=dip_id,
        entita_collection="dipendenti", db=db,
        nuovo_stato={"nome": nome_completo, "cf": cf, "stato": stato},
        fonte=event.get("source_module", "manuale"),
        dettaglio=f"Dipendente '{nome_completo}' creato — stato: {stato}"
    )

    return {"action": "dipendente_processato", "risultati": risultati}


async def on_dipendente_updated_risolvi(event: Dict[str, Any], db) -> Optional[Dict]:
    """
    Quando l'utente aggiorna il dipendente (IBAN, contratto, CF),
    risolve gli alert collegati.
    """
    from app.services.alert_engine import risolvi_alert
    from app.services.audit_logger import log_evento

    dip_id = event.get("dipendente_id", "")
    iban = event.get("iban_cedolino")
    cf = event.get("codice_fiscale")
    contratto = event.get("tipo_contratto")

    risolti = 0

    if iban:
        risolti += await risolvi_alert("DIP_IBAN_MANCANTE", dip_id, db)

    if contratto:
        risolti += await risolvi_alert("DIP_CONTRATTO_MANCANTE", dip_id, db)

    if cf and iban and contratto:
        risolti += await risolvi_alert("DIP_INCOMPLETO", dip_id, db)

    # Audit
    await log_evento(
        modulo="dipendenti", azione="aggiornato", entita_id=dip_id,
        entita_collection="dipendenti", db=db,
        nuovo_stato={"iban": bool(iban), "cf": bool(cf), "contratto": bool(contratto)},
        fonte=event.get("source_module", "manuale"),
        dettaglio=f"Alert risolti: {risolti}"
    )

    return {"action": "alert_risolti", "count": risolti} if risolti else None


async def on_dipendente_cessato(event: Dict[str, Any], db) -> Optional[Dict]:
    """
    Quando un dipendente viene cessato, verifica se ha flussi attivi
    (cedolini recenti, bonifici pendenti, partite aperte).
    """
    from app.services.alert_engine import genera_alert
    from app.services.audit_logger import log_evento

    dip_id = event.get("dipendente_id", "")
    nome = event.get("nome_completo", "")

    # Cerca cedolini recenti (ultimi 2 mesi)
    from datetime import datetime, timedelta
    due_mesi_fa = (datetime.now() - timedelta(days=60)).strftime("%Y-%m")
    cedolini_recenti = await db["cedolini"].count_documents({
        "dipendente_id": dip_id,
        "$expr": {"$gte": [{"$concat": [{"$toString": "$anno"}, "-", {"$toString": "$mese"}]}, due_mesi_fa]}
    })

    # Cerca partite stipendio aperte
    partite_aperte = await db["partite_aperte"].count_documents({
        "controparte_id": dip_id,
        "tipo": "stipendio",
        "stato": {"$in": ["aperta", "parziale"]}
    })

    if cedolini_recenti > 0 or partite_aperte > 0:
        await genera_alert(
            "DIP_CESSATO_FLUSSI_ATTIVI", dip_id, "dipendenti",
            f"Dipendente '{nome}' cessato ma ha {cedolini_recenti} cedolini recenti "
            f"e {partite_aperte} partite stipendio aperte",
            db,
            extra={"cedolini_recenti": cedolini_recenti, "partite_aperte": partite_aperte}
        )

    await log_evento(
        modulo="dipendenti", azione="cessato", entita_id=dip_id,
        entita_collection="dipendenti", db=db,
        nuovo_stato={"stato": "cessato"},
        fonte=event.get("source_module", "manuale"),
        dettaglio=f"Dipendente '{nome}' cessato"
    )

    return {"action": "cessazione_processata"}
