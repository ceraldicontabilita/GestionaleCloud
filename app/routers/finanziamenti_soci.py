"""
FINANZIAMENTO SOCI — endpoint (richiesta utente 18/07/2026).

GET    /api/finanziamenti-soci/schede     → le 4 schede (con scan automatico)
POST   /api/finanziamenti-soci/scan       → sola scansione estratto conto
POST   /api/finanziamenti-soci/movimento  → movimento manuale (apporto/rimborso)
DELETE /api/finanziamenti-soci/movimento/{id} → elimina (es. falso positivo)
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException, Query

from app.database import Database
from app.services.finanziamenti_soci import (
    COLLECTION,
    SOCI,
    scan_finanziamenti_da_ec,
    schede_soci,
)
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
    socio = next((s for s in SOCI if s["id"] == payload.get("socio_id")), None)
    if not socio:
        raise HTTPException(status_code=400, detail="socio_id non valido")
    tipo = payload.get("tipo")
    if tipo not in ("apporto", "rimborso"):
        raise HTTPException(status_code=400, detail="tipo deve essere apporto o rimborso")
    try:
        importo = round(abs(float(payload.get("importo") or 0)), 2)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="importo non valido")
    if importo <= 0:
        raise HTTPException(status_code=400, detail="importo non valido")
    data = str(payload.get("data") or "")[:10]
    if len(data) != 10:
        raise HTTPException(status_code=400, detail="data non valida (YYYY-MM-DD)")

    movimento = {
        "id": str(uuid.uuid4()),
        "socio_id": socio["id"],
        "socio_nome": socio["nome"],
        "tipo": tipo,
        "importo": importo,
        "data": data,
        "descrizione": payload.get("descrizione") or "",
        "estratto_conto_id": None,
        "source": "manuale",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db[COLLECTION].insert_one(dict(movimento))
    return {"success": True, "movimento": movimento}


@router.delete("/movimento/{movimento_id}")
@handle_errors
async def elimina_movimento(movimento_id: str) -> Dict[str, Any]:
    db = Database.get_db()
    res = await db[COLLECTION].delete_one({"id": movimento_id})
    if not getattr(res, "deleted_count", 0):
        raise HTTPException(status_code=404, detail="Movimento non trovato")
    return {"success": True}
