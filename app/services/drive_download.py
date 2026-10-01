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


def scarica_bytes(service, file_id: str, *, conferma_abuso: bool = False) -> bytes:
    """Il contenuto del file Drive, per intero.

    ``conferma_abuso`` riprova un file che Drive ha segnalato come malware o
    spam (403 ``cannotDownloadAbusiveFile``): Drive lo scarica solo se chi
    chiede lo dichiara esplicitamente, ed e' un PDF nostro, non un'esca.
    """
    from googleapiclient.http import MediaIoBaseDownload

    buffer = io.BytesIO()
    richiesta = service.files().get_media(
        fileId=file_id, supportsAllDrives=True, **({"acknowledgeAbuse": True} if conferma_abuso else {}),
    )
    downloader = MediaIoBaseDownload(buffer, richiesta)
    finito = False
    while not finito:
        _, finito = downloader.next_chunk()
    return buffer.getvalue()


def _e_file_segnalato(exc: Exception) -> bool:
    return "cannotDownloadAbusiveFile" in str(exc)


async def _altro_id_per_md5(md5: str, escluso: str) -> str | None:
    """L'id di un'altra copia viva dello stesso contenuto, dal protocollo Drive.

    L'API Drive non permette di cercare per ``md5Checksum`` nella query (400
    «Invalid Value», come in produzione): l'MD5 di ogni file e' gia' nel
    protocollo, che e' l'unico posto dove cercarlo. Se il file originale e'
    finito nel Cestino come doppione, la copia che resta ha lo stesso MD5.
    """
    md5 = "".join(c for c in str(md5) if c.isalnum())
    if len(md5) != 32:
        return None
    from app.services import drive_protocollo

    conn = await drive_protocollo._connessione()
    try:
        righe = await conn.fetch(
            "select drive_id from gestionale.protocollo_drive "
            "where md5 = $1 and stato = 'attivo' and drive_id <> $2 order by percorso",
            md5.lower(), escluso,
        )
    finally:
        await conn.close()
    return righe[0]["drive_id"] if righe else None


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
        except Exception as exc:  # HttpError 403/404: id sparito, nel Cestino o segnalato
            logger.warning("Originale Drive %s rifiutato: %s: %s", file_id, type(exc).__name__, exc)
            if _e_file_segnalato(exc):
                try:
                    return await asyncio.to_thread(scarica_bytes, service, file_id, conferma_abuso=True)
                except Exception as exc2:
                    logger.warning("Originale Drive %s: anche con conferma abuso: %s: %s",
                                   file_id, type(exc2).__name__, exc2)
            if not md5:
                return b""
        try:
            altro = await _altro_id_per_md5(md5, file_id)
            if not altro:
                logger.warning("Originale Drive %s: nessuna copia con MD5 %s nel protocollo", file_id, md5)
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
