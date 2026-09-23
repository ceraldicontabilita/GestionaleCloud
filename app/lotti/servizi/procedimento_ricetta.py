"""Provenienza del procedimento di una ricetta.

Un procedimento puo' essere scritto dal titolare (``manuale``) oppure preso
da una fonte web tracciata (``web``). Quello dal web porta sempre la fonte
(indirizzo e titolo) e resta ``procedimento_da_verificare`` finche' il
titolare non lo conferma o lo riscrive: e' un aiuto per il laboratorio, non
la ricetta di casa. Le dosi non stanno mai nel procedimento, stanno negli
ingredienti della scheda.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

CAMPI_PROVENIENZA = ("procedimento_origine", "procedimento_fonte", "procedimento_da_verificare")
LUNGHEZZA_MASSIMA = 6000


def ha_procedimento(ricetta: dict) -> bool:
    return any(
        str(ricetta.get(campo) or "").strip()
        for campo in ("procedimento_testo", "procedimento", "preparazione", "metodo_preparazione")
    )


def campi_su_modifica(precedente: dict, payload: dict) -> dict:
    """Campi di provenienza da scrivere quando arriva una modifica.

    I campi di provenienza non si accettano dal client: li decide il server.
    Un procedimento cambiato a mano diventa del titolare; uno rimasto uguale
    conserva la provenienza che aveva.
    """
    for campo in CAMPI_PROVENIENZA:
        payload.pop(campo, None)
    if "procedimento_testo" not in payload:
        return {}
    nuovo = str(payload.get("procedimento_testo") or "").strip()
    vecchio = str(precedente.get("procedimento_testo") or "").strip()
    if nuovo == vecchio:
        return {}
    if not nuovo:
        return {"procedimento_origine": None, "procedimento_fonte": None, "procedimento_da_verificare": False}
    return {"procedimento_origine": "manuale", "procedimento_da_verificare": False}


def valida_voce_web(voce: Any) -> tuple[Optional[dict], Optional[str]]:
    """Controlla una voce ``{ricetta_id, procedimento, fonte_url, fonte_titolo}``.

    Restituisce ``(voce_pulita, None)`` oppure ``(None, motivo)``.
    """
    if not isinstance(voce, dict):
        return None, "voce non valida"
    ricetta_id = str(voce.get("ricetta_id") or "").strip()
    testo = str(voce.get("procedimento") or "").strip()
    url = str(voce.get("fonte_url") or "").strip()
    titolo = str(voce.get("fonte_titolo") or "").strip()
    if not ricetta_id:
        return None, "ricetta_id mancante"
    if not testo:
        return None, "procedimento vuoto"
    if len(testo) > LUNGHEZZA_MASSIMA:
        return None, "procedimento troppo lungo"
    indirizzo = urlparse(url)
    if indirizzo.scheme not in ("http", "https") or not indirizzo.netloc:
        return None, "fonte senza indirizzo web valido"
    return {
        "ricetta_id": ricetta_id,
        "procedimento": testo,
        "fonte": {
            "url": url,
            "titolo": titolo or indirizzo.netloc,
            "sito": indirizzo.netloc,
            "compatibilita": str(voce.get("compatibilita") or "").strip() or None,
        },
    }, None


def campi_da_web(voce_pulita: dict, adesso: Optional[datetime] = None) -> dict:
    adesso = adesso or datetime.now(timezone.utc)
    return {
        "procedimento_testo": voce_pulita["procedimento"],
        "procedimento_origine": "web",
        "procedimento_fonte": {**voce_pulita["fonte"], "importato_il": adesso.isoformat()},
        "procedimento_da_verificare": True,
    }
