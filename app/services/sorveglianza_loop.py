"""Sentinella dell'event loop: dice CHI tiene fermo il processo.

Il servizio gira con un solo processo uvicorn. Quando una funzione fa lavoro
pesante senza cedere il turno (un calcolo lungo, una lettura sincrona, un
parser), tutte le altre richieste restano in coda: la Dashboard scade a 20 s,
le pagine IVA finiscono tutte nello stesso istante. I tempi delle richieste
dicono che si aspetta, non chi fa aspettare.

Due pezzi, come negli strumenti di monitoraggio (aiomonitor, Sentry):

- un battito dentro il loop, ogni ``PASSO_SECONDI``;
- un filo separato che controlla il battito. Se il battito tace oltre
  ``SOGLIA_SECONDI``, il filo fotografa lo stack del thread del loop e scrive
  nel log le righe del gestionale (``app/``) che stanno lavorando, una volta
  per episodio; a episodio finito ne scrive la durata.

Sola osservazione: non cambia nessun dato e non ferma niente. Il filo dorme
quasi sempre, il costo e' un risveglio ogni quarto di secondo.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import threading
import time
import traceback
from typing import List, Optional

logger = logging.getLogger(__name__)

PASSO_SECONDI = 0.25
SOGLIA_SECONDI = 1.0
RIGHE_MAX = 12

_stato = {"battito": 0.0, "filo": None, "compito": None, "fermo": None}


def righe_del_gestionale(frame, limite: int = RIGHE_MAX) -> List[str]:
    """Le righe dello stack che stanno nel codice del gestionale, dalla piu' interna.

    Le librerie (asyncio, httpx, pydantic…) si tolgono: dicono dove si e'
    fermi, non quale funzione nostra ci ha portati li'. Se non resta niente,
    si tiene la riga piu' interna, qualunque sia.
    """
    estratte = traceback.extract_stack(frame)
    nostre = [
        f"{f.filename.split('/app/', 1)[-1]}:{f.lineno} {f.name}"
        for f in estratte
        if "/app/" in f.filename.replace("\\", "/") and "sorveglianza_loop" not in f.filename
    ]
    if not nostre and estratte:
        ultima = estratte[-1]
        nostre = [f"{ultima.filename}:{ultima.lineno} {ultima.name}"]
    return list(reversed(nostre))[:limite]


def _sorveglia(id_thread_loop: int, fermo: threading.Event) -> None:
    in_blocco = False
    inizio = 0.0
    while not fermo.wait(PASSO_SECONDI):
        silenzio = time.monotonic() - _stato["battito"]
        if silenzio > SOGLIA_SECONDI and not in_blocco:
            in_blocco = True
            inizio = time.monotonic() - silenzio
            frame = sys._current_frames().get(id_thread_loop)
            righe = righe_del_gestionale(frame) if frame is not None else ["stack non disponibile"]
            logger.warning(
                "[loop bloccato] fermo da %.1f s, sta lavorando: %s",
                silenzio, " <- ".join(righe),
            )
        elif silenzio <= SOGLIA_SECONDI and in_blocco:
            in_blocco = False
            logger.warning("[loop bloccato] ripartito dopo %.1f s", time.monotonic() - inizio)


async def _batti() -> None:
    while True:
        _stato["battito"] = time.monotonic()
        await asyncio.sleep(PASSO_SECONDI)


def avvia() -> None:
    """Da chiamare dentro il loop, all'avvio dell'app. Una sola volta."""
    if _stato["filo"] is not None:
        return
    _stato["battito"] = time.monotonic()
    _stato["compito"] = asyncio.get_running_loop().create_task(_batti(), name="sorveglianza_loop")
    fermo = threading.Event()
    filo = threading.Thread(
        target=_sorveglia, args=(threading.get_ident(), fermo),
        name="sorveglianza_loop", daemon=True,
    )
    _stato.update(filo=filo, fermo=fermo)
    filo.start()


def arresta() -> None:
    fermo: Optional[threading.Event] = _stato.get("fermo")
    if fermo is not None:
        fermo.set()
    compito = _stato.get("compito")
    if compito is not None:
        compito.cancel()
    _stato.update(filo=None, compito=None, fermo=None)
