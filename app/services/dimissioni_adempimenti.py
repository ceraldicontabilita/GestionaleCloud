"""Dimissioni telematiche ricevute -> adempimenti del datore di lavoro.

Richiesta del titolare (14/09/2026): quando in posta (o su Drive/upload)
arriva il "Modulo Recesso Rapporto di Lavoro" del Ministero del Lavoro (le
dimissioni telematiche, art. 26 D.Lgs. 151/2015), e' la conferma che il
dipendente ha dato le dimissioni e il titolare ha **5 giorni** per farlo
comunicare al consulente del lavoro (comunicazione obbligatoria UNILAV di
cessazione ai Centri per l'impiego, art. 4-bis D.Lgs. 181/2000: entro 5 giorni
dalla cessazione). Il lavoratore puo' revocare le dimissioni entro **7 giorni**
dalla trasmissione del modulo.

Il gestionale riconosce gia' il modulo (``fiscal_domain`` ->
``dimissioni_telematiche``, parser ``administrative_document_parser.
parse_dimissioni``). Questo modulo aggiunge cio' che mancava:

* **HR**: il dipendente (per codice fiscale) riceve ``dimissioni`` (dati del
  modulo + scadenze) e ``data_cessazione_prevista``; alert HR
  ``DIP_DIMISSIONI_RICEVUTE`` (critico) con la lista degli adempimenti, visibile
  nel Pannello di controllo di HR;
* **gestionale**: scadenza in ``notifiche_scadenze`` (pagina Scadenze) al
  giorno limite UNILAV;
* idempotente per ``codice_modulo``; una dimissione vecchia (limite UNILAV
  passato da oltre 60 giorni) di un dipendente gia' cessato viene solo
  archiviata sull'anagrafica, senza alert.

Adempimenti (fonte: normativa + prassi, da confermare col consulente del
lavoro; il CCNL applicato e' Pubblici Esercizi/Turismo FIPE):
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

GIORNI_UNILAV = 5      # comunicazione di cessazione entro 5 giorni dalla cessazione
GIORNI_REVOCA = 7      # il lavoratore puo' revocare entro 7 giorni dalla trasmissione
GIORNI_STORICO = 60    # oltre questo ritardo, e dipendente gia' cessato, niente alert
CODICE_ALERT_HR = "DIP_DIMISSIONI_RICEVUTE"
TIPO_SCADENZA = "UNILAV_CESSAZIONE"

FONTI = "D.Lgs. 151/2015 art. 26 (dimissioni telematiche); D.Lgs. 181/2000 art. 4-bis (UNILAV cessazione entro 5 giorni)"


def _data(valore: Any) -> Optional[date]:
    testo = str(valore or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", testo)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})", testo)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return None


def scadenze_dimissioni(metadata: Dict[str, Any], oggi: Optional[date] = None) -> Dict[str, Any]:
    """Date limite calcolate dal modulo: UNILAV (decorrenza + 5) e revoca (trasmissione + 7)."""
    oggi = oggi or date.today()
    decorrenza = _data(metadata.get("data_decorrenza_recesso"))
    trasmissione = _data(metadata.get("data_trasmissione"))
    unilav = (decorrenza + timedelta(days=GIORNI_UNILAV)) if decorrenza else None
    revoca = (trasmissione + timedelta(days=GIORNI_REVOCA)) if trasmissione else None
    giorni_unilav = (unilav - oggi).days if unilav else None
    return {
        "data_decorrenza": decorrenza.isoformat() if decorrenza else None,
        "data_trasmissione": trasmissione.isoformat() if trasmissione else None,
        "scadenza_unilav": unilav.isoformat() if unilav else None,
        "giorni_alla_scadenza_unilav": giorni_unilav,
        "unilav_scaduta": bool(unilav and unilav < oggi),
        "revoca_possibile_fino_al": revoca.isoformat() if revoca else None,
        "revoca_ancora_possibile": bool(revoca and revoca >= oggi),
    }


def adempimenti_datore(metadata: Dict[str, Any], scad: Dict[str, Any]) -> List[Dict[str, str]]:
    """Checklist per il titolare/consulente, in ordine di urgenza."""
    dec = scad.get("data_decorrenza") or "?"
    return [
        {"cosa": "Inviare al consulente del lavoro il modulo e far trasmettere la comunicazione UNILAV di cessazione",
         "entro": scad.get("scadenza_unilav") or "?",
         "nota": f"5 giorni dalla cessazione ({dec}); sanzione amministrativa se in ritardo"},
        {"cosa": "Verificare il preavviso CCNL Pubblici Esercizi (dimissioni volontarie): ultimo giorno di lavoro = data di decorrenza, oppure trattenuta/indennita' di mancato preavviso",
         "entro": dec, "nota": "il modulo indica 'Tipo comunicazione' e la data di decorrenza"},
        {"cosa": "Attendere l'eventuale revoca del lavoratore (7 giorni dalla trasmissione): se revoca, annullare/rettificare l'UNILAV",
         "entro": scad.get("revoca_possibile_fino_al") or "?", "nota": "revoca solo per via telematica"},
        {"cosa": "Ultima busta paga con competenze finali: ratei 13a/14a, ferie e permessi non goduti, TFR (o destinazione a Fon.Te.), eventuale trattenuta preavviso",
         "entro": "con la paga del mese di cessazione", "nota": "il cedolino di cessazione arriva dal consulente e viene depositato in HR"},
        {"cosa": "Chiudere in HR: cessa dipendente (revoca PIN portale, contratti terminati, turni), restituzione divise/chiavi/badge",
         "entro": dec, "nota": "pulsante 'Cessa dipendente' nella scheda HR"},
        {"cosa": "Comunicazioni agli enti bilaterali/fondi (EBNT/EBT, Fondo EST, Fon.Te.) tramite il consulente; Certificazione Unica l'anno successivo",
         "entro": "prossimo invio contributivo", "nota": "verificare col consulente cosa e' automatico con l'UNILAV"},
    ]


def _db_hr():
    from app.hr.database import Database, DatabaseNonConfigurato

    db_hr = Database.get_db()
    if db_hr is None or isinstance(db_hr, DatabaseNonConfigurato):
        return None
    return db_hr


def _testo_alert(nome: str, scad: Dict[str, Any], checklist: List[Dict[str, str]]) -> str:
    righe = [
        f"Dimissioni telematiche ricevute per {nome}: decorrenza {scad.get('data_decorrenza') or '?'}, "
        f"modulo trasmesso il {scad.get('data_trasmissione') or '?'}.",
        f"UNILAV di cessazione entro il {scad.get('scadenza_unilav') or '?'} "
        f"({scad.get('giorni_alla_scadenza_unilav')} giorni) tramite il consulente del lavoro.",
    ]
    if scad.get("revoca_ancora_possibile"):
        righe.append(f"Il lavoratore puo' ancora revocare fino al {scad.get('revoca_possibile_fino_al')}.")
    righe.append("Adempimenti: " + " | ".join(f"{a['cosa']} (entro {a['entro']})" for a in checklist))
    return "\n".join(righe)


async def registra_dimissioni(db, metadata: Dict[str, Any], *, documento_id: Optional[str] = None,
                              filename: Optional[str] = None, oggi: Optional[date] = None) -> Dict[str, Any]:
    """Porta in HR e nelle scadenze del gestionale una dimissione riconosciuta.

    ``metadata`` e' l'uscita di ``parse_dimissioni``. Ritorna un riepilogo;
    non solleva mai per problemi HR (chi chiama archivia comunque il documento).
    """
    oggi = oggi or date.today()
    cf = str(metadata.get("lavoratore_cf") or "").strip().upper()
    codice = str(metadata.get("codice_modulo") or documento_id or "").strip()
    scad = scadenze_dimissioni(metadata, oggi)
    esito: Dict[str, Any] = {"codice_modulo": codice, "codice_fiscale": cf, **scad,
                             "hr": "non_configurato", "scadenza_gestionale": False, "alert": False}
    if not cf or not scad.get("data_decorrenza"):
        esito["hr"] = "dati_incompleti"
        return esito

    db_hr = _db_hr()
    dip = None
    if db_hr is not None:
        dip = await db_hr.dipendenti.find_one(
            {"codice_fiscale": cf, "merged_into": {"$exists": False}}, {"_id": 0})
    nome = (dip or {}).get("nome_completo") or " ".join(
        p for p in (metadata.get("lavoratore_cognome"), metadata.get("lavoratore_nome")) if p) or cf
    esito["dipendente_id"] = (dip or {}).get("id")
    esito["dipendente"] = nome
    checklist = adempimenti_datore(metadata, scad)

    gia_cessato = bool(dip and (dip.get("stato") == "cessato" or dip.get("attivo") is False))
    storico = scad["unilav_scaduta"] and (date.fromisoformat(scad["scadenza_unilav"]) + timedelta(days=GIORNI_STORICO) < oggi)
    esito["storico"] = bool(storico and gia_cessato)

    if db_hr is not None and dip:
        await db_hr.dipendenti.update_one({"id": dip["id"]}, {"$set": {
            "dimissioni": {
                "codice_modulo": codice, "tipo_comunicazione": metadata.get("tipo_comunicazione"),
                "data_decorrenza": scad["data_decorrenza"], "data_trasmissione": scad["data_trasmissione"],
                "scadenza_unilav": scad["scadenza_unilav"],
                "revoca_possibile_fino_al": scad["revoca_possibile_fino_al"],
                "documento_id": documento_id, "filename": filename,
                "ricevuto_il": datetime.now(timezone.utc).isoformat(),
                "adempimenti": checklist, "fonti": FONTI,
            },
            "data_cessazione_prevista": scad["data_decorrenza"],
        }})
        esito["hr"] = "aggiornato"
        if not esito["storico"]:
            from app.hr.services.alert_engine import genera_alert

            alert = await genera_alert(
                CODICE_ALERT_HR, dip["id"], "dipendenti", _testo_alert(nome, scad, checklist), db_hr,
                extra={"codice_modulo": codice, "scadenza_unilav": scad["scadenza_unilav"],
                       "data_decorrenza": scad["data_decorrenza"], "documento_id": documento_id,
                       "adempimenti": checklist},
            )
            esito["alert"] = alert is not None
    elif db_hr is not None:
        esito["hr"] = "dipendente_non_trovato"

    if not esito["storico"]:
        chiave = f"{TIPO_SCADENZA}:{codice}"
        if not await db["notifiche_scadenze"].find_one({"chiave": chiave}, {"_id": 0, "id": 1}):
            import uuid

            await db["notifiche_scadenze"].insert_one({
                "id": str(uuid.uuid4()), "chiave": chiave, "tipo": TIPO_SCADENZA,
                "data_scadenza": scad["scadenza_unilav"],
                "descrizione": f"UNILAV cessazione {nome}: comunicare le dimissioni al consulente del lavoro "
                               f"(decorrenza {scad['data_decorrenza']}, 5 giorni)",
                "importo": 0.0, "priorita": "alta",
                "note": "; ".join(f"{a['cosa']} entro {a['entro']}" for a in checklist),
                "dipendente_id": esito.get("dipendente_id"), "codice_fiscale": cf,
                "documento_id": documento_id, "completata": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            esito["scadenza_gestionale"] = True
    return esito
