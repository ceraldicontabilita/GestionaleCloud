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


def avvia_sync_qromo_background() -> None:
    """Avvia una sola sincronizzazione per processo, senza bloccare FastAPI."""
    global _started
    with _lock:
        if _started:
            return
        _started = True
    thread = threading.Thread(target=_worker, name="qromo-auto-sync", daemon=True)
    thread.start()
