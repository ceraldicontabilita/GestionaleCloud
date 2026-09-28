"""Seleziona credenziali Google Drive verificandole sui folder reali.

Non legge o stampa segreti. Prova soltanto le credenziali gia' presenti nel
runtime Render e restituisce una credenziale soltanto dopo un vero ``files.get``
sulle radici richieste. Un nome di variabile configurato non implica che
quell'account abbia accesso alla gerarchia GESTIONALE.
"""
from __future__ import annotations

import json
import os
from typing import Any, Iterable, Optional, Tuple

from app.config import settings


SCOPES = ["https://www.googleapis.com/auth/drive"]

# Un solo service account per tutto il Drive: le credenziali per canale
# (GOOGLE_SERVICE_ACCOUNT_JSON_FATTURE, _CEDOLINI, ...) sono uscite con i canali.
_CANDIDATE_SETTINGS = (
    "GOOGLE_DRIVE_SA_JSON",
    "GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON",
)


def parse_sa_json(raw: str) -> dict:
    raw = raw.strip()
    if (raw.startswith("'") and raw.endswith("'")) or (
        raw.startswith('"') and raw.endswith('"')
    ):
        raw = raw[1:-1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    cleaned = raw.replace('\\\n', '\\n').replace('\\"', '"')
    return json.loads(cleaned)


def load_shared_credentials():
    """Il service account condiviso: JSON inline oppure file."""
    try:
        from google.oauth2 import service_account
    except ImportError as e:
        return None, f"dipendenze google mancanti: {e}"
    try:
        shared_json = settings.GOOGLE_DRIVE_SA_JSON or settings.GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON
        if shared_json:
            info = parse_sa_json(shared_json)
            return service_account.Credentials.from_service_account_info(info, scopes=SCOPES), None
        return service_account.Credentials.from_service_account_file(
            settings.GOOGLE_DRIVE_SA_FILE, scopes=SCOPES
        ), None
    except json.JSONDecodeError as e:
        return None, f"GOOGLE_DRIVE_SA_JSON non è un JSON valido: {e}"
    except Exception as e:
        return None, f"credenziali service account non valide: {e}"


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

    info = parse_sa_json(raw)
    return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)


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
        return load_shared_credentials()
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
