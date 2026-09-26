"""Probe di salute condivise da ``/api/health`` di ERP, HR e Menu.

Render interroga gli health check ogni pochi secondi e riavvia l'istanza se
non rispondono in tempo: una probe che resta appesa sul database (statement
timeout di Supabase, 8-20 s) faceva cadere un processo sano. Qui stanno le
tre regole, in un posto solo:

- **una sola probe in volo** per chiave e per processo: le chiamate che
  arrivano mentre e' in corso aspettano quella, non ne lanciano un'altra;
- **budget fisso**: chi chiede l'esito aspetta al massimo ``timeout``
  secondi; una probe piu' lenta continua in background e il giro successivo
  ne raccoglie l'esito invece di ripartire;
- l'esito si **riusa** per ``ttl_ok`` secondi (``ttl_errore`` se fallita),
  cosi' la salute non aggiunge carico proprio quando il database e' saturo.

L'esito e' ``("verified", None)`` oppure ``("failed", motivo)``; un motivo
che inizia con ``"probe oltre"`` e' un timeout del budget, non un errore
dichiarato dal servizio (``?strict=true`` lo tratta diversamente).
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable, Optional, Tuple

logger = logging.getLogger(__name__)

VERIFICATA = "verified"
FALLITA = "failed"

Esito = Tuple[str, Optional[str]]


def _esito_task(task: "asyncio.Future") -> Esito:
    if task.cancelled():
        return FALLITA, "probe annullata"
    exc = task.exception()
    if exc is not None:
        # Il tipo sempre: molte eccezioni vere hanno il messaggio vuoto.
        return FALLITA, f"{type(exc).__name__}: {exc}"[:200]
    return VERIFICATA, None


class ProbeUnica:
    """Una probe con al piu' un'esecuzione in volo e l'esito riusato."""

    def __init__(self, nome: str, ttl_ok: float = 60.0, ttl_errore: float = 15.0):
        self.nome = nome
        self.ttl_ok = ttl_ok
        self.ttl_errore = ttl_errore
        self._task: Optional[asyncio.Future] = None
        self._esito: Optional[Esito] = None
        self._at = 0.0

    def azzera(self) -> None:
        """Dimentica esito e probe in volo (test, cambio di configurazione)."""
        self._task = None
        self._esito = None
        self._at = 0.0

    def _raccogli(self) -> Esito:
        esito = _esito_task(self._task)
        self._esito, self._at, self._task = esito, time.monotonic(), None
        return esito

    async def esito(
        self,
        avvia: Callable[[], Awaitable],
        timeout: float = 2.0,
        ttl_ok: Optional[float] = None,
        ttl_errore: Optional[float] = None,
    ) -> Esito:
        ttl_ok = self.ttl_ok if ttl_ok is None else ttl_ok
        ttl_errore = self.ttl_errore if ttl_errore is None else ttl_errore
        task = self._task
        if task is not None and task.get_loop() is not asyncio.get_running_loop():
            # Probe nata su un altro event loop (chiuso): non finira' mai qui.
            self._task = task = None
        if task is not None and task.done():
            self._raccogli()
            task = None
        if self._esito is not None:
            ttl = ttl_ok if self._esito[0] == VERIFICATA else ttl_errore
            if time.monotonic() - self._at < ttl:
                return self._esito
        if task is None:
            task = asyncio.ensure_future(avvia())
            self._task = task
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        except asyncio.TimeoutError:
            return FALLITA, f"probe oltre {timeout:g}s ({self.nome} lento)"
        except Exception as exc:  # noqa: BLE001 - l'esito si legge dal task qui sotto
            logger.debug("Probe %s fallita: %s: %s", self.nome, type(exc).__name__, exc)
        return self._raccogli()


def risposta_salute(
    servizio: str,
    *,
    componenti: "dict[str, Optional[Esito]]",
    auth: "dict[str, bool]",
    strict: bool = False,
    extra: Optional[dict] = None,
):
    """Corpo di ``/api/health`` per HR e Menu, con lo stesso contratto dell'ERP.

    ``componenti``: nome -> esito di ``ProbeUnica.esito`` oppure ``None`` se il
    componente non e' configurato. ``auth``: nome del segreto -> presente
    (mai il valore). Un componente giu' o un segreto mancante danno
    ``degraded`` con HTTP 200: Render usa questi percorsi per decidere se
    riavviare, e un database lento non e' un processo morto. Con
    ``strict=True`` lo stesso guasto torna 503, tranne il solo budget scaduto
    (``probe oltre``), che non prova un guasto: come ``/api/health`` dell'ERP.
    """
    from datetime import datetime, timezone

    from fastapi.responses import JSONResponse

    from app.services.deploy_info import get_deploy_info

    corpo: dict = {"service": servizio}
    guasti_certi = False
    degradato = False
    for nome, esito in componenti.items():
        if esito is None:
            corpo[nome] = "not_configured"
            corpo[f"{nome}_errore"] = "variabili d'ambiente mancanti"
            degradato = guasti_certi = True
            continue
        stato, motivo = esito
        corpo[nome] = "connected" if stato == VERIFICATA else "unreachable"
        corpo[f"{nome}_errore"] = motivo
        if stato != VERIFICATA:
            degradato = True
            if not str(motivo or "").startswith("probe oltre"):
                guasti_certi = True
    corpo["auth"] = {nome: bool(presente) for nome, presente in auth.items()}
    if not all(corpo["auth"].values()):
        degradato = guasti_certi = True
    corpo.update(extra or {})
    corpo.update(get_deploy_info())
    corpo["timestamp"] = datetime.now(timezone.utc).isoformat()
    if strict and guasti_certi:
        corpo["status"] = "unhealthy"
        return JSONResponse(status_code=503, content=corpo)
    corpo["status"] = "degraded" if degradato else "healthy"
    return corpo
