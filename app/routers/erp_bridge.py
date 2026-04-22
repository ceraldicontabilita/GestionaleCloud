"""
ERP Bridge — Endpoint ponte tra Tracciabilità (ceraldiapp.it) e Gestionale.

Riceve notifiche fire-and-forget da Tracciabilità quando importa una nuova fattura
dalla PEC, e la upserta nella collection `fatture_passive` del DB Gestionale.

Header attesi:
  X-Source: tracciabilita
  X-Azienda: <uuid azienda>
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request, Header
from pydantic import BaseModel, Field

from app.database import Database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/erp/ponte", tags=["ERP Bridge"])


# ── Schema payload in arrivo da Tracciabilità ─────────────────────────────────
class RigaFattura(BaseModel):
    descrizione: str = ""
    prezzo_unitario: float = 0.0
    quantita: float = 1.0


class FatturaRicevutaPayload(BaseModel):
    numero_fattura: str
    fornitore: str
    partita_iva: str = ""
    data: str = ""                  # formato DD/MM/YYYY o YYYY-MM-DD
    imponibile: float = 0.0
    iva: float = 0.0
    totale: float = 0.0
    righe: List[RigaFattura] = Field(default_factory=list)


# ── Helper: normalizza data in YYYY-MM-DD ─────────────────────────────────────
def _normalizza_data(data_str: str) -> str:
    if not data_str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if "/" in data_str:
        try:
            parts = data_str.split("/")
            if len(parts) == 3:
                d, m, y = parts
                return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
        except Exception:
            pass
    return data_str[:10]


# ── Endpoint principale ────────────────────────────────────────────────────────
@router.post("/fattura-ricevuta")
async def ricevi_fattura_da_tracciabilita(
    payload: FatturaRicevutaPayload,
    request: Request,
    x_source: Optional[str] = Header(None),
    x_azienda: Optional[str] = Header(None),
):
    """
    Riceve una fattura importata da Tracciabilità e la upserta in `fatture_passive`.
    Usa dedup_key = numero_fattura + partita_iva per evitare duplicati.
    """
    db = Database.get_db()

    data_iso = _normalizza_data(payload.data)
    try:
        anno = int(data_iso[:4])
    except (ValueError, TypeError):
        anno = datetime.now(timezone.utc).year

    dedup_key = f"{payload.numero_fattura}|{payload.partita_iva or payload.fornitore}"

    doc = {
        "dedup_key": dedup_key,
        "numero": payload.numero_fattura,
        "fornitore_denominazione": payload.fornitore,
        "fornitore_piva": payload.partita_iva,
        "data": data_iso,
        "anno": anno,
        "importo_totale": round(payload.totale, 2),
        "imponibile": round(payload.imponibile, 2),
        "iva": round(payload.iva, 2),
        "stato": "importata",
        "source": "tracciabilita",
        "righe": [r.model_dump() for r in payload.righe],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    result = await db["fatture_passive"].update_one(
        {"dedup_key": dedup_key},
        {"$set": doc, "$setOnInsert": {
            "id": str(uuid.uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )

    action = "inserita" if result.upserted_id else "aggiornata"
    logger.info(
        f"[PONTE] Fattura {payload.numero_fattura} da {payload.fornitore} "
        f"{action} (source={x_source}, azienda={x_azienda})"
    )

    return {
        "ok": True,
        "action": action,
        "dedup_key": dedup_key,
        "anno": anno,
    }


# ── Health check del ponte ────────────────────────────────────────────────────
@router.get("/status")
async def ponte_status():
    """Verifica che il ponte ERP sia raggiungibile."""
    db = Database.get_db()
    count = await db["fatture_passive"].count_documents({"source": "tracciabilita"})
    return {
        "ok": True,
        "db": "Gestionale",
        "fatture_da_tracciabilita": count,
    }
