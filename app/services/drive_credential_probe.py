"""Seleziona una credenziale Google Drive verificandola sul folder reale.

Non legge o stampa segreti. Prova soltanto le credenziali gia' presenti nel
runtime Render e restituisce la prima che riesce a leggere il folder canonico.
Serve durante il consolidamento dei vecchi service account dedicati: un nome
di variabile configurato non implica che quell'account abbia ancora accesso
alla nuova gerarchia GESTIONALE.
"""
from __future__ import annotations

import os
from typing import Any, Iterable, Optional, Tuple

from app.config import settings


_CANDIDATE_SETTINGS = (
    "GOOGLE_SERVICE_ACCOUNT_JSON_FATTURE",
    "GOOGLE_SERVICE_ACCOUNT_JSON_CEDOLINI",
    "GOOGLE_SERVICE_ACCOUNT_JSON_CORRISPETTIVI",
    "GOOGLE_SERVICE_ACCOUNT_JSON_QUIETANZE",
    "GOOGLE_SERVICE_ACCOUNT_JSON_ESTRATTI_CONTO",
    "GOOGLE_SERVICE_ACCOUNT_JSON_BONIFICI",
    "GOOGLE_DRIVE_SA_JSON",
    "GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON",
)


def _raw_candidates() -> Iterable[tuple[str, str]]:
    seen: set[str] = set()
    for name in _CANDIDATE_SETTINGS:
        raw = str(getattr(settings, name, None) or "").strip()
        if raw and raw not in seen:
            seen.add(raw)
            yield name, raw

    # Alias storico usato dal modulo HR. Non e' una Settings dichiarata e
    # quindi si legge direttamente dall'ambiente, senza mai esporne il valore.
    raw = str(os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") or "").strip()
    if raw and raw not in seen:
        yield "GOOGLE_SERVICE_ACCOUNT_JSON", raw


def _credentials_from_raw(raw: str):
    from google.oauth2 import service_account
    from app.services.drive_invoice_ingest import _parse_sa_json, _SCOPES

    info = _parse_sa_json(raw)
    return service_account.Credentials.from_service_account_info(info, scopes=_SCOPES)


def _can_access(creds: Any, folder_id: str) -> bool:
    from googleapiclient.discovery import build

    service = build("drive", "v3", credentials=creds, cache_discovery=False)
    try:
        service.files().get(
            fileId=folder_id,
            fields="id",
            supportsAllDrives=True,
        ).execute()
        return True
    except Exception:
        return False
    finally:
        try:
            close = getattr(service, "close", None)
            if callable(close):
                close()
        except Exception:
            pass


def load_credentials_for_folder(folder_id: Optional[str]) -> Tuple[Any, Optional[str]]:
    """Restituisce una credenziale che ha accesso provato a ``folder_id``.

    Se nessuna credenziale JSON funziona, prova anche l'eventuale file service
    account storico. Non rivela mai email, private key o contenuto dei secret.
    """
    folder_id = str(folder_id or "").strip()
    if not folder_id:
        return None, "folder Drive non configurato"

    errors = 0
    for _name, raw in _raw_candidates():
        try:
            creds = _credentials_from_raw(raw)
            if _can_access(creds, folder_id):
                return creds, None
        except Exception:
            errors += 1

    sa_file = str(getattr(settings, "GOOGLE_DRIVE_SA_FILE", None) or "").strip()
    if sa_file:
        try:
            from google.oauth2 import service_account
            from app.services.drive_invoice_ingest import _SCOPES

            creds = service_account.Credentials.from_service_account_file(sa_file, scopes=_SCOPES)
            if _can_access(creds, folder_id):
                return creds, None
        except Exception:
            errors += 1

    return None, (
        "nessun service account configurato ha accesso al folder Drive canonico "
        f"{folder_id}; credenziali non valide/inaccessibili provate={errors}"
    )
