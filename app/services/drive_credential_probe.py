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

    Prima prova esattamente il loader condiviso gia' usato dagli scanner
    storici (incluso Estratti conto). Poi prova le credenziali JSON dedicate.
    In questo modo il probe non replica in modo incompleto la logica di
    ``_load_credentials`` e il diagnostico conta le credenziali realmente
    provate, non soltanto gli errori di parsing.
    """
    folder_id = str(folder_id or "").strip()
    if not folder_id:
        return None, "folder Drive non configurato"

    attempts = 0
    load_errors = 0

    # Percorso identico a quello che rende operativo Estratti conto quando
    # non e' presente una credenziale dedicata. Questo include il secret file
    # storico e gli alias shared senza esporne il contenuto.
    try:
        from app.services.drive_invoice_ingest import _load_credentials

        shared_creds, shared_err = _load_credentials()
        if shared_creds is not None:
            attempts += 1
            if _can_access(shared_creds, folder_id):
                return shared_creds, None
        elif shared_err:
            load_errors += 1
    except Exception:
        load_errors += 1

    # Le credenziali dedicate restano candidate: un canale puo' avere accesso
    # a un ramo che il service account condiviso non vede.
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
