"""Inviti post-consumo alle recensioni per Colazioni B&B.

Supabase decide quali righe sono inviabili: questo servizio vede solo i job
gia' scaduti, ricontrolla il consenso nel database e consegna un template
approvato alla WhatsApp Cloud API. Nessun token o numero viene scritto nei log.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from app.config import settings

logger = logging.getLogger(__name__)


def configurato() -> bool:
    return bool(
        settings.WHATSAPP_CLOUD_PHONE_NUMBER_ID.strip()
        and settings.WHATSAPP_CLOUD_ACCESS_TOKEN.strip()
    )


async def _rpc_runtime(nome: str, payload: dict[str, Any]) -> Any:
    url = (settings.SUPABASE_URL or "").strip().rstrip("/")
    pubblica = (settings.SUPABASE_PUBLISHABLE_KEY or "").strip()
    segreto = (settings.SUPABASE_RUNTIME_SECRET or "").strip()
    if not (url and pubblica and segreto):
        raise RuntimeError("Supabase runtime non configurato")
    headers = {
        "apikey": pubblica,
        "x-gc-api-key": segreto,
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=20), headers=headers
    ) as sessione:
        async with sessione.post(
            f"{url}/rest/v1/rpc/{nome}", json=payload
        ) as risposta:
            corpo = await risposta.json(content_type=None)
            if risposta.status >= 400:
                raise RuntimeError(f"RPC {nome}: HTTP {risposta.status}")
            return corpo


async def _invia_template(*, telefono: str, struttura: str, link: str) -> str:
    base = settings.WHATSAPP_CLOUD_API_BASE.rstrip("/")
    phone_id = settings.WHATSAPP_CLOUD_PHONE_NUMBER_ID.strip()
    url = f"{base}/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_CLOUD_ACCESS_TOKEN.strip()}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": telefono,
        "type": "template",
        "template": {
            "name": settings.WHATSAPP_REVIEW_TEMPLATE_NAME,
            "language": {"code": settings.WHATSAPP_REVIEW_TEMPLATE_LANGUAGE},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": struttura},
                        {"type": "text", "text": link},
                    ],
                }
            ],
        },
    }
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=20), headers=headers
    ) as sessione:
        async with sessione.post(url, json=payload) as risposta:
            corpo = await risposta.json(content_type=None)
            if risposta.status >= 400:
                errore = corpo.get("error", {}).get("message", "errore provider")
                raise RuntimeError(f"WhatsApp HTTP {risposta.status}: {errore}")
            identificativo = ((corpo.get("messages") or [{}])[0]).get("id")
            if not identificativo:
                raise RuntimeError("WhatsApp non ha restituito l'id del messaggio")
            return str(identificativo)


async def processa_inviti_recensioni(limite: int = 20) -> dict[str, int | bool]:
    """Invia un lotto idempotente; i job sono rivendicati con SKIP LOCKED."""

    if not configurato():
        return {"configurato": False, "presi": 0, "inviati": 0, "falliti": 0}
    lavori = await _rpc_runtime("bb_recensioni_inviti_prendi", {"plimite": limite})
    risultato: dict[str, int | bool] = {
        "configurato": True,
        "presi": len(lavori or []),
        "inviati": 0,
        "falliti": 0,
    }
    base = settings.COLAZIONI_PUBLIC_URL.rstrip("/") + "/"
    for lavoro in lavori or []:
        try:
            link = f"{base}#/recensione-invito/{lavoro['review_token']}"
            provider_id = await _invia_template(
                telefono=lavoro["telefono"],
                struttura=lavoro["struttura"],
                link=link,
            )
            await _rpc_runtime(
                "bb_recensioni_invito_esito",
                {
                    "pjob": lavoro["job_id"],
                    "pinviato": True,
                    "pprovider": provider_id,
                    "perrore": "",
                },
            )
            risultato["inviati"] += 1
        except Exception as exc:
            risultato["falliti"] += 1
            logger.error(
                "[RECENSIONI-COLAZIONI] job %s fallito: %s: %s",
                lavoro.get("job_id"),
                type(exc).__name__,
                exc,
            )
            await _rpc_runtime(
                "bb_recensioni_invito_esito",
                {
                    "pjob": lavoro["job_id"],
                    "pinviato": False,
                    "pprovider": "",
                    "perrore": f"{type(exc).__name__}: {exc}"[:400],
                },
            )
    return risultato
