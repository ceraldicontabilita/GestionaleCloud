"""Scaricare i byte di un file Drive: una funzione sola, per tutti.

La usano la cartella unica, «vedi documento» (cedolini, F24, quietanze), la
pulizia fatture e chi legge le LIPE archiviate. Una seconda copia sarebbe
l'ennesimo doppione.
"""
import asyncio
import io
import logging
import random
import time
from typing import Callable, TypeVar

__all__ = ["scarica_bytes", "scarica_originale", "riprova"]

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Codici Drive che passano da soli: quota per utente (429), guasti del server
# (5xx) e il 403 «rateLimitExceeded» con cui Google risponde a una raffica.
_STATI_TRANSITORI = frozenset({408, 429, 500, 502, 503, 504})
_MOTIVI_QUOTA = ("ratelimitexceeded", "userratelimitexceeded", "backenderror", "internalerror")
TENTATIVI = 5
ATTESA_BASE_S = 1.0
ATTESA_MAX_S = 30.0
_dormi = time.sleep  # sostituibile nei test


def e_transitorio(exc: BaseException) -> bool:
    """Un errore Drive che vale la pena riprovare: quota, 5xx, rete caduta."""
    stato = getattr(getattr(exc, "resp", None), "status", None)
    try:
        stato = int(stato) if stato is not None else None
    except (TypeError, ValueError):
        stato = None
    if stato in _STATI_TRANSITORI:
        return True
    if stato == 403:
        testo = str(exc).lower()
        return any(m in testo for m in _MOTIVI_QUOTA)
    if stato is not None:
        return False  # 400, 401, 404...: non cambia riprovando
    return isinstance(exc, (ConnectionError, TimeoutError, OSError)) or \
        type(exc).__name__ in {"SSLError", "HttpLib2Error", "ServerNotFoundError", "RemoteDisconnected",
                               "IncompleteRead", "BrokenPipeError"}


def riprova(fn: Callable[[], T], *, tentativi: int | None = None, quale: str = "Drive") -> T:
    """Esegue ``fn`` e, su 429/5xx/rete, riprova con attesa esponenziale (1, 2, 4, 8 s
    piu' un po' di casualita', tetto 30 s). Gli altri errori passano subito.
    Chiamata da un thread (``asyncio.to_thread``): dorme senza fermare il loop."""
    massimo = max(1, tentativi if tentativi is not None else TENTATIVI)
    for n in range(1, massimo + 1):
        try:
            return fn()
        except Exception as exc:
            if n >= massimo or not e_transitorio(exc):
                raise
            attesa = min(ATTESA_MAX_S, ATTESA_BASE_S * (2 ** (n - 1))) * (0.75 + random.random() / 2)
            logger.warning("[drive] %s: %s, riprovo fra %.1f s (tentativo %d/%d)",
                           quale, type(exc).__name__, attesa, n, massimo)
            _dormi(attesa)
    raise AssertionError("irraggiungibile")  # pragma: no cover


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
        # Un pezzo che fallisce per quota o 5xx si riprova da solo: il chunk
        # non e' stato scritto e il downloader riparte dallo stesso byte.
        _, finito = riprova(downloader.next_chunk, quale="download")
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
