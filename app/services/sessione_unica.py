"""SESSIONE UNICA — un PIN si inserisce per entrare, non a ogni pagina.

Il magazzino (Lotti) e il portale dipendenti (HR) girano nello stesso
servizio ma firmano i token con due segreti diversi: `LOTTI_AUTH_SECRET` e
`HR_JWT_SECRET`. Un token valido di qua non valeva di la', quindi lo stesso
operatore, sullo stesso tablet, doveva rifare il PIN per passare dal
magazzino al portale — e viceversa.

Qui la verifica diventa una sola: si provano quei due segreti e si
restituisce l'identita' in una forma comune. Non cambia chi puo' entrare, non
allarga nessun permesso e non allunga nessuna scadenza: un token vale finche'
vale, e chi l'ha emesso decide quanto dura (il portale tiene 7 giorni, il PIN
del tablet 2 ore, il magazzino sui tablet condivisi chiude comunque dopo 10
minuti di inattivita').

**L'ERP contabile resta fuori**, di proposito: `app/utils/ruoli.py` stabilisce
che un token del portale dipendenti non vale mai sulle rotte del gestionale.
Togliere il doppio PIN di reparto non deve diventare una porta sui conti.

I due token nascono con nomi di campo diversi — `nome`/`ruolo`/`via` in Lotti,
`name`/`role`/`tipo` in HR — e chi li legge non deve sapere da dove arrivano:
la normalizzazione sta qui, in un punto solo.
"""
from typing import Any, Dict, Optional

import jwt

ALGORITMO = "HS256"


def _segreti() -> list:
    """I segreti con cui un token di Lotti o di HR puo' essere stato firmato.

    Solo questi due. L'ERP contabile resta fuori di proposito: `app/utils/
    ruoli.py` stabilisce che un token del portale dipendenti non vale mai
    sulle rotte del gestionale, e HR tiene apposta un segreto suo
    (`HR_JWT_SECRET`). Qui si toglie il doppio PIN fra magazzino e portale —
    le due app che lo stesso operatore usa sullo stesso tablet — non si apre
    la contabilita' a chi entra col PIN di reparto.

    Ordine: prima Lotti, che e' da dove arrivano i token piu' frequenti.
    Se i due segreti coincidono se ne prova uno solo.
    """
    segreti = []
    try:
        from app.lotti.auth import _secret as segreto_lotti

        valore = segreto_lotti()
        if valore:
            segreti.append(valore)
    except Exception:  # Lotti non montato: resta HR
        pass
    try:
        from app.hr.config import settings as impostazioni_hr

        if impostazioni_hr.SECRET_KEY and impostazioni_hr.SECRET_KEY not in segreti:
            segreti.append(impostazioni_hr.SECRET_KEY)
    except Exception:
        pass
    return segreti


# La stessa figura ha due nomi nelle due app: chi in Lotti e' «operatore» in
# HR e' il «dipendente» dell'anagrafica — stessa persona, stessa scheda.
#
# La traduzione e' DIREZIONALE, una per vocabolario: tradurre nei due sensi
# sullo stesso campo faceva diventare `dipendente` un `operatore` anche per
# chi si aspettava il vocabolario di HR, e HR rifiutava il proprio token con
# «unknown user role».
#
# Vale solo sul ruolo base: un operatore non diventa mai amministratore
# passando da un'app all'altra, e un ruolo che non conosciamo resta com'e'.
_VERSO_HR = {"operatore": "dipendente"}
_VERSO_LOTTI = {"dipendente": "operatore"}


def normalizza(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Identita' in forma comune, qualunque app abbia emesso il token.

    Scrive i nomi di campo di ENTRAMBE le app (`nome`/`name`,
    `ruolo`/`role`), cosi' chi legge il token trova il suo senza sapere da
    dove arriva.
    """
    dati = dict(payload)
    dati["sub"] = payload.get("sub", "")
    nome = payload.get("nome") or payload.get("name") or ""
    # NESSUN ruolo di ripiego: un token senza ruolo deve restare senza ruolo e
    # farsi rifiutare da chi lo valida. Mettere «dipendente» per comodita' e'
    # esattamente il difetto che HR si era gia' corretto il 19/09/2026 (prima
    # un token senza ruolo diventava l'utente generico «user» ed entrava).
    ruolo = str(payload.get("ruolo") or payload.get("role") or "").strip().lower()

    dati["nome"] = dati["name"] = nome
    dati["via"] = payload.get("via") or payload.get("auth_method") or "token"
    # `ruolo` lo legge Lotti, `role` lo legge HR e lo valida contro i suoi
    # ruoli: ognuno trova il proprio vocabolario.
    dati["ruolo"] = ruolo if ruolo == "admin" else _VERSO_LOTTI.get(ruolo, ruolo)
    dati["role"] = ruolo if ruolo == "admin" else _VERSO_HR.get(ruolo, ruolo)
    return dati


def verifica_token_condiviso(token: str) -> Optional[Dict[str, Any]]:
    """Il payload normalizzato se il token e' valido per una delle app.

    Un token scaduto o manomesso resta rifiutato da entrambe: qui si prova un
    segreto in piu', non si abbassa la verifica.
    """
    if not token or not isinstance(token, str):
        return None
    for segreto in _segreti():
        try:
            return normalizza(jwt.decode(token, segreto, algorithms=[ALGORITMO]))
        except jwt.PyJWTError:
            continue
    return None
