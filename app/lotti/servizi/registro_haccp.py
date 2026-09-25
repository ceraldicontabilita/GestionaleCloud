"""Regole comuni ai registri HACCP di frigoriferi, congelatori e sanificazione.

Un registro HACCP attesta fatti: chi ha controllato cosa, quel giorno. Tre
regole valgono per ogni scrittura, qualunque sia la scheda:

1. **Niente giorni futuri.** Una rilevazione o una sanificazione si registra
   quando e' stata fatta, non prima.
2. **La firma e' una persona riconosciuta.** Viene dal PIN personale (se
   passato) o dalla sessione verificata del tablet/amministratore. Un nome
   scritto a mano resta `firma_verificata: False`; un nome fisso nel codice
   non firma mai niente.
3. **Nessuna riscrittura silenziosa.** Se un giorno aveva gia' un valore, il
   precedente resta nel record (`sostituisce`), con chi l'ha cambiato.
"""
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from fastapi import HTTPException, Request

from app.lotti.servizi import firma_dipendente

FUSO = ZoneInfo("Europe/Rome")


def oggi_locale() -> date:
    return datetime.now(FUSO).date()


def giorno_registrabile(anno: int, mese: int, giorno: int) -> date:
    """La data esiste e non e' nel futuro; altrimenti 422."""
    try:
        data = date(int(anno), int(mese), int(giorno))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Data non valida: {giorno}/{mese}/{anno}") from exc
    if data > oggi_locale():
        raise HTTPException(
            status_code=422,
            detail=f"{data.strftime('%d/%m/%Y')} non e' ancora arrivato: "
                   "un registro HACCP si compila quando il controllo e' fatto.",
        )
    return data


def _vuoto(valore: Any) -> bool:
    if valore in (None, "", "N/D"):
        return True
    if isinstance(valore, dict):
        return valore.get("temp") is None and not valore.get("eseguita") and not valore.get("valore")
    return False


def verifica_nessun_futuro(registrazioni: Dict[str, Dict[str, Any]], anno: int, mese: Optional[int] = None) -> None:
    """Per le riscritture intere di una scheda: nessun valore su giorni futuri.

    `registrazioni` e' {mese: {giorno: valore}} (temperature) oppure, con
    `mese` fissato, {riga: {giorno: valore}} (sanificazione).
    """
    for chiave, giorni in (registrazioni or {}).items():
        if not isinstance(giorni, dict):
            continue
        m = mese if mese is not None else chiave
        for g, valore in giorni.items():
            if _vuoto(valore) or not str(g).isdigit() or not str(m).isdigit():
                continue
            giorno_registrabile(anno, int(m), int(g))


async def firma_registrazione(
    request: Optional[Request], pin: Optional[str], operatore_dichiarato: str = ""
) -> Dict[str, Any]:
    """Chi firma: PIN personale, poi sessione verificata, poi nome dichiarato."""
    if isinstance(pin, str) and pin.strip():
        from app.lotti.auth import ip_richiesta

        firma = await firma_dipendente.firma_da_pin(
            pin, operatore_dichiarato, chiave_tentativi=ip_richiesta(request))
        firma["firma_via"] = "pin"
        return firma
    from app.lotti.auth import request_actor

    attore = request_actor(request) if request is not None else None
    if attore and attore.get("id") and attore.get("ruolo") != "automazione":
        return {
            "operatore": attore.get("nome") or "",
            "dipendente_id": attore["id"] if attore.get("via") == "pin" else "",
            "firma_verificata": True,
            "firma_via": attore.get("via") or "sessione",
        }
    firma = await firma_dipendente.firma_da_pin("", operatore_dichiarato)
    firma["firma_via"] = "dichiarata" if firma.get("operatore") else ""
    return firma


def conserva_precedente(nuovo: Dict[str, Any], precedente: Any, firma: Dict[str, Any]) -> Dict[str, Any]:
    """Se il giorno aveva gia' un valore, lo tiene nel nuovo record."""
    segnato_non_rilevato = isinstance(precedente, dict) and precedente.get("non_rilevato")
    if _vuoto(precedente) and not segnato_non_rilevato:
        return nuovo
    storia = []
    if isinstance(precedente, dict):
        storia = list(precedente.get("sostituisce") or [])
        vecchio = {k: v for k, v in precedente.items() if k != "sostituisce"}
    else:
        vecchio = {"valore": precedente}
    storia.append({
        **vecchio,
        "sostituito_il": datetime.now(timezone.utc).isoformat(),
        "sostituito_da": firma.get("operatore") or "",
    })
    nuovo["sostituisce"] = storia
    return nuovo
