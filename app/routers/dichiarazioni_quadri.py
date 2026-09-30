"""Ripasso dei quadri delle dichiarazioni fiscali gia' in archivio.

All'ingestione i righi (VL32/VL33/VX1/VX2, RN1/RN2/RN17, IR26/IR27, esito
ISA) si leggono da soli. Qui si rilanciano sull'archivio: le dichiarazioni
importate prima non hanno ne' i valori ne' le coordinate delle pagine.
"""
from typing import Any, Dict

from fastapi import APIRouter, Depends, Query

from app.database import Database
from app.services import dichiarazioni_quadri
from app.utils.dependencies import get_current_admin_user

router = APIRouter()


@router.post(
    "/dichiarazioni/estrai-quadri",
    summary="Rilegge i righi delle dichiarazioni in archivio (IVA, Redditi SC, IRAP, ISA)",
)
async def estrai_quadri(
    dry_run: bool = Query(True, description="Se True legge soltanto, senza scrivere prove ne' riepiloghi"),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Gira in sottofondo (oltre i 5 minuti il proxy Render taglia la
    richiesta); l'esito sta in `GET /dichiarazioni/estrai-quadri/stato`.
    Idempotente: le prove hanno id stabile, rilanciare non duplica."""
    return await dichiarazioni_quadri.avvia_estrazione_archivio(Database.get_db(), dry_run=dry_run)


@router.get("/dichiarazioni/estrai-quadri/stato", summary="Esito dell'ultimo ripasso dei quadri")
async def estrai_quadri_stato(
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    return await dichiarazioni_quadri.stato_estrazione_archivio(Database.get_db())


@router.post(
    "/dichiarazioni/{document_id}/estrai-quadri",
    summary="Rilegge i righi di una sola dichiarazione",
)
async def estrai_quadri_documento(
    document_id: str,
    dry_run: bool = Query(True, description="Se True legge soltanto"),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    return await dichiarazioni_quadri.estrai_quadri_documento(Database.get_db(), document_id, dry_run=dry_run)
