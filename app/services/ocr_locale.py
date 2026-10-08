"""Un solo motore OCR (RapidOCR) per tutto il gestionale, tenuto in memoria solo mentre serve.

Su Render il servizio ha 2 GB e la sua memoria a riposo e' gia' 1,1-1,2 GB. Il motore
(onnxruntime con i suoi modelli) ne vale altri ~600 MB: prima ce n'erano DUE copie
(ricevute PagoPA e dichiarazioni, ognuna con il suo ``lru_cache`` che non lo rilasciava
mai), e il processo veniva ucciso per memoria esaurita ogni volta che un PDF scansito
passava dalla cartella unica Drive: per l'utente erano i 502 su ogni pagina.

Regole:

* **un motore per volta**, creato quando serve e **liberato subito dopo** il documento
  (``motore()``): il costo e' un picco, mai una quota permanente;
* **prima di crearlo si guarda la memoria** (``MemoriaInsufficiente``): se non c'e' posto, il
  documento non si legge adesso e *non* si scarta. Un errore 503 comprensibile (o, per la
  cartella unica, il file che resta dov'e' e si riprova al giro dopo), mai un processo morto.
"""
from __future__ import annotations

import contextlib
import logging
import threading
from typing import Iterator

from fastapi import HTTPException

from app.services import memoria_processo

logger = logging.getLogger(__name__)

# Memoria che il motore aggiunge al processo mentre lavora (misurata in produzione: 1,4 -> 1,8 GB).
OCR_STIMA_MB = 600
# Quota del limite del contenitore che non si supera mai (il resto serve alle altre richieste).
QUOTA_MAX = 0.95

_blocco = threading.Lock()


class MemoriaInsufficiente(HTTPException):
    """Non c'e' memoria per l'OCR adesso: da riprovare, non da scartare."""

    def __init__(self, rss_mb: float, limite_mb: float):
        super().__init__(
            status_code=503,
            detail=(f"memoria insufficiente per leggere la scansione ({rss_mb:.0f} MB su {limite_mb:.0f} MB): "
                    "da ripassare tra qualche minuto"),
        )
        self.rinviabile = True


def verifica_memoria(necessaria_mb: float = OCR_STIMA_MB) -> None:
    """Solleva ``MemoriaInsufficiente`` se il motore non ci sta nel limite del contenitore."""
    rss = memoria_processo.rss_mb()
    if rss is None:       # fuori da Linux non si misura: nessun limite da proteggere
        return
    limite = memoria_processo.limite_mb()
    if rss + necessaria_mb > limite * QUOTA_MAX:
        logger.warning("[ocr] rinviato: RSS %.0f MB + OCR %.0f MB oltre il %.0f%% di %.0f MB",
                       rss, necessaria_mb, QUOTA_MAX * 100, limite)
        raise MemoriaInsufficiente(rss, limite)


@contextlib.contextmanager
def motore() -> Iterator[object]:
    """Il motore OCR per UN documento; alla fine si libera e la memoria torna al sistema."""
    with _blocco:
        verifica_memoria()
        from rapidocr_onnxruntime import RapidOCR

        engine = RapidOCR()
        try:
            yield engine
        finally:
            del engine
            memoria_processo.restituisci()
