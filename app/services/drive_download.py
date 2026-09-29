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


def _cerca_per_md5(service, md5: str) -> str | None:
    """L'id di un file non nel Cestino con lo stesso contenuto (MD5 di Drive)."""
    md5 = "".join(c for c in str(md5) if c.isalnum())
    if len(md5) != 32:
        return None
    risposta = service.files().list(
        q=f"md5Checksum = '{md5}' and trashed = false", fields="files(id)", pageSize=1,
        supportsAllDrives=True, includeItemsFromAllDrives=True,
    ).execute()
    trovati = risposta.get("files") or []
    return trovati[0]["id"] if trovati else None


async def scarica_originale(file_id: str, md5: str | None = None) -> bytes:
    """Un originale per id, con la credenziale provata sulla cartella unica.

    Cedolini, modelli F24 e quietanze lo aprivano ognuno con la credenziale
    del proprio canale, provata sulla cartella del canale: smontate quelle
    cartelle, «Apri PDF» rispondeva vuoto. L'id del file non cambia quando lo
    smistatore lo sposta in ``ELABORATE``.

    Se Drive rifiuta quell'id (copia finita nel Cestino come doppione, file
    tolto) e si conosce l'MD5, si cerca lo stesso contenuto altrove: mai un
    500, al peggio un vuoto che l'endpoint racconta come «non disponibile».
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
        try:
            return await asyncio.to_thread(scarica_bytes, service, file_id)
        except Exception as exc:  # HttpError 403/404: id sparito o nel Cestino
            logger.warning("Originale Drive %s rifiutato: %s: %s", file_id, type(exc).__name__, exc)
            if not md5:
                return b""
        try:
            altro = await asyncio.to_thread(_cerca_per_md5, service, md5)
            if not altro or altro == file_id:
                logger.warning("Originale Drive %s: nessuna copia con MD5 %s", file_id, md5)
                return b""
            return await asyncio.to_thread(scarica_bytes, service, altro)
        except Exception as exc:
            logger.warning("Originale Drive %s: copia per MD5 non leggibile: %s: %s",
                           file_id, type(exc).__name__, exc)
            return b""
    finally:
        close = getattr(service, "close", None)
        if callable(close):
            await asyncio.to_thread(close)
