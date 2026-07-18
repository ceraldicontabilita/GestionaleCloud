"""
CARTA NEXI — endpoint (richiesta utente 18/07/2026).

GET  /api/nexi/stato       → addebiti Nexi in EC bancario, quadrature, alert
POST /api/nexi/verifica    → rilancia il controllo (genera/risolve gli alert)
POST /api/nexi/upload-pdf  → allega manualmente uno statement carta Nexi (PDF)
GET  /api/nexi/movimenti   → operazioni carta di un periodo (YYYY-MM)
"""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, File, Query, UploadFile

from app.database import Database
from app.services.nexi_carta import (
    COLL_ESTRATTI,
    COLL_MOVIMENTI,
    importa_estratto_nexi_pdf,
    verifica_addebiti_nexi,
)
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/stato")
@handle_errors
async def stato_nexi(anno: Optional[int] = Query(None)) -> Dict[str, Any]:
    db = Database.get_db()
    verifica = await verifica_addebiti_nexi(db, anno=anno)
    estratti = await db[COLL_ESTRATTI].find(
        {}, {"_id": 0, "pdf_data": 0}
    ).sort("import_date", -1).to_list(100)
    return {"verifica": verifica, "estratti": estratti}


@router.post("/verifica")
@handle_errors
async def verifica_nexi(anno: Optional[int] = Query(None)) -> Dict[str, Any]:
    db = Database.get_db()
    return await verifica_addebiti_nexi(db, anno=anno)


@router.post("/upload-pdf")
@handle_errors
async def upload_estratto_nexi(file: UploadFile = File(...)) -> Dict[str, Any]:
    db = Database.get_db()
    contenuto = await file.read()
    return await importa_estratto_nexi_pdf(db, file.filename or "estratto_nexi.pdf", contenuto)


@router.get("/movimenti")
@handle_errors
async def movimenti_periodo(periodo: str = Query(..., description="YYYY-MM")) -> Dict[str, Any]:
    db = Database.get_db()
    movimenti = await db[COLL_MOVIMENTI].find(
        {
            "$or": [{"tipo": "carta_credito"}, {"banca": "Nexi"}],
            "data": {"$gte": f"{periodo}-01", "$lte": f"{periodo}-31"},
        },
        {"_id": 0},
    ).sort("data", 1).to_list(2000)
    return {"periodo": periodo, "movimenti": movimenti, "count": len(movimenti)}
