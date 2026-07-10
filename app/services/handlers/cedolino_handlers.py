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
    codice_fiscale = event.get("codice_fiscale", "")
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

    # Alert possibile cedolino duplicato: stesso dipendente (CF) + stesso
    # mese/anno già presente — CED_DUPLICATO era definito in alert_engine.py
    # ma mai generato (vedi memoria/moduli/CEDOLINI.md). Best-effort, non
    # blocca l'import: segnala soltanto, l'utente decide se è un vero doppione.
    if codice_fiscale and mese and anno:
        try:
            duplicato = await db["cedolini"].find_one({
                "codice_fiscale": codice_fiscale,
                "mese": mese,
                "anno": anno,
                "id": {"$ne": cedolino_id},
            }, {"_id": 0, "id": 1})
            if duplicato:
                await genera_alert(
                    "CED_DUPLICATO", cedolino_id, "cedolini",
                    f"Possibile duplicato: {dipendente_nome or codice_fiscale} ha già un cedolino "
                    f"{mese}/{anno} (id {duplicato.get('id')})",
                    db,
                    extra={"duplicato_id": duplicato.get("id")},
                )
                risultati.append("alert_duplicato")
        except Exception:
            logger.exception(f"Errore controllo duplicato cedolino {cedolino_id}")

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

    # Verifica trattenute verbali attese in questo cedolino: se il dipendente
    # ha trattenute comunicate al consulente per questo mese, controlla che la
    # voce di trattenuta compaia nel testo/voci del cedolino (recuperata_in_busta)
    # oppure alza l'alert TRATTENUTA_NON_IN_CEDOLINO. Best-effort: non deve
    # MAI bloccare l'import del cedolino.
    try:
        from app.services.trattenute_verbali_service import verifica_trattenute_cedolino
        esito_trattenute = await verifica_trattenute_cedolino(event, db)
        if esito_trattenute.get("recuperate"):
            risultati.append(f"trattenute_recuperate:{esito_trattenute['recuperate']}")
        if esito_trattenute.get("non_trovate"):
            risultati.append(f"trattenute_non_trovate:{esito_trattenute['non_trovate']}")
    except Exception:
        logger.exception(f"Errore verifica trattenute verbali per cedolino {cedolino_id}")

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
