"""Apertura dell'originale: l'unico endpoint (DRV-04).

* ``GET /api/originale/{tipo}/{id}`` per tipo + id (``?indice=`` per il
  secondo PDF di un verbale o l'allegato di una fattura);
* ``GET /api/originale?drive_id=...`` oppure ``?sha256=...`` per un
  originale della cartella unica.

Solo amministratore. Sola lettura. Errori col contratto dell'API (``code``,
``message``, ``details``, ``correlation_id``): «Originale non disponibile» e'
un 404 con l'elenco di cio' che si e' provato, mai un 200 vuoto.
I vecchi indirizzi (``/api/f24-public/pdf``, ``/api/documenti/documento/{id}/download``
...) restano come alias che rimandano qui.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, RedirectResponse, Response

from app.database import Database
from app.middleware.error_handler import risposta_errore
from app.services import originale_documento as svc
from app.utils.dependencies import get_current_admin_user

logger = logging.getLogger(__name__)

router = APIRouter()


def reindirizza_a_originale(tipo: str, ident: str, **parametri: Any) -> RedirectResponse:
    """Alias dei vecchi indirizzi: 307 verso l'indirizzo canonico, mai una risposta finta."""
    percorso = svc.url_originale(tipo, ident)
    resto = {k: v for k, v in parametri.items() if v not in (None, False, "", 0)}
    if resto:
        percorso += "?" + "&".join(f"{k}={quote(str(v).lower() if isinstance(v, bool) else str(v))}"
                                   for k, v in resto.items())
    return RedirectResponse(percorso, status_code=307)


def _errore(exc: svc.OriginaleErrore, richiesta: str) -> JSONResponse:
    cid = uuid.uuid4().hex[:12]
    logger.warning("[%s] originale %s -> %s %s: %s", cid, richiesta, exc.stato, exc.code, exc.message)
    return risposta_errore(exc.stato, message=exc.message, detail=exc.message, details=exc.details,
                           code=exc.code, correlation_id=cid)


def _risposta(originale: svc.Originale, scarica: bool) -> Response:
    nome_ascii = originale.nome.encode("ascii", "replace").decode("ascii").replace("?", "_")
    disposizione = "attachment" if scarica else "inline"
    return Response(
        content=originale.contenuto,
        media_type=originale.mime,
        headers={
            "Content-Disposition": (f"{disposizione}; filename=\"{nome_ascii}\"; "
                                    f"filename*=UTF-8''{quote(originale.nome)}"),
            "X-Originale-Fonte": originale.fonte,
            "X-Originale-Sha256": originale.sha256,
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("", summary="Originale per id Drive o SHA-256")
async def originale_per_drive_o_impronta(
    drive_id: Optional[str] = Query(None, max_length=200),
    sha256: Optional[str] = Query(None, max_length=64),
    scarica: bool = Query(False),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
):
    db = Database.get_db()
    try:
        if drive_id:
            return _risposta(await svc.apri_per_drive_id(db, drive_id.strip()), scarica)
        if sha256:
            return _risposta(await svc.apri_per_impronta(db, sha256), scarica)
    except svc.OriginaleErrore as exc:
        return _errore(exc, f"drive_id={drive_id} sha256={sha256}")
    return _errore(svc.TipoNonValido("Indicare drive_id oppure sha256", {}), "senza chiave")


@router.get("/{tipo}/{ident:path}", summary="Originale di un documento per tipo e id")
async def originale_per_tipo(
    tipo: str,
    ident: str,
    indice: int = Query(0, ge=0, le=500),
    scarica: bool = Query(False),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
):
    try:
        return _risposta(await svc.apri(Database.get_db(), tipo, ident, indice), scarica)
    except svc.OriginaleErrore as exc:
        return _errore(exc, f"{tipo}/{ident}")
