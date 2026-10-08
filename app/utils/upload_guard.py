"""
Guard-rail sugli upload: limite di dimensione (audit sicurezza 13/07/2026).

Prima gli endpoint facevano `await file.read()` senza alcun limite: un file
(o uno ZIP) enorme poteva saturare la RAM del processo (DoS). Qui leggiamo il
contenuto rispettando `MAX_UPLOAD_SIZE_MB` e, per gli ZIP, un tetto sul totale
decompresso e sul numero di file estratti (anti zip-bomb).
"""
import logging

from fastapi import HTTPException, UploadFile
from app.config import settings

logger = logging.getLogger(__name__)

# Tetti anti zip-bomb (oltre al limite del file .zip stesso).
MAX_ZIP_TOTALE_MB = 200
MAX_ZIP_FILES = 2000


def _limite_bytes() -> int:
    mb = getattr(settings, "MAX_UPLOAD_SIZE_MB", 50) or 50
    return int(mb) * 1024 * 1024


async def leggi_upload(file: UploadFile) -> bytes:
    """Legge un UploadFile applicando MAX_UPLOAD_SIZE_MB. 413 se troppo grande."""
    limite = _limite_bytes()
    content = await file.read()
    if len(content) > limite:
        mb = limite // (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"File troppo grande: il limite è {mb} MB.",
        )
    return content


def controlla_zip(num_estratti: int, byte_totali: int) -> None:
    """Verifica i tetti anti zip-bomb dopo l'estrazione. Solleva 413 se superati."""
    if num_estratti > MAX_ZIP_FILES:
        raise HTTPException(
            status_code=413,
            detail=f"ZIP con troppi file ({num_estratti} > {MAX_ZIP_FILES}).",
        )
    if byte_totali > MAX_ZIP_TOTALE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"ZIP troppo grande una volta decompresso (> {MAX_ZIP_TOTALE_MB} MB).",
        )
