"""Memoria del processo: arene limitate e memoria liberata restituita al sistema.

Su Render il servizio ha 2 GB. Dopo ogni avvio la memoria saliva senza mai
scendere (0,4 GB all'avvio, 2 GB in 20-30 minuti) e il processo veniva ucciso
per memoria esaurita. Due comportamenti noti di glibc con i server Python
(documentati in ``man mallopt`` e ``man malloc_trim``):

- **una arena malloc per thread**: glibc ne apre fino a 8 per core, e ogni
  lavoro spostato in un thread (lettura dei PDF, OCR, chiamate all'AI) ne tiene
  una sua, che non torna mai al sistema. ``mallopt(M_ARENA_MAX, 2)`` le limita,
  come la variabile ``MALLOC_ARENA_MAX=2``, ma dal codice: vale prima che il
  pool dei thread nasca, senza dipendere dalla configurazione di Render;
- **memoria liberata ma non restituita**: dopo un picco (un lotto di PDF,
  una collezione riletta per intero) Python libera gli oggetti, ma glibc tiene
  le pagine. ``malloc_trim(0)`` le restituisce: lo fa un giro ogni
  ``INTERVALLO_SECONDI``, dopo un ``gc.collect()``, e scrive nel log quanta
  memoria c'era prima e dopo.

Fuori da Linux/glibc (sviluppo su Windows o macOS) non fa niente.
"""
from __future__ import annotations

import asyncio
import ctypes
import gc
import logging
import os
import sys
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

INTERVALLO_SECONDI = 300
M_ARENA_MAX = -8
ARENE = 2

_stato: Dict[str, Any] = {"libc": None, "compito": None}


def _libc():
    if not sys.platform.startswith("linux"):
        return None
    if _stato["libc"] is None:
        try:
            _stato["libc"] = ctypes.CDLL("libc.so.6")
        except OSError as exc:
            logger.info("[memoria] libc non disponibile: %s: %s", type(exc).__name__, exc)
            _stato["libc"] = False
    return _stato["libc"] or None


def limita_arene(arene: int = ARENE) -> bool:
    """Limita le arene malloc: da chiamare all'avvio, prima dei thread di lavoro."""
    libc = _libc()
    if libc is None:
        return False
    try:
        return bool(libc.mallopt(M_ARENA_MAX, arene))
    except AttributeError:
        # musl e altre libc non hanno mallopt: niente da limitare.
        return False


def rss_mb() -> Optional[float]:
    """Memoria residente del processo in MB (``/proc/self/statm``)."""
    try:
        with open("/proc/self/statm", encoding="ascii") as statm:
            pagine = int(statm.read().split()[1])
        return round(pagine * os.sysconf("SC_PAGE_SIZE") / 1048576, 1)
    except (OSError, ValueError, IndexError):
        return None


def limite_mb() -> float:
    """Il limite di memoria del contenitore (cgroup v2 o v1); 2 GB, quelli di Render, se non si legge."""
    for percorso in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            with open(percorso, encoding="ascii") as f:
                valore = f.read().strip()
            if valore.isdigit() and int(valore) < (1 << 50):      # «max» o valori enormi = nessun limite
                return round(int(valore) / 1048576, 1)
        except OSError:
            continue
    return 2048.0


def restituisci() -> Dict[str, Any]:
    """Raccoglie gli oggetti irraggiungibili e restituisce al sistema le pagine libere."""
    prima = rss_mb()
    raccolti = gc.collect()
    restituita = False
    libc = _libc()
    if libc is not None:
        try:
            restituita = bool(libc.malloc_trim(0))
        except AttributeError:
            restituita = False
    return {"rss_prima_mb": prima, "rss_dopo_mb": rss_mb(), "oggetti_raccolti": raccolti,
            "restituita": restituita}


async def _giro() -> None:
    while True:
        await asyncio.sleep(INTERVALLO_SECONDI)
        try:
            # malloc_trim rilascia il GIL e puo' durare centinaia di ms: fuori dal loop.
            esito = await asyncio.to_thread(restituisci)
        except Exception as exc:  # noqa: BLE001 - il giro non deve fermarsi mai
            logger.warning("[memoria] giro non riuscito: %s: %s", type(exc).__name__, exc)
            continue
        logger.info(
            "[memoria] %s MB -> %s MB (oggetti raccolti %s)",
            esito["rss_prima_mb"], esito["rss_dopo_mb"], esito["oggetti_raccolti"],
        )


def avvia() -> None:
    """Da chiamare dentro il loop, all'avvio dell'app. Una sola volta."""
    if _stato["compito"] is not None:
        return
    limitate = limita_arene()
    logger.info("[memoria] arene malloc limitate a %s: %s; RSS %s MB",
                ARENE, "si" if limitate else "no", rss_mb())
    _stato["compito"] = asyncio.get_running_loop().create_task(_giro(), name="memoria_processo")


def arresta() -> None:
    compito = _stato.get("compito")
    if compito is not None:
        compito.cancel()
    _stato["compito"] = None
