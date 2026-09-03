"""Punti di aggancio del Menu originale dentro GestionaleCloud.

``app/menu/server.py`` e' il ``server.py`` del repo Menu, identico
salvo gli import assoluti e il percorso del build frontend (``frontend_menu/
build``). Questo modulo espone cio' che serve all'app ospite per montarlo come
sotto-applicazione a ``/menu``:

* ``menu_app``     — l'istanza FastAPI del Menu (le rotte sono ``/api/...``
                     relative al mount, quindi ``/menu/api/...`` dall'esterno;
                     il build React e' servito dalla stessa app, dopo i router);
* ``avvia_menu``   — no-op: il Menu originale non ha handler di startup
                     (il client Supabase e' creato al primo uso);
* ``arresta_menu`` — no-op, per simmetria con ``app.lotti.embed``.

Env richieste dall'ospite: ``MENU_SUPABASE_URL``, ``MENU_SUPABASE_KEY``,
``MENU_JWT_SECRET``, ``MENU_ADMIN_USERNAME``, ``MENU_ADMIN_PASSWORD``.
"""

from __future__ import annotations

import logging

from app.menu.server import app as menu_app

logger = logging.getLogger("uvicorn.error")

__all__ = ["menu_app", "avvia_menu", "arresta_menu"]


async def avvia_menu() -> bool:
    """Nessuno startup da eseguire: ritorna sempre ``True``."""
    logger.info("[MENU] sotto-applicazione pronta (nessuno startup richiesto)")
    return True


async def arresta_menu() -> bool:
    """Nessuno shutdown da eseguire: ritorna sempre ``True``."""
    return True
