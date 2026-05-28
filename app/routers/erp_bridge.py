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



# ────────────────────────────────────────────────────────────────────────────────
# ENDPOINT PULL — Tracciabilita' (ceraldiapp.it) LEGGE le fatture dal gestionale
# ────────────────────────────────────────────────────────────────────────────────
from app.config import settings as _settings_ponte


def _verifica_token_ponte(x_ponte_token: Optional[str]) -> None:
    """Solleva 401 se il token e' assente, vuoto o errato.

    Header atteso: ``X-Ponte-Token: <token>``. Il token vivo si trova nella
    variabile env ``PONTE_TOKEN`` letta da ``app.config.settings``. Se in env
    il token e' assente (None o stringa vuota), l'endpoint rifiuta TUTTI gli
    accessi: cosi' di default ceraldiapp.it non puo' leggere finche' Enzo
    non imposta volutamente il segreto.
    """
    expected = (_settings_ponte.PONTE_TOKEN or "").strip()
    if not expected:
        raise HTTPException(
            status_code=401,
            detail={"errore": "ponte_token_non_configurato",
                    "messaggio": "Lato server PONTE_TOKEN non e' settato"},
        )
    if not x_ponte_token or x_ponte_token.strip() != expected:
        raise HTTPException(
            status_code=401,
            detail={"errore": "ponte_token_invalido"},
        )


@router.get("/fatture")
async def elenca_fatture_per_tracciabilita(
    dal: Optional[str] = None,            # filtro: data minima YYYY-MM-DD
    pagina: int = 1,
    dimensione: int = 50,
    x_ponte_token: Optional[str] = Header(None),
    x_azienda: Optional[str] = Header(None),
):
    """Endpoint PULL per Tracciabilita' (ceraldiapp.it).

    Restituisce le fatture passive del gestionale, paginated, ordinate per
    data discendente, filtrabili da ``dal=YYYY-MM-DD``.

    Sicurezza: header ``X-Ponte-Token`` obbligatorio (vedi PONTE_TOKEN in
    backend/.env). Senza token -> 401.

    Risposta:
        {
            "pagina": 1,
            "dimensione": 50,
            "totale": 123,
            "fatture": [ { ...campi essenziali... } ]
        }
    """
    _verifica_token_ponte(x_ponte_token)

    db = Database.get_db()

    # Costruisco il filtro
    filtro: dict = {}
    if dal:
        # Accetto sia YYYY-MM-DD che DD/MM/YYYY (riuso _normalizza_data)
        filtro["data"] = {"$gte": _normalizza_data(dal)}

    # Limito i campi restituiti: niente _id Mongo, solo dati operativi
    proiezione = {
        "_id": 0,
        "id": 1, "numero": 1, "data": 1, "anno": 1,
        "fornitore_denominazione": 1, "fornitore_piva": 1,
        "imponibile": 1, "iva": 1, "importo_totale": 1,
        "stato": 1, "source": 1,
    }

    # Paginazione difensiva
    pagina = max(1, int(pagina))
    dimensione = max(1, min(int(dimensione), 200))  # massimo 200 per chiamata
    skip = (pagina - 1) * dimensione

    totale = await db["invoices"].count_documents(filtro)
    cursor = (
        db["invoices"]
        .find(filtro, proiezione)
        .sort("data", -1)
        .skip(skip)
        .limit(dimensione)
    )
    fatture = await cursor.to_list(length=dimensione)

    logger.info(
        f"[PONTE-PULL] azienda={x_azienda} dal={dal} pagina={pagina} "
        f"dim={dimensione} totale={totale} restituiti={len(fatture)}"
    )

    return {
        "pagina": pagina,
        "dimensione": dimensione,
        "totale": totale,
        "fatture": fatture,
    }


@router.get("/fatture/{fattura_id}")
async def dettaglio_fattura_per_tracciabilita(
    fattura_id: str,
    x_ponte_token: Optional[str] = Header(None),
    x_azienda: Optional[str] = Header(None),
):
    """Dettaglio singola fattura per ID (ceraldiapp.it -> gestionale)."""
    _verifica_token_ponte(x_ponte_token)
    db = Database.get_db()
    doc = await db["invoices"].find_one({"id": fattura_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404,
                            detail={"errore": "fattura_non_trovata"})
    return doc
