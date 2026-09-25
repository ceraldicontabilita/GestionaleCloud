"""Banco BPM via Enable Banking, modalita' ombra: collega, stato, anteprima.

Tutto riservato all'amministratore (autorizzazione nel backend,
``richiedi_admin``), tranne il ritorno dalla banca: lo apre il browser del
titolare di ritorno da Banco BPM, e si difende da solo con lo ``state``
monouso che il gestionale ha generato (15 minuti). Nessuna scrittura di
movimenti: l'anteprima e' una simulazione (``dry_run``).
"""
from __future__ import annotations

import logging
from typing import Any, Dict

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from app.database import Database
from app.services import enable_banking as eb
from app.utils.login_lockout import client_ip
from app.utils.ruoli import richiedi_admin

logger = logging.getLogger(__name__)
router = APIRouter()

MESSAGGI = {
    "non_configurato": "Mancano Application ID e chiave privata di Enable Banking nelle variabili di Render.",
    "non_collegato": "Il conto non e' collegato: premi «Collega Banco BPM».",
    "consenso_scaduto": "Il permesso della banca e' scaduto o revocato: ricollega il conto.",
    "limite_banca": "La banca ha raggiunto il limite di letture di oggi: riprova domani.",
    "periodo_non_disponibile": "La banca non da' movimenti per il periodo chiesto.",
    "temporaneo": "La banca non risponde in questo momento: riprova tra poco.",
    "cursore_bloccato": "La banca ha restituito pagine che non avanzano: lettura interrotta.",
    "banca_non_disponibile": "Enable Banking non elenca Banco BPM in questo momento.",
    "autorizzazione_non_avviata": "Enable Banking ha rifiutato l'avvio del collegamento.",
    "ritorno_non_valido": "Il ritorno dalla banca non e' valido o e' scaduto: ricomincia il collegamento.",
    "sessione_non_creata": "La banca non ha creato la sessione: ricomincia il collegamento.",
    "rifiutato": "La banca ha rifiutato la richiesta.",
}


def _errore(exc: eb.ErroreLettura) -> HTTPException:
    stato_http = {"non_configurato": 503, "non_collegato": 409, "consenso_scaduto": 409,
                  "limite_banca": 429, "ritorno_non_valido": 400}.get(exc.stato, 502)
    return HTTPException(stato_http, {"code": exc.stato, "message": MESSAGGI.get(exc.stato, exc.stato),
                                      "details": {"http_banca": exc.http, "codice_banca": exc.codice}})


def _richiedi_attivo() -> None:
    if not eb.attivo():
        raise HTTPException(503, {"code": "spento", "message": "Lettura diretta dalla banca non attiva (ENABLE_BANKING_ENABLED)."})
    if not eb.configurato():
        raise _errore(eb.ErroreLettura("non_configurato", 0))


@router.get("/stato")
async def stato(_: Dict[str, Any] = Depends(richiedi_admin)) -> Dict[str, Any]:
    """Mai il session_id: solo se c'e', fino a quando vale, quali conti."""
    return {
        "attivo": eb.attivo(),
        "configurato": eb.configurato(),
        "redirect_url": eb.redirect_url(),
        **(await eb.leggi_sessione(Database.get_db())),
    }


@router.post("/collega")
async def collega(_: Dict[str, Any] = Depends(richiedi_admin)) -> Dict[str, Any]:
    """Indirizzo della banca: la pagina ci naviga (niente POST verso la banca,
    che la CSP ``form-action 'self'`` bloccherebbe)."""
    _richiedi_attivo()
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
            url = await eb.avvia_collegamento(Database.get_db(), client)
    except eb.ErroreLettura as exc:
        raise _errore(exc)
    return {"url": url}


@router.get("/callback", include_in_schema=False)
async def callback(request: Request) -> RedirectResponse:
    """Ritorno dalla banca. Pubblico di proposito (lo apre Banco BPM): vale
    solo con lo ``state`` monouso generato da «Collega», entro 15 minuti."""
    if not eb.attivo() or not eb.configurato():
        return RedirectResponse("/dashboard?banca=spenta", status_code=303)
    if request.query_params.get("error"):
        return RedirectResponse("/dashboard?banca=annullata", status_code=303)
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
            await eb.completa_collegamento(
                Database.get_db(), client,
                code=request.query_params.get("code", ""),
                state=request.query_params.get("state", ""),
            )
    except eb.ErroreLettura as exc:
        logger.warning("[enable-banking] collegamento non completato: %s", exc)
        return RedirectResponse(f"/dashboard?banca={exc.stato}", status_code=303)
    return RedirectResponse("/dashboard?banca=collegata", status_code=303)


@router.get("/anteprima")
async def anteprima(
    request: Request,
    giorni: int = Query(90, ge=1, le=180),
    _: Dict[str, Any] = Depends(richiedi_admin),
) -> Dict[str, Any]:
    """Legge dalla banca e confronta con l'archivio: nuovi / gia' presenti /
    DA_VERIFICARE. Simulazione: non scrive movimenti."""
    _richiedi_attivo()
    psu = eb.headers_psu(client_ip(request), request.headers.get("user-agent", ""))
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=False) as client:
            return await eb.anteprima(Database.get_db(), client, giorni=giorni, psu=psu)
    except eb.ErroreLettura as exc:
        raise _errore(exc)
