"""Incroci fiscali del minisito: LIPE ↔ F24, IRAP ↔ 3800, IVA annuale ↔ 6099, 54-bis.

Montato sotto `/api/fiscale`. Sola lettura: gli alert li scrive il giro del
mattino dello scheduler (`incroci_fiscali`), non questa pagina.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import Database
from app.services import incroci_fiscali
from app.utils.dependencies import get_current_admin_user

router = APIRouter()


def _anni(testo: Optional[str]) -> Optional[List[int]]:
    if not testo:
        return None
    try:
        anni = sorted({int(a.strip()) for a in testo.split(",") if a.strip()})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"anni non validi: {testo!r} (es. 2021,2022)") from exc
    return anni or None


@router.get("/incroci", summary="Incroci fiscali: LIPE ↔ F24 mensile, IRAP, IVA annuale, comunicazioni 54-bis")
async def incroci(
    anni: Optional[str] = Query(None, description="Anni separati da virgola (es. 2021,2022); vuoto = tutti"),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    return await incroci_fiscali.incroci(Database.get_db(), anni=_anni(anni))
