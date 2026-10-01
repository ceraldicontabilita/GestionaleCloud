"""Consensi ospite e inviti WhatsApp post-consumo per Colazioni B&B."""
from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

import aiohttp
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings

logger = logging.getLogger(__name__)
_PHONE_RE = re.compile(r"^\+[1-9]\d{7,14}$")


def normalizza_telefono(valore: str) -> str:
    numero = re.sub(r"[\s().-]", "", valore or "")
    if not _PHONE_RE.fullmatch(numero):
        raise ValueError("Usa il formato internazionale, per esempio +393331234567")
    return numero


def _chiave() -> bytes:
    valore = (settings.WHATSAPP_REVIEW_DATA_KEY or "").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{64}", valore):
        raise RuntimeError("Cifratura contatti WhatsApp non configurata")
    return bytes.fromhex(valore)


def cifra_telefono(numero: str) -> tuple[str, str, str]:
    """AES-256-GCM; restituisce payload, impronta stabile e ultime quattro cifre."""
    import os

    pulito = normalizza_telefono(numero)
    nonce = os.urandom(12)
    payload = nonce + AESGCM(_chiave()).encrypt(nonce, pulito.encode(), b"convenzioni-whatsapp-v1")
    impronta = hashlib.sha256(_chiave() + pulito.encode()).hexdigest()
    return payload.hex(), impronta, pulito[-4:]


def decifra_telefono(payload: str) -> str:
    dati = bytes.fromhex(payload)
    return AESGCM(_chiave()).decrypt(
        dati[:12], dati[12:], b"convenzioni-whatsapp-v1"
    ).decode()


async def _rpc(nome: str, dati: dict[str, Any]) -> Any:
    url = (settings.SUPABASE_URL or "").strip().rstrip("/")
    pubblica = (settings.SUPABASE_PUBLISHABLE_KEY or "").strip()
    segreto = (settings.SUPABASE_RUNTIME_SECRET or "").strip()
    if not (url and pubblica and segreto):
        raise RuntimeError("Supabase runtime non configurato")
    intestazioni = {
        "apikey": pubblica,
        "Authorization": f"Bearer {pubblica}",
        "x-gc-api-key": segreto,
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=20), headers=intestazioni
    ) as sessione:
        async with sessione.post(f"{url}/rest/v1/rpc/{nome}", json=dati) as risposta:
            corpo = await risposta.json(content_type=None)
            if risposta.status >= 400:
                messaggio = corpo.get("message") if isinstance(corpo, dict) else None
                raise RuntimeError(messaggio or f"RPC {nome}: HTTP {risposta.status}")
            return corpo


async def registra_evento(dati: dict[str, Any]) -> Any:
    cifrato = impronta = finale = None
    if dati["finalita"] == "whatsapp" and dati["azione"] == "concesso":
        cifrato, impronta, finale = cifra_telefono(dati.get("telefono") or "")
    posizione = dati.get("posizione") or {}
    return await _rpc(
        "bb_ospite_evento_runtime",
        {
            "vid": dati["voucher_id"],
            "pfonte": dati["fonte"],
            "pfinalita": dati["finalita"],
            "pazion": dati.get("azione") or "concesso",
            "pversione": dati["informativa_versione"],
            "ptelefono_cifrato": cifrato,
            "pimpronta": impronta,
            "pfinale": finale,
            "plat": posizione.get("latitudine"),
            "plon": posizione.get("longitudine"),
            "paccuratezza": posizione.get("accuratezza_m"),
        },
    )


def provider_attivo() -> bool:
    return bool(
        settings.WHATSAPP_REVIEW_PROVIDER == "meta"
        and settings.WHATSAPP_REVIEW_PHONE_NUMBER_ID
        and settings.WHATSAPP_REVIEW_ACCESS_TOKEN
        and settings.WHATSAPP_REVIEW_DATA_KEY
    )


async def _invia_meta(job: dict[str, Any]) -> str:
    numero = decifra_telefono(job["telefono_cifrato"])
    base = settings.WHATSAPP_REVIEW_API_BASE.rstrip("/")
    url = f"{base}/{settings.WHATSAPP_REVIEW_PHONE_NUMBER_ID}/messages"
    corpo = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "template",
        "template": {
            "name": settings.WHATSAPP_REVIEW_TEMPLATE,
            "language": {"code": settings.WHATSAPP_REVIEW_LANGUAGE},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": job["struttura"]},
                        {"type": "text", "text": job["google_url"]},
                        {"type": "text", "text": job["tripadvisor_url"]},
                    ],
                }
            ],
        },
    }
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as sessione:
        async with sessione.post(
            url,
            headers={
                "Authorization": f"Bearer {settings.WHATSAPP_REVIEW_ACCESS_TOKEN}",
                "Content-Type": "application/json",
            },
            json=corpo,
        ) as risposta:
            esito = await risposta.json(content_type=None)
            if risposta.status >= 400:
                dettaglio = esito.get("error", {}).get("message") if isinstance(esito, dict) else None
                raise RuntimeError(dettaglio or f"WhatsApp HTTP {risposta.status}")
            return str((esito.get("messages") or [{}])[0].get("id") or "")


async def processa_inviti_recensione() -> dict[str, int | str]:
    """Job idempotente: senza configurazione Meta non reclama la coda."""
    if not provider_attivo():
        return {"stato": "disattivato", "processati": 0, "inviati": 0}
    lavori = await _rpc("bb_recensioni_claim_runtime", {"plimit": 20}) or []
    inviati = 0
    for lavoro in lavori:
        try:
            provider_id = await _invia_meta(lavoro)
            await _rpc(
                "bb_recensioni_esito_runtime",
                {"vid": lavoro["voucher_id"], "pok": True, "pprovider_id": provider_id, "perrore": None},
            )
            inviati += 1
        except Exception as exc:  # un destinatario non ferma gli altri
            logger.warning("Invito recensione %s non inviato: %s", lavoro.get("voucher_id"), exc)
            await _rpc(
                "bb_recensioni_esito_runtime",
                {"vid": lavoro["voucher_id"], "pok": False, "pprovider_id": None, "perrore": str(exc)[:500]},
            )
    return {"stato": "ok", "processati": len(lavori), "inviati": inviati}
