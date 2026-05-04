"""
ATTENDANCE MODULE - Init
========================
Modulo per la gestione delle presenze dipendenti.
"""

from fastapi import APIRouter

# Import sub-routers
from .no_import_pdf import router as no_import_pdf_router
from .timbrature import router as timbrature_router
from .presenze import router as presenze_router
from .pdf_consulente import router as pdf_router
from .export_consulente import router as export_consulente_router

# Main router che aggrega tutto
router = APIRouter()

# Include sub-routers
# no_import_pdf deve essere registrato prima di presenze_router per intercettare
# il vecchio endpoint legacy /libro-unico/import-pdf.
router.include_router(no_import_pdf_router, tags=["Attendance - Legacy Disabled"])
router.include_router(timbrature_router, tags=["Attendance - Timbrature"])
router.include_router(presenze_router, tags=["Attendance - Presenze"])
router.include_router(pdf_router, tags=["Attendance - PDF"])
router.include_router(export_consulente_router, tags=["Attendance - Export Consulente"])
