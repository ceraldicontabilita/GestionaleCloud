"""Colazioni B&B: il titolare entra con la sessione del gestionale.

L'app Colazioni B&B (`/colazioni/`, pagina statica) parla con Supabase solo
tramite funzioni RPC `bb_*`. Per il titolare non esiste un PIN separato: chi e'
gia' entrato nel gestionale (PIN amministratore `PIN_HASH_ADMIN`, con MFA se
attiva) chiede qui un token di sessione. Il token lo emette il database, dietro
la stessa chiave di runtime `x-gc-api-key` che protegge le altre RPC del
gruppo (`gc_assert_runtime_secret`): senza quella chiave, che ha solo questo
backend, `bb_tit_sessione_apri` risponde «accesso negato».

Il PIN degli albergatori, invece, e' loro: lo scelgono con l'invito e lo
recuperano con il codice di recupero (vedi CLAUDE.md, «Colazioni B&B»).
"""
import logging
from typing import Any, Dict

import aiohttp
from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.utils.dependencies import get_current_admin_user

logger = logging.getLogger(__name__)

router = APIRouter()

ORE_SESSIONE = 12


async def _apri_sessione_supabase() -> Dict[str, Any]:
    url = (settings.SUPABASE_URL or "").strip().rstrip("/")
    chiave = (settings.SUPABASE_PUBLISHABLE_KEY or "").strip()
    segreto = (settings.SUPABASE_RUNTIME_SECRET or "").strip()
    if not (url and chiave and segreto):
        raise HTTPException(status_code=503, detail="Supabase non configurato sul server")
    intestazioni = {
        "apikey": chiave,
        "x-gc-api-key": segreto,
        "Content-Type": "application/json",
    }
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=20), headers=intestazioni
        ) as sessione:
            async with sessione.post(
                f"{url}/rest/v1/rpc/bb_tit_sessione_apri", json={"pore": ORE_SESSIONE}
            ) as risposta:
                corpo = await risposta.json(content_type=None)
                if risposta.status >= 400:
                    logger.error("bb_tit_sessione_apri: %s %s", risposta.status, str(corpo)[:200])
                    raise HTTPException(status_code=502, detail="Colazioni B&B non raggiungibile")
                return corpo
    except aiohttp.ClientError as exc:
        logger.error("bb_tit_sessione_apri: %s", exc)
        raise HTTPException(status_code=502, detail="Colazioni B&B non raggiungibile") from exc


@router.post("/accesso", summary="Sessione del titolare per Colazioni B&B")
async def accesso_titolare(_admin: Dict[str, Any] = Depends(get_current_admin_user)) -> Dict[str, Any]:
    """Token per le RPC del titolare: vale 12 ore ed e' emesso solo a un admin."""
    esito = await _apri_sessione_supabase()
    token = esito.get("token") if isinstance(esito, dict) else None
    if not token:
        raise HTTPException(status_code=502, detail="Colazioni B&B non raggiungibile")
    return {"token": token, "scade": esito.get("scade")}
