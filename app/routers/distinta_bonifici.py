"""Distinta bonifici fornitori (SEPA pain.001): produce un file, non paga.

GET  /api/distinta-bonifici/candidate → fatture aperte con residuo e IBAN risolto
POST /api/distinta-bonifici/anteprima → bonifici per fornitore e scarti col motivo
POST /api/distinta-bonifici/xml       → il file da caricare nell'home banking
"""
from typing import Any, Dict, List

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import Response

from app.database import Database
from app.services import distinta_bonifici as distinta
from app.utils.error_handler import handle_errors

router = APIRouter()


@router.get("/candidate")
@handle_errors
async def candidate() -> Dict[str, Any]:
    righe = await distinta.candidate(Database.get_db())
    return {"fatture": righe, "totale": len(righe)}


@router.post("/anteprima")
@handle_errors
async def anteprima(fattura_ids: List[str] = Body(..., embed=True)) -> Dict[str, Any]:
    return await distinta.componi_bonifici(Database.get_db(), fattura_ids)


@router.post("/xml")
@handle_errors
async def scarica_xml(
    fattura_ids: List[str] = Body(...),
    iban_ordinante: str = Body(...),
    nome_ordinante: str = Body(...),
    data_esecuzione: str = Body(...),
) -> Response:
    esito = await distinta.componi_bonifici(Database.get_db(), fattura_ids)
    try:
        xml = distinta.xml_pain001(
            esito["bonifici"], iban_ordinante=iban_ordinante,
            nome_ordinante=nome_ordinante, data_esecuzione=data_esecuzione,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    nome_file = f"distinta_bonifici_{data_esecuzione}.xml"
    return Response(
        content=xml.encode("utf-8"), media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{nome_file}"',
                 "X-Bonifici": str(esito["numero_bonifici"]),
                 "X-Scartate": str(len(esito["scartate"]))},
    )
