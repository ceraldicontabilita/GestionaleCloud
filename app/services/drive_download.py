"""Scaricare i byte di un file Drive: una funzione sola, per tutti.

La usano la cartella unica, «vedi documento» (cedolini, F24, quietanze), la
pulizia fatture e chi legge le LIPE archiviate. Una seconda copia sarebbe
l'ennesimo doppione.
"""
import asyncio
import io
import logging

__all__ = ["scarica_bytes", "scarica_originale"]

logger = logging.getLogger(__name__)


def scarica_bytes(service, file_id: str) -> bytes:
    """Il contenuto del file Drive, per intero."""
    from googleapiclient.http import MediaIoBaseDownload

    buffer = io.BytesIO()
    richiesta = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    downloader = MediaIoBaseDownload(buffer, richiesta)
    finito = False
    while not finito:
        _, finito = downloader.next_chunk()
    return buffer.getvalue()


async def scarica_originale(file_id: str) -> bytes:
    """Un originale per id, con la credenziale provata sulla cartella unica.

    Cedolini, modelli F24 e quietanze lo aprivano ognuno con la credenziale
    del proprio canale, provata sulla cartella del canale: smontate quelle
    cartelle, «Apri PDF» rispondeva vuoto. L'id del file non cambia quando lo
    smistatore lo sposta in ``ELABORATE``.
    """
    if not file_id:
        return b""
    from app.services.drive_cartella_unica import _service

    try:
        service = await asyncio.to_thread(_service)
    except RuntimeError as exc:
        logger.warning("Originale Drive %s non leggibile: %s: %s", file_id, type(exc).__name__, exc)
        return b""
    try:
        return await asyncio.to_thread(scarica_bytes, service, file_id)
    finally:
        close = getattr(service, "close", None)
        if callable(close):
            await asyncio.to_thread(close)
