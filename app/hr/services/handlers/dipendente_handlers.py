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
    from app.hr.services.alert_engine import genera_alert
    from app.hr.services.audit_logger import log_evento

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
    from app.hr.services.alert_engine import risolvi_alert
    from app.hr.services.audit_logger import log_evento

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
    Quando un dipendente viene cessato esegue il ciclo completo di chiusura:

    1. Termina tutti i contratti attivi (employee_contracts) con data_fine = data_cessazione
    2. Rifiuta automaticamente richieste assenza pending con data > data_cessazione
    3. Annulla partite aperte stipendio residue
    4. Risolve alert aperti sul dipendente (tranne DIP_CESSATO_FLUSSI_ATTIVI nuovo)
    5. Revoca il PIN del portale (nessun nuovo login possibile da qui in poi)
    6. Genera audit + eventuale alert se restano flussi anomali

    Idempotente: se ricevuto due volte non duplica azioni (skip se già terminato).

    NOTA (limite noto, trovato da una review automatica): revoca il PIN, quindi
    blocca ogni NUOVO login, ma un token JWT già emesso a un dipendente resta
    valido fino alla sua scadenza naturale (fino a 7 giorni, get_identity in
    utils/identity.py non ri-verifica lo stato del dipendente ad ogni chiamata,
    solo firma/scadenza del token) — nessuna revoca delle sessioni già aperte.
    Per questa app (poche decine di dipendenti, cessazioni non frequenti) non
    si è ritenuto proporzionato aggiungere una query DB su ogni chiamata API
    protetta solo per coprire questa finestra residua; da rivalutare se diventa
    un problema reale.
    """
    from app.hr.services.alert_engine import genera_alert
    from app.hr.services.audit_logger import log_evento
    from app.hr.services.auth_dipendenti import rimuovi_pin
    from datetime import datetime, timedelta, timezone

    dip_id = event.get("dipendente_id", "")
    nome = event.get("nome_completo", "")
    data_cessazione = event.get("data_cessazione") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    source_module = event.get("source_module", "manuale")
    auto_from_cedolino = event.get("auto_from_cedolino", False)
    diciture = event.get("cessazione_diciture", [])

    now_iso = datetime.now(timezone.utc).isoformat()
    azioni = {
        "contratti_terminati": 0,
        "richieste_future_rifiutate": 0,
        "partite_annullate": 0,
        "alerts_risolti": 0,
        "pin_revocato": False,
    }

    # 0. Revoca il PIN del portale: da qui in poi nessun nuovo login possibile
    #    (il selettore nomi del portale esclude comunque i cessati dall'elenco,
    #    ma senza revocare il PIN un accesso diretto con l'id noto avrebbe
    #    continuato a funzionare).
    try:
        azioni["pin_revocato"] = await rimuovi_pin(dip_id)
    except Exception as e:
        logger.exception(f"Errore revoca PIN per dip {dip_id}: {e}")

    # 1. Termina contratti attivi
    try:
        r_contratti = await db["employee_contracts"].update_many(
            {
                "dipendente_id": dip_id,
                "stato": {"$in": ["attivo", "in_corso", None]},
                "$or": [
                    {"data_fine": None},
                    {"data_fine": {"$exists": False}},
                    {"data_fine": ""},
                    {"data_fine": {"$gte": data_cessazione}},
                ],
            },
            {"$set": {
                "stato": "terminato",
                "data_fine": data_cessazione,
                "motivo_fine": "cessazione_rapporto",
                "terminato_automaticamente": True,
                "terminato_at": now_iso,
            }}
        )
        azioni["contratti_terminati"] = r_contratti.modified_count
    except Exception as e:
        logger.exception(f"Errore terminazione contratti per dip {dip_id}: {e}")

    # 2. Rifiuta richieste assenza future pending
    try:
        r_richieste = await db["richieste_assenza"].update_many(
            {
                "employee_id": dip_id,
                "stato": {"$in": ["pending", "in_attesa", "inviata"]},
                "data_inizio": {"$gte": data_cessazione},
            },
            {"$set": {
                "stato": "rifiutata",
                "rifiutata_automaticamente": True,
                "motivo_rifiuto": "Dipendente cessato",
                "rifiutata_at": now_iso,
            }}
        )
        azioni["richieste_future_rifiutate"] = r_richieste.modified_count
    except Exception as e:
        logger.exception(f"Errore rifiuto richieste future per dip {dip_id}: {e}")

    # 3. Annulla partite aperte stipendio residue
    try:
        r_partite = await db["partite_aperte"].update_many(
            {
                "controparte_id": dip_id,
                "tipo": "stipendio",
                "stato": {"$in": ["aperta", "parziale"]},
            },
            {"$set": {
                "stato": "annullata",
                "annullata_at": now_iso,
                "motivo_annullamento": f"Dipendente {nome} cessato il {data_cessazione}",
            }}
        )
        azioni["partite_annullate"] = r_partite.modified_count
    except Exception as e:
        logger.exception(f"Errore annullamento partite per dip {dip_id}: {e}")

    # 4. Risolve alert aperti sul dipendente
    try:
        r_alerts = await db["alerts"].update_many(
            {
                "entita_id": dip_id,
                "stato": "aperto",
                # Non risolvere l'alert DIP_CESSATO_FLUSSI_ATTIVI che potremmo creare subito dopo
                "codice": {"$ne": "DIP_CESSATO_FLUSSI_ATTIVI"},
            },
            {"$set": {
                "stato": "risolto",
                "risolto": True,
                "resolved_at": now_iso,
                "resolved_by": "cessazione",
                "note_risoluzione": f"Dipendente {nome} cessato il {data_cessazione}",
            }}
        )
        azioni["alerts_risolti"] = r_alerts.modified_count
    except Exception as e:
        logger.exception(f"Errore risoluzione alert per dip {dip_id}: {e}")

    # 5. Check flussi residui anomali (cedolini recenti NON dovrebbero essere
    #    un problema se la cessazione è arrivata proprio da cedolino, quindi
    #    l'alert è generato solo se siamo in cessazione manuale)
    if not auto_from_cedolino:
        due_mesi_fa = (datetime.now() - timedelta(days=60)).strftime("%Y-%m")
        cedolini_recenti = await db["cedolini"].count_documents({
            "dipendente_id": dip_id,
            "$expr": {"$gte": [{"$concat": [{"$toString": "$anno"}, "-", {"$toString": "$mese"}]}, due_mesi_fa]}
        })
        partite_aperte_post = await db["partite_aperte"].count_documents({
            "controparte_id": dip_id,
            "tipo": "stipendio",
            "stato": {"$in": ["aperta", "parziale"]}
        })
        if cedolini_recenti > 0 or partite_aperte_post > 0:
            await genera_alert(
                "DIP_CESSATO_FLUSSI_ATTIVI", dip_id, "dipendenti",
                f"Dipendente '{nome}' cessato ma ha {cedolini_recenti} cedolini recenti "
                f"e {partite_aperte_post} partite stipendio ancora aperte dopo chiusura",
                db,
                extra={"cedolini_recenti": cedolini_recenti, "partite_aperte": partite_aperte_post}
            )

    # Audit log
    dettaglio = f"Dipendente '{nome}' cessato il {data_cessazione}"
    if auto_from_cedolino:
        dettaglio += f" (rilevato da cedolino: {', '.join(diciture) if diciture else 'diciture cessazione'})"
    dettaglio += (
        f" — contratti={azioni['contratti_terminati']}, "
        f"richieste={azioni['richieste_future_rifiutate']}, "
        f"partite={azioni['partite_annullate']}, "
        f"alerts={azioni['alerts_risolti']}, "
        f"pin_revocato={azioni['pin_revocato']}"
    )

    await log_evento(
        modulo="dipendenti", azione="cessato", entita_id=dip_id,
        entita_collection="dipendenti", db=db,
        nuovo_stato={"stato": "cessato", "data_cessazione": data_cessazione, "azioni": azioni},
        fonte=source_module,
        dettaglio=dettaglio,
    )

    return {"action": "cessazione_processata", "azioni": azioni}
