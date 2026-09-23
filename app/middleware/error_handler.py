"""
Contratto unico degli errori API.

Ogni errore risponde con:

- ``code``: codice stabile, leggibile da una macchina (``NON_TROVATO``...);
- ``message``: testo per l'utente, in italiano, sempre una stringa;
- ``details``: dati strutturati (errori di validazione, candidati...) o ``None``;
- ``correlation_id``: lo stesso identificativo scritto nel log;
- ``detail``: quello che l'endpoint ha sollevato, invariato (stringa oppure
  oggetto). Il frontend lo legge in centinaia di punti, anche come oggetto
  (``detail.candidati``): toglierlo faceva sparire il messaggio di ogni
  ``HTTPException`` dalle pagine.

Il frontend interpreta la risposta in un posto solo:
``messaggioErrore`` di ``frontend/src/api.js``.
"""
from __future__ import annotations

import logging
import uuid
from http import HTTPStatus
from typing import Any, Optional

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.exceptions import AppError

logger = logging.getLogger(__name__)

CODICI = {
    400: "RICHIESTA_NON_VALIDA",
    401: "NON_AUTENTICATO",
    403: "NON_AUTORIZZATO",
    404: "NON_TROVATO",
    405: "METODO_NON_AMMESSO",
    409: "CONFLITTO",
    413: "CONTENUTO_TROPPO_GRANDE",
    422: "DATI_NON_VALIDI",
    429: "TROPPE_RICHIESTE",
    500: "ERRORE_INTERNO",
    502: "SERVIZIO_NON_DISPONIBILE",
    503: "SERVIZIO_NON_DISPONIBILE",
    504: "SERVIZIO_NON_DISPONIBILE",
}

MESSAGGI = {
    400: "Richiesta non valida",
    401: "Accesso richiesto",
    403: "Operazione non consentita",
    404: "Non trovato",
    405: "Operazione non disponibile a questo indirizzo",
    409: "Conflitto con i dati esistenti",
    422: "Dati della richiesta non validi",
    429: "Troppe richieste: riprova fra poco",
    500: "Errore interno: riprova o segnala il riferimento",
    503: "Servizio momentaneamente non disponibile",
}


def codice_per_stato(stato: int) -> str:
    return CODICI.get(stato, f"HTTP_{stato}")


def _frase_standard(stato: int) -> str:
    try:
        return HTTPStatus(stato).phrase
    except ValueError:
        return ""


def _messaggio(stato: int, detail: Any) -> str:
    # «Not Found» e simili sono le frasi di default di Starlette, non un
    # messaggio dell'endpoint: all'utente si risponde in italiano.
    if isinstance(detail, str) and detail.strip() and detail != _frase_standard(stato):
        return detail
    if isinstance(detail, dict):
        testo = detail.get("message") or detail.get("messaggio")
        if isinstance(testo, str) and testo.strip():
            return testo
    return MESSAGGI.get(stato, "Operazione non riuscita")


def risposta_errore(
    stato: int,
    *,
    message: str,
    detail: Any,
    details: Any = None,
    code: Optional[str] = None,
    correlation_id: Optional[str] = None,
    headers: Optional[dict] = None,
) -> JSONResponse:
    correlation_id = correlation_id or uuid.uuid4().hex[:12]
    return JSONResponse(
        status_code=stato,
        content=jsonable_encoder({
            "code": code or codice_per_stato(stato),
            "message": message,
            "details": details,
            "correlation_id": correlation_id,
            "detail": detail,
        }),
        headers=headers,
    )


def add_exception_handlers(app: FastAPI) -> None:
    """Registra gli handler del contratto unico sull'app FastAPI."""

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        cid = uuid.uuid4().hex[:12]
        logger.error(
            "[%s] %s %s -> %s %s: %s",
            cid, request.method, request.url.path, exc.status_code,
            type(exc).__name__, exc.message,
        )
        return risposta_errore(
            exc.status_code,
            message=exc.message,
            detail=exc.message,
            details=exc.details or None,
            correlation_id=cid,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        cid = uuid.uuid4().hex[:12]
        errori = jsonable_encoder(exc.errors())
        logger.warning(
            "[%s] %s %s -> 422 %s: %s",
            cid, request.method, request.url.path, type(exc).__name__, errori,
        )
        return risposta_errore(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            message=MESSAGGI[422],
            detail=errori,
            details=errori,
            correlation_id=cid,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        cid = uuid.uuid4().hex[:12]
        log = logger.warning if exc.status_code < 500 else logger.error
        log(
            "[%s] %s %s -> %s %s: %s",
            cid, request.method, request.url.path, exc.status_code,
            type(exc).__name__, exc.detail,
        )
        detail = exc.detail
        return risposta_errore(
            exc.status_code,
            message=_messaggio(exc.status_code, detail),
            detail=detail,
            details=detail if isinstance(detail, (dict, list)) else None,
            correlation_id=cid,
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        cid = uuid.uuid4().hex[:12]
        logger.error(
            "[%s] %s %s -> 500 %s: %s",
            cid, request.method, request.url.path, type(exc).__name__, exc,
            exc_info=True,
        )
        return risposta_errore(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=MESSAGGI[500],
            detail=MESSAGGI[500],
            correlation_id=cid,
        )
