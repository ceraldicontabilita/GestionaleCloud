"""Seleziona credenziali Google Drive verificandole sui folder reali.

Non legge o stampa segreti. Prova soltanto le credenziali gia' presenti nel
runtime Render e restituisce una credenziale soltanto dopo un vero ``files.get``
sulle radici richieste. Un nome di variabile configurato non implica che
quell'account abbia accesso alla gerarchia GESTIONALE.
"""
from __future__ import annotations

import os
from typing import Any, Iterable, Optional, Sequence, Tuple

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


def _shared_candidate():
    try:
        from app.services.drive_invoice_ingest import _load_credentials

        return _load_credentials()
    except Exception as exc:
        return None, str(exc)


def has_configured_credentials() -> bool:
    """Indica se il runtime dispone di almeno una sorgente credenziali Drive.

    Non sceglie una credenziale e non legge dati remoti: la selezione effettiva
    resta affidata a ``load_credentials_for_folder``, che prova l'accesso alla
    cartella richiesta prima di restituire il client.
    """
    if str(getattr(settings, "GOOGLE_DRIVE_SA_FILE", None) or "").strip():
        return True
    return next(iter(_raw_candidates()), None) is not None


def load_credentials_for_folder(folder_id: Optional[str]) -> Tuple[Any, Optional[str]]:
    """Restituisce una credenziale con accesso provato a un singolo folder."""
    folder_id = str(folder_id or "").strip()
    if not folder_id:
        return None, "folder Drive non configurato"

    attempts = 0
    load_errors = 0
    shared_creds, shared_err = _shared_candidate()
    if shared_creds is not None:
        attempts += 1
        if _can_access(shared_creds, folder_id):
            return shared_creds, None
    elif shared_err:
        load_errors += 1

    for _name, raw in _raw_candidates():
        try:
            creds = _credentials_from_raw(raw)
            attempts += 1
            if _can_access(creds, folder_id):
                return creds, None
        except Exception:
            load_errors += 1

    return None, (
        "nessun service account configurato ha accesso al folder Drive canonico "
        f"{folder_id}; credenziali provate={attempts}; errori caricamento={load_errors}"
    )


def load_credentials_for_folders(folder_ids: Sequence[str]) -> Tuple[Any, Optional[str]]:
    """Restituisce una sola credenziale che vede *tutte* le radici indicate.

    E' usata dagli Estratti conto, che possono avere piu' root operative. Una
    ``files.list`` vuota non prova l'accesso al parent: per evitare falsi OK la
    stessa credenziale deve superare ``files.get`` su ogni root prima che lo
    scanner venga avviato.
    """
    roots = list(dict.fromkeys(str(value or "").strip() for value in folder_ids if str(value or "").strip()))
    if not roots:
        return None, "nessuna radice Drive configurata"

    attempts = 0
    load_errors = 0

    shared_creds, shared_err = _shared_candidate()
    if shared_creds is not None:
        attempts += 1
        if all(_can_access(shared_creds, folder_id) for folder_id in roots):
            return shared_creds, None
    elif shared_err:
        load_errors += 1

    for _name, raw in _raw_candidates():
        try:
            creds = _credentials_from_raw(raw)
            attempts += 1
            if all(_can_access(creds, folder_id) for folder_id in roots):
                return creds, None
        except Exception:
            load_errors += 1

    return None, (
        "nessun service account configurato ha accesso a tutte le radici Drive "
        f"richieste; radici={len(roots)}; credenziali provate={attempts}; "
        f"errori caricamento={load_errors}"
    )
