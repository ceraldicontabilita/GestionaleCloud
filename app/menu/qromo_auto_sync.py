"""Riallineamento automatico del menu clienti con Qromo.

Durante la fase di migrazione Qromo resta la fonte di verita' del catalogo
pubblico. Ad ogni avvio del processo eseguiamo una sincronizzazione completa
in background e, a catalogo aggiornato, copiamo le immagini esterne nel bucket
Supabase ``menu-images``. Un errore di Qromo o della rete non deve mai impedire
l'avvio del gestionale.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading

from app.menu.qromo_sync import sincronizza
from app.menu.migrate_images_to_storage import main as migra_immagini

logger = logging.getLogger(__name__)
_started = False
_lock = threading.Lock()


def _worker() -> None:
    try:
        risultato = asyncio.run(sincronizza(dry_run=False))
        logger.info(
            "Qromo auto-sync completato: %s categorie, %s sottocategorie, %s prodotti",
            risultato.get("categories"),
            risultato.get("subcategories"),
            risultato.get("products"),
        )
    except Exception:
        logger.exception("Qromo auto-sync catalogo fallito; avvio gestionale non bloccato")
        return

    try:
        mapping, failures = migra_immagini()
        logger.info(
            "Qromo immagini: %s copiate nello Storage, %s non migrate",
            len(mapping), len(failures),
        )
    except Exception:
        logger.exception("Qromo auto-sync immagini fallito; catalogo gia' aggiornato")


def avvia_sync_qromo_background() -> bool:
    """Avvia una sola sincronizzazione per processo solo se abilitata.

    Una sincronizzazione completa non deve partire come effetto collaterale
    dell'import del server: sostituisce il catalogo e migra centinaia di
    immagini, allungando l'avvio oltre la finestra di health check. Il job
    resta disponibile in opt-in esplicito e l'endpoint admin manuale continua
    a essere la via controllata per la sincronizzazione.
    """
    global _started
    if os.getenv("ENABLE_QROMO_AUTO_SYNC", "false").strip().lower() not in {
        "1", "true", "yes", "on",
    }:
        logger.info("Qromo auto-sync disabilitato: nessuna scrittura all'avvio")
        return False
    with _lock:
        if _started:
            return False
        _started = True
    thread = threading.Thread(target=_worker, name="qromo-auto-sync", daemon=True)
    thread.start()
    return True
