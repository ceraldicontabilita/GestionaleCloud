"""Punti di aggancio di Lotti dentro GestionaleCloud.

``app/lotti/server.py`` resta identico all'originale (crea ``app = FastAPI``
con tutti i router, CORS, limiti multipart, ``/api/health`` e gli handler di
startup/shutdown). Questo modulo espone cio' che serve all'app ospite per
montarlo come sotto-applicazione a ``/lotti``:

* ``lotti_app``     — l'istanza FastAPI di Lotti (le rotte sono ``/api/...``
                      relative al mount, quindi ``/lotti/api/...`` dall'esterno);
* ``avvia_lotti``   — richiama lo startup originale di Lotti (bus eventi,
                      scheduler APScheduler, seed, indici, pre-caricamento).
                      Serve perche' Starlette NON propaga gli eventi lifespan
                      alle sotto-applicazioni montate;
* ``arresta_lotti`` — richiama lo shutdown originale (chiusura archivio);
* ``monta_frontend`` — serve la build React di Lotti dalla radice del mount,
                      DOPO i router API cosi' ``/api/...`` mantiene la priorita'.

Ogni chiamata e' protetta: un errore di Lotti viene loggato e non blocca mai
l'avvio dell'app ospite.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi.staticfiles import StaticFiles

from app.lotti.server import app as lotti_app, startup_event, shutdown_db_client

logger = logging.getLogger("uvicorn.error")

__all__ = ["lotti_app", "avvia_lotti", "arresta_lotti", "monta_frontend"]


async def avvia_lotti() -> bool:
    """Esegue lo startup di Lotti; ``False`` se e' fallito (mai un'eccezione)."""
    try:
        await startup_event()
        logger.info("[LOTTI] sotto-applicazione avviata")
        return True
    except Exception:
        logger.exception("[LOTTI] avvio fallito: l'app ospite continua senza Lotti")
        return False


async def arresta_lotti() -> bool:
    """Esegue lo shutdown di Lotti; ``False`` se e' fallito (mai un'eccezione)."""
    try:
        # Lo scheduler APScheduler di Lotti e' un'istanza separata da quella di
        # GestionaleCloud: va fermato qui, altrimenti resta un thread pendente.
        try:
            from app.lotti.routers import scheduler as _sched

            if _sched.scheduler.running:
                _sched.scheduler.shutdown(wait=False)
                _sched.scheduler_started = False
        except Exception:
            logger.warning("[LOTTI] arresto scheduler non riuscito", exc_info=True)
        await shutdown_db_client()
        logger.info("[LOTTI] sotto-applicazione arrestata")
        return True
    except Exception:
        logger.exception("[LOTTI] arresto fallito (ignorato)")
        return False


def monta_frontend(build_dir: Path | str) -> bool:
    """Monta la build React di Lotti alla radice di ``lotti_app``.

    Va chiamata DOPO che ``server.py`` ha registrato i router (cioe' sempre,
    dato che l'import di questo modulo li registra): il mount ``/`` finisce in
    coda alla tabella delle rotte e ``/api/...`` resta prioritario. Con
    ``html=True`` la SPA (hash routing) viene servita da ``index.html``.
    Restituisce ``False`` se la cartella non esiste (nessuna eccezione).
    """
    build_dir = Path(build_dir)
    if not build_dir.is_dir():
        logger.warning("[LOTTI] build frontend non trovata: %s (API attive, UI assente)", build_dir)
        return False
    lotti_app.mount("/", StaticFiles(directory=str(build_dir), html=True), name="lotti_frontend")
    logger.info("[LOTTI] frontend servito da %s", build_dir)
    return True
