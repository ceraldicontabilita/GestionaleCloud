"""
Ruoli utente e controllo accessi (audit 13/07/2026, scelta utente:
Admin + Operatore + Sola lettura).

Gerarchia:
- ADMIN        → può tutto, incluse cancellazioni di massa e impostazioni.
- OPERATORE    → usa e inserisce (POST/PUT/PATCH sui dati), ma NON accede agli
                 endpoint amministrativi/distruttivi (rollback, reset, delete
                 massivi, configurazioni di sistema).
- SOLA_LETTURA → può solo leggere (GET/HEAD): ogni scrittura è bloccata.

Retrocompatibilità: il vecchio ruolo ``user`` viene trattato come OPERATORE.
Un ruolo assente o sconosciuto non riceve privilegi e viene rifiutato dai
punti di autenticazione. Il login amministratore storico emette sempre il
ruolo ADMIN in modo esplicito.
"""
from fastapi import Depends, HTTPException, status
from typing import Dict, Any

from app.utils.dependencies import get_current_user

ADMIN = "admin"
OPERATORE = "operatore"
SOLA_LETTURA = "sola_lettura"
NON_AUTORIZZATO = "non_autorizzato"

# Ruoli del modulo HR (portale dipendenti). Passano il middleware SOLO sui
# percorsi /api/hr/ (vedi middleware/authentication.py): non sono utenti del
# gestionale e non ricevono mai privilegi di scrittura o amministrazione.
DIPENDENTE = "dipendente"
RESPONSABILE_TURNI = "responsabile_turni"
RUOLI_HR = {DIPENDENTE, RESPONSABILE_TURNI}

RUOLI_VALIDI = {ADMIN, OPERATORE, SOLA_LETTURA} | RUOLI_HR

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
    """Normalizza i ruoli validi; ``user`` legacy diventa OPERATORE.

    Valori assenti o sconosciuti falliscono chiusi: NON_AUTORIZZATO non fa
    parte di RUOLI_VALIDI e non concede né scrittura né amministrazione.
    """
    if not isinstance(ruolo, str):
        return NON_AUTORIZZATO
    normalizzato = ruolo.strip().lower()
    if normalizzato == "user":
        return OPERATORE
    if normalizzato in RUOLI_VALIDI:
        return normalizzato
    return NON_AUTORIZZATO


def puo_scrivere(ruolo: str) -> bool:
    return normalizza_ruolo(ruolo) in {ADMIN, OPERATORE}


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
