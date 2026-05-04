"""
ATTENDANCE - Blocco import PDF presenze
======================================

Regola operativa: le presenze non si importano da PDF del consulente.
Il gestionale e' la fonte primaria; verso il consulente si esporta il mese.

Questo router intercetta il vecchio endpoint legacy `/libro-unico/import-pdf`
prima del router storico, restituendo 410 Gone e indicando il flusso corretto.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.post("/libro-unico/import-pdf")
async def blocca_import_pdf_presenze() -> Dict[str, Any]:
    """Disabilita il flusso legacy di import presenze da PDF."""
    raise HTTPException(
        status_code=410,
        detail=(
            "Import PDF presenze disabilitato: le presenze si inseriscono/modificano "
            "nel gestionale e si esportano al consulente tramite "
            "/api/attendance/export-consulente/csv oppure /api/attendance/genera-pdf-consulente."
        ),
    )
