"""
ATTENDANCE MODULE - Init
========================
Modulo per la gestione delle presenze dipendenti.
"""

from fastapi import APIRouter

# Import sub-routers
from .timbrature import router as timbrature_router
from .presenze import router as presenze_router
from .pdf_consulente import router as pdf_router

# Main router che aggrega tutto
router = APIRouter()

# Include sub-routers
router.include_router(timbrature_router, tags=["Attendance - Timbrature"])
router.include_router(presenze_router, tags=["Attendance - Presenze"])
router.include_router(pdf_router, tags=["Attendance - PDF"])
