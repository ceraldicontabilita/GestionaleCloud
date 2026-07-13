"""
ERP Bridge — Endpoint ponte tra Tracciabilità (ceraldiapp.it) e Gestionale.

Riceve notifiche fire-and-forget da Tracciabilità quando importa una nuova fattura
dalla PEC, e la upserta nella collection `fatture_passive` del DB Gestionale.

Header attesi:
  X-Source: tracciabilita
  X-Azienda: <uuid azienda>
"""
import os
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request, Header
from pydantic import BaseModel, Field

from app.database import Database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/erp/ponte", tags=["ERP Bridge"])

# Segreto condiviso con Tracciabilità (ceraldiapp.it). Il middleware globale
# (app/middleware/authentication.py) richiede sempre un JWT nostro su ogni
# /api/*, ma questo endpoint riceve chiamate da un'app ESTERNA che non può
# averne uno: prima restava semplicemente escluso da nessuna whitelist e
# rispondeva sempre 401 (bug #24 audit memoria/endpoints/README.md) — il
# ponte non ha mai funzionato in produzione. Ora il path è whitelistato
# (vedi PUBLIC_PATHS) ma protetto qui da un segreto dedicato invece di
# restare aperto a chiunque.
ERP_BRIDGE_SECRET = os.environ.get("ERP_BRIDGE_SECRET", "")


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
    x_erp_secret: Optional[str] = Header(None),
):
    """
    Riceve una fattura importata da Tracciabilità e la upserta in `fatture_passive`.
    Usa dedup_key = numero_fattura + partita_iva per evitare duplicati.
    """
    # Scelta utente 13/07/2026: il ponte ERP NON è in uso. L'endpoint è
    # "fail-closed": senza ERP_BRIDGE_SECRET configurato rifiuta sempre (prima
    # accettava scritture da chiunque con solo un warning). Per riattivarlo:
    # impostare ERP_BRIDGE_SECRET sul server e farlo inviare all'app esterna
    # nell'header X-Erp-Secret.
    import hmac as _hmac
    if not ERP_BRIDGE_SECRET:
        logger.warning("[PONTE] Richiesta rifiutata: ponte ERP disattivato (nessun ERP_BRIDGE_SECRET).")
        raise HTTPException(
            status_code=503,
            detail="Ponte ERP non attivo su questo server.",
        )
    if not x_erp_secret or not _hmac.compare_digest(x_erp_secret, ERP_BRIDGE_SECRET):
        raise HTTPException(status_code=401, detail="Segreto ponte non valido o mancante")

    db = Database.get_db()

    data_iso = _normalizza_data(payload.data)
    try:
        anno = int(data_iso[:4])
    except (ValueError, TypeError):
        anno = datetime.now(timezone.utc).year

    # Consolidamento §5.4: il ponte scrive nella collezione CANONICA `invoices`
    # (prima scriveva in `fatture_passive`, sorgente parallela che imponeva un
    # dedup runtime a due collezioni). Dedup per `invoice_key` (numero+P.IVA+data).
    from app.services.fatture_canonico import invoice_key as _invoice_key
    key = _invoice_key(payload.numero_fattura, payload.partita_iva or payload.fornitore, data_iso)

    doc = {
        "invoice_key": key,
        "invoice_number": payload.numero_fattura,
        "supplier_name": payload.fornitore,
        "supplier_vat": payload.partita_iva,
        "invoice_date": data_iso,
        "anno": anno,
        "total_amount": round(payload.totale, 2),
        "imponibile": round(payload.imponibile, 2),
        "iva": round(payload.iva, 2),
        "status": "imported",
        "source": "tracciabilita",
        "linee": [r.model_dump() for r in payload.righe],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    result = await db["invoices"].update_one(
        {"invoice_key": key},
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
        "invoice_key": key,
        "anno": anno,
    }


# ── Health check del ponte ────────────────────────────────────────────────────
@router.get("/status")
async def ponte_status():
    """Verifica che il ponte ERP sia raggiungibile."""
    db = Database.get_db()
    count = await db["invoices"].count_documents({"source": "tracciabilita"})
    return {
        "ok": True,
        "db": "Gestionale",
        "fatture_da_tracciabilita": count,
    }
