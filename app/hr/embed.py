"""Punti di aggancio di AppDipendenti (app/hr) dentro GestionaleCloud.

``app/hr/main.py`` e' l'app originale (FastAPI con tutti i router,
CORS, lifespan con scheduler e seed) con i soli import riscritti nel namespace
``app.hr.*`` e le env prefissate ``HR_``. Questo modulo espone cio'
che serve all'app ospite per montarla come sotto-applicazione a ``/hr``:

* ``hr_app``         — l'istanza FastAPI originale (rotte ``/api/...`` relative al
                       mount, quindi ``/hr/api/...`` dall'esterno);
* ``avvia_hr``       — esegue lo startup originale (connessione DB, scheduler
                       scadenze, seed TFR, scheduler paghe, fix avvio). Serve
                       perche' Starlette NON propaga gli eventi lifespan alle
                       sotto-applicazioni montate;
* ``arresta_hr``     — esegue lo shutdown originale (stop scheduler, chiusura DB);
* ``monta_frontend`` — serve la build Vite (``frontend_hr/dist``, base ``/hr/``)
                       dalla radice del mount, DOPO i router API, con fallback
                       SPA a ``index.html`` per i deep link (``/hr/dipendenti/...``,
                       ``/hr/portale``).

Ogni chiamata e' protetta: un errore del modulo HR viene loggato e non blocca
mai l'avvio dell'app ospite.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi.staticfiles import StaticFiles

from app.hr import main as _hr_main
from app.hr.main import app as hr_app

logger = logging.getLogger("uvicorn.error")

__all__ = ["hr_app", "avvia_hr", "arresta_hr", "monta_frontend"]


async def avvia_hr() -> bool:
    """Esegue lo startup di AppDipendenti; ``False`` se e' fallito (mai un'eccezione)."""
    try:
        await _hr_main.avvio()
        logger.info("[HR] sotto-applicazione AppDipendenti avviata")
        return True
    except Exception:
        logger.exception("[HR] avvio fallito: l'app ospite continua senza il modulo HR")
        return False


async def arresta_hr() -> bool:
    """Esegue lo shutdown di AppDipendenti; ``False`` se e' fallito (mai un'eccezione)."""
    try:
        await _hr_main.arresto()
        logger.info("[HR] sotto-applicazione AppDipendenti arrestata")
        return True
    except Exception:
        logger.exception("[HR] arresto fallito (ignorato)")
        return False


def monta_frontend(build_dir: Path | str) -> bool:
    """Serve la build Vite di AppDipendenti dalla radice di ``hr_app``.

    Riusa ``main.serve_frontend_da`` (mount ``/assets`` + catch-all con fallback
    SPA a ``index.html``): se ``main.py`` ha gia' trovato ``frontend_hr/dist``
    all'import non fa nulla di nuovo. Se la cartella indicata non contiene una
    build, come ultima risorsa monta ``StaticFiles(html=True)`` solo quando la
    cartella esiste. Restituisce ``False`` se non c'e' nulla da servire
    (nessuna eccezione).
    """
    build_dir = Path(build_dir)
    try:
        if _hr_main.serve_frontend_da(build_dir):
            logger.info("[HR] frontend servito da %s", build_dir)
            return True
        if build_dir.is_dir():
            hr_app.mount("/", StaticFiles(directory=str(build_dir), html=True), name="hr_frontend")
            logger.info("[HR] frontend (StaticFiles) servito da %s", build_dir)
            return True
    except Exception:
        logger.exception("[HR] montaggio frontend fallito (API attive, UI assente)")
        return False
    logger.warning("[HR] build frontend non trovata: %s (API attive, UI assente)", build_dir)
    return False
