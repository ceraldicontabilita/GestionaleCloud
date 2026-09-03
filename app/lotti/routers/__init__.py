"""
Router modulari per l'applicazione Tracciabilità Lotti.
"""

from .disinfestazione import router as disinfestazione_router
from .sanificazione import router as sanificazione_router
from .temperature_negative import router as temp_negative_router
from .temperature_positive import router as temp_positive_router
from .materie_prime import router as materie_prime_router
from .ricette import router as ricette_router
from .lotti import router as lotti_router
from .fornitori import router as fornitori_router

__all__ = [
    "disinfestazione_router",
    "sanificazione_router",
    "temp_negative_router",
    "temp_positive_router",
    "materie_prime_router",
    "ricette_router",
    "lotti_router",
    "fornitori_router",
]
