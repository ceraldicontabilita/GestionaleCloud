"""
Ruoli utente e controllo accessi (audit 13/07/2026, scelta utente:
Admin + Operatore + Sola lettura).

Gerarchia:
- ADMIN        → può tutto, incluse cancellazioni di massa e impostazioni.
- OPERATORE    → usa e inserisce (POST/PUT/PATCH sui dati), ma NON accede agli
                 endpoint amministrativi/distruttivi (rollback, reset, delete
                 massivi, configurazioni di sistema).
- SOLA_LETTURA → può solo leggere (GET/HEAD): ogni scrittura è bloccata.

Retrocompatibilità: un token senza ruolo o con ruolo sconosciuto viene
trattato come ADMIN. Motivo: il sistema nasce mono-utente admin (login via
env) e non dobbiamo mai bloccare fuori l'amministratore esistente. I ruoli
ridotti valgono per gli account che li dichiarano esplicitamente.
"""
from fastapi import Depends, HTTPException, status
from typing import Dict, Any

from app.utils.dependencies import get_current_user

ADMIN = "admin"
OPERATORE = "operatore"
SOLA_LETTURA = "sola_lettura"

RUOLI_VALIDI = {ADMIN, OPERATORE, SOLA_LETTURA}

# Metodi che modificano dati: vietati alla sola lettura.
METODI_SCRITTURA = {"POST", "PUT", "PATCH", "DELETE"}

# Prefissi di path riservati agli ADMIN (amministrazione e operazioni
# distruttive). Un OPERATORE che li chiama riceve 403. La lista è usata dal
# middleware come rete di sicurezza, oltre alle dependency sui singoli
# endpoint. Le eccezioni /verify e /logout NON sono qui perché servono a
# tutti gli utenti autenticati.
PREFISSI_SOLO_ADMIN = (
    "/api/admin/",
    "/api/admin-rollback/",
    "/api/rollback/",
)


def normalizza_ruolo(ruolo) -> str:
    """Riporta il ruolo a uno dei valori validi; sconosciuto/assente → ADMIN."""
    if isinstance(ruolo, str) and ruolo.strip().lower() in RUOLI_VALIDI:
        return ruolo.strip().lower()
    return ADMIN


def puo_scrivere(ruolo: str) -> bool:
    return normalizza_ruolo(ruolo) != SOLA_LETTURA


def puo_amministrare(ruolo: str) -> bool:
    return normalizza_ruolo(ruolo) == ADMIN


def richiedi_admin(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Dependency: consente solo agli ADMIN (403 altrimenti)."""
    if not puo_amministrare(current_user.get("role")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operazione riservata all'amministratore",
        )
    return current_user


def richiedi_scrittura(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Dependency: blocca gli utenti in sola lettura (403)."""
    if not puo_scrivere(current_user.get("role")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account in sola lettura: operazione non consentita",
        )
    return current_user
