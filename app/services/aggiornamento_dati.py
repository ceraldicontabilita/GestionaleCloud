"""Riquadro «Aggiornamento dati» della Dashboard: stato delle fonti, in sola lettura.

Per ogni fonte si legge lo stato **dove il suo motore lo scrive gia'**
(`sistema_stato`, `drive_sync_state`) e l'ultimo dato presente nella sua
collezione. Nessun numero si inventa: una lettura che manca o fallisce diventa
``None`` e l'interfaccia scrive «non disponibile». Lo stato ha sempre anche un
testo, perche' il colore da solo non e' un'informazione.

Le fonti sono in ordine fisso, lo stesso in cui gireranno gli aggiornamenti:
banca, fatture, corrispettivi, cedolini e F24, riconciliazione.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

ROMA = ZoneInfo("Europe/Rome")

# Chiave scritta dal giro «Automazioni Prima Nota» dopo
# `riconcilia_documenti_e_pagamenti` (app/scheduler.py).
CHIAVE_RICONCILIAZIONE = "riconciliazione_ultimo_giro"

VERDE, GIALLO, ROSSO, NON_DISPONIBILE = "verde", "giallo", "rosso", "non_disponibile"


def _dt(valore: Any) -> Optional[datetime]:
    if not valore:
        return None
    if isinstance(valore, datetime):
        return valore if valore.tzinfo else valore.replace(tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(valore).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _giorno(valore: Any) -> Optional[date]:
    if not valore:
        return None
    try:
        return date.fromisoformat(str(valore)[:10])
    except ValueError:
        return None


def _minuti_da(momento: Optional[datetime], ora: datetime) -> Optional[float]:
    return None if momento is None else (ora - momento).total_seconds() / 60


def stato_giro(ultimo: Optional[datetime], errore: Any, ora: datetime, *,
               ogni_minuti: int) -> tuple[str, str]:
    """Stato di un giro periodico: in orario, in ritardo, fermo o in errore.

    In orario = entro due turni; fermo = oltre otto turni (un riavvio di
    Render salta un turno, non otto).
    """
    if ultimo is None:
        return NON_DISPONIBILE, "Nessun giro registrato"
    if errore:
        return ROSSO, f"Ultimo giro in errore: {str(errore)[:160]}"
    ritardo = _minuti_da(ultimo, ora)
    if ritardo <= 2 * ogni_minuti:
        return VERDE, "Aggiornato"
    if ritardo <= 8 * ogni_minuti:
        return GIALLO, f"In ritardo: ultimo giro {int(ritardo)} minuti fa"
    return ROSSO, f"Fermo: ultimo giro {int(ritardo // 60)} ore fa"


async def _stato(db, chiave: str) -> Dict[str, Any]:
    try:
        return await db["sistema_stato"].find_one({"chiave": chiave}, {"_id": 0}) or {}
    except Exception as exc:
        logger.warning("[aggiornamento-dati] stato %s non letto: %s: %s",
                       chiave, type(exc).__name__, exc)
        return {}


async def _conta(db, collezione: str, filtro: Optional[dict] = None) -> Optional[int]:
    try:
        return await db[collezione].count_documents(filtro or {})
    except Exception as exc:
        logger.warning("[aggiornamento-dati] conteggio %s non letto: %s: %s",
                       collezione, type(exc).__name__, exc)
        return None


async def _ultimo(db, collezione: str, campo: str) -> Optional[str]:
    """Valore massimo di un campo data, con proiezione senza payload."""
    try:
        righe = await db[collezione].find(
            {campo: {"$nin": [None, ""]}}, {"_id": 0, campo: 1},
        ).sort(campo, -1).limit(1).to_list(1)
    except Exception as exc:
        logger.warning("[aggiornamento-dati] ultimo %s.%s non letto: %s: %s",
                       collezione, campo, type(exc).__name__, exc)
        return None
    return str(righe[0].get(campo))[:10] if righe else None


def _fonte(ordine: int, codice: str, nome: str, *, stato: str, testo: str,
           ultimo_aggiornamento: Optional[datetime] = None,
           ultimo_dato: Optional[str] = None, conteggi: Optional[dict] = None,
           nota: Optional[str] = None) -> Dict[str, Any]:
    return {
        "ordine": ordine,
        "codice": codice,
        "nome": nome,
        "stato": stato,
        "testo": testo,
        "ultimo_aggiornamento": ultimo_aggiornamento.isoformat() if ultimo_aggiornamento else None,
        "ultimo_dato": ultimo_dato,
        "conteggi": conteggi or {},
        "nota": nota,
    }


async def _banca(db, ora: datetime) -> Dict[str, Any]:
    stato = await _stato(db, "drive_estratti_conto_last_sync")
    ultimo_giro = _dt(stato.get("valore"))
    esito = stato.get("last_result") or {}
    colore, testo = stato_giro(ultimo_giro, (esito.get("errors") or None), ora, ogni_minuti=5)
    ultimo_movimento = await _ultimo(db, "estratto_conto_movimenti", "data")
    giorno = _giorno(ultimo_movimento)
    if colore == VERDE and giorno and (ora.astimezone(ROMA).date() - giorno).days > 3:
        colore = GIALLO
        testo = f"Il giro gira, ma l'ultimo movimento in archivio e' del {giorno:%d/%m/%Y}"
    fonte = _fonte(
        1, "banca", "Banca Banco BPM", stato=colore, testo=testo,
        ultimo_aggiornamento=ultimo_giro, ultimo_dato=ultimo_movimento,
        conteggi={
            "movimenti": await _conta(db, "estratto_conto_movimenti"),
            "file_in_attesa": esito.get("pending"),
        },
    )
    fonte["enable_banking"] = diretta = await _stato_enable_banking(db)
    if not diretta["attivo"]:
        fonte["nota"] = "Arriva dagli estratti conto caricati su Drive; la lettura diretta dalla banca e' spenta."
    elif not diretta["collegata"]:
        fonte["nota"] = "Lettura diretta dalla banca attiva ma conto non collegato."
    else:
        fonte["nota"] = "Lettura diretta dalla banca collegata (anteprima, senza scrivere movimenti)."
    return fonte


async def _stato_enable_banking(db) -> Dict[str, Any]:
    from app.services import enable_banking as eb

    try:
        sessione = await eb.leggi_sessione(db)
    except Exception as exc:
        logger.warning("[aggiornamento-dati] sessione banca non letta: %s: %s", type(exc).__name__, exc)
        sessione = {"collegata": False}
    return {"attivo": eb.attivo(), "configurato": eb.configurato(), **sessione}


async def _fatture(db, ora: datetime) -> Dict[str, Any]:
    try:
        stato = await db["drive_sync_state"].find_one({"_id": "fatture_drive"}) or {}
    except Exception as exc:
        logger.warning("[aggiornamento-dati] drive_sync_state non letto: %s: %s",
                       type(exc).__name__, exc)
        stato = {}
    ultimo_giro = _dt(stato.get("last_sync"))
    colore, testo = stato_giro(ultimo_giro, stato.get("last_error"), ora, ogni_minuti=15)
    esito = stato.get("last_result") or {}
    return _fonte(
        2, "fatture", "Fatture (giro Drive ogni 15 minuti)", stato=colore, testo=testo,
        ultimo_aggiornamento=ultimo_giro,
        ultimo_dato=await _ultimo(db, "invoices", "invoice_date"),
        conteggi={
            "fatture": await _conta(db, "invoices"),
            "importate_ultimo_giro": esito.get("imported"),
            "in_attesa": esito.get("pending"),
        },
    )


async def _corrispettivi(db, ora: datetime) -> Dict[str, Any]:
    from app.services.chiusure_attivita import giorni_chiusi

    stato = await _stato(db, "drive_corrispettivi_last_sync")
    ultimo_giro = _dt(stato.get("valore"))
    ultima_giornata = await _ultimo(db, "corrispettivi", "data")
    giorno = _giorno(ultima_giornata)
    ieri = ora.astimezone(ROMA).date() - timedelta(days=1)
    if giorno is None:
        colore, testo = NON_DISPONIBILE, "Nessuna giornata in archivio"
    elif giorno >= ieri:
        colore, testo = VERDE, "Aggiornati a ieri"
    else:
        # I giorni di chiusura (ferie, ristrutturazione) non sono buchi.
        da, a = (giorno + timedelta(days=1)).isoformat(), ieri.isoformat()
        try:
            chiusi = await giorni_chiusi(db, da, a)
        except Exception as exc:
            logger.warning("[aggiornamento-dati] chiusure non lette: %s: %s",
                           type(exc).__name__, exc)
            chiusi = set()
        mancanti = [
            g for g in ((giorno + timedelta(days=i)).isoformat()
                        for i in range(1, (ieri - giorno).days + 1))
            if g not in chiusi
        ]
        if not mancanti:
            colore, testo = VERDE, "Aggiornati (i giorni dopo sono di chiusura)"
        else:
            colore = GIALLO if len(mancanti) <= 2 else ROSSO
            testo = (f"Ultima giornata {giorno:%d/%m/%Y}: mancano {len(mancanti)} giorni di apertura. "
                     "Se il PC del negozio non manda le chiusure, qui non arriva niente.")
    return _fonte(
        3, "corrispettivi", "Corrispettivi", stato=colore, testo=testo,
        ultimo_aggiornamento=ultimo_giro, ultimo_dato=ultima_giornata,
        conteggi={"giornate": await _conta(db, "corrispettivi")},
    )


async def _cedolini_f24(db, ora: datetime) -> Dict[str, Any]:
    ced = await _stato(db, "drive_cedolini_last_sync")
    f24 = await _stato(db, "drive_f24_last_sync")
    giri = [g for g in (_dt(ced.get("valore")), _dt(f24.get("valore"))) if g]
    # Il piu' vecchio dei due comanda: uno fermo basta a fermare la riga.
    ultimo_giro = min(giri) if len(giri) == 2 else None
    errore = ced.get("last_error") or f24.get("last_error")
    colore, testo = stato_giro(ultimo_giro, errore, ora, ogni_minuti=15)
    errori_parser = (ced.get("last_result") or {}).get("parser_errors")
    if colore == VERDE and errori_parser:
        colore, testo = GIALLO, f"Aggiornato, ma {errori_parser} cedolini non si leggono"
    return _fonte(
        4, "cedolini_f24", "Cedolini e F24", stato=colore, testo=testo,
        ultimo_aggiornamento=ultimo_giro,
        conteggi={
            "cedolini": await _conta(db, "cedolini"),
            "f24": await _conta(db, "f24_unificato"),
            "cedolini_illeggibili": errori_parser,
        },
    )


async def _riconciliazione(db, ora: datetime) -> Dict[str, Any]:
    stato = await _stato(db, CHIAVE_RICONCILIAZIONE)
    ultimo_giro = _dt(stato.get("terminato_at"))
    colore, testo = stato_giro(ultimo_giro, stato.get("errore"), ora, ogni_minuti=30)
    return _fonte(
        5, "riconciliazione", "Riconciliazione (giro ogni 30 minuti)", stato=colore, testo=testo,
        ultimo_aggiornamento=ultimo_giro,
        conteggi=stato.get("conteggi") or {},
    )


async def stato_fonti(db, ora: Optional[datetime] = None) -> Dict[str, Any]:
    ora = ora or datetime.now(timezone.utc)
    fonti: List[Dict[str, Any]] = []
    for lettore in (_banca, _fatture, _corrispettivi, _cedolini_f24, _riconciliazione):
        try:
            fonti.append(await lettore(db, ora))
        except Exception as exc:
            logger.warning("[aggiornamento-dati] %s non letto: %s: %s",
                           lettore.__name__, type(exc).__name__, exc)
            fonti.append(_fonte(len(fonti) + 1, lettore.__name__.strip("_"), lettore.__name__.strip("_"),
                                stato=NON_DISPONIBILE, testo="Stato non leggibile in questo momento"))
    return {"generato_at": ora.isoformat(), "fonti": fonti}


async def registra_giro_riconciliazione(db, *, iniziato_at: datetime,
                                        risultato: Optional[dict] = None,
                                        errore: Optional[BaseException] = None) -> None:
    """Il giro dei 30 minuti lascia il suo esito, come gli altri motori."""
    r = risultato or {}
    conteggi = {
        "assegni": (r.get("assegni_intenti") or {}).get("collegati"),
        "stipendi": (r.get("salari") or {}).get("bonifici_associati"),
        "f24": (r.get("f24") or {}).get("movimenti_associati"),
        "bonifici": (r.get("bonifici_pdf") or {}).get("associati"),
    }
    try:
        await db["sistema_stato"].update_one(
            {"chiave": CHIAVE_RICONCILIAZIONE},
            {"$set": {
                "chiave": CHIAVE_RICONCILIAZIONE,
                "iniziato_at": iniziato_at.isoformat(),
                "terminato_at": datetime.now(timezone.utc).isoformat(),
                "errore": f"{type(errore).__name__}: {errore}"[:300] if errore else None,
                "conteggi": {k: v for k, v in conteggi.items() if v is not None},
            }},
            upsert=True,
        )
    except Exception as exc:
        logger.warning("[aggiornamento-dati] esito riconciliazione non scritto: %s: %s",
                       type(exc).__name__, exc)
