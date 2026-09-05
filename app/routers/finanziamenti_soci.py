"""
FINANZIAMENTO SOCI — endpoint.

GET    /api/finanziamenti-soci/schede
POST   /api/finanziamenti-soci/scan
POST   /api/finanziamenti-soci/movimento
DELETE /api/finanziamenti-soci/movimento/{id}
"""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException, Query

from app.database import Database
from app.services.finanziamenti_soci import COLLECTION, scan_finanziamenti_da_ec, schede_soci
from app.services.soci_accounting import registra_movimento_socio
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/schede")
@handle_errors
async def get_schede(
    anno: Optional[int] = Query(None),
    scan: bool = Query(True, description="Aggiorna prima dall'estratto conto"),
) -> Dict[str, Any]:
    db = Database.get_db()
    risultato_scan = None
    if scan:
        try:
            risultato_scan = await scan_finanziamenti_da_ec(db, anno=anno)
        except Exception as e:
            logger.warning(f"Scan finanziamenti soci fallito: {e}")
    dati = await schede_soci(db, anno=anno)
    if risultato_scan:
        dati["scan"] = risultato_scan
    return dati


@router.post("/scan")
@handle_errors
async def scan_estratto_conto(anno: Optional[int] = Query(None)) -> Dict[str, Any]:
    db = Database.get_db()
    return await scan_finanziamenti_da_ec(db, anno=anno)


@router.post("/movimento")
@handle_errors
async def crea_movimento_manuale(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    db = Database.get_db()
    try:
        return await registra_movimento_socio(
            db,
            socio_id=payload.get("socio_id"),
            tipo=str(payload.get("tipo") or ""),
            importo=float(payload.get("importo") or 0),
            data=str(payload.get("data") or ""),
            destinazione=str(payload.get("destinazione") or "cassa"),
            descrizione=str(payload.get("descrizione") or ""),
            operation_id=payload.get("operation_id"),
            source="manuale",
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/movimento/{movimento_id}")
@handle_errors
async def elimina_movimento(movimento_id: str) -> Dict[str, Any]:
    """Revoca il movimento analitico senza cancellare alla cieca la prova contabile.

    Se esiste una Prima Nota collegata, viene marcata come revocata/deleted con
    motivazione. Il fatto resta auditabile e non scompare dalla storia.
    """
    db = Database.get_db()
    movimento = await db[COLLECTION].find_one({"id": movimento_id})
    if not movimento:
        raise HTTPException(status_code=404, detail="Movimento non trovato")

    pn_id = movimento.get("prima_nota_id")
    pn_tipo = movimento.get("prima_nota_tipo")
    if pn_id and pn_tipo in {"cassa", "banca"}:
        await db[f"prima_nota_{pn_tipo}"].update_one({"id": pn_id}, {"$set": {
            "deleted": True,
            "status": "deleted",
            "deleted_reason": "revoca_movimento_socio",
        }})
    await db[COLLECTION].update_one({"id": movimento_id}, {"$set": {
        "deleted": True,
        "stato_finanziario": "revocato",
    }})
    return {"success": True, "revocato": True}
